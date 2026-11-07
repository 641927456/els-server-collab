"""Read-only FH4 decoding using the installed MSVC ehdata4_export.h format."""
from pathlib import Path
import bisect,hashlib,json,os,struct,sys
H=Path(__file__).resolve().parent;os.environ['ELS_RUNTIME_IMAGE']='G:/els/analysis/client-6c6b5180/x2-runtime.bin';sys.path.insert(0,'G:/els');import runtime_queries as r
b=r.b
def uvar(p):
 n=1
 while n<5 and b[p]&(1<<(n-1)):n+=1
 shift=32-7*n if n<5 else 0
 return struct.unpack_from('<I',b,p+n-4)[0]>>shift,p+n
def i32(p):return struct.unpack_from('<i',b,p)[0],p+4
meta=0x443b09c;header=b[meta];p=meta+1;assert header==0x28
uw,p=i32(p);ip,p=i32(p);n,p=uvar(uw);assert 0<n<64;entries=[]
for state in range(n):
 start=p;value,p=uvar(p);kind=value&3;action=None;obj=None
 if kind:action,p=i32(p)
 if kind in (1,2):obj,p=uvar(p)
 entries.append(dict(state=state,entry_RVA=start,previous_entry_RVA=start-(value>>2),type=kind,action_RVA=action,object_frame_offset=obj))
by_RVA={e['entry_RVA']:e['state']for e in entries}
for e in entries:
 prev=e['previous_entry_RVA'];e['previous_state']=by_RVA.get(prev,-1);assert prev in by_RVA or prev<entries[0]['entry_RVA']
n,p=uvar(ip);assert 0<n<128;ips=[];address=0x682d80
for _ in range(n):
 offset,p=uvar(p);state,p=uvar(p);address+=offset;ips.append(dict(IP_RVA=address,state=state-1))
def chain(address):
 state=ips[bisect.bisect_right([v['IP_RVA']for v in ips],address)-1]['state'];found=[];seen=set()
 while state>=0:
  assert state not in seen;seen.add(state);e=entries[state];found.append(e);state=e['previous_state']
 return found
all_ins=json.loads((H.parent/'repair-v9/native-review/original-sender-instructions.json').read_bytes())['instructions']
calls=[]
for ins in all_ins:
 a=int(ins['rva'],16)
 if 0x68318c<=a<0x68358e and ins['instruction'].startswith('call '):
  steps=chain(a+ins['size']-1);calls.append(dict(call_RVA=a,return_RVA=a+ins['size'],unwind_states=[e['state']for e in steps],ctx_cleanup=next((e for e in steps if e['action_RVA']==0x3b7d620),None)))
header_path=Path('C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/VC/Tools/MSVC/14.29.30133/include/ehdata4_export.h')
v=dict(image_sha256=hashlib.sha256(b).hexdigest(),format_reference=str(header_path),format_reference_sha256=hashlib.sha256(header_path.read_bytes()).hexdigest(),function_RVA='0x682d80',unwind_flags=3,EH_handler_RVA='0x3ae46cc',EH_metadata_RVA=hex(meta),header=header,unwind_map_RVA=hex(uw),IP_map_RVA=hex(ip),unwind_entries=entries,IP_states=ips,protected_call_sites=calls,all_CPP_call_unwind_chains_include_ctx_cleanup=all(e['ctx_cleanup']for e in calls),hardware_SEH_cleanup_claimed=False,wrapper_unwind_qualified=False)
(H/'original-sender-EH.json').write_bytes((json.dumps(v,indent=2)+'\n').encode());print(json.dumps(dict(header=header,unwind_entries=len(entries),IP_states=len(ips),call_sites=len(calls),all_CPP_call_unwind_chains_include_ctx_cleanup=v['all_CPP_call_unwind_chains_include_ctx_cleanup'],ctx_cleanup_offsets=sorted({e['ctx_cleanup']['object_frame_offset']for e in calls if e['ctx_cleanup']}))))
