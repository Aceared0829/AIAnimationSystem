"""对待验收库做只读完整性与几何初筛；不发布、不改处理状态、不删除文件。"""
import argparse
import json
from pathlib import Path
import numpy as np
from motionbricks.data.motion_catalog import MotionCatalog
from motionbricks.data.unreal_dataset import file_sha256


def screen(folder):
    catalog=MotionCatalog(folder)
    reports=[]
    try:
        rows=catalog.db.execute("SELECT id,name,output_path,output_sha256,metadata_json FROM motions WHERE state='retargeted_pending_quality'").fetchall()
        for mid,name,filename,digest,metadata in rows:
            errors=[]
            flags=[]
            path=Path(filename).resolve()
            try:
                if not path.is_relative_to(catalog.folder):
                    raise ValueError('output_outside_library')
                if file_sha256(path)!=digest:
                    raise ValueError('output_hash_mismatch')
                bones=json.loads((path.parent/'skeleton.json').read_text())['bones']
                with np.load(path,allow_pickle=False) as archive:
                    frames=archive['frames']
                    roots=archive['root_frames']
                    fps=float(archive['fps'])
                    if frames.shape!=(int(json.loads(metadata)['move_duration_frames']),len(bones),7) or roots.shape!=(len(frames),7):
                        raise ValueError('frame_shape_mismatch')
                    if fps!=120 or not np.isfinite(frames).all() or not np.isfinite(roots).all():
                        raise ValueError('invalid_samples')
                    if not np.allclose(np.linalg.norm(frames[:,:,3:],axis=-1),1,atol=1e-3) or not np.allclose(np.linalg.norm(roots[:,3:],axis=-1),1,atol=1e-3):
                        raise ValueError('invalid_quaternion')
                audits=json.loads((path.parent/'audit.json').read_text())
                matches=[item for item in audits if item.get('output_sha256')==digest]
                if len(matches)!=1:
                    raise ValueError('audit_binding_not_unique')
                audit=matches[0]
                if audit['max_bone_length_error_cm']>0.1:
                    flags.append('bone_length_deviation')
                if min(audit['foot_min_z_cm'].values()) < -2:
                    flags.append('possible_ground_penetration')
                # 几何初筛不能证明视觉质量、脚接触、根朝向和训练划分正确。
                flags.extend(['heading_not_validated','contacts_not_validated','visual_quality_not_validated'])
            except (OSError,ValueError,KeyError,TypeError) as exc:
                errors.append(str(exc))
            reports.append(dict(id=mid,name=name,integrity_errors=errors,review_flags=flags,training_ready=False))
        counts={}
        for report in reports:
            for flag in report['review_flags']+report['integrity_errors']:
                counts[flag]=counts.get(flag,0)+1
        result=dict(checked=len(reports),counts=counts,reports=reports,source_deleted=False)
        output=catalog.folder/'reports/pending_quality_screen.json'
        temp=output.with_suffix('.partial')
        temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(output)
        print(json.dumps(dict(checked=len(reports),counts=counts,report=str(output))))
    finally:
        catalog.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',default='D:/MotionDataLibrary')
    args=parser.parse_args()
    screen(args.library)
