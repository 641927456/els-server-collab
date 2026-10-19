"""Pinned local archive compatibility; disk hashes are never learned at launch."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def resource_compat_source(image,client_directory):
    if hashlib.sha256(image).hexdigest()!='3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a':
        raise ValueError('Unverified resource-checking client image')
    spec=json.loads((ROOT/'tools/dx11_resource_compat.json').read_text(encoding='utf8'))
    for row in spec['compatibility']:
        name=row['file']
        if Path(name).name!=name:raise ValueError('Invalid archive name')
        path=Path(client_directory)/name
        with path.open('rb') as stream:measured=hashlib.file_digest(stream,'sha256').hexdigest()
        if path.stat().st_size!=row['size'] or measured!=row['sha256']:
            raise ValueError(name+' differs from the witnessed archive; refusing compatibility adjustment')
    prefixes={r:image[r:r+16].hex() for r in (0x76d750,0x80e9b0)}
    return (ROOT/'tools/dx11_resource_compat.js').read_text(encoding='utf8').replace('__INTEGRITY_SPEC__',json.dumps(spec)).replace('__INTEGRITY_PREFIXES__',json.dumps(prefixes))
