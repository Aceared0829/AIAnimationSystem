"""合并原生帧率评估结果为单文件 HTML，播放严格使用源时间戳。"""
import argparse
import json
import gzip
import base64
import html as html_module
from collections import defaultdict
from pathlib import Path


TEMPLATE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIAnimationSystem · 原生时间训练验收</title><style>
:root{color-scheme:dark;font-family:Inter,"Microsoft YaHei",sans-serif;background:#0c111b;color:#e2eaf5}*{box-sizing:border-box}body{margin:0}main{max-width:1380px;margin:auto;padding:38px 28px}h1{font-size:34px;margin:8px 0 14px;letter-spacing:-1px}p{line-height:1.8;color:#aab9ce}small,.muted{color:#92a6c0}.eyebrow{font-size:12px;letter-spacing:3px;color:#65d7be}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:26px 0}.stat,.panel{background:#141e2e;border:1px solid #29384e;border-radius:14px;padding:19px}.stat strong{display:block;font-size:27px;color:#ecf5ff;margin:8px 0}.panel{margin:18px 0}button,select,input{accent-color:#65d7be}button,select{background:#1c2b41;color:#eef4fc;border:1px solid #3c506c;border-radius:8px;padding:10px;cursor:pointer}button:hover{border-color:#65d7be}button.active{background:#264d4a}select{max-width:100%}.controls{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin:16px 0}.views{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.view{background:#0c1523;border-radius:12px;overflow:hidden}.view h3{font-size:14px;padding:15px 15px 0;margin:0}.view p{font-size:13px;padding:0 15px;margin:8px 0}canvas{width:100%;height:390px;display:block}.tag{display:inline-block;padding:4px 9px;background:#26364d;border-radius:6px;font-size:12px;margin:3px}.timeline{width:100%}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px;border-bottom:1px solid #29384e}th{color:#92a6c0;font-weight:400}.good{color:#65d7be}.bad{color:#f3ad83}.catalog{display:flex;gap:8px;flex-wrap:wrap}.footer{font-size:13px;border-top:1px solid #29384e;padding-top:18px;overflow-wrap:anywhere}details{margin:16px 0}summary{cursor:pointer;color:#b9d0ec}@media(max-width:850px){.stats{grid-template-columns:repeat(2,1fr)}.views{grid-template-columns:1fr}canvas{height:320px}main{padding:24px 14px}h1{font-size:27px}}
</style><main><div class="eyebrow">AIANIMATIONSYSTEM / NATIVE-TIME QUALITY REVIEW</div><h1>训练完成，用原生节奏看动作</h1>
<p>每段动画保留原生 30 / 60 FPS、逐帧时间与原始时长。下方对照使用同一源动作、同一时刻与同一相机；可切换骨盆对齐视图和真实位移视图。</p>
<div class="stats" id="stats"></div><div class="panel"><h2 style="font-size:20px;margin:0">动作对照</h2><div class="controls"><select id="clip"></select><span id="tags"></span></div>
<div class="catalog" id="catalog"></div><div class="controls"><button id="play">暂停</button><label>速度 <select id="speed"><option value="1">1× 原速</option><option value="0.5">0.5×</option><option value="0.25">0.25×</option></select></label><label>视图 <select id="align"><option value="pose">骨盆对齐 · 看姿态</option><option value="world">原始位移 · 看轨迹</option></select></label><label>新模型条件 <select id="condition"><option value="pred">无姿态关键帧</option><option value="first">首帧姿态</option><option value="ends">首尾姿态</option></select></label><label>相机 <input id="yaw" type="range" min="-180" max="180" value="-30"></label></div>
<div class="views"><div class="view"><h3>源动画 · UE 原始采样</h3><p>源位置作为参考，保留辅助骨平移</p><canvas id="ref"></canvas></div><div class="view"><h3 id="oldTitle">旧模型 · 5,000 步</h3><p id="oldMetric"></p><canvas id="old"></canvas></div><div class="view"><h3>新模型 · 原生时间 + 几何监督</h3><p id="newMetric"></p><canvas id="pred"></canvas></div></div><div class="controls"><span id="time"></span></div><input id="timeline" class="timeline" type="range" min="0" max="1" step="0.0001" value="0"><p id="asset" style="font-size:12px;overflow-wrap:anywhere"></p></div>
<div class="panel"><h2 style="font-size:20px">完整评估集合的结果</h2><p>下表为每段动作指标的等权平均。姿态误差先按骨盆对齐；世界位置误差保留位移与高度。旧模型见过此前全部资产，不能将其称为独立测试成绩。</p><div style="overflow:auto"><table id="results"></table></div></div>
<div class="panel"><h2 style="font-size:20px">这轮做了什么</h2><p>源采样率导出与逐帧时间戳；30 / 60 FPS 分组训练；按资产名称家族划分留出集；统计量只读取训练真实帧；短片段补齐帧不参与重建和运动监督；按类别适度平衡采样；增加姿态、骨盆、脚部、速度与参考接触约束。</p><p>60 FPS 仅有 6 段，单独训练 1,500 步，全部用于训练重建验证。30 FPS 主模型从头训练 20,000 步，使用新数据统计量，没有继承见过测试资产的旧权重。</p><details><summary>评估边界与仍然存在的问题</summary><p>本页面展示 VQ 编码器对已知输入动画的压缩重建；没有证明文字生成、动作混合或 UE 蒙皮角色的最终质量。已有语义标签可检索，但此次 VQ 训练不使用文本条件。姿态关键帧会提供真实参考信息；无关键帧结果是主对照。</p><p>模型根节点是骨盆；UE root、曲线、事件、additive 不在当前输出范围。固定骨长 FK 无法完整表达某些辅助骨平移，表示误差在报告中单列。划分采用资产名称家族规则，缺少原始录制 ID，不能保证录制级无泄漏。原生源资产始终保留。</p></details></div><div class="footer" id="footer"></div></main>
<script>const DATA=__PAYLOAD__;
const $=id=>document.getElementById(id);const clips=DATA.flatMap(d=>d.previews.map(p=>({...p,parents:d.parents})));let index=0,t=0,playing=true,last=performance.now();
const n=v=>Number(v).toFixed(2);const main=DATA.find(d=>d.report.fps===30);const agg=main?.report.aggregate;const improvement=agg?.old?100*(1-agg.new.pose_rmse_cm/agg.old.pose_rmse_cm):null;
$('stats').innerHTML=[['原生数据','1,728 段','1,722 × 30 FPS / 6 × 60 FPS'],['主模型训练','20,000 步','从头训练 · RTX 4070 Laptop'],['30 FPS 测试姿态误差',agg?n(agg.new.pose_rmse_cm)+' cm':'—','骨盆对齐 · '+(main?.report.sample_count||0)+' 段'],['相对旧模型',improvement===null?'—':n(Math.abs(improvement))+'% '+(improvement>=0?'降低':'增加'),'同源同时间对照 · 非单因素消融']].map(s=>`<div class="stat"><small>${s[0]}</small><strong>${s[1]}</strong><small>${s[2]}</small></div>`).join('');
clips.forEach((p,i)=>{let option=document.createElement('option');option.value=i;option.textContent=`${p.fps} FPS · ${p.category} · ${p.name}`;$('clip').append(option);let b=document.createElement('button');b.textContent=`${p.category} ${p.fps}`;b.onclick=()=>select(i);$('catalog').append(b)});
function select(i){index=+i;t=0;$('clip').value=i;[...$('catalog').children].forEach((b,j)=>b.classList.toggle('active',j===index));const p=clips[index];$('tags').textContent=`${p.fps} FPS · ${p.ref.length} 帧 · ${p.time.at(-1).toFixed(3)} 秒 · ${p.split}`;$('asset').textContent=p.scores.asset;$('oldTitle').textContent=p.old?'旧模型 · 5,000 步':'60 FPS · 无同帧率旧模型';updateMetrics()}
function updateMetrics(){const p=clips[index],mode=$('condition').value,m=mode==='pred'?p.scores.new:p.scores[mode];$('newMetric').textContent=`姿态 ${n(m.pose_rmse_cm)} cm · 世界位置 ${n(m.world_rmse_cm)} cm`;$('oldMetric').textContent=p.old?`姿态 ${n(p.scores.old.pose_rmse_cm)} cm · 世界位置 ${n(p.scores.old.world_rmse_cm)} cm`:'保留原生 60 FPS，不套用 30 FPS 模型';}
$('clip').onchange=e=>select(e.target.value);$('condition').onchange=updateMetrics;$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'暂停':'播放'};$('timeline').oninput=e=>t=+e.target.value*clips[index].time.at(-1);
function draw(id,arr,frame,p,color){const c=$(id),r=c.getBoundingClientRect(),ratio=devicePixelRatio||1;if(c.width!==Math.round(r.width*ratio)||c.height!==Math.round(r.height*ratio)){c.width=r.width*ratio;c.height=r.height*ratio}const ctx=c.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,r.width,r.height);if(!arr){ctx.fillStyle='#92a6c0';ctx.font='14px sans-serif';ctx.fillText('无同帧率旧模型对照',30,r.height/2);return}const pose=$('align').value==='pose',angle=+$('yaw').value*Math.PI/180;let center=pose?arr[frame][0]:p.ref[frame][0];let scale=pose?Math.min(r.width/2.5,r.height/2.8):Math.min(r.width/4,r.height/4);const project=a=>{let x=a[0]-center[0],y=a[1]-center[1],z=a[2]-center[2];return[r.width/2+(Math.cos(angle)*x+Math.sin(angle)*z)*scale,r.height*.52-y*scale+(Math.cos(angle)*z-Math.sin(angle)*x)*scale*.2]};
ctx.strokeStyle='#20314a';ctx.lineWidth=1;for(let g=-3;g<=3;g++){let a=project([center[0]+g,pose?center[1]-1:0,center[2]-3]),b=project([center[0]+g,pose?center[1]-1:0,center[2]+3]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke()}
if(!pose){ctx.strokeStyle=color+'66';ctx.beginPath();arr.forEach((f,j)=>{let a=project(f[0]);j?ctx.lineTo(...a):ctx.moveTo(...a)});ctx.stroke()}ctx.strokeStyle=color;ctx.lineWidth=2;arr[frame].forEach((a,j)=>{let parent=p.parents[j];if(parent<0)return;ctx.beginPath();ctx.moveTo(...project(a));ctx.lineTo(...project(arr[frame][parent]));ctx.stroke()});ctx.fillStyle=color;arr[frame].forEach(a=>{ctx.beginPath();ctx.arc(...project(a),2,0,Math.PI*2);ctx.fill()})}
function tick(now){let p=clips[index];if(playing)t+=(now-last)/1000*+$('speed').value;last=now;const duration=p.time.at(-1);if(t>duration)t=0;let frame=0;while(frame+1<p.time.length&&p.time[frame+1]<=t)frame++;draw('ref',p.ref,frame,p,'#70acff');draw('old',p.old,frame,p,'#e4ae70');draw('pred',p[$('condition').value],frame,p,'#65d7be');$('timeline').value=t/duration;$('time').textContent=`${t.toFixed(3)} / ${duration.toFixed(3)} 秒 · 第 ${frame+1} / ${p.ref.length} 帧` ;requestAnimationFrame(tick)}
let table='<tr><th>数据 / 模型</th><th>段数</th><th>姿态 RMSE</th><th>世界位置 RMSE</th><th>水平根误差</th><th>根高度误差</th></tr>';for(const d of DATA){for(const key of ['old','new','representation_fk','representation_positions']){const a=d.report.aggregate[key];if(!a)continue;const label={old:'旧模型',new:'新模型',representation_fk:'源特征 → 固定骨长 FK',representation_positions:'源特征 → 位置还原'}[key];table+=`<tr><td>${d.report.fps} FPS ${d.report.split} · ${label}</td><td>${d.report.sample_count}</td><td>${n(a.pose_rmse_cm)} cm</td><td>${n(a.world_rmse_cm)} cm</td><td>${n(a.root_horizontal_cm)} cm</td><td>${n(a.root_height_cm)} cm</td></tr>`}}$('results').innerHTML=table;$('footer').textContent='本地单文件 · 无外部依赖 · 所有播放帧均嵌入。模型：'+DATA.map(d=>d.report.checkpoint).join(' | ');select(0);requestAnimationFrame(tick);
</script></html>'''


def export(inputs, output):
    data = [json.loads(Path(p).read_text(encoding="utf8")) for p in inputs]
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    compressed = base64.b64encode(gzip.compress(payload.encode("utf8"), compresslevel=6)).decode("ascii")
    decoder = ('JSON.parse(await new Response(new Blob([Uint8Array.from(atob("' + compressed
               + '"),c=>c.charCodeAt(0))]).stream().pipeThrough(new DecompressionStream("gzip"))).text())')
    html = TEMPLATE.replace("__PAYLOAD__", decoder).replace("<script>", '<script type="module">')
    html = html.replace("'60 FPS · 无同帧率旧模型'", "'参考特征 → FK · 非训练模型'")
    html = html.replace("'保留原生 60 FPS，不套用 30 FPS 模型'", "`固定骨长表示误差 ${n(p.scores.representation_fk.pose_rmse_cm)} cm`")
    html = html.replace("draw('old',p.old,frame,p", "draw('old',p.old||p.fk,frame,p")
    html = html.replace("select(0);requestAnimationFrame(tick)", "select(Math.max(0,clips.findIndex(p=>p.fps===30&&p.category==='Walk')));requestAnimationFrame(tick)")
    html = html.replace("<div class=\"stats\"", "<p>本批次原生采样审计：修复 810 段动画缺失末帧的问题，并为 6 段 60 FPS 动画补回 732 个原生采样帧，共恢复 1,542 帧。结束时刻与源时长的最大差异小于 0.000001 秒。</p><div class=\"stats\"")
    main = next((d for d in data if d["report"]["fps"] == 30), None)
    if main:
        baseline_steps = main["report"].get("baseline_steps") or 5000
        html = html.replace("旧模型 · 5,000 步", f"上一轮 · {baseline_steps:,} 步")
        if main["report"].get("pose_aware_sampling"):
            html = html.replace("训练完成，用原生节奏看动作", "相同步数、相同模型，检查姿态优化")
            html = html.replace("旧模型见过此前全部资产，不能将其称为独立测试成绩。", "本页新旧 30 FPS 模型使用相同训练/验证/测试划分，均从头训练 20,000 步；均未训练这 178 段测试动作。")
            html = html.replace("旧模型见过此前全部资产，其对照不能解释为独立测试成绩。", "两轮模型均使用相同留出集。")
            html = html.replace("新模型 · 原生时间 + 几何监督", "本轮 · 短姿态与困难动作采样")
            html = html.replace("<div class=\"footer\"", '<div class="panel"><h2>本轮保持轻量的方式</h2><p>参数规模保持约 2,540 万，网络与码本未扩容，两轮均为 20,000 步。新增长度分桶，短姿态窗口最多补齐 3 帧；Ragdoll、交互和翻越类别提高采样权重。沿用原生帧率、有效帧掩码和几何监督。</p><p>完整 FP32 推理状态约 102 MB；只保留码本和解码器约 54 MB，后者需要兼容 token 输入。均不包含优化器状态，不是完整文字生成系统。60 FPS 沿用上轮 1,500 步模型，本轮没有重训。</p></div><div class="footer"')
        samples = main["report"]["samples"]
        groups = defaultdict(list)
        for sample in samples:
            groups[sample["category"]].append(sample)
        rows = []
        for category, items in sorted(groups.items()):
            new = sum(s["new"]["pose_rmse_cm"] for s in items) / len(items)
            old = sum(s["old"]["pose_rmse_cm"] for s in items) / len(items) if all("old" in s for s in items) else None
            old_text = f"{old:.2f} cm" if old is not None else "—"
            rows.append(f"<tr><td>{html_module.escape(category)}</td><td>{len(items)}</td><td>{old_text}</td><td>{new:.2f} cm</td></tr>")
        worsened = sum(s["new"]["pose_rmse_cm"] > s["old"]["pose_rmse_cm"] for s in samples if "old" in s)
        if main["report"].get("pose_aware_sampling"):
            notice = (f'<div class="panel"><h2 class="bad">实验结论：短姿态改善，常规动作存在退步</h2>'
                      f'<p>{len(samples)} 段中有 {worsened} 段姿态误差上升。整体均值下降主要来自少数困难短姿态；走、跑、蹲类平均误差有所增加。'
                      '本轮作为短姿态实验版本，保留上一轮作为通用基线，不据此直接替换。下方可查看全部类别指标及误差较大的动作。</p></div>')
            html = html.replace('<div class="stats" id="stats"></div>', '<div class="stats" id="stats"></div>' + notice)
        worst = "".join(f"<li>{html_module.escape(s['asset'].split('/')[-1].split('.')[0])}：{s['new']['pose_rmse_cm']:.2f} cm</li>"
                        for s in sorted(samples, key=lambda s: s["new"]["pose_rmse_cm"], reverse=True)[:5])
        panel = ('<div class="panel"><h2 style="font-size:20px">各类动作的姿态误差</h2>'
                 f'<p>误差为骨盆对齐后的每段平均。{len(samples)} 段中有 {worsened} 段的姿态误差高于旧模型；整体改善并不表示每段都更好。</p>'
                 '<table><tr><th>类别</th><th>段数</th><th>旧模型</th><th>新模型</th></tr>' + "".join(rows) + '</table>'
                 '<details><summary>当前误差最大的 5 段</summary><ul>' + worst + '</ul></details></div>')
        html = html.replace('<div class="panel"><h2 style="font-size:20px">这轮做了什么', panel + '<div class="panel"><h2 style="font-size:20px">这轮做了什么')
        if main["report"].get("pose_aware_sampling"):
            html = html.replace("这轮做了什么", "沿用的数据与评估基础")
            html = html.replace("使用新数据统计量，没有继承见过测试资产的旧权重", "沿用上一轮的训练集统计量，没有继承上一轮权重")
            length_rows = []
            for label, low, high in [("极短：不超过 16 帧", 0, 16), ("较短：17–64 帧", 17, 64), ("较长：超过 64 帧", 65, float("inf"))]:
                subset = [s for s in samples if low <= s["frames"] <= high]
                if subset:
                    old_mean = sum(s["old"]["pose_rmse_cm"] for s in subset) / len(subset)
                    new_mean = sum(s["new"]["pose_rmse_cm"] for s in subset) / len(subset)
                    length_rows.append(f"<tr><td>{label}</td><td>{len(subset)}</td><td>{old_mean:.2f} cm</td><td>{new_mean:.2f} cm</td></tr>")
            length_panel = '<div class="panel"><h2>短姿态是否改善</h2><p>下列三个分组互不重叠。样本数较少的分组仅能说明这批动作，不能保证同类动作都能改善。</p><table><tr><th>原生长度</th><th>段数</th><th>上一轮</th><th>本轮</th></tr>' + ''.join(length_rows) + '</table></div>'
            html = html.replace('<div class="footer"', length_panel + '<div class="footer"')
        profile = main["report"].get("resource_profile")
        if profile:
            resource_rows = []
            for row in profile["results"]:
                label = "完整编码与解码" if row["mode"] == "encoder_decoder" else "仅解码（需要 token）"
                resource_rows.append(f"<tr><td>{label}</td><td>{row['frames']} 帧</td><td>{row['median_ms']:.2f} ms</td><td>{row['p95_ms']:.2f} ms</td><td>{row['peak_allocated_bytes']/1024**2:.1f} MiB</td></tr>")
            resources = '<div class="panel"><h2>实际推理资源测量</h2><p>FP32、单流、batch=1。只测神经网络前向，不包含 UE、上游 token 生成器和姿态后处理；显存为本进程已分配张量的峰值，不是整个游戏显存。</p><table><tr><th>模式</th><th>每批长度</th><th>中位耗时</th><th>P95 耗时</th><th>张量显存峰值</th></tr>' + ''.join(resource_rows) + '</table></div>'
            html = html.replace('<div class="footer"', resources + '<div class="footer"')
    Path(output).write_text(html, encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    export(args.input, args.output)
