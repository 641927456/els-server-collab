"""Original39480, current official once-only schedule, original timed rewards."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

QUEST=39480
REWARDS={135871:'5be99248c661c81f0c728eeb80d948911256c0c0f16468df3729c757e43aa69a',
         135872:'49e73da53e290883c6428f88501715f5b261bd442141fed4db012a22114c5a48'}

@functools.lru_cache(maxsize=1)
def catalog():
    p=Path(__file__).parents[1]/'data/reselection_quest.json'
    raw=p.read_bytes();row=json.loads(raw);manifest=json.loads(p.with_suffix('.manifest.json').read_bytes())
    if (manifest['schema_version']!=1 or row['schema_version']!=1
        or row['client_sha256']!=CLIENT_SHA or manifest['client_sha256']!=CLIENT_SHA
        or row['catalog_sha256']!=client_data().manifest['catalog_sha256']
        or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']
        or set(row['quests'])!={'39480'}or set(row['subquests'])!={'39480'}):raise ValueError('First-class reselection source')
    return row

def require_first_class(character):
    from els_server.domain.character_rules import CLASSES
    if CLASSES[character['unit_class']]['stage']!=1:
        raise ValueError('First-class reselection requires current first class')

def definitions():
    rows=[]
    for template,digest in REWARDS.items():
        item=client_data().item(template)
        if hashlib.sha256(item['record']).hexdigest()!=digest or (item['item_type'],item['metadata'])!=(7,0):
            raise ValueError('First-class reselection reward record')
        rows.append(dict(template=template,metadata=0,group=4,max_stack=1))
    return rows

def timed_plan(quest,reward,*,now):
    from els_server.domain.seal_quests import sequence
    from els_server.domain.item_expiration import validate
    if quest!=catalog()['quests']['39480'] or reward not in sequence(quest['Reward']['m_vecItem']):
        raise ValueError('Original reselection reward required')
    template=reward['m_iItemID']
    if template not in REWARDS or reward!=dict(m_iItemID=template,m_iQuantity=1,m_iPeriod=1,m_sSocketOption=0):
        raise ValueError('Original one-day reselection award')
    return dict(template=template,metadata=0,group=4,quantity=1,expires_at=validate(now+86400))
