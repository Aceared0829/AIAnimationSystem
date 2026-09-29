"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");
const root = "E:\\AIAnimationSystemData";
const gib = 1024 ** 3;
const jobs = [
  ["BONES-SEED", path.join(root, "BONES-SEED"), 564.39 * gib],
  ["MotionDataLibrary", path.join(root, "MotionDataLibrary"), 67.56 * gib],
  ["UE export cache", path.join(root, "UE", "AILocomotionDataset"), 81.83 * gib],
  ["prepared datasets", path.join(root, "prepared"), 10.06 * gib],
];
let state = { state: "正在首次统计目标目录…", total_bytes: 0, expected_bytes: jobs.reduce((n, j) => n + j[2], 0), jobs: [], speed_bps: 0, eta_seconds: null, updated_at: null };
let samples = [];

function folderBytes(folder) {
  let total = 0;
  const stack = [folder];
  while (stack.length) {
    const current = stack.pop();
    let entries;
    try { entries = fs.readdirSync(current, { withFileTypes: true }); } catch (_) { continue; }
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      try {
        if (entry.isDirectory()) stack.push(full);
        else if (entry.isFile()) total += fs.statSync(full).size;
      } catch (_) {}
    }
  }
  return total;
}

function scan() {
  const result = jobs.map(([name, folder, expected]) => {
    const copied = folderBytes(folder);
    return { name, copied_bytes: copied, expected_bytes: expected, percent: Math.min(100, copied * 100 / expected) };
  });
  const total = result.reduce((n, job) => n + job.copied_bytes, 0);
  const now = Date.now() / 1000;
  samples = samples.filter(([stamp]) => now - stamp <= 180); samples.push([now, total]);
  let speed = 0;
  if (samples.length > 1) speed = Math.max(0, (total - samples[0][1]) / (now - samples[0][0]));
  const remaining = Math.max(0, state.expected_bytes - total);
  state = { state: "迁移中（每 60 秒采样）", total_bytes: total, expected_bytes: state.expected_bytes, jobs: result, speed_bps: speed, eta_seconds: speed ? remaining / speed : null, updated_at: now };
}

const html = `<!doctype html><meta charset="utf-8"><title>AI Animation System · E盘迁移</title><style>body{font:16px system-ui;background:#10151d;color:#e8eef7;margin:0;padding:34px;max-width:950px}.card{background:#192330;border-radius:12px;padding:18px;margin:16px 0}.bar{height:14px;background:#0b1016;border-radius:9px;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,#49c3ff,#7fdf9d)}.row{display:flex;justify-content:space-between;gap:16px;margin:12px 0 7px}.big{font-size:28px;font-weight:700}small,#status{color:#9aabba}</style><h1>AI Animation System · E盘迁移</h1><div id=status>连接中…</div><div class=card><div class=big id=total>—</div><div class=bar><i id=overall style="width:0"></i></div><div id=meta></div></div><div id=jobs></div><script>const gb=n=>(n/1073741824).toFixed(2)+' GiB',time=s=>s==null?'统计中':s>86400?(s/86400).toFixed(1)+' 天':s>3600?(s/3600).toFixed(1)+' 小时':Math.ceil(s/60)+' 分钟';async function r(){try{let d=await(await fetch('/api')).json(),p=Math.min(100,d.total_bytes*100/d.expected_bytes);total.textContent=p.toFixed(2)+'% · '+gb(d.total_bytes)+' / '+gb(d.expected_bytes);overall.style.width=p+'%';meta.textContent='速度：'+(d.speed_bps?gb(d.speed_bps)+' / 秒':'等待两次采样')+'　预计剩余：'+time(d.eta_seconds);status.textContent=d.state+'　上次更新：'+(d.updated_at?new Date(d.updated_at*1000).toLocaleString():'—');jobs.innerHTML=d.jobs.map(j=>'<div class=card><div class=row><span>'+j.name+'</span><b>'+j.percent.toFixed(2)+'%</b></div><div class=bar><i style="width:'+j.percent+'%"></i></div><small>'+gb(j.copied_bytes)+' / '+gb(j.expected_bytes)+'</small></div>').join('')}catch(e){status.textContent='暂时无法读取服务：'+e}}r();setInterval(r,5000)</script>`;
http.createServer((req, res) => { const body = req.url === "/api" ? JSON.stringify(state) : html; res.writeHead(200, { "Content-Type": req.url === "/api" ? "application/json; charset=utf-8" : "text/html; charset=utf-8" }); res.end(body); }).listen(8767, "127.0.0.1");
setTimeout(scan, 1); setInterval(scan, 60000);
