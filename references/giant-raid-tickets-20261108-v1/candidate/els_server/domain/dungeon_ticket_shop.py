"""Owner-approved permanent giant keys and weekly raid resets, 50 ED each."""
from els_server.game_data import client_data

KEYS=(480356,309244,713224,716829)
RESETS=(135909,136055)
TEMPLATES=frozenset(KEYS+RESETS)
POLICY='giant-raid-tickets-50ed-20261108-v1'

def offers():
    from els_server.domain.daily_ticket_rules import giant_definitions
    from els_server.domain.rosso_reset import definition
    if tuple(t[0] for t in giant_definitions().values())!=KEYS:raise ValueError('Original giant shop key definitions changed')
    for t in RESETS:definition(t)
    return tuple(dict(sku=1200000000+t,template=t,name=client_data().item(t)['name'],
                      category=41,price=50,quantity=1) for t in KEYS+RESETS)

def purchase_source(db,owner,operation,digest,plan):
    from els_server.domain.raid_reward_items import _issue_source
    if any(p['template']not in TEMPLATES for p in plan):raise ValueError('Non-ticket shop plan')
    source=dict(reward_source=POLICY,owner=owner,operation=operation,request_sha256=digest)
    return _issue_source(db,owner,'shop-ticket:'+operation,'npc_trade',source,plan,
                         lambda writer:writer is db and db.in_transaction)

def authorize_output(template,authority):
    if authority is None:return False
    import json
    from els_server.domain.raid_reward_items import validate_source
    a=validate_source(authority);source=json.loads(a._source)
    if source.get('reward_source')!=POLICY:return False
    if template not in TEMPLATES or a.kind!='npc_trade' or source.get('owner')!=a.owner:
        raise ValueError('Ticket shop output scope')
    a.validate_template(template)
    return True
