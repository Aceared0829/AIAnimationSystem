# Modified by the AIAnimationSystem maintainers: localized comments and runtime messages.

import os
import argparse
from omegaconf import OmegaConf, open_dict
from motionbricks.helper.pl_util import load_motion_rep
from hydra.utils import instantiate
import copy
from motionbricks.repository import base_weights

DEFAULT_RESULT_DIR = str(base_weights())
LOCAL_RESULT_DIR = ['./out', 'out/']
COPY_DATASET_TO_LOCAL = False
EXP = [
    "default",
][-1]

def get_path_dir(exp):
    if exp == "default":
        vqvae_path = 'motionbricks_vqvae'
        vqvae_ckpt = 'model-step=2000000.ckpt'

        pose_model_path = 'motionbricks_pose'
        pose_model_ckpt = 'model-step=2000000.ckpt'

        root_model_path = 'motionbricks_root'
        root_model_ckpt = 'model-step=2000000.ckpt'

    else:
        raise NotImplementedError(f"实验配置 {exp} 尚未实现。")

    return {'pose_model_path': pose_model_path, 'pose_model_ckpt': pose_model_ckpt,
            'root_model_path': root_model_path, 'root_model_ckpt': root_model_ckpt,
            'vqvae_path': vqvae_path, 'vqvae_ckpt': vqvae_ckpt}

