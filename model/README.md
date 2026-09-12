# 模型源码

`motionbricks/` 保留 NVIDIA MotionBricks 的网络、量化器、几何与动作表示。上游 Root 网络仍保留以兼容 G1 参考流程，不代表 UE pose-only 数据允许训练 Root。

Python 安装名称仍为 `motionbricks`。根目录 `setup.py` 将数据、训练与推理子包映射到各自职责目录，保持 Hydra `_target_` 和历史检查点可解析。网络导入不要求执行训练脚本。

`helper/data_training_util.py` 的特征转换被训练和推理共用，暂保留兼容名称和唯一实现。`helper/pl_util.py` 只构建动作表示，并不导入 Lightning。
