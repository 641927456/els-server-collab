"""Source-bound native title requests use skill zero on the shared 460 channel."""
import functools
import hashlib
import json
from pathlib import Path
from els_server.game_data import CLIENT_SHA
from els_server.domain.titles import definition


@functools.lru_cache(maxsize=1)
def rules():
    path=Path(__file__).resolve().parents[1]/'data/title_essence.json'
    raw=path.read_bytes()
    manifest=json.loads(path.with_name('title_essence.manifest.json').read_bytes())
    data=json.loads(raw)
    if manifest['format']!=1 or hashlib.sha256(raw).hexdigest()!=manifest['sha256'] or data['format']!=1 or data['client_sha256']!=CLIENT_SHA:
        raise ValueError('Title essence source identity')
    return {row['option']:row for row in data['rules']}


def rule_for(title):
    options=definition(title).get('SOCKET_OPTION',{})
    allowed=rules()
    return next((allowed[value] for key,value in options.items() if key!='0' and value in allowed),None)
