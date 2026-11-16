"""Current thirteen-course guide; finite character rewards without an end date."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    path=PROJECT_ROOT/'els_server/data/growth_guide.json';raw=path.read_bytes()
    manifest=json.loads(path.with_suffix('.manifest.json').read_bytes());data=json.loads(raw)
    if (manifest['schema_version']!=1 or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']
            or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client_data().manifest['catalog_sha256']
            or len(data['quests'])!=61 or len(data['tabs'])!=13):raise ValueError('Growth guide source identity')
    for quest in data['quests'].values():
        if quest['m_eQuestType']!=15 or quest['m_bIsTimeEvent'] or quest['m_bRepeat']!=1:
            raise ValueError('Growth guide source task kind')
    for row in data['reward_definitions']:
        item=client_data().item(row['template'])
        if (item['name']!=row['name'] or item['metadata']!=row['metadata']
                or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):raise ValueError('Growth guide reward identity')
    return data

def contains(identity):return str(identity) in catalog()['quests']
def objective(sub):return catalog()['subquests'].get(str(sub['m_iID']))==sub
def ordinary_active_count(rows):return sum(not contains(row['id'] if isinstance(row,dict) else row) for row in rows)

def target(sub):
    c=sub['m_ClearCondition'];kind=sub['m_eClearType']
    if kind in (31,81,82,107):return 1
    if kind==71:return c['m_iClearStage']
    if kind==14:return c['m_iSocketCount']
    if kind==43:return c['m_iExchangeCount']
    if kind in (2,8,32):return c.get('m_iKillNum',c.get('m_iDungeonClearCount'))
    return c['m_iClearCount']

def require_eligible(character,quest,completed):
    tab=next(t for t in catalog()['tabs'] if quest['m_iID'] in t['quests'])
    condition=tab['open_condition']
    if character['level']<condition['LEVEL']:raise ValueError('Growth guide course level')
    if condition['QUEST_ID']>0 and condition['QUEST_ID'] not in completed:raise ValueError('Growth guide course prerequisite')

def increment(sub,event):
    kind=sub['m_eClearType'];c=sub['m_ClearCondition']
    if kind==71 and event['kind'] in ('stage_clear','clear') and event.get('henir_mode')==c['m_eDungeonMode']:
        return min(target(sub),event.get('henir_stage',0))
    return 0
