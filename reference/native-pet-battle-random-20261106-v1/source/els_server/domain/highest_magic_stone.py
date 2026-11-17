"""Approved exact uniform categories and native legal tiers for highest magic stone."""
from functools import lru_cache
from pathlib import Path
import hashlib,json
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT
DATA_SHA='846d7e4d397543ad3d0d14949b6b131f7a4550c0d0ceccdc627c1dffa1046d45'

@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/highest_magic_stone.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Highest stone approved distribution changed')
    d=json.loads(raw);c=client_data()
    if d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']:raise ValueError('Highest stone client identity')
    for source in d['sources']:
        if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Highest stone native tier source changed')
    item=c.item(109956);row=d['items']['109956']
    if(item['metadata'],item['item_type'])!=(2,7)or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Highest stone native reader')
    for kind,groups in d['categories'].items():
        profile=d['profiles'][row['profiles'][kind]];weights={r['option']:r['weight']for r in profile}
        totals=[]
        if len(groups)!=12 or len(weights)!=len(profile):raise ValueError('Highest stone native categories')
        for group in groups:
            values=[weights[o]for o in group['options']]
            if len(set(values))!=1 or values[0]<=0:raise ValueError('Highest stone equal native tiers')
            totals.append(sum(values))
        if len(set(totals))!=1 or sum(totals)!=sum(weights.values()):raise ValueError('Highest stone equal categories')
    return d
