"""Exact current-client missing key aliases approved with the local box rules."""
import hashlib,json
from pathlib import Path

def source(image):
    path=Path(__file__).with_suffix('.json');raw=path.read_bytes();spec=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=SPEC_SHA:raise ValueError('Owned box key alias policy changed')
    if hashlib.sha256(image).hexdigest()!=spec['image_sha256']:raise ValueError('Owned box key alias image changed')
    for rva,prefix in spec['entry_prefixes'].items():
        offset=int(rva,16)
        if image[offset:offset+16].hex()!=prefix:raise ValueError('Owned box key alias entry changed')
    return Path(__file__).with_suffix('.js').read_text('utf8').replace('__OWNED_BOX_KEY_SPEC__',json.dumps(spec))

SPEC_SHA='c7f8314bba652fdd11027c3aae4bd7fb343f5011f49c69a16a2278684c831c67'
