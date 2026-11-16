"""Pinned current wedding inventory readers; grants and prices are separate."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json

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
    return tuple(data['readers'])
