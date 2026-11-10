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
    return events+[wire.shortcuts(store.shortcuts(s.account.store.path,s.account.uid))]

def periodic(s):
    if not enabled(s) or s.role!='game' or s.phase not in ('town_ready','guild_agit_ready','dungeon_active'):return []
    observe_kills(s)
    value,events=synchronize(s.account.store.path,s.account.uid);active=(s.account.uid,value['title'])
    owned=(s.account.uid,tuple((r['title'],r['expires_at']) for r in value['owned']))
    missions=mission_key(s.account.uid,value)
    previous=getattr(s,'_title_active',active);previous_owned=getattr(s,'_title_owned',None);previous_missions=getattr(s,'_title_missions',None)
    s._title_active=active;s._title_owned=owned;s._title_missions=missions
    if previous!=active and s.phase=='guild_agit_ready':
        from els_server.domain.guild_appearance import observe
        observe(s)
    return events if previous!=active or previous_owned!=owned or previous_missions!=missions else []

def handle(s,event):
    observe_kills(s)
    if event.event_id!=0x202 or event.kind not in (0xc22,0x213,0x9a7,0x9a9):return None
    if not enabled(s) or s.role!='game' or s.phase not in ('town_ready','guild_agit_ready','dungeon_active'):
        return rejection(event.kind)
    try:
        value=wire.shortcuts_request(event.payload)if event.kind==0x9a9 else wire.request(event.payload)
        guard=lambda db:None;publications=[]
        if s.phase=='guild_agit_ready':
            from els_server.domain.guild_agit_flow import bank_capture
            _,guard=bank_capture(s)
        if event.kind==0xc22:return restore(s)
        if event.kind==0x9a7:return [wire.shortcuts(store.shortcuts(s.account.store.path,s.account.uid))]
        if event.kind==0x9a9:return [store.save_shortcuts(s.account.store.path,s.account.uid,value,guard=guard)]
        from els_server.domain.guild_appearance import prepare,deliver
        publish=(lambda db:publications.append(prepare(db,s))) if s.phase=='guild_agit_ready' else None
        answer=store.equip(s.account.store.path,s.account.uid,value,guard=guard,prepare=publish)
        deliver(s,publications);s._title_active=(s.account.uid,value)
        return [answer]
    except ValueError:
        if event.kind==0x9a9:
            return rejection(event.kind,store.shortcuts(s.account.store.path,s.account.uid))
        return rejection(event.kind)


def rejection(kind,slots=None):
    if kind==0x213:return [wire.equipment(result=-1)]
    if kind==0x9a9:return [wire.shortcuts(slots or {},result=2512)]
    if kind==0x9a7:return [wire.shortcuts({})]
    return [wire.initialization({},-1)]


def _kill_run(s):
    if (not enabled(s) or s.role!='game' or s.phase!='dungeon_active' or not s.reward_test
        or not s.item_test or getattr(s,'dungeon_failed',False)) :return None
    run=getattr(s,'dungeon_run',None)
    if run is None or run.run_id!=s.reward_run_id:return None
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if not current_lease(s) or frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=frozenset((s.account.uid,)):return None
    if getattr(s,'reward_transaction',None) is not None:return None
    return run

def _kill_context(s,run,npc,proof):
    if npc.get('dynamic')or npc.get('ally')or npc.get('team',1)==0:return None
    from els_server.domain.dungeon_lifecycle import death_report
    death=death_report(proof)
    if death['index']!=npc['key']or death['killer']!=s.account.uid:return None
    return dict(run=run.run_id,dungeon=run.identity,stage=run.stage,part=run.part,
        visits=run.visits,key=npc['key'],npc=npc['template'],graph=run.graph['source_sha256'])

def _mark_kill(s,mark):
    cursor,key=mark
    run=s.dungeon_run
    if run is None or cursor!=(s.account.uid,run.run_id,run.stage,run.part,run.visits):return
    if getattr(s,'_title_kill_cursor',None)!=cursor:s._title_kill_cursor=cursor;s._title_kill_seen=set()
    s._title_kill_seen.add(key)

def accepted_death_in_writer(s,shadow,npc,proof,db):
    run=_kill_run(s);staged=shadow.dungeon_run
    if run is None or staged is None:return None
    if(run.run_id,run.stage,run.part,run.visits)!=(staged.run_id,staged.stage,staged.part,staged.visits):return None
    if not any(n is npc for n in run.current['npcs'])or staged.defeated.get(npc['key'])!=proof:return None
    context=_kill_context(s,run,npc,proof)
    if context is None:return None
    from els_server.storage.title_kills import record_in_transaction
    record_in_transaction(db,s.account.store.path,s.account.uid,context,proof)
    return(s.account.uid,run.run_id,run.stage,run.part,run.visits),npc['key']

def observe_kills(s):
    """Observe accepted static solo deaths; SQL receipts own exactly-once credit."""
    run=_kill_run(s)
    if run is None:return
    cursor=(s.account.uid,run.run_id,run.stage,run.part,run.visits)
    if getattr(s,'_title_kill_cursor',None)!=cursor:
        s._title_kill_cursor=cursor;s._title_kill_seen=set()
    from els_server.storage.title_kills import record
    for npc in run.current['npcs']:
        key=npc['key']
        if key not in run.defeated or key in s._title_kill_seen:continue
        proof=run.defeated[key];context=_kill_context(s,run,npc,proof)
        if context is None:continue
        record(s.account.store.path,s.account.uid,context,proof)
        s._title_kill_seen.add(key)
