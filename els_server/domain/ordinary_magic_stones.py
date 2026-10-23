"""Versioned ordinary stone compatibility values within pinned native descriptions."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/ordinary_magic_stones.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='2005179847f8c5cfc050909e55af164b34ebcd6deed7e06c2cc5b4bb5c0f6a3d':raise ValueError('Ordinary stone compatibility policy changed')
    d=json.loads(raw)
    if d['schema_version']!=1 or d['policy_id']!='ordinary-socket-compatibility-v1' or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Ordinary stone policy identity')
    for source in d['sources']:
        if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Ordinary stone native source changed')
    for key,row in d['items'].items():
        item=client_data().item(row['template'])
        if key!=str(row['template']) or item['item_type']!=7 or item['metadata']!=row['metadata'] or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Ordinary stone template changed')
    for values in d['profiles'].values():
        if sum(r['weight'] for r in values)!=10000 or len({r['option'] for r in values})!=len(values) or any(type(r['weight']) is not int or r['weight']<=0 or str(r['option']) not in d['options'] for r in values):raise ValueError('Ordinary stone distribution')
    return d

def distribution(item,stone):
    row=catalog()['items'].get(str(stone));target=client_data().item(item['template'])
    if row is None or target['item_type'] not in (1,2):raise ValueError('Unsupported ordinary magic stone')
    return catalog()['profiles'][row['profiles']['weapon' if target['item_type']==1 else 'armor']]

def valid_option(template,value):
    target=client_data().item(template)
    if target['item_type'] not in (1,2):return False
    kind='weapon' if target['item_type']==1 else 'armor'
    return any(value==r['option'] for row in catalog()['items'].values() for r in catalog()['profiles'][row['profiles'][kind]])
