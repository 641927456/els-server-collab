"""Pinned local archive compatibility; disk hashes are never learned at launch."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def pinned_client_profile(client_directory):
    """Select only the witnessed executable; never learn hashes from disk."""
    client=Path(client_directory)/'x2_dx11.exe'
    with client.open('rb') as stream:
        measured=hashlib.file_digest(stream,'sha256').hexdigest()
    spec=json.loads((ROOT/'tools/dx11_resource_compat.json').read_text(encoding='utf8'))
    return measured==spec['client_sha256']


def resource_compat_source(image,client_directory,*,use_pinned_profile=None):
    if hashlib.sha256(image).hexdigest()!='3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a':
        raise ValueError('Unverified resource-checking client image')
    spec=json.loads((ROOT/'tools/dx11_resource_compat.json').read_text(encoding='utf8'))
    if use_pinned_profile is None:
        use_pinned_profile=pinned_client_profile(client_directory)
    if use_pinned_profile and not pinned_client_profile(client_directory):
        raise ValueError('Pinned resource profile requires the exact witnessed client EXE')
    for row in (spec['entries'] if use_pinned_profile else spec['compatibility']):
        name=row['file']
        if Path(name).name!=name:raise ValueError('Invalid archive name')
        path=Path(client_directory)/name
        with path.open('rb') as stream:measured=hashlib.file_digest(stream,'sha256').hexdigest()
        if path.stat().st_size!=row['size'] or measured!=row['sha256']:
            raise ValueError(name+' differs from the witnessed archive; refusing compatibility adjustment')
    prefixes={r:image[r:r+16].hex() for r in (0x76d750,0x80e9b0)}
    return (ROOT/'tools/dx11_resource_compat.js').read_text(encoding='utf8').replace('__INTEGRITY_SPEC__',json.dumps(spec)).replace('__INTEGRITY_PREFIXES__',json.dumps(prefixes)).replace('__PINNED_PROFILE__','true' if use_pinned_profile else 'false')
