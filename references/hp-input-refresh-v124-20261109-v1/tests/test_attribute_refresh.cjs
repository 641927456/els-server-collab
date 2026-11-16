// Execute the production scheduler and ability application, with observable
// substitutes for native calls. This is a component regression, not GUI proof.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const here = __dirname;
const parent = path.join(here, 'fixtures/baseline-native-cache-sections.js');
const candidate = path.join(here, '../source/tools/native_cache_sync.js');

function fixture(file) {
  const text = fs.readFileSync(file, 'utf8');
  const due = text.slice(text.indexOf(' function refreshDue('), text.indexOf(' function sevenAt('));
  const ability = text.slice(text.indexOf(' function abilityInputs('), text.indexOf('\n let busy='));
  assert.ok(due.startsWith(' function refreshDue(') && ability.startsWith(' function abilityInputs('));
  const context = vm.createContext({ Math, Number, Error, Map, Array });
  vm.runInContext(`
    let now=0, epoch='scene1', side=0, fallback=0, current=552259.9375, maximum=767641.3125, multiplier=1.39;
    let builds=0, originalClamps=0, emitted=[];
    let disabled=false, abilityBusy=false, nativeBuildDepth=0, mainThread=1, thread=1, busy=false, writes=0;
    let refreshEpoch='', powerSkipped=0, abilitySkipped=0, identity='owner', refreshRecords=new Map(), refreshIntervalMs=250;
    let abilityCalculations=0, abilityMs=0, abilityOutsideCacheMs=0, finalInputWrites=0, actorBaseWrites=0, immediateAbilityCalculations=0, healthClamps=0;
    const first=[552259.9375,29801.33203125,50689.91015625,14336.4912109375,22176.328125,14861.4716796875,15680.255859375];
    const second=[650000,20000,30000,4000,5000,6000,7000];
    const naked=[157000,1202,1202,0,0,300.5,300.5];
    let built=[first.slice(),second.slice()], memory=new Map();
    class Pointer {
      constructor(address){this.address=address;}
      add(n){return new Pointer(this.address+n);}
      equals(other){return this.address===other.address;}
      toString(){return '0x'+this.address.toString(16);}
      readS32(){if(this.address===0x100000+0x2f54)return side;throw Error('unmapped signed scalar');}
      readU8(){if(this.address===0x100000+0x2f50)return fallback;throw Error('unmapped byte');}
      readPointer(){
        if(this.address===0x100000+0x29c0)return new Pointer(0x500000);
        if(this.address===0x200000)return new Pointer(0x300000);
        if(this.address===0x300000+0x4f8)return module.base.add(0x18e8300);
        if(this.address===0x300000+0x2f0)return module.base.add(0x19204f0);
        throw Error('unmapped pointer '+this.toString());
      }
    }
    const module={base:new Pointer(0x140000000)}, unit=new Pointer(0x100000), actor=new Pointer(0x200000);
    const selected={uid:'1007',family:5,klass:164,unit};
    memory.set(unit.add(0x220).address,naked.slice());memory.set(unit.add(0x268).address,first.slice());
    memory.set(unit.add(0x2b0).address,first.slice());memory.set(actor.add(0x1698).address,first.slice());
    const Process={getCurrentThreadId:()=>thread}, Date={now:()=>now}, bytes=()=>epoch;
    const describe=()=>true, sameSeven=(a,b)=>a.every((v,i)=>v===b[i]), sevenAt=p=>memory.get(p.address).slice();
    function completeAbility(u,n){builds++;const values=built[n].slice();return{values,input:values};}
    function supplyFinalInputs(uid,a,b){memory.set(unit.add(0x268).address,a.slice());memory.set(unit.add(0x2b0).address,b.slice());}
    function supplyActorBase(a,input){memory.set(a.add(0x1698).address,input.slice());}
    const currentHP=()=>current, maximumHP=()=>maximum;
    function refreshActor(a){maximum=Math.fround(memory.get(a.add(0x1698).address)[0]*multiplier);}
    function clampCurrentHP(a,v){current=v;}
    const emit=(name,row)=>emitted.push({name,...row});
    ${due}
    ${ability}
    globalThis.api={
      at(t){now=t;}, overwrite(){memory.set(actor.add(0x1698).address,naked.slice());},
      hp(v){current=v;}, multiplier(v){multiplier=v;}, desired(v){built[0]=[v,...first.slice(1)];},
      side(n,f=0){selected.family=10;side=n;fallback=f;}, epoch(v){epoch=v;},
      frame(){abilityInputs(unit,selected,actor,'before-original-Actor-refresh');refreshActor(actor);if(current>maximum){current=maximum;originalClamps++;}},
      read(){return JSON.parse(JSON.stringify({current,maximum,builds,originalClamps,healthClamps,disabled,actorBaseWrites,powerSkipped,abilitySkipped,finalInputWrites,emitted}));}
    };
  `, context);
  return context.api;
}

const baseline=fixture(parent);
baseline.frame();baseline.at(50);baseline.overwrite();baseline.frame();
assert.equal(baseline.read().current,218230);
assert.equal(baseline.read().originalClamps,1);

const repaired=fixture(candidate);
repaired.frame();const initialBuilds=repaired.read().builds;
repaired.at(20);repaired.frame();assert.equal(repaired.read().builds,initialBuilds);
for (const time of [50,100,150]) {
  repaired.at(time);repaired.overwrite();repaired.frame();
  assert.equal(repaired.read().current,552259.9375);
  assert.equal(repaired.read().maximum,767641.3125);
  assert.equal(repaired.read().originalClamps,0);
  assert.equal(repaired.read().healthClamps,0);
}
repaired.hp(123456);repaired.at(170);repaired.overwrite();repaired.frame();
assert.equal(repaired.read().current,123456); // No free healing of injured players.
const beforeStable=repaired.read().builds;
for (let time=171;time<400;time+=10){repaired.at(time);repaired.frame();}
assert.equal(repaired.read().builds,beforeStable); // Stable frames retain the budget.
repaired.at(500);repaired.desired(50000);repaired.frame();
assert.equal(repaired.read().current,69500); // A real maximum reduction still clamps.
assert.equal(repaired.read().healthClamps,1);
assert.equal(repaired.read().disabled,false);

for (const [side,fallback] of [[0,0],[1,0],[2,0],[2,1]]) {
  const luciel=fixture(candidate);luciel.side(side,fallback);luciel.frame();
  const expected=luciel.read().maximum;
  luciel.at(25);luciel.overwrite();luciel.frame();
  assert.equal(luciel.read().maximum,expected);
  assert.equal(luciel.read().current,552259.9375);
  assert.equal(luciel.read().originalClamps,0);
}

const result={ok:true,baseline_reproduced:true,cases:[
  '3A3 overwrite within refresh budget preserves current HP',
  'repeated updates remain immediate', 'injured HP never healed',
  'stable frames retain native calculation budget', 'actual equipment reduction still clamps',
  'LuCiel active and fallback sides'], native_calls:'observable substitutes', natural_GUI:false};
console.log(JSON.stringify(result));
