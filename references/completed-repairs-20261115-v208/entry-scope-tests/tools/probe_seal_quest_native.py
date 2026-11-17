"""Original quest UI callbacks on this chat's exact disposable process/save.

NATIVE_USE_TEST_SCOPE: confirmation_only
The use action starts at 2260FD0; quest UI callbacks do not prove item right-click.
"""
import hashlib,json,sys,time,tomllib,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/pylibs')]
import psutil
run=Path(sys.argv[1]).resolve();op=sys.argv[2];qid=int(sys.argv[3]) if len(sys.argv)>3 else 6980
if op not in ('inspect','show','accept','claim','use','abandon') or qid not in (6980,6990,35130):raise ValueError('Scoped seal acceptance action')
config=ROOT/'analysis/seal-quests-20261015/acceptance/server.toml'
info=json.loads((run/'client-process.json').read_text(encoding='utf8'));p=psutil.Process(info['pid'])
assert info['no_os_input'] and not info['play'] and info['item_test']
assert abs(p.create_time()-info['created'])<.001 and Path(p.exe()).resolve()==Path(info['exe']).resolve()
assert Path(info['server_config']).resolve()==config.resolve()
assert tomllib.loads(config.read_text(encoding='utf8'))['server']['state_file']=='seal-acceptance.sqlite3'
assert hashlib.sha256(Path(info['exe']).read_bytes()).hexdigest()==info['file_sha256']=='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
image=(ROOT/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
item=None
if op=='use':
    import sqlite3
    from contextlib import closing
    from els_server.storage.inventory_state import load_items
    from els_server.storage.seal_quests import QuestState
    save=config.parent/'seal-acceptance.sqlite3'
    assert 6990 in QuestState(save,account_id=1).completed()
    with closing(sqlite3.connect(save)) as db:items=[i for i in load_items(db,1001) if i['template']==276289]
    assert len(items)==1 and items[0]['count']==1
    item=items[0]
token=uuid.uuid4().hex
code=r'''
(()=>{
const m=Process.getModuleByName('x2_dx11.exe'),op=__OP__,qid=__QID__,item=__ITEM__;
const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
for(const [r,h] of Object.entries(__PREFIXES__))if(hex(m.base.add(+r),8)!==h)throw Error('Seal acceptance build guard '+r);
const fn=(r,t,a)=>new NativeFunction(m.base.add(r),t,a,{exceptions:'propagate'});
const tracked=[];
for(const r of [0x3044b00,0xb8ce40,0x3047020,0x9ba470,0x13a34f0])tracked.push(Interceptor.attach(m.base.add(r),{
 onEnter(a){this.buf=a[4];this.before=this.buf.add(32).readU32();const p=this.buf.add(8).readPointer(),end=this.buf.add(16).readPointer();this.size=end.sub(p).toInt32();this.body=this.size>0&&this.size<=65536?hex(p,Math.min(this.size,48)):null;},
 onLeave(){send({event:'seal_native_handler',rva:r,start:this.before,end:this.buf.add(32).readU32(),size:this.size,body_prefix:this.body});}
}));
tracked.push(Interceptor.attach(m.base.add(0x7b4c20),{onEnter(a){if([0xee,0xf4,0x219].includes(a[1].toInt32()))send({event:'seal_native_request',kind:a[1].toInt32(),dto:hex(a[2],29)});}}));
tracked.push(Interceptor.attach(m.base.add(0xda3620),{onEnter(a){this.buf=a[0].add(8).readPointer();this.start=this.buf.add(32).readU32();},onLeave(v){send({event:'seal_native_initialization',ok:v.toInt32()&255,start:this.start,end:this.buf.add(32).readU32()});}}));
function tree(head,keyOffset,valueOffset){const out=[],seen=new Set(),pending=[head.add(8).readPointer()];while(pending.length){const n=pending.pop();if(n.equals(head)||n.add(25).readU8())continue;if(seen.has(n.toString())||seen.size>1000)throw Error('Native tree bound');seen.add(n.toString());out.push({key:n.add(keyOffset).readS32(),value:valueOffset===null?null:n.add(valueOffset).readPointer()});pending.push(n.readPointer(),n.add(16).readPointer());}return out;}
let done=false;
const frame=Interceptor.attach(m.base.add(0x30d0660),{onEnter(a){this.state=a[0];},onLeave(){if(done)return;
 try{
  const s=this.state;if(s.isNull()||!s.readPointer().add(0x188).readPointer().equals(m.base.add(0x311c030)))return;
  const e=m.base.add(0x4817e70).readPointer(),g=e.add(0xc8).readPointer(),u=g.add(0xa0).readPointer();
  if(u.isNull()||u.add(0x48).readU64().toString()!=='1001')return;
  const manager=e.add(0x88).readPointer(),ui=e.add(0x558).readPointer(),window=ui.add(0x60).readPointer();
  if(window.isNull()||!window.readPointer().equals(m.base.add(0x42e3d68)))throw Error('Native quest window identity');
  const active=tree(manager.add(0x88).readPointer(),32,40).map(row=>{const task=row.value,begin=task.add(16).readPointer(),end=task.add(24).readPointer(),n=end.sub(begin).toInt32()/8;if(!Number.isInteger(n)||n<0||n>50)throw Error('Native objective vector bound');return {id:row.key,objectives:Array.from({length:n},(_,i)=>({id:begin.add(i*8).readS32(),count:begin.add(i*8+4).readU16(),completed:begin.add(i*8+6).readU8()}))};});
  const seals=tree(u.add(0x7c8+0xb0).readPointer(),28,null).map(v=>v.key);
  done=true;frame.detach();send({event:'seal_native_state',token:__TOKEN__,op,qid,pid:Process.id,active,completed:[6980,6990].filter(id=>fn(0xcb0e60,'uchar',['pointer','int'])(manager,id)),unsealed:seals,window_visible:window.add(0x128).readU8()});
  if(op==='show')fn(0x3031f90,'void',['pointer','uchar','int','int'])(window,1,0,0);
  if(op==='accept')send({event:'seal_native_accept',qid,result:fn(0x3044800,'uint64',['pointer','int'])(window,qid).toString()});
  if(op==='claim'){fn(0x302f620,'void',['pointer','uint64','uint64','uint64','int'])(window,0,0,41005,qid);send({event:'seal_native_claim',qid});}
  if(op==='abandon'){fn(0x3046360,'uchar',['pointer','int'])(window,qid);send({event:'seal_native_abandon',qid});}
  if(op==='use'){
   const p=fn(0x197f500,'pointer',['pointer','uint64','uchar'])(u.add(0x440),item.uid,0);
   if(p.isNull()||p.readU64().toString()!==String(item.uid)||p.add(8).readU32()!==276289||p.add(0x14).readU32()!==1)throw Error('Owned awarded book identity');
   const text=Memory.alloc(32);text.writeByteArray(Array(32).fill(0));text.add(24).writeU64(7);
   fn(0x2260fd0,'void',['pointer','uint64','uint64','uint64','uchar','pointer'])(ui.add(0x18).readPointer(),item.uid,0,0,0,text);
   send({event:'seal_native_book_use',uid:item.uid,template:item.template,original_confirmation:true});
  }
 }catch(e){done=true;frame.detach();send({event:'seal_native_error',token:__TOKEN__,error:String(e),stack:e.stack});}
}});
setTimeout(()=>{frame.detach();for(const h of tracked)h.detach();},90000);
})();
'''.replace('__TOKEN__',json.dumps(token)).replace('__OP__',json.dumps(op)).replace('__QID__',str(qid)).replace('__ITEM__',json.dumps(item)).replace('__PREFIXES__',json.dumps({r:image[r:r+8].hex() for r in (0x30d0680,0x3044800,0x302f620,0x3031f90,0x3046360,0xcb0e60,0x2260fd0)}))
(run/'probe-extension.js').write_text(code,encoding='utf8')
deadline=time.monotonic()+60
while time.monotonic()<deadline:
    rows=[]
    for line in (run/'trace.jsonl').read_text(encoding='utf8').splitlines():
        try:row=json.loads(line).get('payload',{})
        except ValueError:continue
        if row.get('token')==token:rows.append(row)
    if rows:
        if any(r.get('event')=='seal_native_error' for r in rows):raise RuntimeError(rows)
        print('Original seal UI callback reached',op,qid,'on owned PID',info['pid']);break
    time.sleep(.25)
else:raise TimeoutError('Original seal callback did not reach the owned town frame')
