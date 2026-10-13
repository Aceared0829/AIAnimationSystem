"""集中兼容历史检查点和上游配置中的 Python 名称。新代码使用职责目录。"""

import importlib
import importlib.abc
import importlib.util
import sys

LEGACY_MODULES = {
    "motionbricks.motion_backbone.models": "training.models.backbone",
    "motionbricks.motion_backbone.inference": "inference.runtime.backbone",
    "motionbricks.motion_backbone.demo": "inference.demo",
    "motionbricks.motionlib.train": "training.common.optim",
    "motionbricks.vqvae.models": "training.models.vqvae",
    "motionbricks.exp_setup": "inference.runtime.experiment",
    "motionbricks.training": "training.common",
    "motionbricks.data": "data.runtime",
    "motionbricks.helper.mujoco_helper": "inference.demo.mujoco_helper",
    "motionbricks.helper": "motionweaver.representation.helper",
    "motionbricks.motionlib": "motionweaver.representation",
    "motionbricks.motion_backbone": "motionweaver.backbone",
    "motionbricks.vqvae": "motionweaver.tokenizer",
    "motionbricks.geometry": "motionweaver.geometry",
    "motionbricks.repository": "motionweaver.repository",
}


def canonical_module(name):
    for old, new in LEGACY_MODULES.items():
        if name == old or name.startswith(old + "."):
            return new + name[len(old):]
    return name


def canonical_config(conf):
    """只迁移 Hydra 类路径，保留数据字段、资源路径和权重契约。"""
    from omegaconf import DictConfig, OmegaConf

    def convert(value):
        if isinstance(value, dict):
            return {key: canonical_module(item) if key == "_target_" and isinstance(item, str)
                    else convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    result = OmegaConf.create(convert(OmegaConf.to_container(conf, resolve=False)))
    if not isinstance(result, DictConfig):
        raise ValueError("Model configuration must be a mapping")
    return result


class LegacyModuleAliases(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        canonical = canonical_module(fullname)
        if canonical == fullname:
            return None
        module = importlib.import_module(canonical)
        return importlib.util.spec_from_loader(fullname, self, is_package=hasattr(module, "__path__"))

    def create_module(self, spec):
        return importlib.import_module(canonical_module(spec.name))

    def exec_module(self, module):
        pass
