"""Original A22 writer and A23 decoder prefix; no game, UI or player state."""
import argparse,pathlib,struct,sys,json
p=argparse.ArgumentParser();p.add_argument('--runtime',type=pathlib.Path,required=True);p.add_argument('--mode',choices=('online','local'),required=True);p.add_argument('--native-root',type=pathlib.Path,required=True);args=p.parse_args()
here=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(args.runtime),str(args.native_root/'tools')]
import els_server,els_server.protocol,els_server.domain
for package,suffix in((els_server,'els_server'),(els_server.protocol,'els_server/protocol'),(els_server.domain,'els_server/domain')):
    for group in('common',args.mode):package.__path__.insert(0,str(here/'source'/group/suffix))
from els_server.protocol.reforge_scroll_messages import request,acknowledgement
from els_server.domain.equipment_reforge_rules import expected_options
from verify_shared_bank_native import SharedBankReplay
from unicorn.x86_const import UC_X86_REG_RSP,UC_X86_REG_RBP,UC_X86_REG_RIP
n=SharedBankReplay();out=[]
for target,source in((1001001,1001002),(2**32+1001001,2**32+1001002)):
    dto=n.alloc(16);n.write(dto,struct.pack('<QQ',target,source))
    wire=n.writer(0x235352e,0x23535b5,dto);assert request(wire)==(target,source)
    out.append(dict(kind='A22',uid64=True,bytes=len(wire)))
gear=dict(uid=2**32+1001001,template=118153,metadata=1,group=1,slot=2,count=1,reforge=[18,63,0],option_groups={'13':expected_options(118153,18)})
for changes in((),(((1,2),gear),((4,0),None))):
    wire=acknowledgement(changes).payload;buf=n.buffer(wire);sp=n.stack-8
    n.write(sp+0x28,struct.pack('<Q',buf));n.uc.reg_write(UC_X86_REG_RSP,sp)
    n.uc.emu_start(n.base+0x2271550,n.base+0x2271646,count=1000000)
    assert n.uc.reg_read(UC_X86_REG_RIP)==n.base+0x2271646
    sp=n.uc.reg_read(UC_X86_REG_RSP);assert n.read(sp+0x48,4)==bytes(4)
    begin,end,cap=struct.unpack('<QQQ',n.read(sp+0x4c,24));assert end-begin==len(changes)*0x408 and end<=cap
    assert int.from_bytes(n.read(buf+32,4),'little')==len(wire)
    out.append(dict(kind='A23',records=len(changes),bytes=len(wire),complete_decoder_prefix=True))
print(json.dumps(dict(ok=True,checks=out,actual_game=False)))
