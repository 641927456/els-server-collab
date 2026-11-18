"""Pinned current wedding inventory readers; grants and prices are separate."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import struct

DATA_SHA = 'f56747d28ac38e936079d0c2dde8664ad7ad2fbcf6725a2dc79dad1a656720df'


@lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data, CLIENT_SHA
    raw = (Path(__file__).resolve().parents[1]/'data/wedding_items.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Wedding item reader source identity')
    data = json.loads(raw);c = client_data()
    if data['client_sha256'] != CLIENT_SHA or data['catalog_sha256'] != c.manifest['catalog_sha256']:
        raise ValueError('Wedding reader client identity')
    for row in data['readers']:
        item = c.item(row['template'])
        if (item['name'] != row['name'] or item['metadata'] != row['metadata']
                or hashlib.sha256(item['record']).hexdigest() != row['record_sha256']):
            raise ValueError('Wedding current native item changed')
    oath = []
    for template in range(277190, 277200):
        item = c.item(template)
        metadata = 2 if template in (277194, 277195, 277196) else 0
        if (item['item_type'], item['flags8'], item['metadata']) != (7, 56, metadata):
            raise ValueError('Vow native item shape')
        stack, = struct.unpack_from('<I', item['record'], 16)
        oath.append(dict(template=template, metadata=metadata, group=4, max_stack=max(1, stack)))
    return (*data['readers'], *oath)
