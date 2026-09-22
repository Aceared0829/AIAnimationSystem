"""本地手选参考姿态实验室。运行 python -m inference.profiling.pose_reference_lab。"""
import argparse
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import numpy as np
import torch
from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_unreal_streaming import localize, positions, simulate, metric, rms
from inference.profiling.hard_pose_constraints import constrain_poses, rotation_errors


class Lab:
    def __init__(self):
        torch.set_num_threads(4)
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        self.device='cuda' if torch.cuda.is_available() else 'cpu'
        net,rep,contract=load_vqvae('training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt')
        dataset=Path(contract['config']['data']['folder'])
        self.skeleton=json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
        clips=json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
        self.clip=next(c for c in clips if 'Neutral_Traversal_Catch_Hurdle_low_run.' in c['asset'])
        with np.load(dataset/self.clip['raw_file']) as raw:self.packed=pack_raw_pose(raw,self.skeleton)
        self.parents=[b['parent'] for b in self.skeleton['bones']]
        self.source=localize(self.packed,self.parents)
        self.wrappers={w:UnrealPoseReconstruction(net,rep,self.skeleton,w,'endpoints').eval().to(self.device) for w in (24,48)}
        self.cache={};self.lock=threading.Lock();self.token=secrets.token_urlsafe(24)

    def validate(self,body):
        if not isinstance(body,dict):raise ValueError('请求必须是JSON对象')
        refs=body.get('references');mode=body.get('mode');edges=body.get('edges')
        if not isinstance(refs,list) or len(refs)>len(self.packed) or any(type(x) is not int or not 0<=x<len(self.packed) for x in refs):
            raise ValueError('参考帧必须是有效源帧整数列表')
        if mode not in ('history','proxy') or type(edges) is not bool:raise ValueError('推理模式或边界选项无效')
        return tuple(sorted(set(refs))),mode,edges

    def infer(self,refs,mode,edges):
        key=(refs,mode,edges)
        if key in self.cache:return self.cache[key]
        width=24 if mode=='history' else 48
        wrapper=self.wrappers[width];windows={};selected=[]
        with torch.inference_mode():
            for end in range(23,len(self.packed),4):
                start=end-23;last=min(width-1,len(self.packed)-1-start)
                ids=np.arange(start,start+width).clip(max=len(self.packed)-1)
                history=self.packed[ids]
                sample=torch.from_numpy(np.concatenate([history,history[-1:]])[None]).to(self.device)
                anchors=sorted(set(([0,last] if edges else [])+[i-start for i in refs if start<=i<=start+last]))
                wrapper.endpoint_mask.zero_();wrapper.endpoint_mask[:,anchors]=True
                prediction=wrapper(sample).cpu().numpy()[0,:24]
                windows[end]=localize(prediction,self.parents)
                selected.append({'window_end':end,'references':[i+start for i in anchors]})
        streamed=simulate(self.source,windows,8,24)
        common=list(range(28,len(self.source)-8))
        soft_local=np.stack([streamed[i] for i in common])
        predicted=positions(soft_local,self.parents)
        reference=positions(self.source[common],self.parents)
        error=predicted-reference;per_frame=rms(error)
        poses=[None]*len(self.source);errors=[None]*len(self.source)
        for i,frame in enumerate(common):poses[frame]=predicted[i].round(4).tolist();errors[frame]=float(per_frame[i])
        result={'poses':poses,'errors':errors,'mean':float(per_frame.mean()),'p95':float(np.percentile(per_frame,95)),
            'max':float(per_frame.max()),'acceleration':metric(rms(np.diff(error,n=2,axis=0)))['mean'],
            'references':list(refs),'mode':mode,'edges':edges,'windows':selected,'interval':[common[0],common[-1]]}
        hard_local=constrain_poses(soft_local,self.source[common],common,refs)
        hard_positions=positions(hard_local,self.parents)
        hard_error=hard_positions-reference;hard_rmse=rms(hard_error)
        hard_poses=[None]*len(self.source);hard_errors=[None]*len(self.source)
        for i,f in enumerate(common):hard_poses[f]=hard_positions[i].round(4).tolist();hard_errors[f]=float(hard_rmse[i])
        hard={'poses':hard_poses,'errors':hard_errors,'mean':float(hard_rmse.mean()),'p95':float(np.percentile(hard_rmse,95)),
            'max':float(hard_rmse.max()),'acceleration':metric(rms(np.diff(hard_error,n=2,axis=0)))['mean'],
            'method':'offline post-fusion local-transform equality projection; radius8; smoothness12; not model-only output or causal runtime',
            'anchors':[]}
        for f in refs:
            item={'frame':f,'scored':f in common}
            if f in common:
                i=f-common[0]
                item.update(soft_cm=float(per_frame[i]),hard_cm=float(hard_rmse[i]),
                    soft_rotation_max_deg=float(rotation_errors(soft_local[i],self.source[f]).max()),
                    hard_rotation_max_deg=float(rotation_errors(hard_local[i],self.source[f]).max()))
            hard['anchors'].append(item)
        result['hard']=hard
        if len(self.cache)>=20:self.cache.pop(next(iter(self.cache)))
        self.cache[key]=result
        return result


def make_server(lab,port):
    """注入实验实例，允许不加载模型的 HTTP 契约回归。"""
    class Handler(BaseHTTPRequestHandler):
        timeout=10
        def local_request(self):
            port=self.server.server_port
            allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
            if self.headers.get('Host') not in allowed or self.headers.get('Origin') not in (None,*(f'http://{host}' for host in allowed)):
                self.respond(403,{'error':'只接受本机实验室页面的请求'})
                return False
            return True
        def respond(self,status,value,kind='application/json; charset=utf-8'):
            data=value.encode('utf8') if isinstance(value,str) else json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8')
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if not self.local_request():return
            if self.path=='/':return self.respond(200,Path(__file__).with_name('pose_reference_lab.html').read_text(encoding='utf8'),'text/html; charset=utf-8')
            if self.path=='/api/init':
                return self.respond(200,{'token':lab.token,'asset':lab.clip['asset'],'source':lab.packed[:,:,:3].round(4).tolist(),
                    'bones':lab.skeleton['bones'],'fps':30,'device':lab.device})
            self.respond(404,{'error':'Not found'})
        def do_POST(self):
            if not self.local_request():return
            if self.path!='/api/run':return self.respond(404,{'error':'Not found'})
            if self.headers.get('X-Lab-Token')!=lab.token:return self.respond(403,{'error':'请重新打开本地页面'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=10000:raise ValueError('请求大小无效')
                refs,mode,edges=lab.validate(json.loads(self.rfile.read(size)))
            except (ValueError,TypeError,AttributeError) as exc:return self.respond(400,{'error':str(exc)})
            if not lab.lock.acquire(blocking=False):return self.respond(409,{'error':'已有推理正在运行，请稍后重试'})
            try:
                baseline=lab.infer((),mode,True)
                result=lab.infer(refs,mode,edges)
                self.respond(200,{'baseline':baseline,'result':result})
            except Exception as exc:
                self.respond(500,{'error':str(exc)})
            finally:lab.lock.release()
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(port):
    server=make_server(Lab(),port)
    print(f'POSE_LAB_READY http://127.0.0.1:{server.server_port}',flush=True)
    with server:server.serve_forever()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8769)
    serve(parser.parse_args().port)
