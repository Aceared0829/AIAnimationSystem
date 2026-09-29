'use strict';
const $=id=>document.getElementById(id);
const camera={yaw:-Math.PI/2,pitch:0.18,distance:340,target:[0,0,95],fov:90,flySpeed:500};
let catalog,data,current,filter='all',frame=0,playing=false,loadVersion=0,last=0,hover=null;
let rmbHeld=false;
const flyKeys=new Set();
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
async function select(entry){if(current&&$('note').value!==(catalog.decisions[current.id]?.note||'')&&!confirm('当前备注尚未保存，仍要切换吗？'))return;const version=++loadVersion;current=entry;data=null;playing=false;frame=0;hover=null;$('play').textContent='▶ 播放';$('loading').classList.remove('error');$('loading').style.display='grid';$('loading').textContent='校验来源哈希并加载真实动作…';$('name').textContent=entry.name;$('description').textContent=entry.reason||'';$('group').textContent=catalog.prepared_mode?'prepared 数据 · 人工复核':catalog.exception_mode?'异常分流 · 人工筛选':'疑似问题 · 全部人工复核';$('note').value=catalog.decisions[entry.id]?.note||'';$('saved').textContent=stateName[catalog.decisions[entry.id]?.status]||'未验收';$('flags').replaceChildren();for(const flag of [...entry.flags,...entry.integrity_errors]){const tag=document.createElement('span');tag.className='tag warn';tag.textContent=translate[flag]||flag;$('flags').append(tag)}if(!entry.flags.length&&!entry.integrity_errors.length){const tag=document.createElement('span');tag.className='tag';tag.textContent='基础完整性 / 几何初筛未发现问题';$('flags').append(tag)}list();try{const loaded=await api('/api/clip/'+entry.id);if(version!==loadVersion)return;data=loaded;for(const rig of [data.source,data.target])if(rig){rig.positions=Float32Array.from(rig.positions);if(rig.root_positions)rig.root_positions=Float32Array.from(rig.root_positions)}$('timeline').max=data.frames-1;$('timeline').value=0;$('sourceCount').textContent=data.source.names.length+' 骨骼';$('targetCount').textContent=data.target?data.target.names.length+' 骨骼':'未生成';$('description').textContent=`${data.package} / ${data.description}${data.review_note?' · '+data.review_note:''}`;$('loading').style.display='none';fitView();updateTime()}catch(error){if(version===loadVersion){$('loading').textContent='无法加载：'+error.message;$('loading').classList.add('error')}}}
function position(rig,f,i){let o=(f*rig.names.length+i)*3;return [rig.positions[o],rig.positions[o+1],rig.positions[o+2]]}
function rootPosition(rig,f){if(rig.root_positions){const o=f*3;return [rig.root_positions[o],rig.root_positions[o+1],rig.root_positions[o+2]]}return position(rig,f,rig.pelvis)}
// 始终使用动画导出坐标，保留 Root 的 XYZ 位移与高度。
function origin(){return [0,0,0]}
function basis(){
 const view=$('view').value;
 if(view==='top')return {direction:[0,0,1],forward:[0,0,-1],right:[1,0,0],up:[0,1,0]};
 const yaw=view==='front'?Math.PI:view==='side'?-Math.PI/2:camera.yaw;
 const pitch=view==='perspective'?camera.pitch:0;
 const direction=[Math.cos(pitch)*Math.cos(yaw),Math.cos(pitch)*Math.sin(yaw),Math.sin(pitch)];
 const forward=direction.map(v=>-v),right=normal(cross(forward,[0,0,1]));
 return {direction,forward,right,up:cross(right,forward)};
}
function projection(width,height){
 const {direction,forward,right,up}=basis(),orthographic=$('view').value!=='perspective';
 const eye=camera.target.map((v,i)=>v+direction[i]*camera.distance);
 const focal=height/(2*Math.tan(camera.fov*Math.PI/360));
 return p=>{
  const rel=sub(p,orthographic?camera.target:eye),z=dot(sub(p,eye),forward);
  if(!orthographic&&z<1)return null;
  const scale=orthographic?height/(2*camera.distance):focal/z;
  return [width/2+dot(rel,right)*scale,height/2-dot(rel,up)*scale,z];
 };
}
function fitView(resetOrientation=true){
 if(resetOrientation){camera.yaw=-Math.PI/2;camera.pitch=.18;$('view').value='perspective'}
 if(!data){camera.target=[0,0,95];camera.distance=340;return}
 const points=[];
 for(const rig of [data.source,data.target])if(rig)for(let f=0;f<data.frames;f++){
  for(let i=0;i<rig.names.length;i++)points.push(position(rig,f,i));
  points.push(rootPosition(rig,f));
 }
 const mins=[Infinity,Infinity,Infinity],maxs=[-Infinity,-Infinity,-Infinity];
 for(const p of points)for(let i=0;i<3;i++){mins[i]=Math.min(mins[i],p[i]);maxs[i]=Math.max(maxs[i],p[i])}
 camera.target=mins.map((v,i)=>(v+maxs[i])/2);
 const {direction,right,up}=basis(),rect=canvases[0].getBoundingClientRect();
 const aspect=Math.max(.25,rect.width/Math.max(1,rect.height));
 let required=150;
 for(const p of points){
  const rel=sub(p,camera.target),depth=dot(rel,direction);
  required=Math.max(required,depth+Math.abs(dot(rel,up))/Math.tan(camera.fov*Math.PI/360)*1.15,
                    depth+Math.abs(dot(rel,right))/(aspect*Math.tan(camera.fov*Math.PI/360))*1.15);
 }
 camera.distance=Math.min(100000,required);
}
function focusCurrentFrame(){
 if(!data)return;
 const rig=data.source||data.target,f=Math.floor(frame),offset=origin(rig,f);
 const points=rig.names.map((_,i)=>sub(position(rig,f,i),offset));
 const mins=[Infinity,Infinity,Infinity],maxs=[-Infinity,-Infinity,-Infinity];
 for(const p of points)for(let i=0;i<3;i++){mins[i]=Math.min(mins[i],p[i]);maxs[i]=Math.max(maxs[i],p[i])}
 camera.target=mins.map((v,i)=>(v+maxs[i])/2);
 const {right,up}=basis(),rect=canvases[0].getBoundingClientRect(),aspect=Math.max(.25,rect.width/Math.max(1,rect.height));
 const halfWidth=Math.max(...points.map(p=>Math.abs(dot(sub(p,camera.target),right))));
 const halfHeight=Math.max(...points.map(p=>Math.abs(dot(sub(p,camera.target),up))));
 const extent=Math.max(halfHeight,halfWidth/aspect,50);
 camera.distance=$('view').value==='perspective'?Math.max(150,extent/Math.tan(camera.fov*Math.PI/360)*1.7):Math.max(75,extent*1.3);
}
function draw(canvas,rig,color){const rect=canvas.getBoundingClientRect();if(rect.width<=0||rect.height<=0)return;const dpr=Math.min(devicePixelRatio||1,2);if(canvas.width!==Math.round(rect.width*dpr)||canvas.height!==Math.round(rect.height*dpr)){canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr)}const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);const gradient=ctx.createLinearGradient(0,0,0,h);gradient.addColorStop(0,'#0e1724');gradient.addColorStop(1,'#141f2e');ctx.fillStyle=gradient;ctx.fillRect(0,0,w,h);const project=projection(w,h);function line(a,b,c,width=1){a=project(a);b=project(b);if(!a||!b)return;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.strokeStyle=c;ctx.lineWidth=width;ctx.stroke()}
const step=camera.distance>5000?500:camera.distance>1200?100:25;
const half=Math.max(500,Math.min(30000,camera.distance*1.2)),view=$('view').value;
const gridAxes=view==='front'?[1,2]:view==='side'?[0,2]:[0,1];
const center=gridAxes.map(axis=>Math.round(camera.target[axis]/step)*step);
 const planePoint=(u,v)=>{const p=[0,0,0];p[gridAxes[0]]=u;p[gridAxes[1]]=v;return p};