def test(args: argparse.Namespace = None):
    if args is None:
        parser = argparse.ArgumentParser(description="模型测试")
        parser.add_argument("--result_dir", type=str, default=DEFAULT_RESULT_DIR)
        parser.add_argument("--data_root", type=str, default="./datasets")
        parser.add_argument("--explicit_dataset_folder", type=str, default=None)
        parser.add_argument("--EXP", type=str, default=None)
        args = parser.parse_args()

    if getattr(args, 'EXP', None) is not None:
        exp = args.EXP
    else:
        exp = EXP
    ckpt_info = get_path_dir(exp)

    models, confs = {}, {}
    for model_name in ['pose', 'root']:
        # 目前暂时硬编码配置路径
        model_key = model_name + '_model'
        ckpt_dir = f"{args.result_dir}/{ckpt_info[model_key + '_path']}/version_1"
        ckpt_path = f"{ckpt_dir}/checkpoints/{ckpt_info[model_key + '_ckpt']}"
        config_path = f"{ckpt_dir}/hparams.yaml"

        conf = OmegaConf.load(config_path)
        conf.ckpt_path = ckpt_path
        # The upstream serialized configs use paths relative to their original out/ folder.
        # Resolve those resources against the selected bundle without rewriting the checkpoint.
        for section in (conf.skeleton, conf.motion_rep.stats):
            folder = str(section.folder).replace('\\', '/')
            if folder.startswith(('out/', './out/')):
                section.folder = os.path.join(args.result_dir, folder.removeprefix('./').removeprefix('out/'))

        if type(conf.model.args.vqvae_model_ckpt_path) == str:
            for prefix in LOCAL_RESULT_DIR:

                if conf.model.args.vqvae_model_ckpt_path.startswith(prefix):
                    conf.model.args.vqvae_model_ckpt_path = \
                        conf.model.args.vqvae_model_ckpt_path.replace(prefix, f"{args.result_dir}/")
            conf.model.args.vqvae_model_ckpt_path = os.path.abspath(conf.model.args.vqvae_model_ckpt_path)

        if args.data_root is not None:
            conf.data_root = args.data_root

        if getattr(args, 'explicit_dataset_folder', None) is not None:
            # 将结果保存到另一目录："+data.explicit_dataset_folder=YOUR_DEBUG_FOLDER"
            conf.data.folder = args.explicit_dataset_folder

        from motionbricks.motionlib.train.utils import get_rank, setup_train_logging
        motion_rep = load_motion_rep(conf)
        if conf.model.pose_vqvae_network is None and model_name == 'pose':
            pose_vqvae_config_path = \
                os.path.abspath(os.path.join(conf.model.args.vqvae_model_ckpt_path, "..", "..", "config.yaml"))
            pose_vqvae_config = OmegaConf.load(pose_vqvae_config_path)
            pose_network_config = pose_vqvae_config.model.pose_network if 'pose_network' in pose_vqvae_config.model \
                else pose_vqvae_config.model.pose_vqvae_network
            conf.model.pose_vqvae_network = copy.deepcopy(pose_network_config)

        if conf.model.pose_vqvae_network is not None:
            pose_vqvae_motion_rep = getattr(conf.model, 'pose_vqvae_motion_rep', 'local')
            pose_vqvae_motion_rep = motion_rep.dual_rep.local_motion_rep if \
                pose_vqvae_motion_rep == 'local' else motion_rep.dual_rep.global_motion_rep
            pose_vqvae_network = instantiate(conf.model.pose_vqvae_network, motion_rep=pose_vqvae_motion_rep)

            # 确保模型与配置中预期的模型一致
            sanitized_vqvae_model_ckpt_path = conf.model.args.vqvae_model_ckpt_path.replace("\\", '/')  # Windows
            assert sanitized_vqvae_model_ckpt_path.split("/")[-4] == ckpt_info['vqvae_path'] and \
                sanitized_vqvae_model_ckpt_path.split("/")[-1] == ckpt_info['vqvae_ckpt'], \
                f"VQ-VAE 模型路径 {conf.model.args.vqvae_model_ckpt_path} 与 {ckpt_info} 不匹配"
        else:
            pose_vqvae_network = None

        # 获取进程序号
        global_rank = get_rank()
        import tempfile
        run_dir = tempfile.mkdtemp(prefix="motionbricks_")
        conf.out_dir = run_dir

        log = setup_train_logging(run_dir, global_rank)

        assert not conf.resume, "续训仅适用于训练模式；请在 `test` 函数中提供检查点路径。"

        import pytorch_lightning as pl
        import torch

        pl.seed_everything(conf.seed + max(0, global_rank), workers=True)

        if conf.trainer.accelerator == "gpu":  # for tinycudann default memory
            torch.cuda.set_device(int(os.environ.get("LOCAL_RANK", "0")))

        if "matmul_precision" in conf:
            torch.set_float32_matmul_precision(conf.matmul_precision)

        # 加载模型
        log.info("正在加载模型")

        # 移除仅用于训练、但会被 Hydra 尝试实例化的配置键
        for key in ['optimizer', 'scheduler']:
            if key in conf.model:
                with open_dict(conf):
                    del conf.model[key]

        backbone_network = instantiate(conf.model.backbone_network, motion_rep=motion_rep)
        models[model_name] = instantiate(conf.model, pose_vqvae_network=pose_vqvae_network,
                                         backbone_network=backbone_network, motion_rep=motion_rep)
        # models[model_name]= instantiate(conf.model)
        confs[model_name] = conf
        assert models[model_name].vqvae_model_loaded, \
            f"{model_name} 模型未加载 VQ-VAE，请检查配置文件。"

    log.info("正在加载数据集")
    assert global_rank == 0, "此脚本仅用于测试，因此只支持序号为 0 的进程。"

    # 兼容旧检查点；使用新检查点后可能不再需要
    conf.data.augment_text = False
    conf.data.use_overview_desc = False

    if hasattr(args, 'return_model_configs') and args.return_model_configs:
        if hasattr(args, 'return_dataloader') and args.return_dataloader:
            dataset_motion_rep = load_motion_rep(conf)
            train_dataset = instantiate(conf.data, split="train", motion_rep=dataset_motion_rep)
            train_dataloader = instantiate(conf.dataloader, train_dataset, shuffle=True)
            # train_dataset, train_dataloader = None, None
            val_dataset = instantiate(conf.data, split="test", motion_rep=dataset_motion_rep)
            val_dataloader = instantiate(conf.dataloader, val_dataset, shuffle=False)
            return models, confs, train_dataloader, val_dataloader
        else:
            return models, confs
    else:
        dataset_motion_rep = load_motion_rep(conf)
        train_dataset = instantiate(conf.data, split="train", motion_rep=dataset_motion_rep)
        train_dataloader = instantiate(conf.dataloader, train_dataset, shuffle=True)
        # train_dataset, train_dataloader = None, None
        val_dataset = instantiate(conf.data, split="test", motion_rep=dataset_motion_rep)
        val_dataloader = instantiate(conf.dataloader, val_dataset, shuffle=False)
