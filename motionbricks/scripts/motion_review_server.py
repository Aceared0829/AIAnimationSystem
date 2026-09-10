"""仅监听本机的人工验收查看器；源动作只读，人工结论独立保存，不发布或删除数据。"""
import argparse
import gzip
import hashlib
import json
import math
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from scipy.spatial.transform import Rotation
from motionbricks.data.bvh_reader import read_bvh
from motionbricks.data.unreal_dataset import file_sha256

STATIC = Path(__file__).resolve().parent / 'review_web'


def choose_cohort(reports, seed):
    problems=[]
    clean=[]
    unresolved={'heading_not_validated','contacts_not_validated','visual_quality_not_validated'}
    for item in reports:
        flags=[f for f in item['review_flags'] if f not in unresolved]
        entry=dict(item,flags=flags)
        (problems if flags or item['integrity_errors'] else clean).append(entry)
    ranked=sorted(clean,key=lambda r: hashlib.sha256((seed+r['id']).encode()).hexdigest())
    sample=ranked[:math.ceil(len(clean)*0.05)]
    return [dict(r,group='issue') for r in problems]+[dict(r,group='sample') for r in sample],len(clean)


class ReviewStore:
    def __init__(self, library, source):
        self.library=Path(library).resolve()
        self.source=Path(source).resolve()
        self.review=self.library/'reviews'
        self.review.mkdir(exist_ok=True)
        screen=self.library/'reports/pending_quality_screen.json'
        digest=file_sha256(screen)
        self.cohort_path=self.review/('cohort_'+digest[:16]+'.json')
        if not self.cohort_path.exists():
            reports=json.loads(screen.read_text(encoding='utf-8'))
            seed=secrets.token_hex(16)
            entries,clean=choose_cohort(reports['reports'],seed)
            cohort=dict(screen_sha256=digest,seed=seed,checked=reports['checked'],basic_clean=clean,entries=entries)
            self.cohort_path.write_text(json.dumps(cohort,ensure_ascii=False,indent=2),encoding='utf-8')
        self.cohort=json.loads(self.cohort_path.read_text(encoding='utf-8'))
        self.ids={e['id'] for e in self.cohort['entries']}
        self.token=secrets.token_urlsafe(32)
        with sqlite3.connect(self.review/'decisions.sqlite3') as db:
            db.execute('CREATE TABLE IF NOT EXISTS decisions(cohort TEXT,id TEXT,status TEXT,note TEXT,updated TEXT,PRIMARY KEY(cohort,id))')

    def decisions(self):
        with sqlite3.connect(self.review/'decisions.sqlite3') as db:
            return {mid:dict(status=status,note=note,updated=updated) for mid,status,note,updated in db.execute('SELECT id,status,note,updated FROM decisions WHERE cohort=?',(self.cohort_path.name,))}

    def save(self, payload):
        mid,status,note=payload.get('id'),payload.get('status'),payload.get('note','')
        if mid not in self.ids or status not in {'approved','rejected','unsure','unreviewed'} or not isinstance(note,str) or len(note)>4000:
            raise ValueError('无效验收记录')
        with sqlite3.connect(self.review/'decisions.sqlite3') as db:
            db.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?)',(self.cohort_path.name,mid,status,note,datetime.now(timezone.utc).isoformat()))

    @lru_cache(maxsize=2)
    def clip(self, mid):
        if mid not in self.ids:
            raise ValueError('动作不在本次验收名单')
        with sqlite3.connect(f'file:{self.library / "catalog.sqlite3"}?mode=ro',uri=True) as db:
            row=db.execute('SELECT name,metadata_json,output_path,output_sha256 FROM motions WHERE id=?',(mid,)).fetchone()
            event=db.execute("SELECT detail FROM events WHERE motion_id=? AND state='retargeted_pending_quality' ORDER BY id DESC LIMIT 1",(mid,)).fetchone()
        if not row or not event:
            raise ValueError('缺少来源回执')
        name,metadata,output,expected=row
        metadata=json.loads(metadata)
        output=Path(output).resolve()
        source=(self.source/metadata['move_soma_uniform_path']).resolve()
        if not output.is_relative_to(self.library) or not source.is_relative_to(self.source/'soma_uniform'):
            raise ValueError('路径越界')
        if file_sha256(output)!=expected or file_sha256(source)!=json.loads(event[0])['source_sha256']:
            raise ValueError('文件已变化，拒绝错误对照')
        bvh=read_bvh(source)
        p,r=bvh.forward()
        hips=bvh.names.index('Hips')
        if bvh.parents[hips]!=0 or bvh.channels[hips][:3]!=['Xposition','Yposition','Zposition']:
            raise ValueError('源平移协议不支持')
        p[:,hips:]-=np.einsum('tij,j->ti',r[:,0],bvh.offsets[hips])[:,None]
        basis=np.array([[1.,0,0],[0,0,1],[0,1,0]])
        p=p@basis.T
        with np.load(output,allow_pickle=False) as archive:
            f=archive['frames'].astype(float)
            roots=archive['root_frames'].astype(float)
            fps=float(archive['fps'])
        if len(p)!=len(f) or fps!=120 or abs(1/bvh.frame_time-fps)>0.01:
            raise ValueError('帧数或时间不一致，不能同步')
        rr=Rotation.from_quat(roots[:,3:]).as_matrix()
        world=np.einsum('tij,tkj->tki',rr,f[:,:,:3])+roots[:,None,:3]
        bones=json.loads((output.parent/'skeleton.json').read_text())['bones']
        def pack(positions,names,parents,pelvis):
            if not np.isfinite(positions).all():
                raise ValueError('非有限坐标')
            return dict(names=names,parents=parents,pelvis=pelvis,positions=np.round(positions,4).reshape(-1).tolist())
        data=dict(id=mid,name=name,fps=fps,frames=len(f),package=metadata.get('package'),description=metadata.get('content_natural_desc_1',''),
                  source=pack(p,bvh.names,bvh.parents,hips),target=pack(world,[b['name'] for b in bones],[b['parent'] for b in bones],0),
                  target_root=np.round(roots[:,:3],4).tolist(),source_sha256=json.loads(event[0])['source_sha256'],output_sha256=expected)
        return gzip.compress(json.dumps(data,separators=(',',':')).encode(),compresslevel=3)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',default='D:/MotionDataLibrary')
    parser.add_argument('--source',default='D:/BONES-SEED')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    store=ReviewStore(args.library,args.source)
    class Handler(BaseHTTPRequestHandler):
        def reply(self,data,kind='application/json',code=200,gz=False):
            if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type',kind+'; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            if gz:self.send_header('Content-Encoding','gzip')
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            path=urlparse(self.path).path
            try:
                if path=='/api/catalog':return self.reply(dict(store.cohort,decisions=store.decisions(),token=store.token))
                if path.startswith('/api/clip/'):return self.reply(store.clip(path.rsplit('/',1)[-1]),gz=True)
                if path=='/api/export':return self.reply(dict(cohort=store.cohort,decisions=store.decisions(),note='人工记录不会自动发布或删除数据'))
                files={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
                if path in files:
                    file,kind=files[path]
                    return self.reply((STATIC/file).read_bytes(),kind)
                self.reply(dict(error='not found'),code=404)
            except Exception as exc:self.reply(dict(error=str(exc)),code=400)
        def do_POST(self):
            try:
                if self.path!='/api/review' or self.headers.get('X-Review-Token')!=store.token:
                    return self.reply(dict(error='forbidden'),code=403)
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<20000:raise ValueError('请求大小无效')
                store.save(json.loads(self.rfile.read(size)))
                self.reply(dict(ok=True))
            except Exception as exc:self.reply(dict(error=str(exc)),code=400)
    print(f'Motion review: http://127.0.0.1:{args.port} | {len(store.ids)} clips | {store.cohort_path}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':main()
