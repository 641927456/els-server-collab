"""Exact native readers shared with the v128 recovery build."""
import functools
import hashlib
import json
import struct
from pathlib import Path

DATA_SHA = '094378769c8676117c3a38aa0c38e8f98c6839641e8fa8d9221f13bcb13af6ab'


@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import CLIENT_SHA, client_data

    raw = (Path(__file__).resolve().parents[1] / 'data/season_pass_rewards.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Pass reward reader identity')
    data = json.loads(raw)
    catalog = client_data()
    if data['client_sha256'] != CLIENT_SHA or data['catalog_sha256'] != catalog.manifest['catalog_sha256']:
        raise ValueError('Pass reward catalog identity')
    for row in data['items']:
        item = catalog.item(row['template'])
        maximum = max(1, struct.unpack_from('<I', item['record'], 16)[0])
        if ({7: 4, 2: 1}.get(item['item_type']) != row['group'] or item['metadata'] != row['metadata']
            or maximum != row['max_stack'] or hashlib.sha256(item['record']).hexdigest() != row['record_sha256']):
            raise ValueError('Pass original reward item reader')
    return tuple(data['items'])
