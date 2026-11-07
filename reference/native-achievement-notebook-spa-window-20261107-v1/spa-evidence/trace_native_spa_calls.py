from pathlib import Path
import bisect, hashlib, json, struct, sys
R = Path('G:/els'); F = Path(__file__).resolve().parent
sys.path[:0] = [str(R/'tools/pylibs'), str(R/'tools/launcher_testdeps')]
import pefile
raw = (R/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
pe = pefile.PE(data=raw, fast_load=True)
d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
functions = sorted((b,e) for b,e,_ in struct.iter_unpack('<III',raw[d.VirtualAddress:d.VirtualAddress+d.Size]) if 0<b<e<=len(raw))
starts = [x[0] for x in functions]
targets = {int(v,16) for v in sys.argv[1:]} if len(sys.argv)>1 else {0x1a28e70,0x1a28ff0,0x1a297e0,0x1a29dc0}
rows = []
for section in pe.sections:
    if not section.Characteristics & 0x20000000: continue
    begin = section.VirtualAddress; end = min(len(raw),begin+section.Misc_VirtualSize)
    p = begin
    while (p := raw.find(b'\xe8',p,end)) >= 0:
        target = p + 5 + struct.unpack_from('<i',raw,p+1)[0]
        if target in targets:
            j = bisect.bisect_right(starts,p)-1
            if j>=0 and p<functions[j][1]:
                rows.append(dict(call=hex(p), target=hex(target), function=[hex(x) for x in functions[j]]))
        p += 1
proof = dict(image_sha256=hashlib.sha256(raw).hexdigest(),direct_call_candidates=rows,
             neighboring_functions=[[hex(b),hex(e)] for b,e in functions if 0x1a28e70<=b<0x1a2a100])
p = F/('native-spa-call-candidates-'+ '-'.join(hex(v) for v in sorted(targets))+'.json' if len(sys.argv)>1 else 'native-spa-call-candidates.json'); assert not p.exists()
p.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(json.dumps(proof,indent=2))
