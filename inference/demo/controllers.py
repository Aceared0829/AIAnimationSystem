# Modified by the AIAnimationSystem maintainers: localized controls and messages.

import torch as t
from motionbricks.motion_backbone.demo.clips import clip_holder_G1
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation as R
import copy
import platform
if platform.system() == 'Linux' or platform.system() == 'Darwin':
    from pynput import keyboard
else:
    import keyboard

class KeyboardHandler:
    def __init__(self):
        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release)
        self.listener.start()
        self._pressed_keys = set()

    def on_press(self, key, injected):
        """跟踪 WASD、方向键、Enter、Shift 和 Ctrl 的按下状态。"""
        if hasattr(key, 'char'):  # 字符键
            key_char = key.char
            self._pressed_keys.add(key_char)
        elif hasattr(key, 'name'):  # 特殊键
            key_char = key.name
            self._pressed_keys.add(key_char)

    def on_release(self, key, injected):
        """跟踪 WASD、方向键、Enter、Shift 和 Ctrl 的释放状态。"""
        if hasattr(key, 'char'):  # 字符键
            key_char = key.char
            if key_char in self._pressed_keys:
                self._pressed_keys.remove(key_char)
        elif hasattr(key, 'name'):  # 特殊键
            key_char = key.name
            if key_char in self._pressed_keys:
                self._pressed_keys.remove(key_char)

    def get_pressed_keys(self):
        return self._pressed_keys.copy()

class base_controller(object):
    """处理控制信号的基础控制器类。"""
    def __init__(self, clips: str = "G1", min_token: int = 6, max_token: int = 16):
        self._prev_qpos: np.ndarray = None
        self._FPS = 30
        self._CONTROLLER_DT = 8 / self._FPS  # 每 8 帧重新生成一次结果
        self._clip_holder_class = clip_holder_G1
        self._min_token = min_token
        self._max_token = max_token

    def generate_control_signals(self):
        raise NotImplementedError("子类必须实现此方法")

    def get_prev_qpos(self):
        return self._prev_qpos.copy()

    def get_controller_dt(self):
        return self._CONTROLLER_DT

    def reset(self):
        self._prev_qpos = None

    @property
    def is_activated(self):
        return True  # 默认启用控制器并监听键盘命令

    @property
    def snapshot_keyboard_control(self):
        if platform.system() == 'Linux' or platform.system() == 'Darwin':
            if not hasattr(self, 'keyboard_handler'):
                self.keyboard_handler = KeyboardHandler()
            key_pressed = self.keyboard_handler.get_pressed_keys()
            candidates = ['w', 'a', 's', 'd', 'left', 'right', 'up', 'down', 'shift', 'ctrl', 'enter',
                          'x', 'z', 'c', 'v', 'b', 'r', 't', 'f', 'g', 'q', 'e']
            key_pressed = {key: True if key in key_pressed else False for key in candidates}
        else:
            # Windows / macOS
            key_pressed = {
                # 移动方向
                "w": keyboard.is_pressed('w'), "a": keyboard.is_pressed('a'),
                "s": keyboard.is_pressed('s'), "d": keyboard.is_pressed('d'),

                # 朝向
                "left": keyboard.is_pressed('left'), "right": keyboard.is_pressed('right'),
                "up": keyboard.is_pressed('up'), "down": keyboard.is_pressed('down'),

                # 模式控制；ZXCVB 分别对应不同动作风格
                "z": keyboard.is_pressed('z'),
                "x": keyboard.is_pressed('x'),
                "c": keyboard.is_pressed('c'),
                "v": keyboard.is_pressed('v'),
                "b": keyboard.is_pressed('b'),

                "r": keyboard.is_pressed('r'),
                "t": keyboard.is_pressed('t'),
                "f": keyboard.is_pressed('f'),
                "g": keyboard.is_pressed('g'),
                "q": keyboard.is_pressed('q'),
                "e": keyboard.is_pressed('e'),

                # 旧版模式控制
                "shift": keyboard.is_pressed('shift'), "ctrl": keyboard.is_pressed('ctrl'),
                "enter": keyboard.is_pressed('enter'),
            }
        return key_pressed

    def get_default_allowed_pred_num_tokens(self, mode: str | int):
        if type(mode) == int:
            assert mode >= 0 and mode < len(list(self._clip_holder_class.CLIPS.keys())), "无效的模式编号"
            mode = list(self._clip_holder_class.CLIPS.keys())[mode]
        assert mode in list(self._clip_holder_class.CLIPS.keys()), "无效的模式"

        if self._clip_holder_class.CLIPS[mode].get('allowed_pred_num_tokens', None) is not None:
            return t.tensor(self._clip_holder_class.CLIPS[mode]['allowed_pred_num_tokens']).view([1, -1])
        else:
            return t.ones(self._max_token - self._min_token + 1, dtype=t.int).view([1, -1])  # 默认值

