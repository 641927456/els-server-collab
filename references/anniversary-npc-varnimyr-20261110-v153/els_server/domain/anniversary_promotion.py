"""Local 15th anniversary promotion outfit using the client's seven existing boxes."""
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

from els_server.game_data import client_data

BOXES = (719927, 719928, 719929, 719930, 719931, 719932, 719933)
STARTS = int(datetime.fromisoformat('2026-11-11T10:00:00+08:00').timestamp())
ENDS = int(datetime.fromisoformat('2026-11-20T10:00:00+08:00').timestamp())
MAIL_DEADLINE = int(datetime.fromisoformat('2026-11-25T09:59:00+08:00').timestamp())
REQUIRED_SECONDS = 3600
CAMPAIGN = 'cn15-anniversary-promotion-20261111'
CATALOG_SHA = '22edbe68375e18b83e613d7786c02ff47448d47aee025bd2e8b6cbf80cf3e6f0'


def mail_key(template):
    return f'{CAMPAIGN}-{template}'


@lru_cache(maxsize=1)
def routes():
    path = Path(__file__).resolve().parents[1] / 'data/anniversary_promotion.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA:
        raise ValueError('Anniversary outfit catalog changed')
    return json.loads(raw)


@lru_cache(maxsize=1)
def fashion_templates():
    return frozenset(template for route in routes().values() for part in route for template in part)


def outputs_for(box, unit_class):
    route = routes().get(str(unit_class))
    if route is None:
        raise ValueError('Anniversary outfit requires a third-job character')
    return tuple(dict(template=template, quantity=1) for template in route[BOXES.index(box)])


@lru_cache(maxsize=1)
def definitions():
    client = client_data()
    definitions = []
    for template in (*BOXES, *sorted(fashion_templates())):
        item = client.item(template)
        box = template in BOXES
        if (item['metadata'] != 0 or struct.unpack_from('<I', item['record'], 0x10)[0] != 0
                or (box and item['item_type'] != 7)
                or (not box and (not item['flags4'] & 1 or item['flags8'] & 256))):
            raise ValueError('Anniversary outfit native item classification changed')
        definitions.append(dict(template=template, metadata=0, group=4 if box else 7,
                                max_stack=1, equip_position=item['equip_position']))
    return tuple(definitions)
