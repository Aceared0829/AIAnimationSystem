const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const elements = new Map();
const documentEvents = {};
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', checked: false, style: {}, classList: { add() {}, remove() {} },
    addEventListener() {}, setAttribute() {}, focus() {}, setPointerCapture() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 600 }; },
  });
  return elements.get(id);
}
element('view').value = 'perspective';
const context = vm.createContext({
  document: { getElementById: element, querySelectorAll() { return []; },
    addEventListener(type, handler) { documentEvents[type] = handler; } },
  window: { addEventListener() {} },
  location: { origin: 'http://127.0.0.1:8765', search: '', href: 'http://127.0.0.1:8765/' },
  fetch() { return new Promise(() => {}); }, requestAnimationFrame() {}, URL, Float32Array,
  devicePixelRatio: 1, confirm() { return true; }, alert() {},
});
const script = fs.readFileSync(path.join(__dirname, '../data/tools/review_web/app.js'), 'utf8');
vm.runInContext(script, context);
vm.runInContext(`data={frames:2,fps:30,source:{names:['Root','Hand'],parents:[-1,0],pelvis:0,
  positions:Float32Array.from([0,0,50,0,0,150,100,0,150,100,0,250]),
  root_positions:Float32Array.from([0,0,0,100,0,100])},target:null}`, context);

assert.deepEqual(Array.from(vm.runInContext('rootPosition(data.source,1)', context)), [100, 0, 100],
  'Root track is read from the server contract, not from the pelvis');
assert.deepEqual(Array.from(vm.runInContext('origin(data.source,1)', context)), [0, 0, 0],
  'exported Root coordinates are never recentered');
vm.runInContext('fitView()', context);
const target = vm.runInContext('camera.target', context);
assert(target[0] > 0 && target[2] > 0, 'overview frames the moving, elevated actor');
const visibility = vm.runInContext(`(() => {
  const out=[];for(let f=0;f<data.frames;f++)for(let i=0;i<data.source.names.length;i++){
    const p=projection(800,600)(position(data.source,f,i));
    out.push(!!p&&p[0]>=0&&p[0]<=800&&p[1]>=0&&p[1]<=600);
  }return out;
})()`, context);
assert(visibility.every(Boolean), 'all frames remain inside the overview');
vm.runInContext('frame=1;updateTime()', context);
assert.match(element('rootLocation').textContent, /导出 Root.*X 100\.0.*Z 100\.0.*ΔX 100\.0.*ΔZ 100\.0/);
vm.runInContext(`catalog={exception_mode:false};data.target={...data.source,
  root_positions:Float32Array.from([0,0,0,250,0,-75])};updateTime()`, context);
assert.match(element('rootLocation').textContent, /导出 Root.*X 250\.0.*Z -75\.0.*ΔX 250\.0.*ΔZ -75\.0/,
  'the dual-rig review reports the UE export rather than the source BVH');
vm.runInContext('data.target=null;catalog.exception_mode=true;updateTime()', context);
assert.match(element('rootLocation').textContent, /源动作 Root（UE 轴）/,
  'exception triage labels the converted source coordinate accurately');
element('view').value = 'side';
const vertical = vm.runInContext('projection(800,600)([100,0,100])[1]-projection(800,600)([100,0,0])[1]', context);
assert(Math.abs(vertical) > 1, 'orthographic side view preserves Root height');
element('view').value = 'perspective';

const canvas = element('source');
const event = (buttons, x, y, altKey = false) => ({ buttons, clientX: x, clientY: y, altKey,
  pointerId: 1, preventDefault() {} });
const beforeOrbit = vm.runInContext('camera.yaw', context);
canvas.onpointerdown(event(1, 0, 0, true));
canvas.onpointermove(event(1, 20, 0, true));
canvas.onpointerup(event(0, 20, 0, true));
assert.notEqual(vm.runInContext('camera.yaw', context), beforeOrbit, 'Alt+LMB orbits');
const beforePan = Array.from(vm.runInContext('camera.target', context));
canvas.onpointerdown(event(4, 0, 0));
canvas.onpointermove(event(4, 20, 0));
canvas.onpointerup(event(0, 20, 0));
assert.notDeepEqual(Array.from(vm.runInContext('camera.target', context)), beforePan, 'MMB pans');
const beforeLook = vm.runInContext('camera.yaw', context);
canvas.onpointerdown(event(2, 0, 0));
canvas.onpointermove(event(2, 20, 10));
assert.notEqual(vm.runInContext('camera.yaw', context), beforeLook, 'RMB looks around');
documentEvents.keydown({ code: 'KeyW', target: { tagName: 'CANVAS' }, preventDefault() {} });
assert(vm.runInContext("flyKeys.has('KeyW')", context), 'RMB+W enters fly movement');
const beforeFlight = Array.from(vm.runInContext('camera.target', context));
element('source').getBoundingClientRect = element('target').getBoundingClientRect =
  () => ({ left: 0, top: 0, width: 0, height: 0 });
vm.runInContext('last=1000;tick(1100)', context);
assert.notDeepEqual(Array.from(vm.runInContext('camera.target', context)), beforeFlight, 'RMB+W moves camera');
documentEvents.keyup({ code: 'KeyW' });
canvas.onpointerup(event(0, 20, 10));
console.log('Motion Review exported Root, full trajectory framing, and viewport controls: OK');