class WASD_controller(base_controller):
    """处理 WASD 输入的控制器类。

    输入：WASD 按键状态。
    输出：目标位置、目标朝向和角色当前模式。
    """
    def __init__(self, lookat_movement_direction: bool = False, clips: str = "G1", **kwargs):
        super(WASD_controller, self).__init__(clips, **kwargs)
        # 为真时角色朝向键盘输入方向，否则朝向相机方向
        self._LOOKAT_MOVEMENT_DIRECTION = lookat_movement_direction
        self._NUM_HISTORY_STEPS = 5  # 用于计算平均速度
        self._prev_qpos = None

    def generate_control_signals(self, viewer, mj_model: mujoco.MjModel, mj_data: mujoco.MjData,
                                 visualize: bool = True, control_info: dict = {}):

        if self._prev_qpos is None:
            self._prev_qpos = np.zeros((self._NUM_HISTORY_STEPS, mj_model.nq))
            self._prev_qpos[:] = mj_data.qpos.copy().reshape(1, -1)

        key_pressed = self.snapshot_keyboard_control if \
            'key_pressed' not in control_info or control_info['key_pressed'] is None else control_info['key_pressed']

        # 控制模式
        mode = 'walk' if (key_pressed["w"] or key_pressed["a"] or key_pressed["s"] or key_pressed["d"]) else 'idle'
        for candidate_mode in [i for i in list(self._clip_holder_class.CLIPS.keys()) if i != 'idle' and i != 'walk']:
            mode = candidate_mode \
                if key_pressed.get(self._clip_holder_class.DEFAULT_KEYS[candidate_mode], False) else mode

        # 生成目标位置与方向
        movement_direction, facing_direction = \
            self._generate_target_position_and_heading(viewer, mj_model, mj_data, key_pressed, mode)

        mode = t.tensor([list(self._clip_holder_class.CLIPS.keys()).index(mode)])

        # 完成处理后更新上一组 qpos
        self._prev_qpos = np.concatenate((self._prev_qpos[1:], mj_data.qpos.copy().reshape(1, -1)), axis=0)
        control_signals = {
            "movement_direction": t.from_numpy(movement_direction).view([1, -1]),
            "facing_direction": t.from_numpy(facing_direction).view([1, -1]),
            "mode": mode.view([1, -1])
        }
        control_signals['allowed_pred_num_tokens'] = self.get_default_allowed_pred_num_tokens(mode.item())
        return control_signals

    def _generate_target_position_and_heading(self, viewer, mj_model: mujoco.MjModel,
                                              mj_data: mujoco.MjData, key_pressed: dict, mode: str):
        # 获取相机观察点和相机位置，使用二者确定移动方向
        lookat_position = viewer.cam.lookat

        cam_distance = viewer.cam.distance
        cam_azimuth = -np.radians(viewer.cam.azimuth) - np.pi / 2.0
        cam_elevation = -1 * np.radians(viewer.cam.elevation)  # 负仰角表示向下观察

        # 计算相机实际位置
        cam_pos = lookat_position + cam_distance * np.array([
            np.cos(cam_elevation) * np.sin(cam_azimuth),
            np.cos(cam_elevation) * np.cos(cam_azimuth),
            np.sin(cam_elevation)
        ])

        # 相机方向
        camera_direction = (lookat_position - cam_pos) * np.array([1.0, 1.0, 0.0])
        camera_direction = camera_direction / np.linalg.norm(camera_direction)

        if mode != 'idle':
            # 获取控制输入的相对方向
            controller_relative_direction = \
                np.array([1.0, 0.0, 0.0]) * key_pressed["w"] + np.array([-1.0, 0.0, 0.0]) * key_pressed["s"] + \
                np.array([0.0, -1.0, 0.0]) * key_pressed["d"] + np.array([0.0, 1.0, 0.0]) * key_pressed["a"]
            controller_relative_direction = \
                controller_relative_direction / (np.linalg.norm(controller_relative_direction) + 1e-5)

            z_axis_camera_angle = np.arctan2(camera_direction[1], camera_direction[0])
            controller_relative_direction_angle = \
                np.arctan2(controller_relative_direction[1], controller_relative_direction[0])

            abs_heading_angle = z_axis_camera_angle + controller_relative_direction_angle
            movement_direction = np.array([np.cos(abs_heading_angle), np.sin(abs_heading_angle), 0.0])

            if self._LOOKAT_MOVEMENT_DIRECTION:
                facing_direction = movement_direction
            else:
                facing_direction = camera_direction

        else:  # 待机状态
            # 待机时延续当前速度与朝向
            qvel = (self._prev_qpos[1:, :3] - self._prev_qpos[:-1, :3]).mean(axis=0) * \
                np.array([1.0, 1.0, 0.0]) / mj_model.opt.timestep
            movement_direction = qvel / (np.linalg.norm(qvel) + 1e-5)  # qvel 很小时视为不移动
            facing_direction = \
                R.from_quat(self._prev_qpos[-1, 3: 7], scalar_first=True).apply(np.array([1.0, 0.0, 0.0])) * \
                np.array([1.0, 1.0, 0.0])
            facing_direction = facing_direction / (np.linalg.norm(facing_direction) + 1e-5)

        return movement_direction, facing_direction

