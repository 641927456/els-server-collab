"""Native Mirror selection: server-owned state, pinned routes and opaque fields."""
import functools,json,sqlite3,struct
from contextlib import closing
from els_server.domain import silver_mirror_policy as policy
from els_server.storage import silver_mirror_state as store
from els_server.protocol.protocol_codec import Event

@functools.lru_cache(maxsize=1)
def configuration():
    from els_server.paths import PROJECT_ROOT
    config=json.loads((PROJECT_ROOT/'config/dungeon_rotation_local.json').read_text(encoding='utf8'))
    if config['schema_version']!=2 or config['policy_file']!='els_server/data/silver_mirror.json'or not config['static_rotation_removed']or config['opaque_leading_fields']!=[0,0]or type(config.get('admissions_enabled'))is not bool:raise ValueError('Mirror runtime policy binding')
    return config

def admissions_enabled():return configuration()['admissions_enabled']

def rotation():
    import time
    from els_server.domain.dungeon_routes import route_catalog
    configuration()
    if any(not route_catalog().supports(i)for i in policy.ALL):raise ValueError('Mirror original route unavailable')
    normal,special=policy.layout(policy.week_start(time.time()))
    return dict(rotation=0,boss_count=0,normal=list(normal),story=special,buffs=[0,0])

def tower_encounter(identity):return identity in policy.ALL

def selected(identity,account=None):
    import time
    if not admissions_enabled():return False
    if account is None:
        return identity in policy.STORY.values()or identity in policy.deployed(policy.week_start(time.time()),0)
    try:
        with closing(sqlite3.connect(account.store.path,timeout=10))as db:
            db.execute('BEGIN')
            from els_server.storage.profession_state import require_owner
            from els_server.storage.item_actor import require_active_character
            require_owner(db,account.uid,account.account_id);require_active_character(db,account.uid)
            state=store.read(db,account.uid)
            policy.eligible(state['week'],state['memory'],state['progress'],identity)
            return not policy.blackout(time.time())
    except(ValueError,AttributeError):return False

def body(state=None):
    if state is None:
        r=rotation();normal,special,buffs=r['normal'],r['story'],r['buffs']
    else:
        normal,special=policy.layout(state['week']);buffs=[state['buff0'],state['buff1']]
    # Both leading native integers remain opaque compatibility zeros. Memory
    # is Engine+1870 map[3][1], not the previously misnamed second integer.
    return struct.pack('>10i',0,0,3,*normal,special,2,*buffs)

def notification(state=None):return Event(0x201,kind=0xcca,payload=body(state))

def in_db(db,owner,account_id):
    from els_server.protocol.content_count_messages import notification as counts
    from els_server.protocol.weekly_dungeon_counts import notification as weekly
    return[counts(db,owner,account_id),weekly(db,owner),notification(store.read(db,owner))]

def initialization(s):
    from els_server.domain.silver_mirror_flow import enabled
    if not enabled(s):return []
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        db.execute('BEGIN');store.guard(db,s.account.uid,s.account.account_id,lambda:enabled(s))
        return in_db(db,s.account.uid,s.account.account_id)

def handle(s,event):
    if event.event_id!=0x202 or event.kind!=0xccc:return None
    envelope=(event.performers==(0,)and event.uid==event.target_uid==2**64-1 and event.payload_mode==0)
    if envelope and len(event.payload)==4:
        from els_server.domain.silver_mirror_flow import choose
        return choose(s,struct.unpack('>i',event.payload)[0])
    if envelope and not event.payload and s.phase=='town_ready':
        try:
            events=initialization(s)
            if events:return [Event(0x201,kind=0xccd,payload=struct.pack('>i',0)+events[-1].payload),*events]
        except ValueError:pass
    return[Event(0x201,kind=0xccd,payload=struct.pack('>i',-1)+body())]
