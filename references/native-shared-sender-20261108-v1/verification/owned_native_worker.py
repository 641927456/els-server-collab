"""Only add same-script observations to the existing owned client probe."""
from pathlib import Path
import runpy,sys
H=Path(__file__).resolve().parent;C=H.parent/'repair-v9/candidate'
BASELINE='--baseline'in sys.argv
if BASELINE:sys.argv.remove('--baseline')
sys.path[:0]=[str(C/'tools'),str(C),str(C/'tools/pylibs')]
import native_cache_sync
compose=native_cache_sync.compose
def observed(*args):
 source=compose(*args).replace('__LIGHTWEIGHT_PLAY__','false')
 if BASELINE:source=source.replace('  prepareElsNativeSendSerialization()();','  // Owned no-lock baseline.')
 return source+('''\n
const ownedSendCheck=setInterval(()=>{
 const installed=globalThis.elsNativeSendSerialization;
 if(!installed&&!(__OWNED_BASELINE__&&elsNativeCacheSync))return;
 const repeated=installed?prepareElsNativeSendSerialization()():null;
 const recursion=()=>installed?installed.lock.add(12).readS32():0;
 note({event:'owned_send_serialization_loaded',active:installed?installed.active():false,repeated_install_same:!!installed&&installed===repeated,baseline:__OWNED_BASELINE__});
 const ownedSenderAliases=new Map();
 elsObserveNativeSend({
  onEnter(args){this.kind=args[1].add(0x34).readU16();const key=args[0].toString();if(!ownedSenderAliases.has(key))ownedSenderAliases.set(key,ownedSenderAliases.size+1);note({event:'owned_send_enter',kind:this.kind,sender_alias:ownedSenderAliases.get(key),lock_recursion:recursion(),caller_RVA:this.returnAddress.sub(Process.getModuleByName('x2_dx11.exe').base).toString()});},
  onLeave(){note({event:'owned_send_leave',kind:this.kind});}
 });
 elsObserveNativeSend({onLeave(){note({event:'owned_send_leave_only'});}});
 setInterval(()=>note({event:'owned_send_lock_state',recursion:recursion(),logical_observers:installed.observerCount()}),500);
 clearInterval(ownedSendCheck);
},250);
'''.replace('__OWNED_BASELINE__','true'if BASELINE else'false'))
native_cache_sync.compose=observed
sys.argv=[str(C/'tools/probe_updated_client.py'),*sys.argv[1:]]
runpy.run_path(sys.argv[0],run_name='__main__')
