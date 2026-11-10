'use strict';
// Executes the real JS bodies in an inert VM. Native refresh is a contract mock,
// not a native-code or gameplay test. A separate checksum oracle detects raw
// writes that fail to update the registered record.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const assert = require('assert/strict');

const AREA = path.resolve(__dirname, '..');
const candidatePath = path.join(AREA, 'tools/native_title_options.js');
const baselinePath = path.join(__dirname, 'fixtures/native_title_options.v121.js');
const relative = filename => path.relative(AREA, filename).split(path.sep).join('/');
const candidate = fs.readFileSync(candidatePath, 'utf8');
const baseline = fs.readFileSync(baselinePath, 'utf8');
const sha = s => crypto.createHash('sha256').update(s).digest('hex');
const pinSites = [0xfe7560, 0x216fe40, 0x2181ed0, 0xb11a90, 0x36d720, 0x373950, 0x2184560];
const base = 0x140000000n;
const at = { engine: 0x100000n, manager: 0x110000n, head: 0x120000n,
  node: 0x130000n, vector: 0x140000n, app: 0x150000n, registry: 0x160000n };
const cases = [];

function fixture(source, options = {}) {
  const memory = new Map(), writes = [], calls = [], events = [], order = [];
  const put = (p, bytes) => { for (let i=0;i<bytes.length;i++) memory.set(p+BigInt(i), bytes[i]); };
  const get = (p, n) => Uint8Array.from({length:n}, (_,i) => {
    const a=p+BigInt(i); if (!memory.has(a)) throw Error('Unmapped fixture read '+a.toString(16));
    return memory.get(a);
  });
  const set32=(p,n)=>{const b=Buffer.alloc(4);b.writeUInt32LE(n>>>0);put(p,b);};
  const set64=(p,n)=>{const b=Buffer.alloc(8);b.writeBigUInt64LE(n);put(p,b);};
  const read32=p=>Buffer.from(get(p,4)).readUInt32LE();
  class Pointer {
    constructor(n) { this.value = n instanceof Pointer?n.value:BigInt(n); }
    add(n) { return new Pointer(this.value+BigInt(n)); }
    sub(n) { return new Pointer(this.value-(n instanceof Pointer?n.value:BigInt(n))); }
    toInt32() { return Number(BigInt.asIntN(32,this.value)); }
    isNull() { return this.value===0n; }
    equals(other) { return this.value===other.value; }
    readPointer() { return new Pointer(Buffer.from(get(this.value,8)).readBigUInt64LE()); }
    readU8() { return get(this.value,1)[0]; }
    readS32() { return Buffer.from(get(this.value,4)).readInt32LE(); }
    readByteArray(n) { return get(this.value,n).buffer; }
    writeS32(n) { writes.push({address:this.value.toString(16),value:n});order.push('write:'+n);set32(this.value,n); }
    toString() { return '0x'+this.value.toString(16); }
  }
  for(const p of Object.values(at)) put(p,Buffer.alloc(0x200));
  const pins={};
  for(let i=0;i<pinSites.length;i++) {
    const b=Buffer.from(Array.from({length:16},(_,j)=>(i*31+j*7+11)&255));
    pins[pinSites[i]]=b.toString('hex'); put(base+BigInt(pinSites[i]),b);
  }
  if(options.badPin!==undefined) memory.set(base+BigInt(options.badPin),0xff);
  set64(base+0x4817e70n,options.noEngine?0n:at.engine);
  set64(at.engine+0x4d8n,options.noManager?0n:at.manager);
  set64(at.manager,at.head);set64(at.head+8n,at.node);put(at.head+25n,[1]);
  set64(at.node,options.treeCycle?at.node:at.head);set64(at.node+16n,at.head);
  set32(at.node+32n,options.title??12360);
  set64(at.node+0xe0n,at.vector);set64(at.node+0xe8n,at.vector+BigInt(options.vectorBytes??8));
  set32(at.vector,options.firstOption??87017);set32(at.vector+4n,options.option??87018);
  set64(base+0x4816400n,options.noApp?0n:at.app);
  set64(at.app+0x320n,options.noRegistry?0n:at.registry);
  // Independent invariant oracle over the registered title identity and payload.
  // Polynomial CRC is deliberately not shared with either production JS body.
  function checksum() {
    let c=0xffff;
    for(const b of [...get(at.node+32n,4),...get(at.vector,8)]) {
      c ^= b<<8;
      for(let i=0;i<8;i++) c=((c<<1)^((c&0x8000)?0x1021:0))&0xffff;
    }
    return c;
  }
  let stored=checksum(); if(options.staleRegistered) stored^=1;
  const initialStored=stored;
  const NativeFunction = function(address, result, args, config) {
    assert.equal(address.value,base+0x36d720n,'refresh entry');
    assert.equal(result,'uint8','AL-only return contract');
    assert.deepEqual(Array.from(args),['pointer','pointer']);
    assert.equal(config.exceptions,'propagate');
    if(options.factoryError) throw options.factoryError;
    return function(registry, object) {
      assert.equal(registry.value,at.registry,'B registry object');
      assert.equal(object.value,at.node+32n,'registered title pointer, not tree node/vector');
      assert.equal(read32(at.vector+4n),100003019,'refresh after mutation');
      calls.push({registry:registry.toString(),object:object.toString(),before:stored,current:checksum()});
      order.push('refresh');
      if(options.nativeError) throw options.nativeError;
      const result=options.refreshResult??1;
      if(result===1) stored=checksum(); // Real helper's success-only record update contract.
      return result;
    };
  };
  const context=vm.createContext({
    Process:{getModuleByName:n=>{assert.equal(n,'x2_dx11.exe');return{base:new Pointer(base)};},getCurrentThreadId:()=>771},
    NativeFunction,Uint8Array,send:event=>{order.push('send');events.push(event);}
  });
  const configured=source.replace('__TITLE_OPTION_PINS__',JSON.stringify(pins));
  assert.ok(!configured.includes('__TITLE_OPTION_PINS__'));
  vm.runInContext(configured,context,{filename:'native_title_options.js'});
  return {run:()=>context.installElsTitleOptionData(),writes,calls,events,order,checksum,
    option:()=>read32(at.vector+4n),registered:()=>stored,initialStored,
    invariant:()=>assert.equal(stored,checksum(),'registered checksum must match current title payload')};
}
function test(name, fn) { fn();cases.push({name,passed:true}); }
function rejected(name, options, message) {
  test(name,()=>{const f=fixture(candidate,options);assert.throws(f.run,message);
    assert.equal(f.writes.length,0);assert.equal(f.calls.length,0);assert.equal(f.events.length,0);
    assert.equal(f.registered(),f.initialStored);});
}

