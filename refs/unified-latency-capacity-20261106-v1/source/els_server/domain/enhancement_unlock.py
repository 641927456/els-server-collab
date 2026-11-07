"""Derived native enhancement unlocks; never persisted or accepted as socket input."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/enhancement_unlock.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='79121bc46abedc28f723442064bc2baa165da031146bff5f96a016354457874e':raise ValueError('Enhancement unlock source changed')
    data=json.loads(raw)
    if data['client_sha256']!=CLIENT_SHA:raise ValueError('Enhancement unlock client mismatch')
    return data


def options(template,enhancement):
    data=catalog();group=data['templates'].get(str(template))
    if group is None:return []
    return [option for minimum,option in data['groups'][str(group)] if enhancement>=minimum]
