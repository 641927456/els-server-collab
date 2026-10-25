"""Explicit user-authorized 2014 base EXP compatibility, never retail rules."""
import copy,functools,hashlib,json,sqlite3,struct
from contextlib import closing
from pathlib import Path

@functools.lru_cache(maxsize=1)
def policy():
    p=Path(__file__).resolve().parents[1]/'data/compat/legacy_2014_pve_exp.json'
    raw=p.read_bytes();m=json.loads(p.with_suffix('.manifest.json').read_text(encoding='utf8'));v=json.loads(raw)
    from els_server.game_data import CLIENT_SHA
    if (m['schema_version']!=1 or m['payload_sha256']!=hashlib.sha256(raw).hexdigest()
        or v['schema_version']!=1 or v['policy']!=m['policy'] or v['client_sha256']!=CLIENT_SHA
        or v['provenance']!='user_authorized_legacy_2014_extension'
        or set(v['levels'])!={str(i) for i in range(1,101)}
        or any(type(x) is not int or not 1<=x<=2**31-1 for x in v['levels'].values())
        or v['clear']['rate']!=0.3):raise ValueError('Legacy EXP policy identity/bounds')
    return v

def bind_run(run):
    p=policy();row=p['maps'].get(str(run.identity));run.legacy_experience=None
    if row is not None:
        if row['graph_sha256']!=run.graph['source_sha256']:raise ValueError('Legacy EXP route source changed')
        from els_server.domain.gm_rates import snapshot
        rate=snapshot()['experience_bp'];base_level=row.get('experience_base_level',row['npc_level'])
        if 'experience_base_level'in row:
            from els_server.game_data import client_data
            current=client_data().dungeon(run.identity)
            if run.identity!=120010 or base_level!=99 or row['npc_level']!=1 or current.get('m_bRelativeMonsterLevel')!=1 or current.get('m_MinLevel')!=99:raise ValueError('Relative EXP local reference/source')
        base=p['levels'][str(base_level)]
        run.legacy_experience=dict(policy=p['policy'],policy_sha256=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest(),
            npc_level=row['npc_level'],table_experience=base,experience_bp=rate,base_experience=min(2**31-1,base*rate//10000))

def enabled(s):
    from els_server.domain.raid_economy_flow import managed as raid_managed
    if raid_managed(s):return False
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    return bool(getattr(getattr(s,'dungeon_run',None),'legacy_experience',None) is not None
        and getattr(s,'reward_test',False) and getattr(s,'reward_run_id',None)==s.dungeon_run.run_id
        and s.phase=='dungeon_active' and s.dungeon_substage_synced and not getattr(s,'dungeon_failed',False)
        and getattr(s.account,'store',None) is not None and getattr(s,'reward_transaction',None) is None
        and getattr(s,'active_challenge',None) is None and current_lease(s)
        and frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))==frozenset((s.account.uid,)))

def eligible(npc,expired=False):
    return bool(not expired and npc.get('active') and not npc.get('no_drop') and not npc.get('ally')
                and npc.get('team',1)!=0 and not npc.get('dynamic'))

def identity(s,npc):
    r=s.dungeon_run
    numbers=dict(r.legacy_experience)
    resolved=r.catalog.static_npc_level(r.identity,r.graph,r.stage,r.part,npc)
    if resolved is not None and resolved!=numbers['npc_level']:
        base=policy()['levels'][str(resolved)];numbers.update(npc_level=resolved,table_experience=base,base_experience=min(2**31-1,base*numbers['experience_bp']//10000))
    return dict(owner=s.account.uid,run_id=s.reward_run_id,dungeon=r.identity,stage=r.stage,part=r.part,
        visits=r.visits,npc_key=npc['key'],template=npc['template'],source_index=npc['source_index'],boss=bool(npc['boss']),graph_sha256=r.graph['source_sha256'],**numbers)

def experience_limit():
    from els_server.game_data import client_data
    return min(2**31-1,client_data().thresholds[-1])

def clear_amount(s):
    if not enabled(s):return None
    from els_server.storage.legacy_pve_exp import run_total
    with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:total=run_total(db,s.account.uid,s.reward_run_id,clear_basis=True)
    f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
    return min(2**31-1,int(f32(f32(total)*f32(policy()['clear']['rate']))))

def accepted_death(s,event,npc,death,expired,finish):
    """Fallback AD path: SQL, positive AF, gate and memory become one result."""
    if not enabled(s) or not eligible(npc,expired):return None
    from els_server.storage.legacy_pve_exp import commit
    from els_server.domain.dungeon_lifecycle import experience_death_notice,death_ack
    from els_server.domain.dungeon_flow import periodic
    from els_server.protocol.protocol_codec import encode_event
    shadow=copy.copy(s);shadow.dungeon_run=copy.copy(s.dungeon_run)
    shadow.dungeon_run.defeated=dict(s.dungeon_run.defeated);shadow.dungeon_clock=copy.copy(s.dungeon_clock)
    shadow.world_drops=dict(s.world_drops)
    with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        result=commit(db,s.account.reward_store,identity(s,npc),event.payload,death['killer'])
        if result['replayed']:
            shadow.dungeon_run.defeated[npc['key']]=bytes(event.payload);shadow.defeated_npcs=shadow.dungeon_run.defeated
            replies=[death_ack(),*periodic(shadow)]
        else:
            notice=experience_death_notice(npc['key'],death['killer'],s.account.uid,result['experience'])
            replies=finish(shadow,event,npc,death,expired,notice)
        for e in replies:encode_event(e)
    for name in ('defeated','next','ready_at'):setattr(s.dungeon_run,name,getattr(shadow.dungeon_run,name))
    for name in ('defeated_npcs','part_end_notified','world_drops','world_drop_sequence','world_drop_issued'):
        setattr(s,name,getattr(shadow,name))
    s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
    return replies
