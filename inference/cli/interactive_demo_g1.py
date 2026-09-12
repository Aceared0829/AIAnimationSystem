# Modified by the AIAnimationSystem maintainers: added Chinese demo controls and adapted the interactive interface.

import argparse
import time
import platform

from motionbricks.helper.argparse_zh import enable_chinese_argparse
from motionbricks.repository import repository_root, base_weights


def _disable_mujoco_keyboard_shortcuts(controller_keys='wasdrtfgeqzxcvb'):
    """阻止 MuJoCo 查看器处理与 WASD 动作控制器冲突的快捷键。

    在 Linux/X11 上：通过被动按键抓取，在 GLFW 收到按键前由 X 服务器
    拦截按键；pynput 仍可通过 XRecord 捕获按键。

    在 macOS/Windows 上：暂不支持，MuJoCo 快捷键可能产生干扰。
    """
    if platform.system() != 'Linux':
        return
    try:
        from Xlib import display as xdisplay, X
        _xdpy = xdisplay.Display()
        _root = _xdpy.screen().root

        def _find_window_by_name(win, name_substr):
            try:
                name = win.get_wm_name()
                if name and name_substr in name:
                    return win
            except Exception:
                pass
            for child in win.query_tree().children:
                r = _find_window_by_name(child, name_substr)
                if r:
                    return r
            return None

        time.sleep(0.5)
        mj_win = _find_window_by_name(_root, 'MuJoCo')
        if mj_win:
            for ch in controller_keys:
                keycode = _xdpy.keysym_to_keycode(ord(ch) - 32)
                mj_win.grab_key(keycode, X.AnyModifier,
                                False, X.GrabModeAsync, X.GrabModeAsync)
            _xdpy.sync()
    except Exception as e:
        print(f"提示：无法禁用 MuJoCo 键盘快捷键：{e}")


def main(args) -> None:
    import torch as t
    import numpy as np
    try:
        import mujoco
        import mujoco.viewer
        from motionbricks.motion_backbone.demo.utils import navigation_demo
        from motionbricks.motion_backbone.demo.chinese_control_panel import ChineseControlPanel
    except ModuleNotFoundError as error:
        raise RuntimeError('G1 演示缺少可选依赖；请从仓库根目录安装 .[demo] 并准备 G1 权重。') from error
    demo_agent = navigation_demo(args)
    control_panel = ChineseControlPanel() if args.chinese_ui else None

    num_runs = 0
    while num_runs < args.num_runs:
        num_runs += 1
        print(f"正在运行第 {num_runs} 次迭代，共 {args.num_runs} 次……")
        random_seed = args.random_seed * (num_runs + 2333) * 2333 % (2 ** 32 - 1)
        np.random.seed(random_seed)
        t.manual_seed(random_seed)
        demo_agent.full_agent.reset()

        steps = 0

        if args.has_viewer:
            with mujoco.viewer.launch_passive(
                demo_agent.mj_model,
                demo_agent.mj_data,
                show_left_ui=not args.chinese_ui,
                show_right_ui=not args.chinese_ui,
            ) as viewer:
                _disable_mujoco_keyboard_shortcuts()
                if control_panel:
                    control_panel.embed_mujoco_window()

                while viewer.is_running() and steps < args.max_steps and not (
                    control_panel and control_panel.is_closed
                ):
                    if control_panel:
                        for command, value in control_panel.poll_commands():
                            if command == "reset":
                                demo_agent.full_agent.reset()
                                steps = 0
                            elif command == "camera":
                                viewer.cam.azimuth, viewer.cam.elevation, viewer.cam.distance = value
                            elif command == "display":
                                viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = value["contact"]
                                viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_JOINT] = value["joint"]
                                viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_TRANSPARENT] = value["transparent"]

                        if control_panel.is_paused:
                            viewer.sync()
                            time.sleep(demo_agent.mj_model.opt.timestep)
                            continue

                    force_idle = steps + 100 > args.max_steps
                    steps += 1
                    viewer.user_scn.ngeom = 0
                    step_start = time.time()
                    qpos = demo_agent.full_agent.get_next_frame()
                    context_motion_features = demo_agent.full_agent.get_context_motion_features()
                    context_mujoco_qpos = demo_agent.full_agent.get_context_mujoco_qpos()
                    demo_agent.mj_data.qpos[:] = qpos

                    control_signals = demo_agent.controller.generate_control_signals(
                        viewer, demo_agent.mj_model, demo_agent.mj_data, visualize=True,
                        control_info={"force_idle": force_idle,
                                      'allowed_mode': getattr(args, 'allowed_mode', None)}
                    )

                    if args.use_qpos:
                        control_signals['context_mujoco_qpos'] = context_mujoco_qpos
                    else:
                        control_signals['context_motion_features'] = context_motion_features

                    with t.no_grad():
                        demo_agent.full_agent.generate_new_frames(
                            control_signals,
                            demo_agent.controller.get_controller_dt() * args.generate_dt
                        )

                    mujoco.mj_forward(demo_agent.mj_model, demo_agent.mj_data)
                    viewer.cam.lookat[:] = demo_agent.controller.get_prev_qpos()[:, :3].mean(axis=0)
                    viewer.sync()
                    time_until_next_step = demo_agent.mj_model.opt.timestep - (time.time() - step_start)
                    if time_until_next_step > 0:
                        time.sleep(time_until_next_step)
            if control_panel:
                control_panel.close()
        else:
            while steps < args.max_steps:
                steps += 1
                force_idle = steps + 100 > args.max_steps
                qpos = demo_agent.full_agent.get_next_frame()
                context_motion_features = demo_agent.full_agent.get_context_motion_features()
                context_mujoco_qpos = demo_agent.full_agent.get_context_mujoco_qpos()
                demo_agent.mj_data.qpos[:] = qpos

                control_signals = demo_agent.controller.generate_control_signals(
                    None, demo_agent.mj_model, demo_agent.mj_data, visualize=False,
                    control_info={"force_idle": force_idle, 'allowed_mode': getattr(args, 'allowed_mode', None)}
                )
                if args.use_qpos:
                    control_signals['context_mujoco_qpos'] = context_mujoco_qpos
                else:
                    control_signals['context_motion_features'] = context_motion_features

                with t.no_grad():
                    demo_agent.full_agent.generate_new_frames(
                        control_signals, demo_agent.controller.get_controller_dt() * args.generate_dt
                    )

                mujoco.mj_forward(demo_agent.mj_model, demo_agent.mj_data)


