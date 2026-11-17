"""Existing-owned EXP medals and coupons, from current item/resource records."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

DATA_SHA='d6f0e6c6a2ee8a9733e7866d958f7eca3774dafd077b18232dd3bd2dbea66039'


@lru_cache(maxsize=1)
def catalog():
    from els_server.game_data import client_data, CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/experience_items.json').read_bytes()
    data=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['client_sha256']!=CLIENT_SHA or data['new_acquisition_sources']:
        raise ValueError('Experience item source identity')
    client=client_data()
    for row in (*data['medals'].values(),*data['coupons'].values()):
        item=client.item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or item['metadata']!=row['metadata']:
            raise ValueError('Experience item record changed')
    return data


def definitions():
    data=catalog()
    return tuple(data['medals'].values())+tuple(data['coupons'].values())


def coupon(dungeon,template):
    data=catalog()
    if template not in data['coupon_maps'].get(str(dungeon),()):return None
    return data['coupons'][str(template)]


def medal_selection(items):
    """Ordinary medals share one maximum; explicit per-item stacks keep their cap."""
    rules=catalog()['medals'];groups={}
    for item in items:
        rule=rules.get(str(item['template']))
        if rule is not None:groups.setdefault(item['template'],[]).append(item)
    candidates=[]
    for template,copies in groups.items():
        rule=rules[str(template)]
        copies=sorted(copies,key=lambda i:(i.get('expires_at',2**63-1),i['slot'],i['uid']))[:rule['max_copies']]
        candidates.append((rule['basis_points']*len(copies),template,copies))
    if not candidates:return 0,[]
    amount,_,selected=max(candidates,key=lambda row:(row[0],-row[1]))
    return amount,selected
