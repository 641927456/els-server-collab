"""Owner-approved dungeon extra entries and reward resets, 1,000,000 ED each."""
from els_server.game_data import client_data

KEYS=(480356,309244,713224,716829)
RESETS=(135909,136055)
RESTORES=(720853,136153,136154)
DAILY_ENTRIES=(711786,710131,720832)
EVENT_ENTRIES=(190342,190448,190918)
PERMANENT_ENTRIES=(118341,118651)
CHAOS_RESET=62260
MIRROR_INVITATION=722538
PRODUCTS=KEYS+RESETS+RESTORES+DAILY_ENTRIES+EVENT_ENTRIES+PERMANENT_ENTRIES+(CHAOS_RESET,MIRROR_INVITATION)
TEMPLATES=frozenset(PRODUCTS)
# Keep the existing source identity so previously committed receipts remain valid.
POLICY='giant-raid-tickets-50ed-20261108-v1'
UNIT_PRICE=1_000_000

def offers():
    from els_server.domain.daily_ticket_rules import giant_definitions
    from els_server.domain.rosso_reset import definition
    if tuple(t[0] for t in giant_definitions().values())!=KEYS:raise ValueError('Original giant shop key definitions changed')
    for t in RESETS:definition(t)
    from els_server.domain.atma_temple_reward_flow import TAGS
    from els_server.domain.owned_scroll_families import catalog as scrolls
    from els_server.domain.daily_ticket_rules import tickets
    from els_server.domain.event_dungeons import definition as event_definition
    if RESTORES[0] not in TAGS or any(t not in scrolls()['challenge'] for t in RESTORES[1:]):
        raise ValueError('Dungeon reward restoration definition changed')
    for dungeon,t in ((34530,711786),(34540,711786),(34010,710131),(34030,710131),(35700,720832)):
        if t not in tickets(dungeon):raise ValueError('Daily extra-entry shop definition changed')
    for dungeon,t in zip((41550,41580,41620),EVENT_ENTRIES):
        if t not in event_definition(dungeon)['tickets']:raise ValueError('Event extra-entry shop definition changed')
    from els_server.domain.native_ticket_rules import tickets as permanent_tickets
    from els_server.storage.henir_chaos import RESET_TICKETS
    for dungeon,t in zip((35100,35360),PERMANENT_ENTRIES):
        if t not in permanent_tickets(dungeon):raise ValueError('Permanent entry shop definition changed')
    if CHAOS_RESET not in RESET_TICKETS:raise ValueError('Chaos reward reset shop definition changed')
    from els_server.domain.silver_mirror_catalog import INVITATIONS
    if MIRROR_INVITATION not in INVITATIONS:raise ValueError('Mirror weekly restoration shop definition changed')
    return tuple(dict(sku=1200000000+t,template=t,name=client_data().item(t)['name'],
                      category=41,price=UNIT_PRICE,quantity=1) for t in PRODUCTS)

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
