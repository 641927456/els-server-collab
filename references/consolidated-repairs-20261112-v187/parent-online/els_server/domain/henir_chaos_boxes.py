"""Owned reward boxes with exact Chinese client contents."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from els_server.game_data import CLIENT_SHA, client_data


DATA_SHA = 'a455d8a2697833b6a8b7e466ea40632283dbf58696614371f0f037279d411455'


@lru_cache(maxsize=1)
def catalog():
    raw = (Path(__file__).resolve().parents[1] / 'data/henir_chaos_boxes.json').read_bytes()
    if sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Henir Chaos box definition identity')
    data = json.loads(raw)
    client = client_data()
    if (data['client_sha256'], data['catalog_sha256']) != (CLIENT_SHA, client.manifest['catalog_sha256']):
        raise ValueError('Henir Chaos box client identity')
    for row in data['readers']:
        item = client.item(row['template'])
        if (item['name'], item['metadata'], sha256(item['record']).hexdigest()) != (
            row['name'], row['metadata'], row['record_sha256'],
        ):
            raise ValueError('Henir Chaos box item identity')
    return data


@lru_cache(maxsize=1)
def boxes():
    return frozenset(row['template'] for row in catalog()['boxes'])
