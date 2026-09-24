'use strict';
const $=id=>document.getElementById(id);
const camera={yaw:-Math.PI/4,pitch:0.28,distance:340,panX:0,panZ:0,target:[0,0,95],followRootZ:0};
let catalog,data,current,filter='all',frame=0,playing=false,loadVersion=0,last=0,hover=null;
const translate={possible_ground_penetration:'疑似穿地',bone_length_deviation:'骨长异常',heading_not_validated:'根朝向待人工核对',contacts_not_validated:'脚接触待人工核对',visual_quality_not_validated:'视觉待验收'};
const stateName={approved:'人工通过',rejected:'有问题',unsure:'待定',unreviewed:'未验收'};
const canvases=[$('source'),$('target')];
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
function normal(a){let n=Math.hypot(...a);return a.map(v=>v/n)}
function reviewPage(){return Number(new URLSearchParams(location.search).get('page')||1)}
function pageUrl(page){const url=new URL(location.href);url.searchParams.set('page',page);return url}
async function api(path,options){const url=new URL(path,location.origin);url.searchParams.set('page',reviewPage());const response=await fetch(url,options);const value=await response.json();if(!response.ok)throw Error(value.error||response.status);return value}
function visible(){return catalog.entries.filter(e=>(filter==='all'||e.group===filter)&&e.name.toLowerCase().includes($('search').value.toLowerCase()))}
function list(){const holder=$('list');holder.replaceChildren();for(const entry of visible()){const button=document.createElement('button');button.className='item'+(entry.id===current?.id?' active':'');const title=document.createElement('strong');title.textContent=entry.name;const meta=document.createElement('small');meta.className=entry.group==='issue'?'issue':'';meta.textContent=(entry.group==='issue'?'● 疑似问题':catalog.prepared_mode?'◇ 分类抽样':'◇ 固定 5% 抽样')+' · '+(stateName[catalog.decisions[entry.id]?.status]||'未验收');button.append(title,meta);button.onclick=()=>select(entry);holder.append(button)}$('progress').textContent=`已标记 ${Object.values(catalog.decisions).filter(d=>d.status!=='unreviewed').length} / ${catalog.entries.length} · 记录保存在本机`}
async function select(entry){if(current&&$('note').value!==(catalog.decisions[current.id]?.note||'')&&!confirm('当前备注尚未保存，仍要切换吗？'))return;const version=++loadVersion;current=entry;data=null;playing=false;frame=0;hover=null;$('play').textContent='▶ 播放';$('loading').classList.remove('error');$('loading').style.display='grid';$('loading').textContent='校验来源哈希并加载真实动作…';$('name').textContent=entry.name;$('description').textContent=entry.reason||'';$('group').textContent=catalog.prepared_mode?'prepared 数据 · 人工复核':catalog.exception_mode?'异常分流 · 人工筛选':'疑似问题 · 全部人工复核';$('note').value=catalog.decisions[entry.id]?.note||'';$('saved').textContent=stateName[catalog.decisions[entry.id]?.status]||'未验收';$('flags').replaceChildren();for(const flag of [...entry.flags,...entry.integrity_errors]){const tag=document.createElement('span');tag.className='tag warn';tag.textContent=translate[flag]||flag;$('flags').append(tag)}if(!entry.flags.length&&!entry.integrity_errors.length){const tag=document.createElement('span');tag.className='tag';tag.textContent='基础完整性 / 几何初筛未发现问题';$('flags').append(tag)}list();try{const loaded=await api('/api/clip/'+entry.id);if(version!==loadVersion)return;data=loaded;for(const rig of [data.source,data.target])if(rig){rig.positions=Float32Array.from(rig.positions);if(rig.root_positions)rig.root_positions=Float32Array.from(rig.root_positions)}$('timeline').max=data.frames-1;$('timeline').value=0;$('sourceCount').textContent=data.source.names.length+' 骨骼';$('targetCount').textContent=data.target?data.target.names.length+' 骨骼':'未生成';$('description').textContent=`${data.package} / ${data.description}${data.review_note?' · '+data.review_note:''}`;$('loading').style.display='none';fitCamera();updateTime()}catch(error){if(version===loadVersion){$('loading').textContent='无法加载：'+error.message;$('loading').classList.add('error')}}}
function position(rig,f,i){let o=(f*rig.names.length+i)*3;return [rig.positions[o],rig.positions[o+1],rig.positions[o+2]]}
function rootPosition(rig,f){if(rig.root_positions){const o=f*3;return [rig.root_positions[o],rig.root_positions[o+1],rig.root_positions[o+2]]}return position(rig,f,rig.pelvis)}
function origin(rig,f){const at=$('mode').value==='follow'?f:0;const p=rootPosition(rig,at);return [p[0],p[1],0]}
function trailPoint(rig,f,offset){return sub(rootPosition(rig,f),offset)}
function fitCamera(onlyCurrent=false){
 if(!data)return;
 const follow=$('mode').value==='follow',f=Math.max(0,Math.min(data.frames-1,Math.floor(frame)));
 const low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity];
 for(const rig of [data.source,data.target]){
  if(!rig)continue;
  const first=follow||onlyCurrent?f:0,last=follow||onlyCurrent?f:data.frames-1;
  for(let k=first;k<=last;k++){
   const offset=origin(rig,k);
   for(let i=0;i<rig.names.length;i++){
    const p=sub(position(rig,k,i),offset);
    for(let axis=0;axis<3;axis++){low[axis]=Math.min(low[axis],p[axis]);high[axis]=Math.max(high[axis],p[axis])}
   }
   const root=sub(rootPosition(rig,k),offset);
   for(let axis=0;axis<3;axis++){low[axis]=Math.min(low[axis],root[axis]);high[axis]=Math.max(high[axis],root[axis])}
  }
 }
 camera.target=low.map((v,i)=>(v+high[i])/2);
 camera.followRootZ=rootPosition(data.source,f)[2];
 camera.distance=Math.max(300,Math.hypot(...high.map((v,i)=>v-low[i]))*1.45);
 camera.panX=0;camera.panZ=0;
}
function viewTarget(){
 const target=[...camera.target];
 target[2]+=camera.panZ;
 if(data&&$('mode').value==='follow')target[2]+=rootPosition(data.source,Math.floor(frame))[2]-camera.followRootZ;
 return target;
}
function projection(width,height){
 const target=viewTarget();
 const direction=[Math.cos(camera.pitch)*Math.cos(camera.yaw),Math.cos(camera.pitch)*Math.sin(camera.yaw),Math.sin(camera.pitch)];
 const eye=target.map((v,i)=>v+direction[i]*camera.distance),forward=direction.map(v=>-v);
 const right=normal(cross(forward,[0,0,1])),up=cross(right,forward);
 return p=>{const rel=sub(p,eye),z=dot(rel,forward);if(z<1)return null;const focal=height/(2*Math.tan(Math.PI/7));return [width/2+(dot(rel,right)-camera.panX)*focal/z,height/2-dot(rel,up)*focal/z,z]};
}
function draw(canvas,rig,color){
 const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
 if(rect.width<=0||rect.height<=0)return;
 if(canvas.width!==Math.round(rect.width*dpr)||canvas.height!==Math.round(rect.height*dpr)){canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr)}
 const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
 const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);
 const gradient=ctx.createLinearGradient(0,0,0,h);gradient.addColorStop(0,'#0e1724');gradient.addColorStop(1,'#141f2e');ctx.fillStyle=gradient;ctx.fillRect(0,0,w,h);
 const project=projection(w,h);
 function line(a,b,c,width=1){a=project(a);b=project(b);if(!a||!b)return;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.strokeStyle=c;ctx.lineWidth=width;ctx.stroke()}
 const extent=Math.max(500,camera.distance*1.15),rough=extent/12,power=10**Math.floor(Math.log10(rough));
 const step=[1,2,5,10].map(v=>v*power).find(v=>v>=rough);
 const cx=camera.target[0],cy=camera.target[1];
 for(let n=Math.floor((cx-extent)/step)*step;n<=cx+extent;n+=step)line([n,cy-extent,0],[n,cy+extent,0],Math.abs(n)<step/2?'#36586a':'#223142');
 for(let n=Math.floor((cy-extent)/step)*step;n<=cy+extent;n+=step)line([cx-extent,n,0],[cx+extent,n,0],Math.abs(n)<step/2?'#4e4253':'#223142');
 line([0,0,0],[50,0,0],'#e98987',2);line([0,0,0],[0,50,0],'#85c292',2);line([0,0,0],[0,0,50],'#86aaf3',2);
 ctx.font='10px Segoe UI';ctx.fillStyle='#697e98';ctx.fillText(`网格 ${step} cm · Z ↑ · Root 轨迹为三维`,15,h-15);
 if(!rig)return;
 const f=Math.max(0,Math.min(data.frames-1,Math.floor(frame))),offset=origin(rig,f),points=rig.names.map((_,i)=>sub(position(rig,f,i),offset));
 if($('trail').checked){
  const stride=Math.max(1,Math.floor(data.frames/300));
  for(let k=0;k<data.frames-1;k+=stride){const end=Math.min(data.frames-1,k+stride);line(trailPoint(rig,k,offset),trailPoint(rig,end,offset),end<=f?color+'bb':color+'55',end<=f?2:1.5)}
  const root=trailPoint(rig,f,offset),ground=[root[0],root[1],0];
  line(ground,root,color+'88',1);
  const marker=project(root);
  if(marker){ctx.beginPath();ctx.arc(marker[0],marker[1],4,0,2*Math.PI);ctx.fillStyle='#fff';ctx.fill();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke()}
 }
