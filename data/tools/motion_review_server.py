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
from urllib.parse import parse_qs, urlparse

import numpy as np
from scipy.spatial.transform import Rotation
from motionbricks.data.bvh_reader import read_bvh
from motionbricks.data.unreal_dataset import file_sha256

STATIC = Path(__file__).resolve().parent / 'review_web'
MAX_REVIEW_ITEMS = 50
EXCEPTION_STATES = {'needs_segmentation', 'needs_skeleton_review'}


def choose_cohort(reports, seed):
    problems=[]
    clean=[]
    unresolved={'heading_not_validated','contacts_not_validated','visual_quality_not_validated'}
    for item in reports:
        flags=[f for f in item['review_flags'] if f not in unresolved]
        entry=dict(item,flags=flags)
        (problems if flags or item['integrity_errors'] else clean).append(entry)
    if len(problems)>MAX_REVIEW_ITEMS:
        raise ValueError('疑似问题超过 50 条：先修复或隔离问题再生成验收名单，不能截断异常并批准整批')
    ranked=sorted(clean,key=lambda r: hashlib.sha256((seed+r['id']).encode()).hexdigest())
    sample=ranked[:min(math.ceil(len(clean)*0.05),MAX_REVIEW_ITEMS-len(problems))]
    return [dict(r,group='issue') for r in problems]+[dict(r,group='sample') for r in sample],len(clean)


class ReviewStore:
    def __init__(self, library, source, exception_entries=None, exception_digest=None, page=1):
        self.library=Path(library).resolve()
        self.source=Path(source).resolve()
        self.review=self.library/'reviews'
        self.review.mkdir(exist_ok=True)
        self.exception_mode=exception_entries is not None
        if self.exception_mode:
            entries=exception_entries[(page-1)*MAX_REVIEW_ITEMS:page*MAX_REVIEW_ITEMS]
            self.cohort_path=self.review/f'exception_triage_{exception_digest[:16]}_p{page:02}.json'
            if not self.cohort_path.exists():
                cohort=dict(mode='exception_triage',manifest_sha256=exception_digest,page=page,page_size=MAX_REVIEW_ITEMS,
                            total=len(exception_entries),checked=len(exception_entries),basic_clean=0,entries=entries)
                self.cohort_path.write_text(json.dumps(cohort,ensure_ascii=False,indent=2),encoding='utf-8')
        else:
            screen=self.library/'reports/pending_quality_screen.json'
            digest=file_sha256(screen)
            self.cohort_path=self.review/('cohort_'+digest[:16]+'.json')
            if not self.cohort_path.exists():
                reports=json.loads(screen.read_text(encoding='utf-8'))
                seed=secrets.token_hex(16)
                entries,clean=choose_cohort(reports['reports'],seed)
                cohort=dict(mode='retarget_review',screen_sha256=digest,seed=seed,checked=reports['checked'],basic_clean=clean,entries=entries)
                self.cohort_path.write_text(json.dumps(cohort,ensure_ascii=False,indent=2),encoding='utf-8')
        self.cohort=json.loads(self.cohort_path.read_text(encoding='utf-8'))
        if len(self.cohort['entries'])>MAX_REVIEW_ITEMS:
            raise ValueError('历史名单超过 50 条，须保留原记录并重新安排，不能静默截断')
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
            row=db.execute('SELECT name,metadata_json,output_path,output_sha256,state FROM motions WHERE id=?',(mid,)).fetchone()
            event=db.execute("SELECT detail FROM events WHERE motion_id=? AND state='retargeted_pending_quality' ORDER BY id DESC LIMIT 1",(mid,)).fetchone()
        if not row:
            raise ValueError('缺少来源回执')
        name,metadata,output,expected,state=row
        metadata=json.loads(metadata)
        source=(self.source/metadata['move_soma_uniform_path']).resolve()
        if not source.is_relative_to(self.source/'soma_uniform'):
            raise ValueError('路径越界')
        if self.exception_mode:
            entry=next(e for e in self.cohort['entries'] if e['id']==mid)
            if state not in EXCEPTION_STATES or file_sha256(source)!=entry['source_sha256']:
                raise ValueError('异常来源或隔离状态已变化，拒绝继续验收')
        else:
            if not event:
                raise ValueError('缺少来源回执')
            output=Path(output).resolve()
            if not output.is_relative_to(self.library) or file_sha256(output)!=expected or file_sha256(source)!=json.loads(event[0])['source_sha256']:
                raise ValueError('文件已变化，拒绝错误对照')
        bvh=read_bvh(source)
        p,r=bvh.forward()
        hips=bvh.names.index('Hips')
        if bvh.parents[hips]!=0 or bvh.channels[hips][:3]!=['Xposition','Yposition','Zposition']:
            raise ValueError('源平移协议不支持')
        p[:,hips:]-=np.einsum('tij,j->ti',r[:,0],bvh.offsets[hips])[:,None]
        basis=np.array([[1.,0,0],[0,0,1],[0,1,0]])
        p=p@basis.T
        def pack(positions,names,parents,pelvis):
            if not np.isfinite(positions).all():
                raise ValueError('非有限坐标')
            return dict(names=names,parents=parents,pelvis=pelvis,positions=np.round(positions,4).reshape(-1).tolist())
        if self.exception_mode:
            data=dict(id=mid,name=name,fps=round(1/bvh.frame_time),frames=len(p),package=metadata.get('package'),description=metadata.get('content_natural_desc_1',''),
                      source=pack(p,bvh.names,bvh.parents,hips),target=None,target_root=None,source_sha256=entry['source_sha256'],output_sha256=None,
                      review_note='该动作在 UE 重定向前被隔离，右侧没有 UEFN 输出可供对比。')
        else:
            with np.load(output,allow_pickle=False) as archive:
                f=archive['frames'].astype(float)
                roots=archive['root_frames'].astype(float)
                fps=float(archive['fps'])
            if len(p)!=len(f) or fps!=120 or abs(1/bvh.frame_time-fps)>0.01:
                raise ValueError('帧数或时间不一致，不能同步')
            rr=Rotation.from_quat(roots[:,3:]).as_matrix()
            world=np.einsum('tij,tkj->tki',rr,f[:,:,:3])+roots[:,None,:3]
            bones=json.loads((output.parent/'skeleton.json').read_text())['bones']
            data=dict(id=mid,name=name,fps=fps,frames=len(f),package=metadata.get('package'),description=metadata.get('content_natural_desc_1',''),
                      source=pack(p,bvh.names,bvh.parents,hips),target=pack(world,[b['name'] for b in bones],[b['parent'] for b in bones],0),
                      target_root=np.round(roots[:,:3],4).tolist(),source_sha256=json.loads(event[0])['source_sha256'],output_sha256=expected)
        return gzip.compress(json.dumps(data,separators=(',',':')).encode(),compresslevel=3)


