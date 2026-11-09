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

def source(image,directory,allow_variants=False,*,use_retained_original_indexes=False):
    if hashlib.sha256(image).hexdigest()!='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229':
        raise ValueError('Unverified resource-index client')
    if use_retained_original_indexes and allow_variants:
        raise ValueError('Retained indexes require the exact pinned resource profile')
    pins={}
    selected=dict(PINNED)
    if use_retained_original_indexes:
        pins=json.loads((ROOT/'tools/original_index_pins.json').read_text(encoding='utf8'))['archives']
        selected.update({name:row['sha256'] for name,row in pins.items()})
    specs={}
    for name,digest in selected.items():
        if Path(name).name!=name:raise ValueError('Invalid archive name')
        path=Path(directory)/name
        with path.open('rb') as stream:measured=hashlib.file_digest(stream,'sha256').hexdigest()
        if measured!=digest:
            if not allow_variants:raise ValueError('Unverified local archive: '+name)
            print('CLIENT_RESOURCE_DECISION: '+json.dumps(dict(file=name,index_path='original',reason='archive-not-witnessed')),flush=True)
            continue
        file_size=path.stat().st_size
        with path.open('rb') as stream:
            header=stream.read(72)
            if len(header)!=72:raise ValueError('Invalid disk directory: '+name)
            count,_,time_sum,adler,size=struct.unpack_from('<5I',header,52)
            if size>file_size-72:raise ValueError('Invalid disk directory: '+name)
            index=stream.read(size)
        if len(index)!=size or zlib.adler32(index)!=adler:raise ValueError('Invalid disk directory: '+name)
        if name in pins:
            row=pins[name]
            if (file_size!=row['size'] or count!=row['entry_count'] or hashlib.sha256(header).hexdigest()!=row['header_sha256'] or hashlib.sha256(index).hexdigest()!=row['index_sha256'] or row['index_status']!='parsed'):
                raise ValueError('Original index source pin mismatch: '+name)
        specs[name]={'sha256':digest,'header':header.hex(),'count':count,'adler':adler,'time_sum':time_sum,'size':size}
        if allow_variants:print('CLIENT_RESOURCE_DECISION: '+json.dumps(dict(file=name,index_path='witnessed-disk-index',sha256=digest)),flush=True)
    if not specs:return None
    return (ROOT/'tools/local_resource_index_compat.js').read_text(encoding='utf8').replace('__INDEX_SPECS__',json.dumps(specs)).replace('__INDEX_PREFIX__',image[0x3653b0:0x3653c0].hex())
