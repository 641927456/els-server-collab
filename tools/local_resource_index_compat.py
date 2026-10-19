"""Pin the two local resource archives before selecting their native disk index.

This is a local mixed-resource profile, not evidence of retail-version parity.
The native archive reader still checks and parses the on-disk index. A private
expected-header copy prevents the newer embedded index from replacing it.
"""
import hashlib,json,struct,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PINNED={'datai015.kom':'739f89d75e6fe5408f8d0b4d61aabfacb73d726c089e524b70a77365f3f275ac',
        'data036.kom':'56bb739e04e856e2ebf4c93c0df0cca7c181914e65d7cf4d140e167f593c6601'}

def source(image,directory,allow_variants=False):
    if hashlib.sha256(image).hexdigest()!='3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a':
        raise ValueError('Unverified resource-index client')
    specs={}
    for name,digest in PINNED.items():
        data=(Path(directory)/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:
            if not allow_variants:raise ValueError('Unverified local archive: '+name)
            print('CLIENT_RESOURCE_DECISION: '+json.dumps(dict(file=name,index_path='original',reason='archive-not-witnessed')),flush=True)
            continue
        if len(data)<72:raise ValueError('Invalid disk directory: '+name)
        header=data[:72];count,_,time_sum,adler,size=struct.unpack_from('<5I',header,52)
        if size>len(data)-72 or zlib.adler32(data[72:72+size])!=adler:raise ValueError('Invalid disk directory: '+name)
        specs[name]={'sha256':digest,'header':header.hex(),'count':count,'adler':adler,'time_sum':time_sum,'size':size}
        if allow_variants:print('CLIENT_RESOURCE_DECISION: '+json.dumps(dict(file=name,index_path='witnessed-disk-index',sha256=digest)),flush=True)
    if not specs:return None
    return (ROOT/'tools/local_resource_index_compat.js').read_text(encoding='utf8').replace('__INDEX_SPECS__',json.dumps(specs)).replace('__INDEX_PREFIX__',image[0x3653b0:0x3653c0].hex())
