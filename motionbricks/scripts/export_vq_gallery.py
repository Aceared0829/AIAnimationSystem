"""把一批 UE VQ-VAE 重建预览导出为可离线打开的单文件 HTML。"""

import argparse
import base64
import html
import json
from pathlib import Path


def gif_data_url(path):
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/gif;base64,{encoded}"


def main(args):
    report_path = Path(args.report).resolve()
    source = report_path.parent
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cards = []
    for sample in report["samples"]:
        labels = sample["labels"]
        preview = source / sample["preview"]
        cards.append(f'''<article class="card">
  <img src="{gif_data_url(preview)}" alt="{html.escape(labels['description_zh'])}">
  <div class="body"><h2>{html.escape(labels['description_zh'])}</h2>
  <p>{html.escape(' · '.join(labels['tags']))}</p>
  <dl><div><dt>位置 RMSE</dt><dd>{sample['position_rmse_m']:.3f} m</dd></div>
      <div><dt>旋转平均误差</dt><dd>{sample['rotation_mean_deg']:.1f}°</dd></div></dl></div>
</article>''')
    aggregate = report["aggregate"]
    document = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AIAnimationSystem · VQ 动画训练效果</title><style>
:root {{ color-scheme: dark; --ink:#edf3fa; --muted:#a4b2c4; --card:#152235; --line:#2a405d; --blue:#2d74da; --orange:#e87b22; }}
* {{ box-sizing:border-box }} body {{ margin:0; font-family:"Microsoft YaHei",system-ui,sans-serif; background:#09111d; color:var(--ink) }}
header {{ padding:52px max(28px,calc((100vw - 1280px)/2)); background:linear-gradient(120deg,#102844,#17263b) }}
h1 {{ margin:0 0 12px; font-size:clamp(28px,5vw,46px) }} header p {{ max-width:800px; color:var(--muted); line-height:1.7 }}
.metrics,.grid {{ max-width:1280px; margin:28px auto; padding:0 28px; display:grid; gap:16px }}
.metrics {{ grid-template-columns:repeat(4,minmax(0,1fr)) }} .metric,.card {{ background:var(--card); border:1px solid var(--line); border-radius:16px }}
.metric {{ padding:20px }} .metric small,.card p,dt {{ color:var(--muted) }} .metric strong {{ display:block; font-size:26px; margin-top:7px }}
.legend {{ max-width:1280px; margin:0 auto 28px; padding:0 28px; color:var(--muted) }} .blue {{ color:var(--blue) }} .orange {{ color:var(--orange) }}
.grid {{ grid-template-columns:repeat(auto-fit,minmax(340px,1fr)) }} .card {{ overflow:hidden }} img {{ width:100%; display:block; background:#fff }} .body {{ padding:16px }} h2 {{ font-size:18px; margin:0 0 8px }}
dl {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:16px 0 0 }} dl div {{ padding:10px; background:#0f1a2a; border-radius:10px }} dt {{ font-size:12px }} dd {{ margin:4px 0 0; font-weight:700 }}
footer {{ max-width:1280px; margin:38px auto; padding:0 28px 42px; color:var(--muted); line-height:1.7 }}
@media (max-width:700px) {{ .metrics {{ grid-template-columns:1fr 1fr }} }}
</style></head><body><header><h1>VQ 动画训练效果 · 批量预览</h1>
<p>每张卡片左侧蓝色骨架是训练特征经过固定骨长 FK 还原的参考，右侧橙色骨架是 VQ-VAE 的无姿态关键帧重建。两边按根节点对齐；该旧版预览不是未经表示转换的 Unreal 原始采样。</p></header>
<section class="metrics"><div class="metric"><small>样本数量</small><strong>{len(report['samples'])}</strong></div><div class="metric"><small>平均位置 RMSE</small><strong>{aggregate['position_rmse_m']:.3f} m</strong></div><div class="metric"><small>平均旋转误差</small><strong>{aggregate['rotation_mean_deg']:.1f}°</strong></div><div class="metric"><small>平均根轨迹 RMSE</small><strong>{aggregate['root_path_rmse_m']:.3f} m</strong></div></section>
<p class="legend"><span class="blue">蓝色：特征 FK 参考</span>　<span class="orange">橙色：训练后 VQ 重建</span></p><main class="grid">{''.join(cards)}</main>
<footer>这是选定特征窗口的重建质量预览，不等同于文字生成或 Unreal 运行时最终画面。GIF 时间精度受格式限制；完整原生时间和源位置对照请使用 evaluate_native_quality.py 与 export_native_gallery.py。</footer></body></html>'''
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"已导出 {output}，大小 {output.stat().st_size / 1024:.1f} KiB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    main(parser.parse_args())
