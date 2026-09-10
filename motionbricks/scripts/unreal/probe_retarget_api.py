"""记录当前引擎的 Python 接口，不修改资产。"""
import json
import os
from pathlib import Path
import unreal

result = {}
for name in ['IKRigDefinitionFactory', 'IKRetargetFactory', 'IKRigController', 'IKRetargeterController', 'IKRetargetBatchOperation', 'RetargetSourceOrTarget', 'RetargetAutoAlignMethod', 'AnimPoseExtensions', 'Skeleton']:
    cls = getattr(unreal, name, None)
    result[name] = {member: str(getattr(cls, member).__doc__)[:2500] for member in dir(cls) if any(token in member for token in ['retarget', 'chain', 'rig', 'pose', 'bone', 'SOURCE', 'TARGET', 'CHAIN'])} if cls else None
Path(os.environ['MOTION_PIPELINE_WORK_ROOT'], 'retarget_api.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
