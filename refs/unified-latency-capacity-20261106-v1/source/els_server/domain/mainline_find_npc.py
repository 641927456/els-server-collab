"""Finite original FindNPC tasks: admitted part and native creation witnesses.

2014 DungeonRoom's loaded-part list and GS accepted NPC-create notifications
feed FindNPC; current B3/BD and 2CE/2D0 retain those sources. No proximity,
spawn, kill, timer or client effect is fabricated here.
"""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA

PAYLOAD_SHA='16e11be14cf010b339b7e67007b998f8b875adf8ea4d6f33738a4bc1a1e1a88f'


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/mainline_find_npc.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA:raise ValueError('FindNPC source identity')
    value=json.loads(raw)
    if value['schema_version']!=1 or value['client_sha256']!=CLIENT_SHA:raise ValueError('FindNPC client identity')
    from els_server.domain.dungeon_routes import route_catalog
    for identity,digest in value['graphs'].items():
        if route_catalog().graph(int(identity))['source_sha256']!=digest:raise ValueError('FindNPC graph identity')
    return value


def supported(sub):
    entry=catalog()['subquests'].get(str(sub.get('m_iID')))
    return entry is not None and sub==entry['source']


def target(sub):
    if not supported(sub):raise ValueError('FindNPC source definition')
    return 1


def increment(sub,event):
    if not supported(sub) or event.get('kind')!='visit_dungeon':return 0
    witness=event.get('mainline_find')
    if not isinstance(witness,dict) or set(witness)!={'policy','source','subquests'}:return 0
    if witness['policy']!='accepted-part-or-NPC-create-v1':return 0
    source=catalog()['graphs'].get(str(event['dungeon']))
    return int(source is not None and witness['source']==source and sub['m_iID'] in witness['subquests'])


def _creation(entries):
    from els_server.protocol.npc_uid_map import uid_translation_vector
    return (struct.pack('>I',len(entries))+b''.join(n['wire'] for n in entries)+bytes(8)
            +uid_translation_vector((n['key'],n['template']) for n in entries)
            +struct.pack('>I',len(entries))+b''.join(struct.pack('>i',n['key'])+n['init'] for n in entries)+bytes(8))


def _actor(s,run):
    from els_server.domain.quest_flow import account_source_actor
    if (not account_source_actor(s) or s.phase!='dungeon_active' or run is None or run is not s.dungeon_run
        or not s.dungeon_substage_synced or run.started_at is None or s.clear_notified
        or s.dungeon_id!=run.identity or s.reward_run_id!=run.run_id):return None
    registry=getattr(getattr(s,'application',None),'registry',None)
    if registry is not None and not registry.enabled(s.account.account_id):return None
    if catalog()['graphs'].get(str(run.identity))!=run.graph.get('source_sha256'):return None
    from els_server.domain.dungeon_routes import route_catalog
    if run.graph!=route_catalog().graph(run.identity):return None
    return (str(s.account.store.path),s.account.account_id,s.account.uid,s.shop_session_id,
            id(s.account.root),id(s.account),id(run),run.run_id,run.identity,run.stage,run.part,run.visits)


def _members(entries):
    return tuple((id(n),n['key'],n['template'],hashlib.sha256(n['wire']).hexdigest()) for n in entries)


def _matching(s,run,entries,state):
    hits=set();generations=[]
    for row in state['active']:
        if row['id'] not in catalog()['quest_ids']:continue
        selected=[]
        for sid,definition in catalog()['subquests'].items():
            if row['id'] not in definition['quests']:continue
            identity=int(sid)
            # Raw source lookup is independently checked by target/loader;
            # never reuse another task's current objective state.
            if identity not in row['objectives'] or row['objectives'][identity]>=1:continue
            from els_server.domain.mainline_subquest_groups import can_progress
            from els_server.domain.seal_quests import quest_catalog
            if not can_progress(quest_catalog().quest(row['id']),definition['source'],row['objectives']):continue
            for entry in entries:
                if entry['key'] in run.defeated:continue
                for match in definition['matches']:
                    if match['dungeon']!=run.identity or match['stage']!=run.stage:continue
                    if match['kind']=='static':
                        valid=(not entry.get('dynamic') and match['part']==run.part
                               and all(entry.get(k)==v for k,v in match['source'].items()))
                    else:
                        valid=(entry.get('dynamic') is True and entry['template']==match['npc']
                               and entry['template'] in run.graph['stages'][str(run.stage)]['allowed_summons'])
                    if valid:selected.append(identity);break
                if identity in selected:break
        if selected:
            hits.update(selected);generations.append((row['id'],row['generation'],row['accepted_at']))
    relevant={q for sid in hits for q in catalog()['subquests'][str(sid)]['quests']}
    generations=[(row['id'],row['generation'],row['accepted_at']) for row in state['active'] if row['id'] in relevant]
    return sorted(hits),sorted(generations)


