"""将离线跑酷骨架对照渲染为视频；蓝色源姿态，橙色重建。"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def render(report_path, baseline_name='endpoints2', candidate_name='targeted4', prefix='targeted'):
    report_path = Path(report_path)
    report = json.loads(report_path.read_text(encoding='utf8'))
    arrays = np.load(report_path.with_suffix('.npz'))
    skeleton = json.loads(Path('data/prepared/native30_relative_v2_worldcontacts/skeleton.json').read_text(encoding='utf8'))
    names = {b['name']: i for i, b in enumerate(skeleton['bones'])}
    chains = [['pelvis', 'spine_03', 'spine_05', 'neck_01', 'head'],
        ['spine_05', 'upperarm_l', 'lowerarm_l', 'hand_l'], ['spine_05', 'upperarm_r', 'lowerarm_r', 'hand_r'],
        ['pelvis', 'thigh_l', 'calf_l', 'foot_l', 'ball_l'], ['pelvis', 'thigh_r', 'calf_r', 'foot_r', 'ball_r']]
    edges = [(names[a], names[b]) for chain in chains for a, b in zip(chain, chain[1:])]
    selected = [(str(i), c) for i, c in enumerate(report['clips']) if c['category'] == 'Traversal']
    if not selected:
        raise ValueError('报告没有可渲染的 Traversal 动画')
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 17)
    small = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 14)
    width, height = 1200, 76+len(selected)*260
    def frame_image(tick=None):
        canvas = Image.new('RGB', (width, height), '#f4f6fa')
        draw = ImageDraw.Draw(canvas)
        draw.text((20, 10), 'OFFLINE SKELETON COMPARISON | same source frames, 30 FPS | not UE gameplay', fill='#15253d', font=font)
        draw.text((20, 38), f'Blue: source   Orange: reconstruction   Left: {baseline_name}   Right: {candidate_name}', fill='#15253d', font=font)
        for row, (key, clip) in enumerate(selected):
            source = arrays[key+'_source']
            baseline = arrays[key+'_'+baseline_name]
            peak = int(np.linalg.norm(baseline-source, axis=-1).mean(axis=1).argmax())
            index = peak if tick is None else min(tick, len(source)-1)
            title = clip['asset'].split('/')[-1].split('.')[0].replace('M_Neutral_Traversal_', '').replace('M_Relaxed_Traversal_', '')
            for col, name in enumerate((baseline_name, candidate_name)):
                x, y = col*600, 76+row*260
                draw.rectangle((x+8, y+2, x+592, y+254), fill='white', outline='#dce2eb')
                predicted = arrays[key+'_'+name][index]
                error = np.sqrt(np.mean(np.sum((predicted-source[index])**2, axis=-1)))
                draw.text((x+20, y+9), title, fill='#15253d', font=font)
                draw.text((x+20, y+32), f'{name} | source frame {index+clip["source_interval"][0]} | RMSE {error:.2f} cm', fill='#45546b', font=small)
                origin = source[index, 0]
                # 固定比例与相机；共享源骨盆中心保留重建骨盆偏差。
                for view, (ax, ay) in enumerate(((1., 0.), (.55, .835))):
                    for pose, color in ((source[index], '#2682c4'), (predicted, '#e77824')):
                        p = pose-origin
                        xy = np.stack([p[:, 0]*ax+p[:, 1]*ay, -p[:, 2]], axis=-1)*.8
                        xy += [x+170+view*270, y+150]
                        for a, b in edges:
                            draw.line([tuple(xy[a]), tuple(xy[b])], fill=color, width=2)
                    draw.text((x+130+view*270, y+232), 'side' if view == 0 else 'oblique', fill='#62728b', font=small)
        return canvas
    frame_image().save(report_path.with_name(prefix+'_traversal_peaks.png'))
    video = report_path.with_name(prefix+'_traversal_comparison.mp4')
    command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', '30', '-i', '-', '-an', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        count = max(len(arrays[key+'_source']) for key, _ in selected)
        for _ in range(3):
            for tick in range(count+15):
                process.stdin.write(frame_image(tick).tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError('ffmpeg failed')
    print(video)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report')
    parser.add_argument('--baseline',default='endpoints2')
    parser.add_argument('--candidate',default='targeted4')
    parser.add_argument('--prefix',default='targeted')
    args=parser.parse_args()
    render(args.report,args.baseline,args.candidate,args.prefix)
