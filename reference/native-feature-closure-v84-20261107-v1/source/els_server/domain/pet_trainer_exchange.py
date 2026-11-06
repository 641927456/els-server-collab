"""Seven original Camilla pet-token recipes and exact inventory outputs."""
from functools import lru_cache
from pathlib import Path
import hashlib,json,struct,uuid
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='b8237724192fac2664a70ee1087a01570f2f3b5db2e1b377060882e19d1a2045'
POLICY='pet-trainer-original-exchange-20261106-v1'
SOURCE_ONLY=frozenset((109956,135980,160164,710096))

@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/pet_trainer_exchange.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Pet trainer original recipes changed')
    d=json.loads(raw);c=client_data()
    if d['policy']!=POLICY or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']:raise ValueError('Pet trainer client identity')
    for row in d['definitions']:
        item=c.item(row['template'])
        if(item['metadata'],item['item_type'])!=(row['metadata'],row['item_type'])or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or struct.unpack_from('<I',item['record'],16)[0]!=row['raw_max_stack']:raise ValueError('Pet trainer native item reader')
    return d

def definitions():return tuple(catalog()['definitions'])

def recipe(r,town):
    d=catalog()
    if(town not in map(int,d['towns'])or r.house!=40016 or r.source!=324815 or r.source_uid!=0
            or r.native_flag!=1 or r.native_index!=0 or not 1<=r.quantity<=1000):raise ValueError('Pet trainer current original selection')
    rows=[a['arguments']for a in d['recipes']if a['arguments'][2]==r.exchange_type and a['arguments'][7]['m_iSourceQuantity']==r.source_quantity]
    if r.exchange_type==3:rows=[a for a in rows if a[4]==r.destination]
    elif r.exchange_type!=1 or r.destination!=0:raise ValueError('Pet trainer fixed recipe requires original zero destination')
    if len(rows)!=1:raise ValueError('Pet trainer original recipe selection')
    return rows[0]

def source_factory(town,r):
    a=recipe(r,town)
    def issue(db,owner,operation,plan,guard):
        from els_server.domain.raid_reward_items import _issue_source
        identity=dict(policy=POLICY,definition_sha256=DATA_SHA,owner=owner,town=town,recipe=a,quantity=r.quantity)
        def current(writer):guard();return True
        return _issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'pet-trainer:'+operation)),'ordinary',identity,plan,current)
    return issue

def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!=POLICY:return False
    a=identity['recipe'];quantity=identity['quantity']
    if(source.kind!='ordinary'or identity['definition_sha256']!=DATA_SHA or identity['owner']!=source.owner
            or identity['town']not in map(int,catalog()['towns'])or a not in[r['arguments']for r in catalog()['recipes']]
            or type(quantity)is not int or not 1<=quantity<=1000 or a[4]!=template):raise ValueError('Pet trainer exact recipe authority')
    row=next(r for r in definitions()if r['template']==template);total=a[5]*quantity;cap=row['max_stack']
    source.validate_plan([dict(template=template,metadata=row['metadata'],group=row['group'],quantity=min(cap,total-offset))for offset in range(0,total,cap)])
    return True

def box_entry():
    catalog()
    return dict(template=160164,selection_count=0,resurrection_gain=3,pet_trainer_box=True,entries=())
