"""Pinned local archive compatibility; disk hashes are never learned at launch."""
import hashlib,json
from pathlib import Path
from client_compatibility import digest_file
from native_support import load, prefix
ROOT=Path(__file__).resolve().parents[1]

def pinned_client_profile(client_directory, file_hashes=None):
    """Select only the witnessed executable; never learn hashes from disk."""
    client=Path(client_directory)/'x2_dx11.exe'
    measured=digest_file(client,file_hashes)
    spec=json.loads((ROOT/'tools/dx11_resource_compat.json').read_text(encoding='utf8'))
    return measured==spec['client_sha256']


def resource_compat_source(client_directory,*,use_pinned_profile=False,file_hashes=None):
    load()
    spec=json.loads((ROOT/'tools/dx11_resource_compat.json').read_text(encoding='utf8'))
    if use_pinned_profile and not pinned_client_profile(client_directory,file_hashes):
        raise ValueError('Pinned resource profile requires the exact witnessed client EXE')
    for row in (spec['entries'] if use_pinned_profile else spec['compatibility']):
        name=row['file']
        if Path(name).name!=name:raise ValueError('Invalid archive name')
        path=Path(client_directory)/name
        measured=digest_file(path,file_hashes)
        if path.stat().st_size!=row['size'] or measured!=row['sha256']:
            raise ValueError(name+' differs from the witnessed archive; refusing compatibility adjustment')
    prefixes={r:prefix(r,16) for r in (0x76d750,0x80e9b0)}
    return (ROOT/'tools/dx11_resource_compat.js').read_text(encoding='utf8').replace('__INTEGRITY_SPEC__',json.dumps(spec)).replace('__INTEGRITY_PREFIXES__',json.dumps(prefixes)).replace('__PINNED_PROFILE__','true' if use_pinned_profile else 'false')
