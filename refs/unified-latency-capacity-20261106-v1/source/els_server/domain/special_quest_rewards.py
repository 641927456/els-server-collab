"""Exact seven-day accessory awards from current special quest definitions."""
import hashlib

ITEMS={
    237280:'0df4948b3080217d56d3e46caffa0126fa0cb008c45a0a102e767632f47ccf28',
    200700:'ca08ffcd6f5475e7dcef11e61b5f3ecf09c3217e2d4db539a93e715ebea9b230',
    200620:'0bd0e764b49bcd5688e887837d495e8e5aada52da88fbbccec9419123da0fbb2',
}


def timed_plan(quest,reward,*,now):
    from els_server.domain.seal_quests import quest_catalog,sequence
    if quest['m_iID']not in(32030,35490)or quest!=quest_catalog().quest(quest['m_iID']):
        raise ValueError('Original special quest required')
    if reward not in sequence(quest['Reward']['m_vecItem']):raise ValueError('Reward outside original task')
    template=reward['m_iItemID']
    if reward!=dict(m_iItemID=template,m_iQuantity=1,m_iPeriod=7,m_sSocketOption=0)or template not in ITEMS:
        raise ValueError('Original seven-day accessory reward')
    from els_server.game_data import client_data
    from els_server.domain.item_expiration import validate
    item=client_data().item(template)
    if hashlib.sha256(item['record']).hexdigest()!=ITEMS[template]:raise ValueError('Native timed reward changed')
    return dict(template=template,metadata=item['metadata'],group=7,quantity=1,expires_at=validate(now+7*86400))
