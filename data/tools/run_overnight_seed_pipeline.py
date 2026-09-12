"""夜间监督 500 条处理批：自动校验、正式入库，并按精确清单清理。"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


ROOT=Path(__file__).resolve().parent


def states(library):
    with sqlite3.connect(library/'catalog.sqlite3') as db:
        return dict(db.execute("SELECT state,COUNT(*) FROM motions GROUP BY state"))


def execute(command,log):
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=7200,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('阶段失败：'+str(log))
    return log.read_text(encoding='utf-8',errors='replace')


def latest_validation(library):
    candidates=sorted((library/'work').glob('training_check_*/training_validation.json'),key=lambda path:path.stat().st_mtime,reverse=True)
    if not candidates:raise RuntimeError('未找到训练验证回执')
    return candidates[0]


def start_queue(library):
    stamp=time.strftime('%Y%m%d_%H%M%S')
    stop=library/'work/STOP'
    if stop.exists():
        stop.replace(library/'reports'/('STOP_overnight_'+stamp+'.txt'))
    command=[sys.executable,'-u',str(ROOT/'run_seed_queue.py'),'--max-batches','1000']
    subprocess.Popen(command,cwd=ROOT.parent.parent,stdout=(library/'work'/('overnight_queue_'+stamp+'.log')).open('w',encoding='utf-8'),stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)


def run(library,once=False):
    library=Path(library).resolve()
    lock=(library/'work/overnight.lock').open('a+b')
    import msvcrt
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise RuntimeError('已有夜间监督进程')
    try:
        while True:
            current=states(library)
            if current.get('retarget_running',0):
                pass
            elif current.get('retargeted_pending_quality',0)>=500:
                execute([sys.executable,str(ROOT/'screen_pending_quality.py'),'--library',str(library)],library/'work/overnight_screen.log')
                execute([sys.executable,str(ROOT/'validate_seed_training.py'),'--library',str(library)],library/'work/overnight_training.log')
                validation=latest_validation(library)
                execute([sys.executable,str(ROOT/'close_seed_batch.py'),'--library',str(library),'--validation',str(validation),'--auto-accept','--commit'],library/'work/overnight_stage.log')
                stage=json.loads((library/'work/overnight_stage.log').read_text(encoding='utf-8').splitlines()[-1])
                execute([sys.executable,str(ROOT/'promote_seed_training.py'),'--plan',stage['plan']],library/'work/overnight_promote.log')
                execute([sys.executable,str(ROOT/'cleanup_seed_batch.py'),'--library',str(library),'--plan',stage['plan'],'--execute'],library/'work/overnight_cleanup.log')
                if shutil.disk_usage(library).free>=44*1024**3 and shutil.disk_usage(Path(os.environ.get('LOCALAPPDATA','C:/'))).free>=14*1024**3:
                    start_queue(library)
            # 监督器重启时，当前 500 条批可能已完成一部分。未满额且无在途任务时必须续跑，
            # 否则会在 1..499 条待验收的状态永久空转。
            elif current.get('retargeted_pending_quality',0)<500 and not current.get('retarget_running',0):
                if shutil.disk_usage(library).free>=44*1024**3 and shutil.disk_usage(Path(os.environ.get('LOCALAPPDATA','C:/'))).free>=14*1024**3:
                    start_queue(library)
            if once:return
            time.sleep(30)
    finally:lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',default='D:/MotionDataLibrary')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    run(args.library,args.once)