const edges=[];for(let i=0;i<points.length;i++){let parent=rig.parents[i];if(parent<0)continue;const a=project(points[parent]),b=project(points[i]);if(a&&b)edges.push({i,a,b,z:(a[2]+b[2])/2})}edges.sort((a,b)=>b.z-a.z);for(const e of edges){ctx.beginPath();ctx.moveTo(e.a[0],e.a[1]);ctx.lineTo(e.b[0],e.b[1]);ctx.strokeStyle=color;ctx.lineWidth=/Hand|index|middle|ring|pinky|thumb|twist/i.test(rig.names[e.i])?1.2:2.5;ctx.stroke()}
let nearest=null;for(let i=0;i<points.length;i++){const p=project(points[i]);if(!p)continue;ctx.beginPath();ctx.arc(p[0],p[1],i===rig.pelvis?4:2,0,2*Math.PI);ctx.fillStyle=i===rig.pelvis?'#ffffff':color;ctx.fill();if($('names').checked){ctx.fillStyle='#b1c3d7';ctx.font='8px Segoe UI';ctx.fillText(rig.names[i],p[0]+4,p[1]-3)}if(hover?.canvas===canvas){const dist=Math.hypot(p[0]-hover.x,p[1]-hover.y);if(dist<15&&(!nearest||dist<nearest.dist))nearest={p,dist,i}}}if(nearest){ctx.font='12px Segoe UI';const text=rig.names[nearest.i];ctx.fillStyle='#070c12e8';ctx.fillRect(nearest.p[0]+8,nearest.p[1]-24,ctx.measureText(text).width+16,24);ctx.fillStyle='#fff';ctx.fillText(text,nearest.p[0]+16,nearest.p[1]-8)}}
function updateTime(){if(!data)return;const f=Math.floor(frame);$('timeline').value=f;$('time').textContent=`${f+1} / ${data.frames} · ${(f/data.fps).toFixed(2)}s`}
function cameraDirection(){return [Math.cos(camera.pitch)*Math.cos(camera.yaw),Math.cos(camera.pitch)*Math.sin(camera.yaw),Math.sin(camera.pitch)]}
function cameraAxes(){const forward=cameraDirection().map(v=>-v),right=normal(cross(forward,[0,0,1]));return {forward,right,up:cross(right,forward)}}
function moveCamera(delta){camera.target=camera.target.map((v,i)=>v+delta[i])}
function lookAround(dx,dy){
 const eye=viewTarget().map((v,i)=>v+cameraDirection()[i]*camera.distance);
 camera.yaw-=dx*.008;camera.pitch=Math.max(-1.45,Math.min(1.45,camera.pitch+dy*.008));
 const shift=viewTarget()[2]-camera.target[2];
 camera.target=eye.map((v,i)=>v-cameraDirection()[i]*camera.distance-(i===2?shift:0));
 $('view').value='perspective';
}
const flyKeys=new Set();let flyActive=false,flySpeed=1;
function tick(now){
 const delta=Math.min(Math.max((now-last)/1000,0),.1);
 if(flyActive&&flyKeys.size){
  const {forward,right}=cameraAxes(),movement=[0,0,0];
  const add=(axis,sign)=>axis.forEach((v,i)=>movement[i]+=v*sign);
  if(flyKeys.has('KeyW'))add(forward,1);if(flyKeys.has('KeyS'))add(forward,-1);
  if(flyKeys.has('KeyD'))add(right,1);if(flyKeys.has('KeyA'))add(right,-1);
  if(flyKeys.has('KeyE'))movement[2]++;if(flyKeys.has('KeyQ'))movement[2]--;
  const length=Math.hypot(...movement);
  if(length)moveCamera(movement.map(v=>v/length*delta*Math.max(150,camera.distance*.55)*flySpeed));
 }
 if(data&&playing){frame+=delta*data.fps*Number($('speed').value);if(frame>=data.frames){if($('loop').checked)frame%=data.frames;else{frame=data.frames-1;playing=false;$('play').textContent='▶ 播放'}}updateTime()}
 last=now;draw(canvases[0],data?.source,'#5bd6cc');draw(canvases[1],data?.target,'#f1b865');requestAnimationFrame(tick);
}
function pauseStep(delta){playing=false;$('play').textContent='▶ 播放';if(data){frame=Math.max(0,Math.min(data.frames-1,Math.floor(frame)+delta));updateTime()}}
$('play').onclick=()=>{if(!data)return;playing=!playing;$('play').textContent=playing?'❚❚ 暂停':'▶ 播放'};$('prevFrame').onclick=()=>pauseStep(-1);$('nextFrame').onclick=()=>pauseStep(1);$('timeline').oninput=()=>{const selected=Number($('timeline').value);pauseStep(0);frame=selected;updateTime()};
// Both canvases share the same UE-style camera controls and view state.
for(const canvas of canvases){
 let drag=null;
 canvas.tabIndex=0;
 canvas.oncontextmenu=e=>e.preventDefault();
 canvas.onpointerdown=e=>{e.preventDefault();canvas.focus();drag={x:e.clientX,y:e.clientY};flyActive=!!(e.buttons&2);canvas.setPointerCapture(e.pointerId)};
 canvas.onpointermove=e=>{
  const box=canvas.getBoundingClientRect();hover={canvas,x:e.clientX-box.left,y:e.clientY-box.top};
  if(!drag)return;
  const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
  flyActive=!!(e.buttons&2)&&!e.altKey;
  if(e.altKey&&(e.buttons&1)){
   camera.yaw-=dx*.008;camera.pitch=Math.max(-1.45,Math.min(1.45,camera.pitch+dy*.008));$('view').value='perspective';
  }else if((e.buttons&4)||((e.buttons&1)&&(e.buttons&2))){
   const {right,up}=cameraAxes(),scale=2*camera.distance*Math.tan(Math.PI/7)/Math.max(box.height,1);
   moveCamera(right.map((v,i)=>-v*dx*scale+up[i]*dy*scale));
  }else if(e.altKey&&(e.buttons&2)){
   camera.distance=Math.max(40,Math.min(200000,camera.distance*Math.exp((dx+dy)*.006)));
  }else if(e.buttons&2){
   lookAround(dx,dy);
  }else if(e.buttons&1){
   lookAround(dx,0);
   moveCamera(cameraAxes().forward.map(v=>v*-dy*camera.distance/500));
  }
  drag.x=e.clientX;drag.y=e.clientY;
 };
 canvas.onpointerup=e=>{drag=null;flyActive=!!(e.buttons&2);if(!flyActive)flyKeys.clear()};
 canvas.onpointercancel=()=>{drag=null;flyActive=false;flyKeys.clear()};
 canvas.onpointerleave=()=>hover=null;
 canvas.addEventListener('wheel',e=>{e.preventDefault();if(flyActive){flySpeed=Math.max(.1,Math.min(8,flySpeed*Math.exp(-e.deltaY*.001)));$('cameraSpeed').textContent=`飞行 ${flySpeed.toFixed(1)}×`}else camera.distance=Math.max(40,Math.min(200000,camera.distance*Math.exp(e.deltaY*.001)))},{passive:false});
}
window.addEventListener('blur',()=>{flyActive=false;flyKeys.clear()});
$('reset').onclick=()=>{camera.yaw=-Math.PI/4;camera.pitch=.28;fitCamera();$('view').value='perspective'};
$('mode').onchange=()=>fitCamera();
$('view').onchange=()=>{const v=$('view').value;camera.yaw=v==='front'?0:v==='side'?-Math.PI/2:-Math.PI/4;camera.pitch=v==='top'?1.45:v==='perspective'?.28:0};
$('search').oninput=list;document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));list()});
let bulkSaving=false;
async function save(status){if(bulkSaving||!current)return;const entry=current, note=$('note').value;$('saved').textContent='保存中…';try{await api('/api/review',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':catalog.token},body:JSON.stringify({id:entry.id,status,note})});catalog.decisions[entry.id]={status,note};if(current.id===entry.id)$('saved').textContent=stateName[status]+' · 已保存';list()}catch(e){$('saved').textContent='保存失败：'+e.message}}
async function bulkReview(status){
 if(!catalog||bulkSaving)return;
 const action=status==='approved'?'通过':'不通过';
 if(current&&$('note').value!==(catalog.decisions[current.id]?.note||'')){alert(`请先保存当前备注，再批量标记${action}。`);return}
 let done=0;
 bulkSaving=true;$('approveVisible').disabled=true;$('rejectVisible').disabled=true;
 try{
  // 先刷新持久化结论，避免覆盖其他页面已保存的有问题/待定记录。
  const fresh=await api('/api/catalog');catalog.decisions=fresh.decisions;catalog.token=fresh.token;
  const entries=visible().filter(e=>!catalog.decisions[e.id]||catalog.decisions[e.id].status==='unreviewed');
  if(!entries.length){$('bulkResult').textContent='当前列表没有未验收动作。';return}
  const issues=entries.filter(e=>e.group==='issue').length;
  if(!confirm(`将当前筛选中的 ${entries.length} 条未验收动作批量标记${action}（含 ${issues} 条疑似问题）。\n这不代表逐条观看；已有结论保留，不会自动入库或删除。确定继续？`))return;
  for(const entry of entries){
   const previous=catalog.decisions[entry.id]?.note||'';
   const note=previous+`\n[批量${action}：用户一键标记，未声明逐条观看]`;
   await api('/api/review',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':catalog.token},body:JSON.stringify({id:entry.id,status,note})});
   catalog.decisions[entry.id]={status,note};done++;
   $('bulkResult').textContent=`已保存 ${done} / ${entries.length} 条`;
  }
  $('bulkResult').textContent=`批量${action} ${done} 条，记录已保存；未入库、未删除。`;
 }catch(error){$('bulkResult').textContent=`已保存 ${done} 条，操作停止：${error.message}。可刷新核对后重试。`}
 finally{bulkSaving=false;$('approveVisible').disabled=false;$('rejectVisible').disabled=false;list();if(current){$('note').value=catalog.decisions[current.id]?.note||'';$('saved').textContent=stateName[catalog.decisions[current.id]?.status]||'未验收'}}
}
$('approveVisible').onclick=()=>bulkReview('approved');
$('rejectVisible').onclick=()=>bulkReview('rejected');
document.querySelectorAll('[data-status]').forEach(b=>b.onclick=()=>save(b.dataset.status));$('saveNote').onclick=()=>save(catalog.decisions[current?.id]?.status||'unreviewed');$('nextClip').onclick=()=>{const entries=visible(),index=entries.findIndex(e=>e.id===current?.id);if(entries.length)select(entries[(index+1)%entries.length])};$('export').onclick=async()=>{const result=await api('/api/export');const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='motion-review.json';a.click();URL.revokeObjectURL(url)};
const flyAliases={ArrowUp:'KeyW',ArrowDown:'KeyS',ArrowLeft:'KeyA',ArrowRight:'KeyD',Numpad8:'KeyW',Numpad2:'KeyS',Numpad4:'KeyA',Numpad6:'KeyD',Numpad9:'KeyE',Numpad7:'KeyQ'};
document.addEventListener('keydown',e=>{
 if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;
 const flyCode=flyAliases[e.code]||e.code;
 if(flyActive&&['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE'].includes(flyCode)){e.preventDefault();flyKeys.add(flyCode);return}
 if(e.code==='KeyF'&&!flyActive){e.preventDefault();fitCamera(true)}
 if(e.code==='Space'){e.preventDefault();$('play').click()}
 if(e.code==='ArrowLeft'){e.preventDefault();pauseStep(-1)}
 if(e.code==='ArrowRight'){e.preventDefault();pauseStep(1)}
});
document.addEventListener('keyup',e=>flyKeys.delete(flyAliases[e.code]||e.code));
api('/api/catalog').then(value=>{catalog=value;const issues=value.entries.filter(e=>e.group==='issue').length;$('total').textContent=value.exception_mode||value.prepared_mode?`${value.total}（本页 ${value.entries.length}）`:value.entries.length;$('summary').textContent=value.prepared_mode?`已审计 ${value.checked} 条 · 复核 ${value.total} 条 · 第 ${value.page} / ${value.page_count} 页`:value.exception_mode?`异常分流 ${value.total} 条 · 第 ${value.page} / ${value.page_count} 页 · 不会自动入库或删除`:`已初筛 ${value.checked} 条 · 疑似问题 ${issues} 条 + 5% 抽样 ${value.entries.length-issues} 条`;if(value.prepared_mode){$('mode').value='world';document.body.classList.add('prepared-mode');$('queuePill').textContent='● prepared 数据复核 · 原始数据受保护';$('sampleFilter').textContent='分类抽样';$('sourceLabel').textContent='UE 导出动作 · Root 合成';$('source').setAttribute('aria-label','UE 导出动作骨骼交互视图');$('description').textContent='Root 驱动的 UE 导出动作骨架';$('disclaimer').textContent='30 FPS，厘米制 Root 合成骨架。这里可核对轨迹、姿态与异常帧；蒙皮、脚底接触、碰撞和场景语义仍须在 UE 验收。';$('saveLocation').textContent='结论保存到本地 MotionDataLibrary/reviews/decisions.sqlite3；仅用于复核，不会自动修改训练数据。';document.querySelector('.sync').textContent='单动作骨架 / 时间轴';} $('prevPage').disabled=value.page<=1;$('nextPage').disabled=value.page>=value.page_count;$('prevPage').onclick=()=>location.href=pageUrl(value.page-1);$('nextPage').onclick=()=>location.href=pageUrl(value.page+1);list();if(value.entries.length)select(value.entries[0]);else $('loading').textContent='本次名单为空'}).catch(e=>$('loading').textContent=e.message);requestAnimationFrame(tick);
