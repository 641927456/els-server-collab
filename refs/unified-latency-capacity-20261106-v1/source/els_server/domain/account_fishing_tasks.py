"""Two exact original followups; genuine attempts/exchanges supply progress."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
IDS=frozenset((25601,25602))


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/account_fishing_followups.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='96f6c5152d49d255f4d09ff68b06c3de87b81330b43ea29e12e6c9ec1290733d':raise ValueError('Original fishing followup source')
    data=json.loads(raw)
    if set(map(int,data['quests']))!=IDS or set(map(int,data['subquests']))!={25602,25603}:raise ValueError('Finite fishing task scope')
    return data


def target(sub):
    if sub!=catalog()['subquests'].get(str(sub['m_iID'])):raise ValueError('Original fishing target source')
    if sub['m_iID']==25602:return sub['m_ClearCondition']['m_iClearCount']
    if sub['m_iID']==25603:return sub['m_ClearCondition']['m_iExchangeCount']
    raise ValueError('Finite fishing target')


def actor_binding(s):
    from els_server.domain.quest_flow import account_source_actor
    if not account_source_actor(s):raise ValueError('Fishing quest current account actor')
    a=s.account;app=getattr(s,'application',None);world=getattr(app,'world',None)
    if app is None or world is None:raise ValueError('Fishing quest actual Application world')
    room=world.room(s);entry=room.get(s)
    if s.phase=='town_ready'and(world.members.get(s)!=(1,s.active_map)or entry is None or entry[0]['uid']!=a.uid or entry[1]['map']!=s.active_map):raise ValueError('Fishing quest original town roster')
    if entry is None:room=None
    from pathlib import Path
    paths=(str(Path(a.store.path).resolve()),str(Path(a.characters.path).resolve()),str(Path(app.config.state_file).resolve()))
    if len(set(paths))!=1:raise ValueError('Fishing quest same original database paths')
    run=s.dungeon_run
    objects=(a,a.store,a.characters,getattr(a,'root',None),app,s.identity,world,room,entry,run)
    facts=(a.uid,a.account_id,a.store.uid,s.shop_session_id,s.role,s.phase,s.active_map,
       s.dungeon_id,None if run is None else(run.identity,run.run_id,run.stage,run.part,run.visits),
       repr(a.get_location()),id(getattr(a,'location',None)),repr(getattr(a,'location',None)),
       id(s.pending_map),repr(s.pending_map),getattr(s,'map_synchronizing',False),repr(s.completed),
       s.item_test,s.client_build,paths,world.members.get(s),repr(entry[0])if entry is not None else None,
       repr(entry[1])if entry is not None else None)
    return objects,facts


def current_actor(s,bound):
    try:
        now=actor_binding(s)
        return all(a is b for a,b in zip(now[0],bound[0]))and now[1]==bound[1]
    except(ValueError,AttributeError,KeyError,TypeError):return False


def actor_guard(s,bound):
    from pathlib import Path
    path=Path(bound[0][1].path).resolve();uid=bound[1][0];account=bound[1][1]
    def guard(db):
        from els_server.domain.quest_flow import account_source_guard
        if not current_actor(s,bound):raise ValueError('Fishing quest original actor graph changed')
        account_source_guard(s,db)
        if (not db.in_transaction or db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account,)
            or Path(next(r[2]for r in db.execute('PRAGMA database_list')if r[1]=='main')).resolve()!=path):raise ValueError('Fishing quest original owned database')
    return guard
