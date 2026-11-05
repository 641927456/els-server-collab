"""One original seven-day quest pass; native UI/count/expiry remain native."""
import functools,hashlib
from els_server.game_data import client_data
TEMPLATE=118149
SOURCE_REWARD=dict(m_iPeriod=7,m_iQuantity=1,m_iItemID=TEMPLATE,m_sSocketOption=0)

@functools.lru_cache(maxsize=1)
def definition():
    data=client_data();item=data.item(TEMPLATE)
    if (hashlib.sha256(item['record']).hexdigest()!='876db2acef6ecd924a93d7436b4bc76df0361f59b72ab4a9c00fd82e77e978ad'
        or item['item_type']!=7 or item['metadata']!=0
        or data.resource('Enum.lua')['PERIOD_TYPE']['PT_INFINITY']!=0):raise ValueError('Travel pass source identity')
    from els_server.domain.acquisition_policy import require_acquirable
    require_acquirable(TEMPLATE)
    return dict(template=TEMPLATE,metadata=0,group=4,max_stack=1)

def quest_reward_plan(quest,reward,*,now):
    from els_server.domain.town_dialogue import catalog
    if quest!=catalog()['quests']['100240'] or reward!=SOURCE_REWARD:
        raise ValueError('Outside original timed pass quest reward')
    if type(now) is not int:raise ValueError('Pass grant clock')
    from els_server.domain.item_expiration import validate
    rule=definition()
    return dict(template=TEMPLATE,metadata=rule['metadata'],group=rule['group'],quantity=1,
                expires_at=validate(now+reward['m_iPeriod']*24*60*60))
