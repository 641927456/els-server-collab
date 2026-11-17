"""Use one coupon through the original confirmation callback on a disposable save.

NATIVE_USE_TEST_SCOPE: confirmation_only
Starts at 2260FD0; does not prove inventory right-click dispatch or natural UI.
"""
import hashlib,json,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/pylibs')]
import psutil
run=Path(sys.argv[1]).resolve();i=json.loads((run/'client-process.json').read_text());p=psutil.Process(i['pid'])
config=ROOT/'analysis/integration-20261015/expansion-coupon-acceptance.toml'
assert Path(i['server_config']).resolve()==config.resolve()
assert tomllib.loads(config.read_text())['server']['state_file']=='expansion-coupon-acceptance.sqlite3'
assert i['no_os_input'] and i['item_test'] and not i['play']
assert abs(p.create_time()-i['created'])<.001 and Path(p.exe()).resolve()==Path(i['exe']).resolve()
assert hashlib.sha256(Path(i['exe']).read_bytes()).hexdigest()==i['file_sha256']=='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
image=(ROOT/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
events=[json.loads(l) for l in (run/'server-logs/server.jsonl').read_text().splitlines()]
assert [e for e in events if e.get('event')=='business_phase'][-1]['after']=='town_ready','Wait for the real 227/228 scene handshake'
assert not any(e.get('event')=='client_request' and e.get('kind')==0x219 for e in events)
item=json.loads((config.parent/'expansion-coupon-item.json').read_text());assert item['template']==274160
code=r'''
(()=>{
 const m=Process.getModuleByName('x2_dx11.exe'),item=__ITEM__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h] of Object.entries(__PREFIXES__))if(hex(m.base.add(+r),8)!==h)throw Error('Coupon guard '+r);
 const fn=(r,t,a)=>new NativeFunction(m.base.add(r),t,a,{exceptions:'propagate'});
 const current=()=>{
  const manager=m.base.add(0x4817e70).readPointer(),game=manager.add(0xc8).readPointer();if(game.isNull())return null;
  const u=game.add(0xa0).readPointer();if(u.isNull()||u.add(0x48).readU64().toString()!=='1001')return null;
  const p=fn(0x197f500,'pointer',['pointer','uint64','uint8'])(u.add(0x440),item.uid,0);
  return {manager,u,p,state:fn(0x8face0,'int',['pointer','int'])(u.add(0x7c8),0)};
 };
 const notice=Interceptor.attach(m.base.add(0x9b8b50),{onLeave(){const c=current();if(c)send({event:'coupon_native_applied',state:c.state,item_absent:c.p.isNull(),pid:Process.id});}});
 let sent=false,readyAt=0;const frame=Interceptor.attach(m.base.add(0x30d0660),{onLeave(){if(sent)return;
  try{const c=current();if(!c)return;if(c.p.isNull())return;
   if(!readyAt)readyAt=Date.now();if(Date.now()-readyAt<2000)return;
   if(c.state===2||c.p.readU64().toString()!==String(item.uid)||c.p.add(8).readU32()!==274160||c.p.add(0x14).readU32()!==1)throw Error('Coupon precondition');
   sent=true;frame.detach();const text=Memory.alloc(32);text.writeByteArray(Array(32).fill(0));text.add(24).writeU64(7);
   const controller=c.manager.add(0x558).readPointer().add(0x18).readPointer();
   send({event:'coupon_native_before',state:c.state,item_uid:item.uid,template:item.template});
   fn(0x2260fd0,'void',['pointer','uint64','uint64','uint64','uint8','pointer'])(controller,item.uid,0,0,0,text);
   send({event:'coupon_native_confirmation_called',pid:Process.id,no_os_input:true});
  }catch(e){sent=true;frame.detach();send({event:'coupon_native_error',error:String(e)});}
 }});setTimeout(()=>frame.detach(),90000);setTimeout(()=>notice.detach(),90000);
})();
'''.replace('__ITEM__',json.dumps(item)).replace('__PREFIXES__',json.dumps({r:image[r:r+8].hex() for r in (0x30d0680,0x2260fd0,0x197f500,0x8face0,0x9b8b50)}))
(run/'probe-extension.js').write_text(code,encoding='utf8')
print('Queued one original confirmation callback on isolated coupon save.')
