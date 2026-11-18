from pathlib import Path
import hashlib,json,struct,sys
R=Path('G:/els');F=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'tools/pylibs'),str(R/'tools/launcher_testdeps')]
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
raw=(R/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes();digest=hashlib.sha256(raw).hexdigest()
assert digest=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
pe=pefile.PE(data=raw,fast_load=True);d=pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
functions={b:e for b,e,_ in struct.iter_unpack('<III',raw[d.VirtualAddress:d.VirtualAddress+d.Size])if 0<b<e<=len(raw)}
md=Cs(CS_ARCH_X86,CS_MODE_64);directory=F/'native-functions';directory.mkdir(exist_ok=True)
for argument in sys.argv[1:]:
    start=int(argument,16);end=functions[start];assert end-start<=65536
    rows=[dict(rva=hex(i.address-0x140000000),mnemonic=i.mnemonic,operands=i.op_str)for i in md.disasm(raw[start:end],0x140000000+start)]
    proof=dict(image_sha256=digest,function=[hex(start),hex(end)],function_bytes_sha256=hashlib.sha256(raw[start:end]).hexdigest(),instructions=rows)
    p=directory/(hex(start)+'.json');assert not p.exists();p.write_bytes((json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps(dict(function=proof['function'],instructions=len(rows),spa_global_references=[r for r in rows if '0x1230'in r['operands']])))
