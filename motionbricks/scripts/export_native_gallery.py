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
<p>每段动画保留原生帧率、逐帧时间和独立权威 Root 轨道。骨盆对齐视图跟随角色观察姿态；权威轨迹视图固定取景，显示 Root 与相对姿态重新合成后的实际移动。</p>
<div class="stats" id="stats"></div><div class="panel"><h2 style="font-size:20px;margin:0">动作对照</h2><div class="controls"><select id="clip"></select><span id="tags"></span></div>
<div class="catalog" id="catalog"></div><div class="controls"><button id="play">暂停</button><label>速度 <select id="speed"><option value="1">1× 原速</option><option value="0.5">0.5×</option><option value="0.25">0.25×</option></select></label><label>视图 <select id="align"><option value="world">权威 Root · 固定全轨迹</option><option value="pose">骨盆对齐 · 看姿态</option></select></label><label>新模型条件 <select id="condition"><option value="pred">无姿态关键帧</option><option value="first">首帧姿态</option><option value="ends">首尾姿态</option></select></label><label>相机 <input id="yaw" type="range" min="-180" max="180" value="-30"></label></div>
<div class="views"><div class="view"><h3>源动画 · UE 原始采样</h3><p>源位置作为参考，保留辅助骨平移</p><canvas id="ref"></canvas></div><div class="view"><h3 id="oldTitle">旧模型 · 5,000 步</h3><p id="oldMetric"></p><canvas id="old"></canvas></div><div class="view"><h3>新模型 · 原生时间 + 几何监督</h3><p id="newMetric"></p><canvas id="pred"></canvas></div></div><div class="controls"><span id="time"></span></div><input id="timeline" class="timeline" type="range" min="0" max="1" step="0.0001" value="0"><p id="asset" style="font-size:12px;overflow-wrap:anywhere"></p></div>
<div class="panel"><h2 style="font-size:20px">完整评估集合的结果</h2><p>下表为每段动作指标的等权平均。姿态误差先按骨盆对齐；世界位置误差保留位移与高度。对照是否使用相同训练分区，以输入报告中的限制说明为准。</p><div style="overflow:auto"><table id="results"></table></div></div>
<div class="panel"><h2 style="font-size:20px">这轮做了什么</h2><p>源采样率导出与逐帧时间戳；30 / 60 FPS 分组训练；按资产名称家族划分留出集；统计量只读取训练真实帧；短片段补齐帧不参与重建和运动监督；按类别适度平衡采样；增加姿态、骨盆、脚部、速度与参考接触约束。</p><details><summary>评估边界与仍然存在的问题</summary><p>本页面展示 VQ 编码器对已知输入动画的压缩重建；没有证明文字生成、动作混合或 UE 蒙皮角色的最终质量。已有语义标签可检索，但此次 VQ 训练不使用文本条件。姿态关键帧会提供真实参考信息；无关键帧结果是主对照。</p><p>模型根节点是骨盆；UE root、曲线、事件、additive 不在当前输出范围。固定骨长 FK 无法完整表达某些辅助骨平移，表示误差在报告中单列。划分采用资产名称家族规则，缺少原始录制 ID，不能保证录制级无泄漏。原生源资产始终保留。</p></details></div><div class="footer" id="footer"></div></main>
<script>const DATA=__PAYLOAD__;
const $=id=>document.getElementById(id);const clips=DATA.flatMap(d=>d.previews.map(p=>({...p,parents:d.parents,baselineSteps:d.report.baseline_steps})));let index=0,t=0,playing=true,last=performance.now();
const n=v=>Number(v).toFixed(2);const main=DATA.find(d=>d.report.fps===30)||DATA[0];const agg=main?.report.aggregate;const improvement=agg?.old?100*(1-agg.new.pose_rmse_cm/agg.old.pose_rmse_cm):null;
$('stats').innerHTML=[['评估动作',DATA.reduce((s,d)=>s+d.report.sample_count,0)+' 段',DATA.map(d=>d.report.fps+' FPS / '+d.report.split).join(' · ')],['模型训练',main.report.training_steps==null?'未记录':main.report.training_steps.toLocaleString()+' 步','以输入检查点记录为准'],['姿态误差',agg?.new?n(agg.new.pose_rmse_cm)+' cm':'—','骨盆对齐 · '+main.report.fps+' FPS'],['相对旧模型',improvement===null?'无基线':n(Math.abs(improvement))+'% '+(improvement>=0?'降低':'增加'),'每段等权平均，不代表所有动作改善']].map(s=>`<div class="stat"><small>${s[0]}</small><strong>${s[1]}</strong><small>${s[2]}</small></div>`).join('');
clips.forEach((p,i)=>{let option=document.createElement('option');option.value=i;option.textContent=`${p.fps} FPS · ${p.category} · ${p.name}`;$('clip').append(option);let b=document.createElement('button');b.textContent=`${p.category} ${p.fps}`;b.onclick=()=>select(i);$('catalog').append(b)});
function select(i){index=+i;t=0;$('clip').value=i;[...$('catalog').children].forEach((b,j)=>b.classList.toggle('active',j===index));const p=clips[index];$('tags').textContent=`${p.fps} FPS · ${p.ref.length} 帧 · ${p.time.at(-1).toFixed(3)} 秒 · ${p.split}`;$('asset').textContent=p.scores.asset;$('oldTitle').textContent=p.old?'旧模型 · '+(p.baselineSteps==null?'步数未记录':p.baselineSteps.toLocaleString()+' 步'):'参考特征 → FK · 非训练模型';updateMetrics()}
function updateMetrics(){const p=clips[index],mode=$('condition').value,m=mode==='pred'?p.scores.new:p.scores[mode];$('newMetric').textContent=`姿态 ${n(m.pose_rmse_cm)} cm · 世界位置 ${n(m.world_rmse_cm)} cm`;$('oldMetric').textContent=p.old?`姿态 ${n(p.scores.old.pose_rmse_cm)} cm · 世界位置 ${n(p.scores.old.world_rmse_cm)} cm`:`固定骨长表示误差 ${n(p.scores.representation_fk.pose_rmse_cm)} cm`;}
$('clip').onchange=e=>select(e.target.value);$('condition').onchange=updateMetrics;$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'暂停':'播放'};$('timeline').oninput=e=>t=+e.target.value*clips[index].time.at(-1);
function draw(id,arr,frame,p,color){const c=$(id),r=c.getBoundingClientRect(),ratio=devicePixelRatio||1;if(c.width!==Math.round(r.width*ratio)||c.height!==Math.round(r.height*ratio)){c.width=r.width*ratio;c.height=r.height*ratio}const ctx=c.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,r.width,r.height);if(!arr){ctx.fillStyle='#92a6c0';ctx.font='14px sans-serif';ctx.fillText('无同帧率旧模型对照',30,r.height/2);return}const pose=$('align').value==='pose',angle=+$('yaw').value*Math.PI/180;const roots=p.ref.map(f=>f[0]),xs=roots.map(a=>Math.cos(angle)*a[0]+Math.sin(angle)*a[2]),zs=roots.map(a=>Math.cos(angle)*a[2]-Math.sin(angle)*a[0]),rx=roots.map(a=>a[0]),rz=roots.map(a=>a[2]);const span=Math.max(2,Math.max(...xs)-Math.min(...xs),Math.max(...zs)-Math.min(...zs));let center=pose?arr[frame][0]:[(Math.min(...rx)+Math.max(...rx))/2,roots[0][1],(Math.min(...rz)+Math.max(...rz))/2];let scale=pose?Math.min(r.width/2.5,r.height/2.8):Math.min(r.width/(span+2),r.height/3);const project=a=>{let x=a[0]-center[0],y=a[1]-center[1],z=a[2]-center[2];return[r.width/2+(Math.cos(angle)*x+Math.sin(angle)*z)*scale,r.height*.52-y*scale+(Math.cos(angle)*z-Math.sin(angle)*x)*scale*.2]};
ctx.strokeStyle='#20314a';ctx.lineWidth=1;for(let g=-3;g<=3;g++){let a=project([center[0]+g,pose?center[1]-1:0,center[2]-3]),b=project([center[0]+g,pose?center[1]-1:0,center[2]+3]);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke()}
if(!pose){ctx.strokeStyle=color+'66';ctx.beginPath();arr.forEach((f,j)=>{let a=project(f[0]);j?ctx.lineTo(...a):ctx.moveTo(...a)});ctx.stroke()}ctx.strokeStyle=color;ctx.lineWidth=2;arr[frame].forEach((a,j)=>{let parent=p.parents[j];if(parent<0)return;ctx.beginPath();ctx.moveTo(...project(a));ctx.lineTo(...project(arr[frame][parent]));ctx.stroke()});ctx.fillStyle=color;arr[frame].forEach(a=>{ctx.beginPath();ctx.arc(...project(a),2,0,Math.PI*2);ctx.fill()})}
function tick(now){let p=clips[index];if(playing)t+=(now-last)/1000*+$('speed').value;last=now;const duration=p.time.at(-1);if(t>duration)t=0;let frame=0;while(frame+1<p.time.length&&p.time[frame+1]<=t)frame++;draw('ref',p.ref,frame,p,'#70acff');draw('old',p.old||p.fk,frame,p,'#e4ae70');draw('pred',p[$('condition').value],frame,p,'#65d7be');$('timeline').value=t/duration;$('time').textContent=`${t.toFixed(3)} / ${duration.toFixed(3)} 秒 · 第 ${frame+1} / ${p.ref.length} 帧` ;requestAnimationFrame(tick)}
let table='<tr><th>数据 / 模型</th><th>段数</th><th>姿态 RMSE</th><th>世界位置 RMSE</th><th>水平根误差</th><th>根高度误差</th></tr>';for(const d of DATA){for(const key of ['old','new','representation_fk','representation_positions']){const a=d.report.aggregate[key];if(!a)continue;const label={old:'旧模型',new:'新模型',representation_fk:'源特征 → 固定骨长 FK',representation_positions:'源特征 → 位置还原'}[key];table+=`<tr><td>${d.report.fps} FPS ${d.report.split} · ${label}</td><td>${d.report.sample_count}</td><td>${n(a.pose_rmse_cm)} cm</td><td>${n(a.world_rmse_cm)} cm</td><td>${n(a.root_horizontal_cm)} cm</td><td>${n(a.root_height_cm)} cm</td></tr>`}}$('results').innerHTML=table;$('footer').textContent='本地单文件 · 无外部依赖 · 所有播放帧均嵌入。模型：'+DATA.map(d=>d.report.checkpoint).join(' | ');select(0);requestAnimationFrame(tick);
</script></html>'''


def export(inputs, output):
    data = [json.loads(Path(p).read_text(encoding="utf8")) for p in inputs]
    if not data or not any(d.get("previews") for d in data):
        raise ValueError("没有可播放的评估动作")
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    compressed = base64.b64encode(gzip.compress(payload.encode("utf8"), compresslevel=6)).decode("ascii")
    decoder = ('JSON.parse(await new Response(new Blob([Uint8Array.from(atob("' + compressed
               + '"),c=>c.charCodeAt(0))]).stream().pipeThrough(new DecompressionStream("gzip"))).text())')
    html = TEMPLATE.replace("__PAYLOAD__", decoder).replace("<script>", '<script type="module">')
    panels = []
    for dataset in data:
        report = dataset["report"]
        samples = report["samples"]
        paired = [s for s in samples if "old" in s]
        worsened = sum(s["new"]["pose_rmse_cm"] > s["old"]["pose_rmse_cm"] for s in paired)
        title = f'{report["fps"]} FPS / {html_module.escape(report["split"])}'
        if paired:
            notice = (f'<div class="panel"><h2>{title}：逐段对照</h2><p>有 {worsened} / {len(paired)} 段姿态误差上升。'
                      '均值下降不代表所有动作改善；是否替换基线，应同时检查常规动作与困难动作。</p></div>')
            html = html.replace('<div class="stats" id="stats"></div>', '<div class="stats" id="stats"></div>' + notice)
        groups = defaultdict(list)
        for sample in samples:
            groups[sample["category"]].append(sample)
        def row(label, items):
            new = sum(s["new"]["pose_rmse_cm"] for s in items) / len(items)
            old = sum(s["old"]["pose_rmse_cm"] for s in items) / len(items) if all("old" in s for s in items) else None
            old_text = f"{old:.2f} cm" if old is not None else "无基线"
            return f"<tr><td>{html_module.escape(label)}</td><td>{len(items)}</td><td>{old_text}</td><td>{new:.2f} cm</td></tr>"
        table_head = '<table><tr><th>分组</th><th>段数</th><th>旧模型</th><th>新模型</th></tr>'
        panels.append(f'<div class="panel"><h2>{title}：类别误差</h2>' + table_head
                      + "".join(row(category, items) for category, items in sorted(groups.items())) + '</table></div>')
        length_rows = []
        for label, low, high in [("极短：不超过 16 帧", 0, 16), ("较短：17–64 帧", 17, 64), ("较长：超过 64 帧", 65, float("inf"))]:
            subset = [s for s in samples if low <= s["frames"] <= high]
            if subset:
                length_rows.append(row(label, subset))
        panels.append(f'<div class="panel"><h2>{title}：长度分组</h2><p>分组互不重叠；少量样本不能代表整个动作类别。</p>'
                      + table_head + "".join(length_rows) + '</table></div>')
        limitations = "".join(f'<li>{html_module.escape(text)}</li>' for text in report.get("limitations", []))
        panels.append(f'<div class="panel"><h2>{title}：报告边界</h2><ul>{limitations}</ul></div>')
        profile = report.get("resource_profile")
        if profile:
            rows = []
            for result in profile["results"]:
                label = "完整编码与解码" if result["mode"] == "encoder_decoder" else "仅解码（需要 token）"
                rows.append(f"<tr><td>{label}</td><td>{result['frames']} 帧</td><td>{result['median_ms']:.2f} ms</td>"
                            f"<td>{result['p95_ms']:.2f} ms</td><td>{result['peak_allocated_bytes']/1024**2:.1f} MiB</td></tr>")
            panels.append('<div class="panel"><h2>实际推理资源测量</h2><p>FP32、batch=1，仅神经网络前向，'
                          '不含 UE、上游 token 生成与后处理；显存为张量分配峰值，不是整个应用显存。</p>'
                          '<table><tr><th>模式</th><th>长度</th><th>中位耗时</th><th>P95 耗时</th><th>张量显存峰值</th></tr>'
                          + "".join(rows) + '</table></div>')
    html = html.replace('<div class="footer"', "".join(panels) + '<div class="footer"')
    Path(output).write_text(html, encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    export(args.input, args.output)
