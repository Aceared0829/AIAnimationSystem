"""Run real G1 model generation and MuJoCo rendering with a bounded frame count."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import mujoco
import numpy as np
import torch
from PIL import Image

from inference.cli.interactive_demo_g1 import parse_args
from motionbricks.motion_backbone.demo.utils import navigation_demo
from motionbricks.repository import base_weights, repository_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=180)
    args = parser.parse_args()
    if args.frames < 120:
        parser.error('Use at least 120 frames to exercise generation beyond the initial clip.')
    args.output.mkdir(parents=True, exist_ok=False)
    identities = []
    for path in sorted(base_weights().rglob('*.ckpt')):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            first = stream.read(256)
            if first.startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise RuntimeError(f'Weight is still an LFS pointer: {path}')
            digest.update(first)
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        identities.append({'path': str(path.relative_to(repository_root())), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()})
    config = parse_args(['--controller', 'random', '--has_viewer', '0', '--chinese_ui', '0', '--max_steps', str(args.frames)])
    torch.manual_seed(1234)
    np.random.seed(1234)
    started = time.perf_counter()
    demo = navigation_demo(config)
    initialization_seconds = time.perf_counter() - started
    generated_calls = 0
    predict = demo.inferencer.predict
    def record_predict(*values, **keywords):
        nonlocal generated_calls
        result = predict(*values, **keywords)
        generated_calls += 1
        return result
    demo.inferencer.predict = record_predict
    demo.full_agent.reset()
    camera = mujoco.MjvCamera()
    camera.distance, camera.azimuth, camera.elevation = 4.0, 135, -18
    frame_positions = []
    images = []
    started = time.perf_counter()
    demo.mj_model.vis.global_.offwidth = max(800, demo.mj_model.vis.global_.offwidth)
    demo.mj_model.vis.global_.offheight = max(480, demo.mj_model.vis.global_.offheight)
    with mujoco.Renderer(demo.mj_model, height=480, width=800) as renderer:
        for frame in range(args.frames):
            with torch.no_grad():
                qpos = demo.full_agent.get_next_frame()
                if not np.isfinite(qpos).all():
                    raise AssertionError(f'Non-finite qpos at frame {frame}')
                demo.mj_data.qpos[:] = qpos
                signals = demo.controller.generate_control_signals(None, demo.mj_model, demo.mj_data, visualize=False,
                                                                  control_info={'force_idle': False, 'allowed_mode': None})
                signals['context_mujoco_qpos'] = demo.full_agent.get_context_mujoco_qpos()
                demo.full_agent.generate_new_frames(signals, demo.controller.get_controller_dt() * config.generate_dt)
                mujoco.mj_forward(demo.mj_model, demo.mj_data)
            if not np.isfinite(demo.mj_data.xpos).all():
                raise AssertionError(f'Non-finite body positions at frame {frame}')
            frame_positions.append(np.array(qpos, copy=True))
            if frame % 3 == 0:
                camera.lookat[:] = demo.mj_data.qpos[:3]
                renderer.update_scene(demo.mj_data, camera=camera)
                pixels = renderer.render().copy()
                if pixels.std() < 1:
                    raise AssertionError('Render is blank')
                images.append(Image.fromarray(pixels))
    positions = np.stack(frame_positions)
    if generated_calls == 0 or np.max(np.abs(np.diff(positions, axis=0))) < 1e-5:
        raise AssertionError('No generated motion observed')
    images[-1].save(args.output / 'g1-preview.png')
    images[0].save(args.output / 'g1-motion.gif', save_all=True, append_images=images[1:], duration=100, loop=0)
    np.save(args.output / 'qpos.npy', positions)
    report = {'mujoco': mujoco.__version__, 'torch': torch.__version__, 'gpu': torch.cuda.get_device_name(0),
              'frames': args.frames, 'model_predict_calls': generated_calls, 'rendered_frames': len(images),
              'qpos_finite': True, 'body_positions_finite': True, 'qpos_shape': list(positions.shape),
              'root_xy_displacement_m': float(np.linalg.norm(positions[-1, :2] - positions[0, :2])),
              'initialization_seconds': initialization_seconds, 'generation_and_render_seconds': time.perf_counter() - started,
              'weights': identities, 'scope': 'G1 pretrained motion generation and kinematic MuJoCo rendering, not UE or physical control'}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