def parse_args(argv=None):
    enable_chinese_argparse()
    parser = argparse.ArgumentParser(description="G1 人形角色交互演示")

    # 路径配置
    parser.add_argument("--humanoid_xml", type=str, default=str(repository_root() / "inference/assets/skeletons/g1/scene_29dof.xml"),
                        help="G1 场景 XML 文件路径")
    parser.add_argument("--result_dir", type=str, default=str(base_weights()), help="模型检查点目录")
    parser.add_argument("--data_root", type=str, default=str(repository_root() / "data/raw"), help="数据集根目录")
    parser.add_argument("--explicit_dataset_folder", type=str, default=None, help="显式指定数据集目录")
    parser.add_argument("--reprocess_clips", type=int, default=0, help="是否重新处理动作片段")

    # 控制器配置
    parser.add_argument("--controller", type=str, default="wasd",
                        choices=["wasd", "random"], help="控制器类型：键盘或随机控制")
    parser.add_argument("--lookat_movement_direction", type=int, default=0,
                        help="角色是否朝向移动方向")
    parser.add_argument("--has_viewer", type=int, default=1, help="是否打开 MuJoCo 查看器")
    parser.add_argument("--pre_filter_qpos", type=int, default=1, help="是否预先平滑关节位置")
    parser.add_argument("--source_root_realignment", type=int, default=1, help="是否重新对齐源根节点")
    parser.add_argument("--target_root_realignment", type=int, default=1, help="是否重新对齐目标根节点")
    parser.add_argument("--force_canonicalization", type=int, default=1, help="是否强制执行动作标准化")
    parser.add_argument("--skip_ending_target_cond", type=int, default=0, help="是否忽略末尾目标条件")
    parser.add_argument("--random_speed_scale", type=int, default=0, help="是否随机调整速度比例")
    parser.add_argument("--speed_scale", type=str, default="0.8,1.2", help="最小和最大速度比例")
    parser.add_argument("--generate_dt", type=float, default=2.0, help="每次生成的时间跨度")

    # 运行配置
    parser.add_argument("--max_steps", type=int, default=10000, help="最大运行步数")
    parser.add_argument("--random_seed", type=int, default=1234, help="随机种子")
    parser.add_argument("--num_runs", type=int, default=1, help="重复运行次数")

    # 模型配置
    parser.add_argument("--use_qpos", type=int, default=1, help="是否使用 MuJoCo qpos 作为上下文")
    parser.add_argument("--planner", type=str, default="default", help="动作规划器配置")
    parser.add_argument("--allowed_mode", type=str, default=None, help="允许使用的动作模式")
    parser.add_argument("--clips", type=str, default="G1", help="动作片段集合")
    parser.add_argument("--chinese_ui", type=int, default=1,
                        help="启用完整中文控制台并隐藏 MuJoCo 英文侧栏")

    args = parser.parse_args(argv)

    args.return_model_configs = True
    args.return_dataloader = True
    args.recording_dir = None
    args.EXP = args.planner
    args.speed_scale = [float(i) for i in args.speed_scale.split(",")]

    return args


if __name__ == "__main__":
    main(parse_args())