class RetiredSource(ValueError):
    pass


def observe(s,run,replies,store):
    """Only original server-emitted BD/2D0 can capture a new progress source."""
    actor=_actor(s,run)
    if actor is None:
        s._mainline_find_pending=[]
        return []
    pending=[w for w in getattr(s,'_mainline_find_pending',[]) if w['actor']==actor]
    from els_server.protocol.dungeon_messages import begin_substage
    expected=begin_substage(run.part,npc_entries=((n['key'],n['template']) for n in run.current['npcs'])).payload
    witnesses=[]
    for reply in replies:
        if reply.event_id!=0x201:continue
        if reply.kind==0xbd and reply.payload==expected:
            witnesses.append((reply,tuple(run.current['npcs'])))
        elif reply.kind==0x2d0 and len(reply.payload)>=4:
            count=struct.unpack_from('>I',reply.payload)[0]
            entries=run.current['npcs']
            if not 1<=count<=64:continue
            for first in range(len(entries)-count+1):
                batch=tuple(entries[first:first+count])
                if all(n.get('dynamic') for n in batch) and _creation(batch)==reply.payload:
                    witnesses.append((reply,batch));break
    if witnesses:
        state=store.notification_snapshot()
        for reply,entries in witnesses:
            hits,generations=_matching(s,run,entries,state)
            if not hits:continue
            evidence=dict(actor=list(actor),source=run.graph['source_sha256'],subquests=hits,
                          generations=generations,members=_members(entries),notice_kind=reply.kind,
                          notice_sha256=hashlib.sha256(reply.payload).hexdigest())
            raw=json.dumps(evidence,sort_keys=True,separators=(',',':')).encode()
            identity='mainline-find:'+hashlib.sha256(raw).hexdigest()
            if not any(w['identity']==identity for w in pending):
                pending.append(dict(actor=actor,entries=entries,members=_members(entries),hits=hits,generations=generations,
                                    identity=identity,raw=raw))
    if len(pending)>64:raise ValueError('FindNPC pending source bound')
    # A failed precommit encoder retains the exact already-admitted witness.
    # It cannot create evidence for newly accepted tasks or another run/part.
    s._mainline_find_pending=pending
    events=[]
    for witness in tuple(pending):
        transaction=[None]
        def validate(db):
            from els_server.storage.item_actor import require_active_character
            if _actor(s,run)!=witness['actor'] or _members(witness['entries'])!=witness['members']:
                raise RetiredSource('FindNPC source actor changed')
            if any(not any(n is original for n in run.current['npcs']) or n['key'] in run.defeated for original in witness['entries'] for n in [original]):
                raise RetiredSource('FindNPC instance retired')
            if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(s.account.uid,)).fetchone()!=(s.account.account_id,):
                raise RetiredSource('FindNPC SQL owner changed')
            require_active_character(db,s.account.uid)
            for qid,generation,accepted in witness['generations']:
                if db.execute('SELECT generation,accepted_at FROM character_quests WHERE owner=? AND quest=?',(s.account.uid,qid)).fetchone()!=(generation,accepted):
                    raise RetiredSource('FindNPC acceptance changed')
            # Shared objective IDs may belong to more than one source task;
            # do not let a concurrent new acceptance consume an earlier notice.
            expected_ids={q for q,_,_ in witness['generations']}
            relevant={q for sid in witness['hits'] for q in catalog()['subquests'][str(sid)]['quests']}
            active_ids={q for q, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(s.account.uid,))}
            if active_ids & relevant != expected_ids:raise RetiredSource('FindNPC active task set changed')
            transaction[0]=db
        def prepare(replies,replayed):
            from els_server.protocol.protocol_codec import encode_event
            for reply in replies:encode_event(reply)
            validate(transaction[0])
            return replies
        event=dict(kind='visit_dungeon',dungeon=run.identity,level=s.account.character()['level'],
                   mainline_find=dict(policy='accepted-part-or-NPC-create-v1',source=run.graph['source_sha256'],subquests=witness['hits']))
        try:
            events.extend(store.record(witness['identity'],event,witness['raw'],validate=validate,prepare=prepare))
        except RetiredSource:
            pending.remove(witness)
            continue
        pending.remove(witness)
    return events
