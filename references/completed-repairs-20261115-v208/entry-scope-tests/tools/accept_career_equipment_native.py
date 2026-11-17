"""Original owned career callback, unchanged gear, native contribution capture.

NATIVE_USE_TEST_SCOPE: confirmation_only
Starts at 2260FD0; does not prove inventory right-click dispatch or natural UI.
"""
import hashlib,json,sqlite3,sys,tomllib
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools/pylibs')]
import psutil
from els_server.storage.inventory_state import load_items
from els_server.domain.careers import RULES
run=Path(sys.argv[1]);template=int(sys.argv[2]);assert template in (242140,242130)
i=json.loads((run/'client-process.json').read_text());p=psutil.Process(i['pid'])
assert Path(i['server_config']).resolve()==ROOT/'analysis/integration-20261015/quick-slots-acceptance.toml'
assert abs(p.create_time()-i['created'])<.001 and Path(p.exe()).resolve()==Path(i['exe']).resolve() and i['no_os_input'] and not i['play']
assert hashlib.sha256(Path(i['exe']).read_bytes()).hexdigest()==i['file_sha256']=='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
image=(ROOT/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes();assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
events=[json.loads(l) for l in (run/'server-logs/server.jsonl').read_text().splitlines()];assert [e for e in events if e.get('event')=='business_phase'][-1]['after']=='town_ready'
with closing(sqlite3.connect(ROOT/'analysis/integration-20261015/quick-slots-acceptance.sqlite3')) as db:
    items=load_items(db,1001);before=db.execute('SELECT unit_class FROM characters WHERE uid=1001').fetchone()[0]
ticket=next(i for i in items if i['template']==template);assert ticket['count']==1 and before!=RULES[template]['target']
expected=[i for i in items if i['uid']!=ticket['uid']]
code=r'''
(()=>{const m=Process.getModuleByName('x2_dx11.exe'),ticket=__TICKET__,expected=__EXPECTED__,before=__BEFORE__,after=__AFTER__;
const hex=p=>Array.from(new Uint8Array(p.readByteArray(8)),v=>v.toString(16).padStart(2,'0')).join('');
for(const [r,h] of Object.entries(__GUARDS__))if(hex(m.base.add(+r))!==h)throw Error('Career equipment prefix');
const fn=(r,t,a)=>new NativeFunction(m.base.add(r),t,a,{exceptions:'propagate'}),get=fn(0x197f500,'pointer',['pointer','uint64','uint8']),group=fn(0x197f660,'int',['pointer','uint64']),slot=fn(0x197f740,'int',['pointer','uint64']);
let started=false,done=false,received=0;const vectors=[];
function state(){const engine=m.base.add(0x4817e70).readPointer(),u=engine.add(0xc8).readPointer().add(0xa0).readPointer();if(u.isNull()||u.add(0x48).readU64().toNumber()!==1001)throw Error('Owner');return {engine,u,bag:u.add(0x440)};}
function verify(){const s=state();if(s.u.add(0x58).readU16()!==after)throw Error('Career state');const actual=expected.map(i=>{const n=get(s.bag,i.uid,0);if(n.isNull())throw Error('Missing UID '+i.uid);return {uid:i.uid,template:n.add(8).readU32(),count:n.add(20).readS32(),group:group(s.bag,i.uid),slot:slot(s.bag,i.uid),durability:n.add(16).readS32(),attributes:Array.from({length:4},(_,j)=>n.add(0x1c+4*j).readS32())};});
for(let j=0;j<expected.length;j++){const a=actual[j],e=expected[j];if(a.template!==e.template||a.count!==e.count||a.group!==e.group||a.slot!==e.slot||a.durability!==(e.durability||0)||JSON.stringify(a.attributes)!==JSON.stringify(e.attributes||[0,0,0,0]))throw Error('Inventory mismatch '+JSON.stringify({a,e}));}
if(!get(s.bag,ticket.uid,0).isNull())throw Error('Ticket not consumed');
send({event:'career_equipment_accepted',before,after,ticket,items:actual,equipmentVectors:vectors,direct_inventory_write:false});done=true;cleanup();}
const stats=Interceptor.attach(m.base.add(0x862160),{onEnter(a){this.ours=started&&!done&&a[0].equals(state().u);this.out=a[1];this.cls=state().u.add(0x58).readU16();},onLeave(){if(this.ours)vectors.push({unit_class:this.cls,values:Array.from({length:13},(_,j)=>this.out.add(j*4).readFloat())});}});
const notice=Interceptor.attach(m.base.add(0xb9c380),{onLeave(){if(started&&!done)received=Date.now();}});
const frame=Interceptor.attach(m.base.add(0x30d0660),{onLeave(){if(done)return;try{if(received&&Date.now()-received>1000){verify();return;}if(started)return;const s=state();if(s.u.add(0x58).readU16()!==before)throw Error('Initial class');const n=get(s.bag,ticket.uid,0);if(n.isNull()||n.add(8).readU32()!==ticket.template)throw Error('Ticket');const text=Memory.alloc(32);text.writeByteArray(Array(32).fill(0));text.add(24).writeU64(7);started=true;
fn(0x2260fd0,'void',['pointer','uint64','uint64','uint64','uint8','pointer'])(s.engine.add(0x558).readPointer().add(0x18).readPointer(),ticket.uid,0,0,0,text);
send({event:'career_equipment_requested',before,after,ticket});
}catch(e){send({event:'career_equipment_error',error:String(e)});done=true;cleanup();}}});
function cleanup(){for(const h of [stats,notice,frame])h.detach();}
setTimeout(()=>{cleanup();if(!done)send({event:'career_equipment_timeout',before,after});},30000);
})();
'''
for a,b in [('__TICKET__',ticket),('__EXPECTED__',expected),('__BEFORE__',before),('__AFTER__',RULES[template]['target']),('__GUARDS__',{r:image[r:r+8].hex() for r in (0x197f500,0x197f660,0x197f740,0x2260fd0,0x862160,0xb9c380)})]:code=code.replace(a,json.dumps(b))
(run/f'career-equipment-{template}.js').write_text(code,encoding='utf8');(run/'probe-extension.js').write_text(code,encoding='utf8')
print('Queued',template)