test('baseline reproduces registered-checksum mismatch',()=>{
  const f=fixture(baseline);f.run();assert.equal(f.option(),100003019);
  assert.equal(f.registered(),f.initialStored);assert.notEqual(f.checksum(),f.initialStored);
  assert.throws(f.invariant,/registered checksum must match/);
});
test('candidate restores registration invariant in correct order',()=>{
  const f=fixture(candidate);f.run();f.invariant();assert.equal(f.option(),100003019);
  assert.equal(f.calls.length,1);assert.equal(f.events.length,1);
  assert.deepEqual(f.order,['write:100003019','refresh','send']);
  const e=f.events[0];assert.equal(e.applied,true);assert.equal(e.native_integrity_refreshed,true);
  assert.equal(e.thread,771);assert.equal(e.title,12360);assert.equal(e.old_option,87018);
  assert.equal(e.option,100003019);assert.equal(e.existing_native_value,0.2);
});
for(const value of [0,2,255]) test('non-success AL '+value+' restores old value without success event',()=>{
  const f=fixture(candidate,{refreshResult:value});assert.throws(f.run,/refresh rejected/);
  assert.equal(f.option(),87018);assert.equal(f.calls.length,1);assert.equal(f.events.length,0);
  assert.equal(f.registered(),f.initialStored);f.invariant();
  assert.deepEqual(f.order,['write:100003019','refresh','write:87018']);
});
test('already-target idempotence avoids registry and native calls',()=>{
  const f=fixture(candidate,{option:100003019,noApp:true});f.run();f.invariant();
  assert.equal(f.writes.length,0);assert.equal(f.calls.length,0);
  assert.equal(f.events[0].applied,false);assert.equal(f.events[0].native_integrity_refreshed,false);
});
test('already-target does not bless an unrelated stale checksum',()=>{
  const f=fixture(candidate,{option:100003019,staleRegistered:true});f.run();
  assert.equal(f.registered(),f.initialStored);assert.equal(f.calls.length,0);
  assert.equal(f.writes.length,0);assert.throws(f.invariant,/registered checksum must match/);
  assert.equal(f.events[0].native_integrity_refreshed,false);
});
test('second invocation is idempotent',()=>{
  const f=fixture(candidate);f.run();f.run();f.invariant();
  assert.equal(f.calls.length,1);assert.equal(f.writes.length,1);assert.equal(f.events.length,2);
  assert.equal(f.events[1].applied,false);assert.equal(f.events[1].native_integrity_refreshed,false);
});
for(const rva of pinSites) rejected('prefix mismatch '+rva.toString(16)+' has no write',{badPin:rva},/identity/);
rejected('missing engine',{noEngine:true},/engine absent/);
rejected('missing title manager',{noManager:true},/manager absent/);
rejected('missing title',{title:12359},/title absent/);
rejected('tree bound',{treeCycle:true},/tree bound/);
rejected('wrong vector extent',{vectorBytes:12},/option vector changed/);
rejected('wrong first option',{firstOption:1},/option vector changed/);
rejected('unknown drop option',{option:999},/drop option changed/);
rejected('missing integrity app before raw write',{noApp:true},/integrity app absent/);
rejected('missing registry before raw write',{noRegistry:true},/registry absent/);
test('native wrapper construction failure precedes mutation',()=>{
  const error=new Error('fixture constructor failure'),f=fixture(candidate,{factoryError:error});
  assert.throws(f.run,e=>e===error);assert.equal(f.writes.length,0);assert.equal(f.calls.length,0);
  assert.equal(f.events.length,0);f.invariant();
});
test('native exception preserves identity and emits no success',()=>{
  const error=new Error('fixture native failure'),f=fixture(candidate,{nativeError:error});
  assert.throws(f.run,e=>e===error);assert.equal(f.events.length,0);assert.equal(f.calls.length,1);
  // No fictional SEH recovery: this candidate does not catch/replace propagated failures.
  assert.equal(f.option(),100003019);assert.equal(f.registered(),f.initialStored);
});
const result={passed:true,cases,case_count:cases.length,
  baseline:{path:relative(baselinePath),sha256:sha(fs.readFileSync(baselinePath)),expected_failure:'raw option change leaves stored registered checksum stale'},
  candidate:{path:relative(candidatePath),sha256:sha(fs.readFileSync(candidatePath))},
  test_source_sha256:sha(fs.readFileSync(__filename)),
  method:'Node VM executes actual production JS functions over private synthetic pointer memory; refresh is an AL-return/success-only checksum-update contract mock.',
  limits:['The oracle is independent synthetic CRC, not proof of native checksum algorithm or ABI.',
    'Native36D720/title callback emulation and exact saved-dump mismatch are separate evidence.',
    'Native propagated exception is not modeled as recoverable; false AL return rollback is verified.',
    'No gameplay stability, signed composition or installed-runtime acceptance is claimed.']};
assert.equal(cases.length,26,'the complete original behavior regression must execute');
console.log(JSON.stringify({...result,baseline_expected_failure:true}));
