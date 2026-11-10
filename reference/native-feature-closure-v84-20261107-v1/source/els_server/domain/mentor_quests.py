"""Four original repeat tasks, ten student tasks and current approved rewards."""
from pathlib import Path
from functools import lru_cache
import hashlib,json

DATA_SHA='a12db404ba7fdbbe392448e2ff11e12b6121b634ee3ab133a194cf7f0a36d6c5'
POLICY='mentor-native-tasks-current-CN-20261106-v1'


@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/mentor_quests.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Mentor task source changed')
    data=json.loads(raw)
    from els_server.game_data import client_data,CLIENT_SHA
    client=client_data()
    if (data['schema_version']!=1 or data['policy']!=POLICY or data['client_sha256']!=CLIENT_SHA
            or data['catalog_sha256']!=client.manifest['catalog_sha256']
            or set(map(int,data['quests']))!={*range(45001,45005),*range(45031,45041)}):
        raise ValueError('Mentor task client identity')
    for row in data['reward_definitions']:
        item=client.item(row['template'])
        if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
                or (item['metadata'],item['item_type'])!=(row['metadata'],row['item_type'])):
            raise ValueError('Mentor task reward identity')
    return data


def contains(quest):return str(quest)in catalog()['quests']
def teacher(quest):return quest in catalog()['teacher_repeat_ids']
def objective(sub):return catalog()['subquests'].get(str(sub.get('m_iID')))==sub


def target(sub):
    if not objective(sub):raise ValueError('Outside mentor objective source')
    kind=sub['m_eClearType'];c=sub['m_ClearCondition']
    return c['m_iCollectionItemNum']if kind==3 else c['m_iKillNum']if kind==2 else c['m_iPVPPlay']if kind==9 else c['m_iPVPWin']if kind==10 else c['m_iDungeonClearCount']if kind==8 else c['m_iClearCount']


def definitions():return tuple(row for row in catalog()['reward_definitions']if not row['previously_registered'])


def reward_plan(quest,now):
    from els_server.domain.seal_quests import sequence
    from els_server.domain.item_expiration import validate
    rows={r['template']:r for r in catalog()['reward_definitions']}
    plan=[]
    for reward in sequence(catalog()['quests'][str(quest)]['Reward']['m_vecItem']):
        row=rows[reward['m_iItemID']]
        item=dict(template=row['template'],metadata=row['metadata'],group=row['group'],quantity=reward['m_iQuantity'])
        if reward['m_iPeriod']:item['expires_at']=validate(now+reward['m_iPeriod']*86400)
        plan.append(item)
    return plan


def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!=POLICY:return False
    if (source.kind!='ordinary' or identity['owner']!=source.owner
            or identity['definition_sha256']!=DATA_SHA or not contains(identity['quest'])):
        raise ValueError('Mentor reward source identity')
    plan=reward_plan(identity['quest'],identity['at'])
    source.validate_plan(plan)
    if template not in {row['template']for row in plan}:raise ValueError('Outside exact mentor reward vector')
    return True


def increment(quest,sub,fact,activity):
    if activity['kind']=='black_gate':return int(quest==45038 and activity['dungeon']==38300 and activity['npc']==1367)
    if activity['kind']=='duel':
        if quest in(45002,45039):return 1
        if quest==45040:return int(activity['winner']==fact['student'])
        return 0
    if activity['kind']=='random':return int(quest==45037)
    if activity['kind']!='clear':return 0
    if quest==45001:return int(fact['fatigue_free'])
    if quest==45038:return int(activity['dungeon']==38300 and activity['boss_witness'])
    if sub['m_eClearType']!=8:return 0
    from els_server.domain.seal_quests import sequence
    from els_server.domain.dungeon_routes import route_catalog
    resolve=route_catalog().entry_identity
    return int(any(resolve(mid)==resolve(activity['dungeon'])for mid in sequence(sub['m_ClearCondition'].get('m_eDungeonID',{}))))
