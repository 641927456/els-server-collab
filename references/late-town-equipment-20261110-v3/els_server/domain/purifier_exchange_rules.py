"""Deterministic exchanges from Betty's original Abyss menu."""
import functools
import hashlib
import json
import struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA, client_data

ACCESSORY_BOXES = frozenset((136107, 136108))


@functools.lru_cache(maxsize=1)
def catalog():
    raw = (Path(__file__).resolve().parents[1]/'data/purifier_exchange.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '4a1895f0deacf26832791bdc47852710fa940ce57c5378f71a4ce37524ea303d':
        raise ValueError('Purifier exchange source identity')
    c = json.loads(raw)
    if (c['client_sha256'] != CLIENT_SHA
            or c['catalog_sha256'] != client_data().manifest['catalog_sha256']):
        raise ValueError('Purifier exchange build identity')
    if set(r['template'] for r in c['definitions']) != {136115,136109,136110,136111}:
        raise ValueError('Purifier exchange finite inventory')
    for row in c['definitions']:
        d=client_data().item(row['template']);b=d['record']
        maximum=500 if row['template']==136115 else 300
        if (len(b)!=232 or hashlib.sha256(b).hexdigest()!=row['record_sha256']
                or d['name']!=row['name'] or d['item_type']!=7 or d['metadata']!=2
                or row['metadata']!=2 or row['group']!=4 or row['max_stack']!=maximum
                or row['raw_max_stack']!=maximum or struct.unpack_from('<H',b,16)[0]!=maximum
                or d['flags4']&33 or d['flags8']!=56):
            raise ValueError('Purifier exchange original instance definition')
    expected={(7,136109),(7,136110),(7,136111),(40,136080),(40,136081),(40,136082)}
    expected.update((84,t) for t in ACCESSORY_BOXES)
    if len(c['recipes'])!=len(expected) or {(r['source_quantity'],r['destination']) for r in c['recipes']}!=expected:
        raise ValueError('Purifier exchange finite recipes')
    for r in c['recipes']:
        a=r['original_call']['arguments']
        if (r['original_call']['function']!='g_pItemManager.AddItemExchangeData'
                or a[1:7]!=[40272,3,136115,r['destination'],1,100]
                or a[7]!={'m_iServerGroupID':-1,'m_iSourceQuantity':r['source_quantity']}):
            raise ValueError('Purifier exchange original recipe')
    e=c['entry']
    if (e['town'],e['world'],e['house'],e['npc'],e['button'])!=(20013,1023,40272,10382,11):
        raise ValueError('Purifier exchange current NPC entry')
    return c


def inventory_definitions():
    return catalog()['definitions']


def recipe(r):
    for row in catalog()['recipes']:
        if (r.source_quantity,r.destination)==(row['source_quantity'],row['destination']):
            return row
    raise ValueError('Unqualified purifier exchange selection')
