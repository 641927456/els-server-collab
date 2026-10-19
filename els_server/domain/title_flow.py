"""Title requests operate only on the session's authenticated selected character."""
from els_server.protocol import title_messages as wire
from els_server.storage import titles as store
from els_server.storage.title_levels import synchronize

def enabled(s):
    return s.client_build=='dx11_260923' and s.account.characters is not None and s.account.store is not None

def mission_key(uid,value):
    return (uid,tuple((m['mission'],m['flag'],tuple((p['sub'],p['count'],bool(p['done'])) for p in m['progress'])) for m in value['missions']))


def restore(s):
    value,events=synchronize(s.account.store.path,s.account.uid)
    s._title_active=(s.account.uid,value['title'])
    s._title_owned=(s.account.uid,tuple((r['title'],r['expires_at']) for r in value['owned']))
    s._title_missions=mission_key(s.account.uid,value)
    return events

def periodic(s):
    if not enabled(s) or s.role!='game' or s.phase not in ('town_ready','dungeon_active'):return []
    observe_kills(s)
    value,events=synchronize(s.account.store.path,s.account.uid);active=(s.account.uid,value['title'])
    owned=(s.account.uid,tuple((r['title'],r['expires_at']) for r in value['owned']))
    missions=mission_key(s.account.uid,value)
    previous=getattr(s,'_title_active',active);previous_owned=getattr(s,'_title_owned',None);previous_missions=getattr(s,'_title_missions',None)
    s._title_active=active;s._title_owned=owned;s._title_missions=missions
    return events if previous!=active or previous_owned!=owned or previous_missions!=missions else []

def handle(s,event):
    observe_kills(s)
    if event.event_id!=0x202 or event.kind not in (0xc22,0x213):return None
    if not enabled(s) or s.role!='game' or s.phase not in ('town_ready','dungeon_active'):
        return [wire.equipment(result=-1)] if event.kind==0x213 else [wire.initialization({},-1)]
    try:
        value=wire.request(event.payload)
        if event.kind==0xc22:return restore(s)
        answer=store.equip(s.account.store.path,s.account.uid,value);s._title_active=(s.account.uid,value)
        return [answer]
    except ValueError:
        return [wire.equipment(result=-1)] if event.kind==0x213 else [wire.initialization({},-1)]


def observe_kills(s):
    """Consume only accepted static solo deaths, before a stage can disappear.

    handle() runs before BB changes the cursor; periodic() covers idle actors.
    The persistent receipt, not this bounded cache, provides exactly-once credit.
    """
    if (not enabled(s) or s.role!='game' or s.phase!='dungeon_active' or not s.reward_test
        or not s.item_test or getattr(s,'dungeon_failed',False)) :return
    run=getattr(s,'dungeon_run',None)
    if run is None or run.run_id!=s.reward_run_id:return
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if not current_lease(s) or frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=frozenset((s.account.uid,)):return
    if getattr(s,'reward_transaction',None) is not None:return
    cursor=(s.account.uid,run.run_id,run.stage,run.part,run.visits)
    if getattr(s,'_title_kill_cursor',None)!=cursor:
        s._title_kill_cursor=cursor;s._title_kill_seen=set()
    from els_server.storage.title_kills import record
    from els_server.domain.dungeon_lifecycle import death_report
    for npc in run.current['npcs']:
        key=npc['key']
        if key not in run.defeated or key in s._title_kill_seen:continue
        if npc.get('dynamic') or npc.get('ally') or npc.get('team',1)==0:continue
        proof=run.defeated[key];death=death_report(proof)
        if death['index']!=key or death['killer']!=s.account.uid:continue
        context=dict(run=run.run_id,dungeon=run.identity,stage=run.stage,part=run.part,
                     visits=run.visits,key=key,npc=npc['template'],graph=run.graph['source_sha256'])
        record(s.account.store.path,s.account.uid,context,proof)
        s._title_kill_seen.add(key)
