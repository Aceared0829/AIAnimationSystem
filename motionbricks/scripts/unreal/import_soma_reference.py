"""导入数据自带 SOMA USD 参考网格；仅写入管线专用资产目录。"""
import json
import os
from pathlib import Path
import unreal

work = Path(os.environ['MOTION_PIPELINE_WORK_ROOT']).resolve()
work.mkdir(parents=True, exist_ok=True)
request = json.loads((work / 'source_reference_request.json').read_text(encoding='utf-8'))
task = unreal.AssetImportTask()
task.filename = request['source_usd']
task.destination_path = '/Game/MotionPipeline/SOMAReference'
task.automated = True
task.save = True
task.replace_existing = False
options = unreal.UsdStageImportOptions()
options.import_actors = False
options.import_geometry = True
options.import_skeletal_animations = False
options.import_materials = False
options.import_level_sequences = False
task.options = options
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
assets = [dict(path=obj.get_path_name(), type=obj.get_class().get_name()) for obj in task.get_objects()]
(work / 'source_reference_report.json').write_text(json.dumps(assets, indent=2), encoding='utf-8')
if not any(obj['type'] == 'SkeletalMesh' for obj in assets):
    raise RuntimeError('USD 导入没有生成源骨骼网格，禁止继续重定向')
