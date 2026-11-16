"""Original31130 definitions, current marriage eligibility and fixed rewards."""
from functools import lru_cache
from pathlib import Path
import hashlib,json

QUEST=31130
POLICY='wedding-weekly-original31130-20261106-v1'
DATA_SHA='184a54afa86d883ba55d232860ca35c792780278cf90525715cf4965a4b6156c'


@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/wedding_quests.json').read_bytes()
    from els_server.game_data import client_data,CLIENT_SHA
    data=json.loads(raw);client=client_data()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['policy']!=POLICY or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']:
        raise ValueError('Wedding task source identity')
    for row in data['reward_definitions']:
        item=client.item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:
            raise ValueError('Wedding task reward source')
    return data


def current(db,owner,account,now):
    from els_server.storage.relationships import snapshot
    saved=snapshot(db,owner,account)
    return saved if saved is not None and saved['kind']==2 and saved['refreshed_at']<=now<saved['refreshed_at']+365*86400 else None


def reward_plan():
    return [dict(template=row['template'],metadata=row['metadata'],group=row['group'],quantity=2)
            for row in catalog()['reward_definitions']]


def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!=POLICY:return False
    if source.kind!='ordinary' or identity.get('owner')!=source.owner or identity.get('quest')!=QUEST or identity.get('definition_sha256')!=DATA_SHA:
        raise ValueError('Wedding task exact reward source')
    source.validate_plan(reward_plan())
    if template not in (710097,710193):raise ValueError('Outside wedding task rewards')
    return True
