"""Original CX2World iteration; condition/actions/allocator are explicit shims."""
from pathlib import Path
import json,struct,sys
O=Path(__file__).resolve().parent;R=Path('G:/els')
sys.path[:0]=[str(R/'tools'),str(R/'tools/pylibs')]
from role_native_replay import Replay
from unicorn import UC_HOOK_CODE,UcError
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_RIP

r=Replay();original={p:r.read(r.base+p,16)for p in(0x92e0a3,0x92e1c0)}
state={};head_offsets=(0x2a8,0x2b8);count_offsets=(0x2b0,0x2c0)
def hook(rva,fn):r.uc.hook_add(UC_HOOK_CODE,lambda *args:fn(),begin=r.base+rva,end=r.base+rva)
def current(reg):return r.uc.reg_read(reg)
def predicate():
    row=state['entries'][current(UC_X86_REG_RDX)]
    state['visited'].append(row['label']);r.finish_shim(int(row['expired']))
def action():
    row=state['entries'][current(UC_X86_REG_RDX)];state['actions'].append(row['label']);r.finish_shim(0)
def destroy():
    row=state['entries'][current(UC_X86_REG_RCX)]
    assert row['label']in state['actions']
    state['destroyed'].append(row['label'])
    # Freed iterator's parent becomes unreadable, as in the observed native fault.
    r.write(row['inner']+8,struct.pack('<Q',0xdeadbeef000));r.finish_shim(0)
def free():
    row=state['nodes'][current(UC_X86_REG_RCX)]
    assert row['label']in state['destroyed'];state['freed'].append(row['label']);r.finish_shim(0)
hook(0x92bfd0,predicate);hook(0x92ca30,action);hook(0x92d080,action)
hook(0x923ff0,destroy);hook(0x4f40a0,free);hook(0x3ae38f0,lambda:r.finish_shim(0))

def run_case(groups,fixed):
    r.next=0x200001000;r.allocations.clear();state.clear()
    state.update(entries={},nodes={},visited=[],actions=[],destroyed=[],freed=[])
    for p,raw in original.items():r.write(r.base+p,raw)
    world=r.alloc(0x330);r.write(world,struct.pack('<Q',r.base+0x415fe48));heads=[]
    for group,expired in enumerate(groups):
        head=r.alloc(0x20);heads.append(head);nodes=[]
        for index,flag in enumerate(expired):
            node=r.alloc(0x70);tree=r.alloc(0xa0);inner=r.alloc(0xa0)
            r.write(tree,struct.pack('<QQQ',inner,inner,inner));r.write(tree+0x19,b'\1')
            r.write(inner,struct.pack('<QQQ',tree,tree,tree))
            r.write(node+(0x20 if group==0 else 0x30),struct.pack('<Q',tree))
            row=dict(node=node,inner=inner,label=[group,index],expired=flag)
            state['entries'][node+0x10]=row;state['nodes'][node]=row;nodes.append(node)
        chain=[head,*nodes,head]
        r.write(head,struct.pack('<QQ',nodes[0]if nodes else head,nodes[-1]if nodes else head))
        for i,node in enumerate(nodes):r.write(node,struct.pack('<QQ',chain[i+2],chain[i]))
        r.write(world+head_offsets[group],struct.pack('<QQ',head,len(nodes)))
    if fixed:
        for site,resume in((0x92e0a3,0x92e13f),(0x92e1c0,0x92e25f)):
            stub=r.alloc(128)
            # Exact original free prelude, native call, then saved-next and outer check.
            code=r.read(r.base+site,32)
            code+=bytes.fromhex('ff1502000000eb08')+struct.pack('<Q',r.base+0x923ff0)
            code+=bytes.fromhex('ba700000004889f9')
            # Call [RIP+2], jump over its address literal on return.
            code+=bytes.fromhex('ff1502000000eb08')+struct.pack('<Q',r.base+0x4f40a0)
            code+=bytes.fromhex('4889f7ff2500000000')+struct.pack('<Q',r.base+resume)
            r.write(stub,code)
            r.write(r.base+site,bytes.fromhex('ff2500000000')+struct.pack('<Q',stub)+b'\x90'*2)
    r.uc.ctl_remove_cache(r.base+0x92e010,r.base+0x92e636)
    r.uc.ctl_remove_cache(0x200000000,0x200e00000)
    fault=None
    try:r.call(0x92e010,world)
    except (ValueError,UcError) as e:fault=dict(error=str(e),rva=hex(current(UC_X86_REG_RIP)-r.base))
    counts=[struct.unpack('<Q',r.read(world+o,8))[0]for o in count_offsets]
    out=dict(input=groups,fixed=fixed,visited=state['visited'],actions=state['actions'],destroyed=state['destroyed'],freed=state['freed'],remaining=counts,fault=fault)
    if fixed:
        assert fault is None,out
        expected=[[g,i]for g,group in enumerate(groups)for i,_ in enumerate(group)]
        deleted=[[g,i]for g,group in enumerate(groups)for i,flag in enumerate(group)if flag]
        assert out['visited']==expected and out['actions']==out['destroyed']==out['freed']==deleted,out
        assert counts==[len(group)-sum(group)for group in groups],out
    return out

rows=[]
for groups,site in(([[True],[]],'0x92e0e6'),([[],[True]],'0x92e203')):
    row=run_case(groups,False);assert row['fault']and row['fault']['rva']==site,row;rows.append(row)
for groups in([[True],[]],[[True,False],[]],[[True,True],[]],[[False,False],[]],[[],[True]],[[],[True,False]],[[],[True,True]],[[],[False,False]],[[True,False,True],[True,False,True]]):
    rows.append(run_case(groups,True))
out=dict(ok=True,original_native_loop=True,original_native_code_except_two_hooks=True,explicit_shims=['condition result','action observation','destructor/free poisoning','security cookie'],actual_game=False,rows=rows)
(O/'world-iteration-native-qualification.json').write_text(json.dumps(out,indent=2),encoding='utf8')
print(json.dumps(dict(ok=True,baseline_faults=2,fixed_cases=len(rows)-2)))