class random_controller(base_controller):
    """随机生成控制信号。"""
    def __init__(self, disable_running: bool = True, lookat_movement_direction: bool = False,
                 new_control_dt: float = 2.0,
                 max_angle_change_between_controls: float = 0.5 * np.pi,
                 clips: str = "G1", **kwargs):
        super(random_controller, self).__init__(clips, **kwargs)
        self._prev_qpos = None
        self._NUM_HISTORY_STEPS = 5             # 用于计算平均速度
        self._NEW_CONTROL_DT = new_control_dt   # 每隔 new_control_dt 秒切换控制（默认 2.0 秒）
        self._time_since_prev_control = 0.0
        self._control = None
        self._disable_running = disable_running  # 禁用奔跑
        self._max_angle_change_between_controls = max_angle_change_between_controls
        self._LOOKAT_MOVEMENT_DIRECTION = lookat_movement_direction

    def generate_control_signals(self, viewer, mj_model: mujoco.MjModel, mj_data: mujoco.MjData,
                                 visualize: bool = True, control_info: dict = None):

        if self._prev_qpos is None:
            self._prev_qpos = np.zeros((self._NUM_HISTORY_STEPS, mj_model.nq))
            self._prev_qpos[:] = mj_data.qpos.copy().reshape(1, -1)

        self._time_since_prev_control += mj_model.opt.timestep

        if self._time_since_prev_control < self._NEW_CONTROL_DT and self._control is not None:
            self._prev_qpos = np.concatenate((self._prev_qpos[1:], mj_data.qpos.copy().reshape(1, -1)), axis=0)
            return copy.deepcopy(self._control)
        else:
            self._time_since_prev_control = 0.0  # 生成新控制

        # 控制模式
        candidates = [i for i in list(self._clip_holder_class.CLIPS.keys()) if
                      not ((i == 'run' or i == 'sprint') and self._disable_running)]
        if self._control is not None and self._control["mode"].item() == \
                list(self._clip_holder_class.CLIPS.keys()).index('idle'):
            candidates.remove("idle")  # 待机后不再连续待机
        else:
            candidates.remove("idle")  # 奔跑后不再连续奔跑
        if control_info is not None and control_info["force_idle"]:
            candidates = ["idle"]
        if control_info is not None and control_info["allowed_mode"] is not None:
            candidates = [i for i in list(self._clip_holder_class.CLIPS.keys()) if i in control_info["allowed_mode"]]
        mode = np.random.choice(candidates, size=1, replace=False)
        mode = t.tensor([list(self._clip_holder_class.CLIPS.keys()).index(mode[0])])

        # 生成目标位置与方向
        movement_angle, facing_angle = t.rand(1) * 2 * t.pi, t.rand(1) * 2 * t.pi
        if self._control is not None:
            angle_diff = (t.rand(1) * 2 - 1) * self._max_angle_change_between_controls
            facing_angle = self._control["facing_angle"] + angle_diff
            facing_angle = facing_angle % (2 * t.pi)
        else:
            facing_angle = facing_angle * 0.0  # 第一次运行提供初始全局朝向角
        movement_direction = t.tensor([t.cos(movement_angle), t.sin(movement_angle), 0.0])
        facing_direction = t.tensor([t.cos(facing_angle), t.sin(facing_angle), 0.0])

        if self._LOOKAT_MOVEMENT_DIRECTION:
            # facing_direction = movement_direction
            movement_direction = facing_direction

        # 完成处理后更新上一组 qpos
        self._prev_qpos = np.concatenate((self._prev_qpos[1:], mj_data.qpos.copy().reshape(1, -1)), axis=0)
        self._control = {"movement_direction": movement_direction.view([1, -1]),
                         "facing_direction": facing_direction.view([1, -1]), "mode": mode.view([1, -1]),
                         "movement_angle": movement_angle, "facing_angle": facing_angle}
        self._control['allowed_pred_num_tokens'] = self.get_default_allowed_pred_num_tokens(mode.item())
        return copy.deepcopy(self._control)

