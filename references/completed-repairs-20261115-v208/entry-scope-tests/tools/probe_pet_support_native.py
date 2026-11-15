"""Bounded original UI actions in this task's isolated acceptance process.

NATIVE_USE_TEST_SCOPE: confirmation_only
The confirm action starts at 2260FD0 and does not prove right-click dispatch;
the separate rightclick action must supply that evidence.
"""
import hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/pylibs')]
import psutil
run=Path(sys.argv[1]).resolve();action=sys.argv[2]
info=json.loads((run/'client-process.json').read_text());p=psutil.Process(info['pid'])
assert info['no_os_input'] and not info['play'] and Path(info['server_config']).resolve()==ROOT/'analysis/pet-mount-20261015/acceptance.toml'
assert abs(p.create_time()-info['created'])<.001 and Path(p.exe()).resolve()==Path(info['exe']).resolve()
image=(ROOT/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes();assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
item=None
if action in ('rightclick','confirm','equip'):
    template=int(sys.argv[3]);assert template in (500720,164566,330562,135974,135975,135976,980035)
    with sqlite3.connect(ROOT/'analysis/pet-mount-20261015/acceptance.sqlite3') as db:
        r=db.execute('SELECT uid,template,bag_group,slot,count FROM inventory_items WHERE owner=1001 AND template=?',(template,)).fetchall()
    assert len(r)==1;item=dict(zip(('uid','template','group','slot','count'),r[0]))
assert action in ('read','rightclick','confirm','show-life','equip','auto-open','auto-bind','auto-settings','auto-trigger')
code=r'''
(()=>{const m=Process.getModuleByName('x2_dx11.exe'),hx=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
const get=new NativeFunction(m.base.add(0x4ab6d0),'pointer',['pointer'],{exceptions:'propagate'});
const str=p=>{const n=p.add(16).readU64().toNumber(),cap=p.add(24).readU64().toNumber();if(n>4096||cap<n)throw Error('Native string bound');return n?(cap>7?p.readPointer():p).readUtf16String(n):'';};
let done=false;const hook=Interceptor.attach(m.base.add(0x30d0660),{onLeave(){if(done)return;try{
 const gm=m.base.add(0x4817e70).readPointer(),u=gm.add(0xc8).readPointer().add(0xa0).readPointer();if(u.isNull()||u.add(0x48).readU64().toString()!=='1001')return;
 done=true;hook.detach();const ui=gm.add(0x558).readPointer(),panel=ui.add(0x70).readPointer();
 const begin=u.add(0x2e10).readPointer(),n=u.add(0x2e18).readPointer().sub(begin).toInt32()/0xfb;if(n<0||n>1000||!Number.isInteger(n))throw Error('Pet vector bound');
 const pets=[];for(let j=0;j<n;j++){const p=begin.add(j*0xfb),head=p.add(0x47).readPointer(),count=p.add(0x4f).readU64().toNumber(),gear=[];if(count>16)throw Error('Pet gear bound');
 const walk=(node,depth)=>{if(node.equals(head))return;if(depth>16||node.add(25).readU8())throw Error('Pet gear topology');walk(node.readPointer(),depth+1);gear.push({slot:node.add(28).readS32(),template:node.add(32).readS32(),socket:node.add(36).readS32()});walk(node.add(16).readPointer(),depth+1);};walk(head.add(8).readPointer(),0);if(gear.length!==count)throw Error('Pet gear count');
 pets.push({uid:p.readU64().toString(),unit:p.add(8).readS32(),name:str(p.add(12)),pickup:p.add(0xc2).readU8(),pickupExpiry:p.add(0xc3).readU64().toString(),gear});}
 const sm=new NativeFunction(m.base.add(0x166890),'pointer',[],{exceptions:'propagate'})(),strings={};for(const id of [0xcd96,0xcd97]){const b=sm.add(8).readPointer(),n=sm.add(16).readPointer().sub(b).toInt32()/32;if(n<id||n>1000000)throw Error('String table bound');strings[id]=str(b.add(id*32));}
 let slots=null;try{const main=get(panel.add(0x1a0)),petinfo=get(main.add(0x90));slots={mainVtable:main.readPointer().sub(m.base).toString(),petInfoVtable:petinfo.readPointer().sub(m.base).toString(),count:main.add(0x154).readS32()};}catch(e){slots={error:String(e)};}
 const potion=new NativeFunction(m.base.add(0x197f500),'pointer',['pointer','uint64','uint8'],{exceptions:'propagate'})(u.add(0x440),1001001,0),pm=gm.add(0x5e8).readPointer();send({event:'pet_support_native_consumable_state',count:potion.isNull()?0:potion.add(0x14).readS32(),activePet:u.add(0x2e28).readU64().toString(),automaticTimers:pm.isNull()?null:[pm.add(0x548).readFloat(),pm.add(0x54c).readFloat()]});
 send({event:'pet_support_native_state',action:__ACTION__,pets,automaticHex:hx(u.add(0x2fac),24),strings,slots,autoControl:panel.add(0x140).readPointer().isNull()?null:panel.add(0x140).readPointer().readPointer().sub(m.base).toString(),timestamp:Date.now()});
 if(__ACTION__==='show-life'){new NativeFunction(m.base.add(0x22f0a40),'void',['pointer','uint64','uint64','uint64','uint8'],{exceptions:'propagate'})(ui,0x2d,1,0,0);new NativeFunction(m.base.add(0x22387f0),'uint8',['pointer','int','int'],{exceptions:'propagate'})(ui.add(0x18).readPointer(),21,-1);send({event:'pet_support_native_life_bag_open'});}
 if(__ACTION__==='equip'){
  const item=__ITEM__,slot=__SLOT__;if(panel.add(0x48).readU64().toString()!=='1001076'||panel.add(0x160).readU64().toString()!==String(item.uid))throw Error('Native selected owned pet/accessory mismatch');
  new NativeFunction(m.base.add(0x3020900),'void',['pointer','int'],{exceptions:'propagate'})(panel,slot);send({event:'pet_support_native_equipment_confirm',item,slot,source:'301C580 ->3020900 original confirmation callback'});
 }
 if(__ACTION__==='auto-open'){new NativeFunction(m.base.add(0x17a2d0),'void',['pointer','uint','uint','pointer','uint8'],{exceptions:'propagate'})(m.base.add(0x4816400).readPointer(),0x467,0xac09,ptr(0),1);send({event:'pet_support_native_auto_open'});}
 if(__ACTION__==='auto-bind'){
  const owned=new NativeFunction(m.base.add(0x197f500),'pointer',['pointer','uint64','uint8'],{exceptions:'propagate'})(u.add(0x440),1001001,0);if(owned.isNull()||owned.add(8).readU32()!==77000||owned.add(0x14).readS32()<1)throw Error('Owned ordinary potion');
  const control=panel.add(0x140).readPointer(),out=Memory.alloc(8),text=Memory.alloc(32);if(control.isNull())throw Error('Native automatic panel not open');const handles=[];for(let off=0;off<0x130;off+=8){try{const z=get(control.add(off));if(!z.isNull())handles.push({off:off,vtable:z.readPointer().sub(m.base).toString()});}catch(e){}}send({event:'pet_support_native_control_handles',handles});const autoUI=get(control.add(0x128));send({event:'pet_support_native_auto_ui',vtable:autoUI.readPointer().sub(m.base).toString()});out.writePointer(autoUI.add(0xd0).readPointer());
  const container=get(out),inner=Memory.alloc(8),slotName=Memory.alloc(32);inner.writeU64(0);new NativeFunction(m.base.add(0x152210),'pointer',['pointer','pointer'],{exceptions:'propagate'})(slotName,Memory.allocUtf16String('Item'));new NativeFunction(container.readPointer().add(0x2b8).readPointer(),'pointer',['pointer','pointer','pointer'],{exceptions:'propagate'})(container,inner,slotName);out.writePointer(inner.readPointer());new NativeFunction(m.base.add(0x152710),'void',['pointer'],{exceptions:'propagate'})(slotName);
  const widget=new NativeFunction(m.base.add(0x523020),'pointer',['pointer'],{exceptions:'propagate'})(out);if(widget.isNull())throw Error('Native HP item widget missing');
  const vf=off=>new NativeFunction(widget.readPointer().add(off).readPointer(),'int',['pointer'],{exceptions:'propagate'})(widget);send({event:'pet_support_native_widget',group:vf(0x290),slot:vf(0x278),vtable:widget.readPointer().sub(m.base).toString()});if(![18,24].includes(vf(0x290))||vf(0x278)!==0)throw Error('Native automatic HP widget identity');
  send({event:'pet_support_native_auto_bind_start',uid:'1001001',group:vf(0x290),slot:vf(0x278)});
  new NativeFunction(m.base.add(0x3058810),'void',['pointer','uint64','pointer'],{exceptions:'propagate'})(ui.add(0x58).readPointer(),1001001,out.readPointer());
 }
 if(__ACTION__==='auto-settings'){
  const control=panel.add(0x140).readPointer();if(control.isNull()||!control.readPointer().equals(m.base.add(0x42e41f0)))throw Error('Native automatic controller identity');
  new NativeFunction(m.base.add(0x3023cf0),'void',['pointer','uint8','int'],{exceptions:'propagate'})(control,1,60);
  new NativeFunction(m.base.add(0x3020540),'void',['pointer'],{exceptions:'propagate'})(panel);send({event:'pet_support_native_auto_settings_saved',hp_seconds:60,original_ui:true});
 }
 if(__ACTION__==='auto-trigger'){
  // Explicit test input to the original low-HP trigger; no HP/item/model writes.
  new NativeFunction(m.base.add(0x2dcacf0),'void',['uint64','uint8','float'],{exceptions:'propagate'})(1001,1,.25);send({event:'pet_support_native_auto_trigger',test_hp_ratio:.25,original_condition_callback:true});
 }
}catch(e){done=true;hook.detach();send({event:'pet_support_native_error',error:String(e)});}}});setTimeout(()=>hook.detach(),20000);
})();
'''.replace('__ACTION__',json.dumps(action)).replace('__ITEM__',json.dumps(item)).replace('__SLOT__',str(int(sys.argv[4]) if action=='equip' else 1))
if action=='rightclick':
    click=(ROOT/'tools/request_fashion_rightclick.js').read_text().replace('__ITEM__',json.dumps(item)).replace('__PREFIXES__',json.dumps({r:image[r:r+8].hex() for r in (0x4ab6d0,0x197f500,0x197f660,0x220ebd0)}))
    click=click.replace('!==27','!=='+str(item['group'])).replace('fashion','pet_support').replace('Fashion','Pet support')
    code+='\n'+click
if action=='confirm':
    assert item['template'] in (500720,164566,330562)
    code+=r'''
(()=>{const m=Process.getModuleByName('x2_dx11.exe'),item=__ITEM__;let done=false;
const h=Interceptor.attach(m.base.add(0x30d0660),{onLeave(){if(done)return;try{
 const gm=m.base.add(0x4817e70).readPointer(),u=gm.add(0xc8).readPointer().add(0xa0).readPointer();if(u.isNull()||u.add(0x48).readU64().toString()!=='1001')return;
 const ui=gm.add(0x558).readPointer(),panel=ui.add(0x70).readPointer(),p=new NativeFunction(m.base.add(0x197f500),'pointer',['pointer','uint64','uint8'],{exceptions:'propagate'})(u.add(0x440),item.uid,0);
 if(p.isNull()||p.add(8).readU32()!==item.template||p.add(0x14).readU32()!==1)throw Error('Owned coupon identity');
 const target=item.template===500720?panel.add(0x48).readU64():uint64(0);if(item.template===500720&&target.toString()!=='1001076')throw Error('Owned selected native pet');
 done=true;h.detach();const text=Memory.alloc(32);text.writeByteArray(Array(32).fill(0));text.add(24).writeU64(7);
 new NativeFunction(m.base.add(0x2260fd0),'void',['pointer','uint64','uint64','uint64','uint8','pointer'],{exceptions:'propagate'})(ui.add(0x18).readPointer(),item.uid,target,0,0,text);
 send({event:'pet_support_native_confirmation',item,target:target.toString(),source:'original 2260FD0 confirmation callback',timestamp:Date.now()});
}catch(e){done=true;h.detach();send({event:'pet_support_native_confirmation_error',error:String(e)});}}});setTimeout(()=>h.detach(),15000);})();
'''.replace('__ITEM__',json.dumps(item))
phases=[json.loads(l) for l in (run/'server-logs/server.jsonl').read_text(encoding='utf8').splitlines()]
phase=[x for x in phases if x.get('event')=='business_phase'][-1]['after']
if phase=='dungeon_active':code=code.replace('m.base.add(0x30d0660)','m.base.add(0xc231c0)')
(run/'probe-extension.js').write_text(code,encoding='utf8');print('Queued',action,item or '')
