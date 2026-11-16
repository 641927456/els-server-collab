"""Current original54620 account weekly task and its fixed material reward."""
from functools import lru_cache
from pathlib import Path
import hashlib,json,struct

QUEST=54620
REWARD=324815
POLICY='pet-battle-account54620-20261106-v1'
DATA_SHA='6ea5b3a3b430d056c98c3f74d94423a2f654f20b26870a3c9e8eb1f181d39dda'


@lru_cache(maxsize=1)
def catalog():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/pet_battle_quest.json').read_bytes()
    data=json.loads(raw);client=client_data()
    if (hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['policy']!=POLICY or data['client_sha256']!=CLIENT_SHA
            or data['catalog_sha256']!=client.manifest['catalog_sha256']):
        raise ValueError('Pet weekly original task source identity')
    row=data['reward_definitions'][0];item=client.item(REWARD)
    if (row['template']!=REWARD or item['item_type']!=7 or item['metadata']!=row['metadata']
            or (row['metadata'],row['group'],row['max_stack'],row['quantity'])!=(2,4,300,7)
            or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or struct.unpack_from('<I',item['record'],0x10)[0]!=row['max_stack']):
        raise ValueError('Pet weekly exact native material reward')
    return data


def objective(sub):
    return sub==catalog()['subquests'].get(str(sub.get('m_iID')))


def target(sub):
    if not objective(sub):raise ValueError('Outside original pet weekly objective')
    return 3


def definitions():return tuple(catalog()['reward_definitions'])


def reward_plan():
    return [dict(template=REWARD,metadata=2,group=4,quantity=7)]


def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!=POLICY:return False
    if (source.kind!='ordinary' or identity.get('owner')!=source.owner
            or identity.get('quest')!=QUEST or identity.get('definition_sha256')!=DATA_SHA
            or template!=REWARD):
        raise ValueError('Pet weekly exact reward source')
    source.validate_plan(reward_plan())
    return True