for(let n=-half;n<=half;n+=step){
 line(planePoint(center[0]+n,center[1]-half),planePoint(center[0]+n,center[1]+half),'#223142');
 line(planePoint(center[0]-half,center[1]+n),planePoint(center[0]+half,center[1]+n),'#223142');
}
line([0,0,0],[50,0,0],'#e98987',2);line([0,0,0],[0,50,0],'#85c292',2);line([0,0,0],[0,0,50],'#86aaf3',2);
ctx.font='10px Segoe UI';ctx.fillStyle='#697e98';ctx.fillText(`网格 ${step} cm · ${gridAxes.map(i=>'XYZ'[i]).join('')} 平面 · Z ↑`,15,h-15);if(!rig)return;
const f=Math.max(0,Math.min(data.frames-1,Math.floor(frame))),offset=origin(rig,f),points=rig.names.map((_,i)=>sub(position(rig,f,i),offset));
if($('trail').checked){let previous;for(let k=0;k<data.frames;k+=Math.max(1,Math.floor(data.frames/300))){const p=sub(rootPosition(rig,k),offset);if(previous)line(previous,p,color+'99',1.5);previous=p}line(previous,sub(rootPosition(rig,data.frames-1),offset),color+'99',1.5);for(const [sample,shade,label] of [[0,'#6dafff','起点'],[data.frames-1,'#f7b267','终点']]){const p=project(sub(rootPosition(rig,sample),offset));if(p){ctx.beginPath();ctx.arc(p[0],p[1],4,0,2*Math.PI);ctx.fillStyle=shade;ctx.fill();ctx.font='10px Segoe UI';ctx.fillText(label,p[0]+6,p[1]-6)}}}
const edges=[];for(let i=0;i<points.length;i++){let parent=rig.parents[i];if(parent<0)continue;const a=project(points[parent]),b=project(points[i]);if(a&&b)edges.push({i,a,b,z:(a[2]+b[2])/2})}edges.sort((a,b)=>b.z-a.z);for(const e of edges){ctx.beginPath();ctx.moveTo(e.a[0],e.a[1]);ctx.lineTo(e.b[0],e.b[1]);ctx.strokeStyle=color;ctx.lineWidth=/Hand|index|middle|ring|pinky|thumb|twist/i.test(rig.names[e.i])?1.2:2.5;ctx.stroke()}
let nearest=null;for(let i=0;i<points.length;i++){const p=project(points[i]);if(!p)continue;ctx.beginPath();ctx.arc(p[0],p[1],i===rig.pelvis?4:2,0,2*Math.PI);ctx.fillStyle=i===rig.pelvis?'#ffffff':color;ctx.fill();if($('names').checked){ctx.fillStyle='#b1c3d7';ctx.font='8px Segoe UI';ctx.fillText(rig.names[i],p[0]+4,p[1]-3)}if(hover?.canvas===canvas){const dist=Math.hypot(p[0]-hover.x,p[1]-hover.y);if(dist<15&&(!nearest||dist<nearest.dist))nearest={p,dist,i}}}const root=project(sub(rootPosition(rig,f),offset));if(root){ctx.beginPath();ctx.arc(root[0],root[1],5,0,2*Math.PI);ctx.fillStyle='#ff8b69';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.stroke()}if(nearest){ctx.font='12px Segoe UI';const text=rig.names[nearest.i];ctx.fillStyle='#070c12e8';ctx.fillRect(nearest.p[0]+8,nearest.p[1]-24,ctx.measureText(text).width+16,24);ctx.fillStyle='#fff';ctx.fillText(text,nearest.p[0]+16,nearest.p[1]-8)}}
function updateTime(){if(!data)return;const f=Math.floor(frame);$('timeline').value=f;$('time').textContent=`${f+1} / ${data.frames} · ${(f/data.fps).toFixed(2)}s`;const rig=data.target||data.source,root=rootPosition(rig,f),first=rootPosition(rig,0),delta=sub(root,first),kind=!rig.root_positions?'骨盆参考':catalog?.exception_mode?'源动作 Root（UE 轴）':'导出 Root';$('rootLocation').textContent=`${kind} (cm) X ${root[0].toFixed(1)} · Y ${root[1].toFixed(1)} · Z ${root[2].toFixed(1)} | ΔX ${delta[0].toFixed(1)} · ΔY ${delta[1].toFixed(1)} · ΔZ ${delta[2].toFixed(1)}`}
function tick(now){
 const dt=Math.min(.05,Math.max(0,(now-last)/1000));
 if(rmbHeld&&$('view').value==='perspective'&&flyKeys.size){
  const {forward,right}=basis(),motion=[0,0,0];
  const add=(axis,sign)=>{for(let i=0;i<3;i++)motion[i]+=axis[i]*sign};
  if(flyKeys.has('KeyW')||flyKeys.has('ArrowUp'))add(forward,1);
  if(flyKeys.has('KeyS')||flyKeys.has('ArrowDown'))add(forward,-1);
  if(flyKeys.has('KeyD')||flyKeys.has('ArrowRight'))add(right,1);
  if(flyKeys.has('KeyA')||flyKeys.has('ArrowLeft'))add(right,-1);
  if(flyKeys.has('KeyE')||flyKeys.has('PageUp'))add([0,0,1],1);
  if(flyKeys.has('KeyQ')||flyKeys.has('PageDown'))add([0,0,1],-1);
  if(flyKeys.has('KeyR'))add(basis().up,1);
  if(flyKeys.has('KeyF'))add(basis().up,-1);
  const length=Math.hypot(...motion);
  if(length)camera.target=camera.target.map((v,i)=>v+motion[i]/length*camera.flySpeed*dt);
 }
 if(data&&playing){frame+=dt*data.fps*Number($('speed').value);if(frame>=data.frames){if($('loop').checked)frame%=data.frames;else{frame=data.frames-1;playing=false;$('play').textContent='▶ 播放'}}updateTime()}
 last=now;draw(canvases[0],data?.source,'#5bd6cc');draw(canvases[1],data?.target,'#f1b865');requestAnimationFrame(tick);
}
function pauseStep(delta){playing=false;$('play').textContent='▶ 播放';if(data){frame=Math.max(0,Math.min(data.frames-1,Math.floor(frame)+delta));updateTime()}}
$('play').onclick=()=>{if(!data)return;playing=!playing;$('play').textContent=playing?'❚❚ 暂停':'▶ 播放'};$('prevFrame').onclick=()=>pauseStep(-1);$('nextFrame').onclick=()=>pauseStep(1);$('timeline').oninput=()=>{const selected=Number($('timeline').value);pauseStep(0);frame=selected;updateTime()};
// Epic Viewport Controls：RMB 原地看向、Alt+LMB 绕焦点、MMB 平移、RMB+WASD/EQ 飞行。
function cameraInputMode(e){
 const left=!!(e.buttons&1),right=!!(e.buttons&2),middle=!!(e.buttons&4);
 if($('view').value!=='perspective')return left&&right?'dolly':right||middle?'pan':null;
 if(e.altKey&&right)return 'dolly';
 if(e.altKey&&middle)return 'pan';
 if(e.altKey&&left)return 'orbit';
 if(left&&right||middle)return 'pan';
 if(right)return 'look';
 if(left)return 'drive';
 return null;
}
function panCamera(dx,dy,height){
 const {right,up}=basis();
 const scale=$('view').value==='perspective'?2*camera.distance*Math.tan(camera.fov*Math.PI/360)/height:2*camera.distance/height;
 camera.target=camera.target.map((v,i)=>v-right[i]*dx*scale+up[i]*dy*scale);
}
function rotateCamera(dx,dy,keepEye){
 const eye=keepEye?camera.target.map((v,i)=>v+basis().direction[i]*camera.distance):null;
 camera.yaw-=dx*.008;
 camera.pitch=Math.max(-1.45,Math.min(1.45,camera.pitch+dy*.008));
 if(eye){const {direction}=basis();camera.target=eye.map((v,i)=>v-direction[i]*camera.distance)}
}
for(const canvas of canvases){
 let drag=null;
 canvas.tabIndex=0;
 canvas.oncontextmenu=e=>e.preventDefault();
 canvas.onpointerdown=e=>{
  const mode=cameraInputMode(e);
  if(!mode)return;
  e.preventDefault();canvas.focus();
  rmbHeld=!!(e.buttons&2);
  drag={x:e.clientX,y:e.clientY,id:e.pointerId};
  canvas.setPointerCapture(e.pointerId);canvas.style.cursor='grabbing';
 };
 canvas.onpointermove=e=>{
  const box=canvas.getBoundingClientRect();hover={canvas,x:e.clientX-box.left,y:e.clientY-box.top};
  if(!drag||drag.id!==e.pointerId)return;
  rmbHeld=!!(e.buttons&2);
  const dx=e.clientX-drag.x,dy=e.clientY-drag.y,mode=cameraInputMode(e);
  if(mode==='pan')panCamera(dx,dy,Math.max(1,box.height));
  else if(mode==='dolly')camera.distance=Math.max(40,Math.min(30000,camera.distance*Math.exp(dy*.01)));
  else if(mode==='orbit')rotateCamera(dx,dy,false);
  else if(mode==='look')rotateCamera(dx,dy,true);
  else if(mode==='drive'){
   rotateCamera(dx,0,true);
   const {forward}=basis(),amount=-dy*camera.distance*.008;
   camera.target=camera.target.map((v,i)=>v+forward[i]*amount);
  }
  drag.x=e.clientX;drag.y=e.clientY;
 };
 const finish=e=>{rmbHeld=!!(e.buttons&2);if(drag?.id===e.pointerId&&e.buttons===0){drag=null;canvas.style.cursor='grab'}};
 canvas.onpointerup=finish;canvas.onpointercancel=e=>{rmbHeld=false;drag=null;canvas.style.cursor='grab'};
 canvas.onpointerleave=()=>hover=null;
 canvas.addEventListener('wheel',e=>{
  e.preventDefault();
  if(rmbHeld&&$('view').value==='perspective'){
   camera.flySpeed=Math.max(10,Math.min(10000,camera.flySpeed*Math.exp(-e.deltaY*.001)));
   $('cameraSpeed').textContent=`飞行速度 ${Math.round(camera.flySpeed)} cm/s`;
  }
  else camera.distance=Math.max(40,Math.min(30000,camera.distance*Math.exp(e.deltaY*.001)));
 },{passive:false});
}
$('reset').onclick=fitView;
$('focus').onclick=focusCurrentFrame;
$('view').onchange=()=>{if($('view').value==='perspective'){camera.yaw=-Math.PI/2;camera.pitch=.18}};
$('search').oninput=list;
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));list()});
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
const flightCodes=new Set(['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','KeyR','KeyF','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','PageUp','PageDown']);
document.addEventListener('keydown',e=>{
 if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;
 if(rmbHeld&&$('view').value==='perspective'&&flightCodes.has(e.code)){e.preventDefault();flyKeys.add(e.code);return}
 if(e.code==='KeyF'&&canvases.includes(document.activeElement)){e.preventDefault();focusCurrentFrame();return}
 if(e.code==='Space'){e.preventDefault();$('play').click()}
 if(e.code==='ArrowLeft'){e.preventDefault();pauseStep(-1)}
 if(e.code==='ArrowRight'){e.preventDefault();pauseStep(1)}
});
document.addEventListener('keyup',e=>flyKeys.delete(e.code));
window.addEventListener('blur',()=>{rmbHeld=false;flyKeys.clear()});
api('/api/catalog').then(value=>{
 catalog=value;
 if(value.exception_mode)document.querySelector('.view-mode-label').textContent='源动作 Root 坐标 · 查看位移';
 const issues=value.entries.filter(e=>e.group==='issue').length;
 $('total').textContent=value.exception_mode||value.prepared_mode?`${value.total}（本页 ${value.entries.length}）`:value.entries.length;
 $('summary').textContent=value.prepared_mode?`已审计 ${value.checked} 条 · 复核 ${value.total} 条 · 第 ${value.page} / ${value.page_count} 页`:value.exception_mode?`异常分流 ${value.total} 条 · 第 ${value.page} / ${value.page_count} 页 · 不会自动入库或删除`:`已初筛 ${value.checked} 条 · 疑似问题 ${issues} 条 + 5% 抽样 ${value.entries.length-issues} 条`;
 if(value.prepared_mode){
  document.body.classList.add('prepared-mode');
  $('queuePill').textContent='● prepared 数据复核 · 原始数据受保护';
  $('sampleFilter').textContent='分类抽样';
  $('sourceLabel').textContent='UE 导出动作 · Root 合成';
  $('source').setAttribute('aria-label','UE 导出动作骨骼交互视图');
  $('description').textContent='Root 驱动的 UE 导出动作骨架';
  $('disclaimer').textContent='30 FPS，UE 厘米制动画导出 Root 轨道，始终保留导出位置与高度。它不是关卡 Actor 的世界 Location；蒙皮、接触、碰撞和场景语义仍须在 UE 验收。';
  $('saveLocation').textContent='结论保存到本地 MotionDataLibrary/reviews/decisions.sqlite3；仅用于复核，不会自动修改训练数据。';
  document.querySelector('.sync').textContent='单动作骨架 / 时间轴';
 }
 $('prevPage').disabled=value.page<=1;
 $('nextPage').disabled=value.page>=value.page_count;
 $('prevPage').onclick=()=>location.href=pageUrl(value.page-1);
 $('nextPage').onclick=()=>location.href=pageUrl(value.page+1);
 list();
 if(value.entries.length)select(value.entries[0]);else $('loading').textContent='本次名单为空';
}).catch(e=>$('loading').textContent=e.message);
requestAnimationFrame(tick);