def exception_manifest(library, source):
    with sqlite3.connect(f'file:{library / "catalog.sqlite3"}?mode=ro',uri=True) as db:
        rows=db.execute("SELECT id,name,metadata_json,state FROM motions WHERE state IN (?,?) ORDER BY state,name,id",tuple(sorted(EXCEPTION_STATES))).fetchall()
    entries=[]
    for mid,name,metadata,state in rows:
        metadata=json.loads(metadata)
        path=(source/metadata['move_soma_uniform_path']).resolve()
        if not path.is_relative_to(source/'soma_uniform') or not path.is_file():
            raise ValueError(f'异常来源路径无效：{mid}')
        frames=int(float(metadata.get('move_duration_frames',0)))
        reason=('超过 3000 帧，需要分段后再重定向' if state=='needs_segmentation' else '源骨骼头未被已验证 UEFN 映射覆盖，需要人工判定')
        entries.append(dict(id=mid,name=name,group='issue',state=state,flags=[state],integrity_errors=[],frames=frames,reason=reason,
                            package=metadata.get('package'),description=metadata.get('content_natural_desc_1',''),source_sha256=file_sha256(path)))
    digest=hashlib.sha256(json.dumps(entries,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return entries,digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',default='D:/MotionDataLibrary')
    parser.add_argument('--source',default='D:/BONES-SEED')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--exception-triage',action='store_true',help='审核 needs_segmentation 与 needs_skeleton_review；每页最多 50 条')
    args=parser.parse_args()
    library=Path(args.library).resolve()
    source=Path(args.source).resolve()
    exception_entries,exception_digest=(exception_manifest(library,source) if args.exception_triage else (None,None))
    page_count=max(1,math.ceil(len(exception_entries)/MAX_REVIEW_ITEMS)) if exception_entries is not None else 1
    stores={}
    def store_for(page):
        if exception_entries is None:
            page=1
        elif not 1<=page<=page_count:
            raise ValueError(f'页码必须在 1 到 {page_count} 之间')
        if page not in stores:
            stores[page]=ReviewStore(library,source,exception_entries,exception_digest,page)
        return stores[page]
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
            parsed=urlparse(self.path)
            path=parsed.path
            try:
                page=int(parse_qs(parsed.query).get('page',['1'])[0])
                store=store_for(page)
                if path=='/api/catalog':return self.reply(dict(store.cohort,decisions=store.decisions(),token=store.token,page=page,page_count=page_count,exception_mode=args.exception_triage))
                if path.startswith('/api/clip/'):return self.reply(store.clip(path.rsplit('/',1)[-1]),gz=True)
                if path=='/api/export':return self.reply(dict(cohort=store.cohort,decisions=store.decisions(),note='人工记录不会自动发布、入库或删除数据'))
                files={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
                if path in files:
                    file,kind=files[path]
                    return self.reply((STATIC/file).read_bytes(),kind)
                self.reply(dict(error='not found'),code=404)
            except Exception as exc:self.reply(dict(error=str(exc)),code=400)
        def do_POST(self):
            try:
                parsed=urlparse(self.path)
                page=int(parse_qs(parsed.query).get('page',['1'])[0])
                store=store_for(page)
                if parsed.path!='/api/review' or self.headers.get('X-Review-Token')!=store.token:
                    return self.reply(dict(error='forbidden'),code=403)
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<20000:raise ValueError('请求大小无效')
                store.save(json.loads(self.rfile.read(size)))
                self.reply(dict(ok=True))
            except Exception as exc:self.reply(dict(error=str(exc)),code=400)
    first=store_for(1)
    print(f'Motion review: http://127.0.0.1:{args.port} | {len(exception_entries) if exception_entries is not None else len(first.ids)} clips | {page_count} pages | {first.cohort_path}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':main()
