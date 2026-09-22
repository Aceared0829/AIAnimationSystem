"""在相同源时间点比较末帧拼接与固定步长重叠播放；CPU 仅做算法质量对照。"""
import argparse
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort
from scipy.spatial.transform import Rotation
from inference.export.export_unreal_animgraph import pack_raw_pose


def blend(a, b, weight):
    out = np.empty_like(a)
    out[..., :3] = a[..., :3] * (1 - weight) + b[..., :3] * weight
    qa, qb = a[..., 3:], b[..., 3:].copy()
    dot = np.sum(qa * qb, axis=-1, keepdims=True)
    qb = np.where(dot < 0, -qb, qb)
    angle = np.arccos(np.clip(np.abs(dot), 0, 1))
    sine = np.sin(angle)
    q = (np.sin((1 - weight) * angle) * qa + np.sin(weight * angle) * qb) / np.maximum(sine, 1.e-8)
    q = np.where(sine < 1.e-5, qa * (1 - weight) + qb * weight, q)
    out[..., 3:] = q / np.linalg.norm(q, axis=-1, keepdims=True)
    return out


def localize(packed, parents):
    shape = packed.shape[:-1]
    rotations = packed[..., 3:].reshape(*shape, 3, 3)
    positions = packed[..., :3]
    result = np.empty((*shape, 7), dtype=np.float64)
    for bone, parent in enumerate(parents):
        rotation = rotations[..., bone, :, :]
        position = positions[..., bone, :]
        if parent >= 0:
            inverse = np.swapaxes(rotations[..., parent, :, :], -1, -2)
            rotation = inverse @ rotation
            position = (inverse @ (position - positions[..., parent, :])[..., None])[..., 0]
        result[..., bone, :3] = position
        result[..., bone, 3:] = Rotation.from_matrix(rotation.reshape(-1, 3, 3)).as_quat().reshape(*shape[:-1], 4)
    return result


def positions(local, parents):
    rotation = Rotation.from_quat(local[..., 3:].reshape(-1, 4)).as_matrix().reshape(*local.shape[:-1], 3, 3)
    result = local[..., :3].copy()
    for bone, parent in enumerate(parents):
        if parent >= 0:
            result[:, bone] = result[:, parent] + (rotation[:, parent] @ local[:, bone, :3, None])[..., 0]
            rotation[:, bone] = rotation[:, parent] @ rotation[:, bone]
    return result


def simulate(source, windows, delay):
    # 用 60 Hz 播放冻结左右插值端点，对齐 UE 的 Commit 规则；只导出整数 30 Hz 采样点。
    models, weights, output = {}, {}, {}
    frozen = -1
    stationary, resume = [0], [0]
    for i in range(1, len(source)):
        same_position = np.all(np.abs(source[i, :, :3] - source[i - 1, :, :3]) <= .01)
        angle = 2 * np.arccos(np.clip(np.abs(np.sum(source[i, :, 3:] * source[i - 1, :, 3:], axis=-1)), 0, 1))
        same = same_position and np.all(angle < .001)
        stationary.append(min(stationary[-1] + 1, 1000) if same else 0)
        resume.append(4 if not same and stationary[-2] >= 6 else max(0, resume[-1] - 1))
    for tick in range(len(source) * 2):
        end = tick // 2
        if tick % 2 == 0 and end >= 15 and (end - 15) % 4 == 0:
            for offset, prediction in enumerate(windows[end]):
                index = end - 15 + offset
                if index <= frozen:
                    continue
                weight = 1 + min(offset, 15 - offset)
                models[index] = prediction.copy() if index not in models else blend(models[index], prediction, weight / (weights[index] + weight))
                weights[index] = weights.get(index, 0) + weight
        playback = max(0, tick / 2 - delay)
        low, high = int(np.floor(playback)), int(np.ceil(playback))
        for index in range(max(1, frozen + 1), high + 1):
            if index not in models or index - 1 not in models:
                continue
            if stationary[index] >= 6:
                models[index] = models[index - 1].copy()
            elif resume[index] > 0:
                models[index] = blend(models[index - 1], models[index], (5 - resume[index]) / 4)
        if tick % 2 == 0 and low in models and high in models:
            output[low] = models[low].copy()
        frozen = max(frozen, high)
    return output


def metric(x):
    return {'mean': float(np.mean(x)), 'p95': float(np.percentile(x, 95)), 'max': float(np.max(x))}


def rms(x):
    return np.sqrt(np.mean(np.sum(x * x, axis=-1), axis=-1))


def evaluate(bundle, dataset, output):
    bundle, dataset, output = Path(bundle), Path(dataset), Path(output)
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf8'))
    skeleton = json.loads((dataset / 'skeleton.json').read_text(encoding='utf8'))
    clips = json.loads((dataset / 'dataset.json').read_text(encoding='utf8'))['clips']
    parents = [b['parent'] for b in skeleton['bones']]
    feet = [i for i, b in enumerate(skeleton['bones']) if b['name'] in ('foot_l', 'foot_r')]
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(bundle / 'model.onnx'), options, providers=['CPUExecutionProvider'])
    report = {'scope': 'algorithm quality, 60 Hz playback, same source times; not GPU performance or gameplay validation',
              'model_sha256': manifest['onnx_sha256'], 'clips': []}
    for item in manifest['validation']:
        clip = next(c for c in clips if c['asset'] == item['asset'])
        with np.load(dataset / clip['raw_file']) as raw:
            packed = pack_raw_pose(raw, skeleton)
        source = localize(packed, parents)
        windows = {}
        for end in range(15, len(packed)):
            sample = np.concatenate([packed[end - 15:end + 1], packed[end:end + 1]])[None]
            prediction = session.run(None, {'pose_history': sample})[0][0]
            windows[end] = localize(prediction, parents)
        variants = {'last_frame': {end: value[-1] for end, value in windows.items()},
                    'overlap4': simulate(source, windows, 4), 'overlap8': simulate(source, windows, 8)}
        common = sorted(set(range(20, len(source) - 8)).intersection(*(set(v) for v in variants.values())))
        if len(common) < 10 or np.any(np.diff(common) != 1):
            raise ValueError('缺少连续且对齐的评估区间')
        reference = source[common]
        reference_positions = positions(reference, parents)
        result = {'category': item['category'], 'asset': item['asset'], 'source_frame_start': common[0], 'source_frame_end': common[-1],
                  'samples': len(common), 'source_acceleration_cm_per_frame2': metric(rms(np.diff(reference_positions, n=2, axis=0))), 'variants': {}}
        for name, frames in variants.items():
            values = np.stack([frames[i] for i in common])
            predicted = positions(values, parents)
            angle = 2 * np.arccos(np.clip(np.abs(np.sum(values[..., 3:] * reference[..., 3:], axis=-1)), 0, 1)) * 180 / np.pi
            scores = {'joint_rmse_cm': metric(rms(predicted - reference_positions)),
                      'local_rotation_rmse_degrees': metric(np.sqrt(np.mean(angle * angle, axis=-1))),
                      'acceleration_cm_per_frame2': metric(rms(np.diff(predicted, n=2, axis=0))),
                      'velocity_error_cm_per_frame': metric(rms(np.diff(predicted, axis=0) - np.diff(reference_positions, axis=0)))}
            if feet:
                scores['foot_velocity_error_cm_per_frame'] = metric(rms(np.diff(predicted[:, feet], axis=0) - np.diff(reference_positions[:, feet], axis=0)))
            result['variants'][name] = scores
        report['clips'].append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    evaluate(args.bundle, args.dataset, args.output)
