"""将 AIAnimationSystem 的本地动作数据迁移到 E 盘，并以 Junction 保留旧路径兼容性。"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Transfer:
    name: str
    source: Path
    destination: Path
    recreate_link: bool


def is_reparse(path):
    return os.path.isjunction(path) or bool(path.stat(follow_symlinks=False).st_file_attributes & 0x400)


def inventory(root):
    files=[]
    for current,dirs,names in os.walk(root,followlinks=False):
        current_path=Path(current)
        dirs[:]=[name for name in dirs if not is_reparse(current_path/name)]
        for name in names:
            path=current_path/name
            if is_reparse(path):
                continue
            stat=path.stat()
            files.append(dict(relative=str(path.relative_to(root)),bytes=stat.st_size))
    return files


def verify(destination,files):
    missing=[]
    for item in files:
        path=destination/item['relative']
        if not path.is_file() or path.stat().st_size!=item['bytes']:
            missing.append(str(path))
            if len(missing)>=8:
                break
    if missing:
        raise RuntimeError('迁移后目标缺失或大小不符：'+', '.join(missing))


def robocopy(source,destination,log):
    destination.mkdir(parents=True,exist_ok=True)
    command=['robocopy',str(source),str(destination),'/E','/MOVE','/COPY:DAT','/DCOPY:DAT','/XJ','/R:2','/W:2','/MT:16','/FFT','/NP','/LOG:'+str(log)]
    result=subprocess.run(command,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode>=8:
        raise RuntimeError(f'Robocopy 失败({result.returncode})：{log}')
    return result.returncode


def remove_empty_tree(root):
    if not root.exists() and not root.is_symlink():
        return
    for current,dirs,files in os.walk(root,topdown=False,followlinks=False):
        current_path=Path(current)
        if files:
            raise RuntimeError(f'来源根仍含文件，拒绝切换链接：{current_path}')
        for name in dirs:
            child=current_path/name
            try:
                child.rmdir()
            except OSError as exc:
                raise RuntimeError(f'来源目录未清空，拒绝切换链接：{child}') from exc
    root.rmdir()


def create_junction(link,target):
    if link.exists() or link.is_symlink():
        raise RuntimeError(f'旧路径仍存在，拒绝覆盖：{link}')
    link.parent.mkdir(parents=True,exist_ok=True)
    result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f'创建兼容 Junction 失败：{result.stdout}{result.stderr}')
    if link.resolve()!=target.resolve():
        raise RuntimeError(f'Junction 目标不匹配：{link}')


def transfers(workspace,target_root):
    bones_target=target_root/'BONES-SEED'
    return [
        Transfer('c_bones_proportional',Path('C:/BONES-SEED'),bones_target,True),
        Transfer('d_bones_remaining',Path('D:/BONES-SEED'),bones_target,True),
        Transfer('motion_library',Path('D:/MotionDataLibrary'),target_root/'MotionDataLibrary',True),
        Transfer('ue_export_cache',Path('D:/GameAnimationSample/Saved/AILocomotionDataset'),target_root/'UE/AILocomotionDataset',True),
        Transfer('prepared_datasets',workspace/'data/prepared',target_root/'prepared',True),
    ]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-root',default='E:/AIAnimationSystemData')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    workspace=Path(__file__).resolve().parents[2]
    target_root=Path(args.target_root).resolve()
    if target_root.drive.upper()!='E:':
        raise ValueError('目标必须位于 E 盘')
    if shutil.disk_usage(target_root.drive+'\\').free<600*1024**3:
        raise RuntimeError('E 盘可用空间不足 600 GiB，拒绝迁移')
    jobs=transfers(workspace,target_root)
    if any(not job.source.exists() for job in jobs):
        missing=[str(job.source) for job in jobs if not job.source.exists()]
        raise FileNotFoundError('来源缺失：'+', '.join(missing))
    if any(job.source.resolve()==job.destination.resolve() for job in jobs):
        raise ValueError('来源与目标不能相同')
    target_root.mkdir(parents=True,exist_ok=True)
    plan=[]
    for job in jobs:
        files=inventory(job.source)
        plan.append(dict(name=job.name,source=str(job.source),destination=str(job.destination),files=files,
                         file_count=len(files),bytes=sum(item['bytes'] for item in files),recreate_link=job.recreate_link))
    report=dict(schema_version=1,created_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),target_root=str(target_root),jobs=plan)
    report_path=target_root/'migration'/'ai_animation_system_storage_migration.json'
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    summary=dict(report=str(report_path),files=sum(job['file_count'] for job in plan),bytes=sum(job['bytes'] for job in plan),jobs=[dict(name=job['name'],files=job['file_count'],bytes=job['bytes']) for job in plan])
    if not args.execute:
        print(json.dumps(summary,ensure_ascii=False))
        return
    for job,entry in zip(jobs,plan):
        log=report_path.parent/(job.name+'.robocopy.log')
        entry['robocopy_exit_code']=robocopy(job.source,job.destination,log)
        verify(job.destination,entry['files'])
        entry['verified']=True
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for job,entry in zip(jobs,plan):
        if not entry['verified']:
            raise RuntimeError('存在未经验证的任务')
        remove_empty_tree(job.source)
        if job.recreate_link:
            create_junction(job.source,job.destination)
        entry['compatibility_junction']=str(job.source)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    summary['complete']=True
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
