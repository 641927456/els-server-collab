"""Five ordinary original Boss sources: explicit local7.5%, original ground flow.

The first finite slice supports solo five maps and the existing shared34320
material transaction. It does not open the other four maps' party loot.
"""
import hashlib,json,sqlite3,struct
from pathlib import Path

POLICY='fishing-bait-five-original-boss-local-v1'
MAPS=frozenset((30282,33202,33232,33252,34320))
TEMPLATES=frozenset((99809,))
WRITER_ENABLED=True


def _canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'))


def _facts(s):
    app=getattr(s,'application',None);world=getattr(app,'world',None)
    return (id(world),id(getattr(world,'dungeons',None)),id(getattr(app,'registry',None)),
            repr(getattr(s,'identity',None)),getattr(s,'active_map',None),repr(s.account.get_location()),
            repr(getattr(s,'pending_map',None)),getattr(s,'map_synchronizing',None))


def _actor(run,npc):
    from els_server.domain.hunter_chest_rules import SOURCE_ROUTES
    if (run.identity not in MAPS or run.graph['source_sha256']!=SOURCE_ROUTES[run.identity][1]
            or not any(n is npc for n in run.current['npcs']) or npc.get('dynamic')
            or npc.get('hunter_source') or not npc['active'] or not npc['boss']
            or npc['no_drop'] or npc.get('ally') or npc.get('team',1)==0):
        raise ValueError('Bait exact original Boss source')
    def leaves(row):
        if 'options' in row:
            for child in row['options']:yield from leaves(child)
        else:yield row
    part=run.graph['stages'][str(run.stage)]['parts'][str(run.part)]
    matches=[a for group in part['groups'] for n in group['npcs'] for a in leaves(n)
             if (a['template'],a['source_index'])==(npc['template'],npc['source_index'])
             and a['active'] and a['boss'] and not a['no_drop']
             and not a.get('ally') and a.get('team',1)!=0]
    if len(matches)!=1:raise ValueError('Bait current graph Boss identity')
    return dict(stage=run.stage,part=run.part,template=npc['template'],source_index=npc['source_index'],npc_key=npc['key'])


class _Source:
    def __init__(self,s,npc,dispatcher=None,room=None):
        from els_server.domain.hunter_chest_flow import _checked
        self.s=s;self.npc=npc;self.dispatcher=dispatcher;self.room=room
        self.bound=_checked(s,dispatcher,room)
        members,actual_room,path,context,_=self.bound
        if actual_room is not None and s.dungeon_run.identity!=34320:
            raise ValueError('Bait other party transaction not qualified')
        self.actor=_actor(s.dungeon_run,npc)
        self.origin=dict(policy=POLICY,source_run=s.dungeon_run.run_id,actor=self.actor,
                         graph_sha256=s.dungeon_run.graph['source_sha256'],roster=context['roster'])
        self.owner=s.account.uid;self.account=s.account.account_id;self.path=path;self.writing=False
        self.facts=_facts(s)

    def validate(self,db):
        from els_server.storage.dungeon_equipment_loot import LootActorRejected
        try:return self._validate(db)
        except (ValueError,AttributeError,KeyError,TypeError,StopIteration) as error:
            raise LootActorRejected(str(error)) from error

    def _validate(self,db):
        if self.writing and not WRITER_ENABLED:raise ValueError('Bait writer held before commit')
        from els_server.domain.hunter_chest_flow import _checked
        from els_server.storage.item_actor import require_active_character
        from els_server.storage.profession_state import require_owner
        from els_server.storage.seal_quests import load_character,completed_ids
        from els_server.domain.region_quests import region_catalog
        if (_checked(self.s,self.dispatcher,self.room)!=self.bound or _facts(self.s)!=self.facts
                or _actor(self.s.dungeon_run,self.npc)!=self.actor
                or self.s.dungeon_run.defeated.get(self.npc['key']) is not None):
            raise ValueError('Bait original source/lease/generation changed')
        attached=db.execute('PRAGMA database_list').fetchall()
        if (not db.in_transaction or any(r[1] not in ('main','temp') for r in attached)
                or Path(next(r[2] for r in attached if r[1]=='main')).resolve()!=self.path):
            raise ValueError('Bait transaction database')
        for m in self.bound[0]:
            require_active_character(db,m.account.uid);require_owner(db,m.account.uid,m.account.account_id)
            c=load_character(db,m.account.uid,m.account.account_id)
            if not region_catalog().dungeon_allowed(self.s.dungeon_run.identity,c,completed_ids(db,m.account.uid)):
                raise ValueError('Bait original region qualification')

    def issue(self,db,c,proof,drop_id,xyz,randbelow):
        self.writing=True
        self.validate(db)
        if not WRITER_ENABLED:raise ValueError('Bait new source held')
        from els_server.storage.fishing_bait_loot import issue
        return issue(db,c,proof,drop_id,xyz,self.origin,self.account,randbelow)


def source(s,npc,*,dispatcher=None,room=None):
    run=s.dungeon_run
    if (not WRITER_ENABLED or run is None or run.identity not in MAPS
            or not npc.get('active') or not npc.get('boss') or npc.get('dynamic')
            or npc.get('hunter_source') or npc.get('no_drop') or npc.get('ally') or npc.get('team',1)==0):return None
    return _Source(s,npc,dispatcher,room)


def _claim_source(s,drop):
    from els_server.domain.dungeon_equipment_loot_flow import enabled,identity,_claim_context
    from els_server.domain.dungeon_material_loot_catalog import POLICY as MATERIAL_POLICY
    from els_server.domain.manufacture_flow import _binding,_saved_paths
    from els_server.domain.friends_material_loot import _clear_claim_checked
    from els_server.domain.hunter_chest_flow import _checked as _hunter_checked
    import copy,uuid
    run=s.dungeon_run
    if run is None or run.identity not in MAPS:raise ValueError('Bait current issued run missing')
    room=s.application.world.dungeons.room(s)if getattr(s,'application',None)is not None else None
    if room is not None and run.identity!=34320:raise ValueError('Bait other party remains held')
    if room is not None and room.phase=='clear':
        mode='clear';extra=_clear_claim_checked(s);members=None;path=extra[3]
    else:
        # Preserve every original active loaded roster/build/flag/lease gate,
        # including current exit-part2; only the issued actor cursor is older.
        extra=_hunter_checked(s);members=extra[0];path=extra[2]
        mode='solo'if room is None else'party'
    # Reuse exactly the established34320 same-stage Boss-part1 -> exit-part2
    # retention. No other stage, visit or run is projected backwards.
    c=_claim_context(s,dict(drop,source=MATERIAL_POLICY),None)
    if any(drop.get(k)!=v for k,v in c.items()):raise ValueError('Bait issued source cursor changed')
    if mode=='clear'and(c['stage'],c['part'])!=(3,0):raise ValueError('Bait clear only original finalBoss')
    source=copy.copy(run);source.part=c['part']
    npc=next((n for n in source.current['npcs']if n['key']==c['npc_key']),None)
    if npc is None:raise ValueError('Bait original source actor missing')
    actor=_actor(source,npc);proof=run.defeated.get(npc['key'],b'')
    if not isinstance(proof,bytes)or not proof or hashlib.sha256(proof).hexdigest()!=drop.get('death_proof_sha256'):raise ValueError('Bait original accepted death changed')
    origin=drop.get('bait_origin')
    if not isinstance(origin,dict)or any(origin.get(k)!=v for k,v in dict(policy=POLICY,source_run=run.run_id,actor=actor,graph_sha256=run.graph['source_sha256']).items()):raise ValueError('Bait issued original source')
    if members is not None:
        roster=[dict(owner=m.account.uid,account=m.account.account_id,connection=m.shop_session_id,reward_run=m.reward_run_id)for m in members]
        if origin.get('roster')!=roster:raise ValueError('Bait original current source roster')
    else:
        # The mature clear/detach guard checks this exact original owner's
        # static generation. Other peers may have normally retired their lease.
        own=dict(owner=s.account.uid,account=s.account.account_id,connection=s.shop_session_id,reward_run=s.reward_run_id)
        if not isinstance(origin.get('roster'),list)or [r for r in origin['roster']if r.get('owner')==s.account.uid]!=[own]:raise ValueError('Bait original clear owner roster')
    b=_binding(s)
    binding=tuple(id(b[n])for n in(0,1,2,3,8,9))+b[4:8]+(id(run),id(npc),run.stage,run.part,run.visits,repr(run.next),_facts(s))
    return mode,extra,path,binding,c,_canonical(origin)


def claim(s,request,drop):
    if drop.get('source')!=POLICY:return None
    from els_server.protocol.protocol_codec import Event,encode_event
    from els_server.storage.inventory_state import InventoryFull
    try:
        if drop.get('owner')!=s.account.uid or drop.get('run_id')!=s.reward_run_id:return []
        bound=_claim_source(s,drop);path=bound[2];c=bound[4];context=json.loads(bound[5])
        def validate(db):
            from els_server.storage.item_actor import require_active_character
            from els_server.storage.profession_state import require_owner
            if _claim_source(s,drop)!=bound:raise ValueError('Bait pickup original actor/source changed')
            attached=db.execute('PRAGMA database_list').fetchall()
            if not db.in_transaction or any(r[1]not in('main','temp')for r in attached)or Path(next(r[2]for r in attached if r[1]=='main')).resolve()!=path:raise ValueError('Bait pickup database')
            require_active_character(db,s.account.uid);require_owner(db,s.account.uid,s.account.account_id)
        def prepare(items,replayed):
            from els_server.domain.dungeon_drops import ground_pickup_notice,pickup_inventory_notice
            reply=[Event(0x201,kind=0xd1,payload=bytes(4))]
            if not replayed:reply.append(ground_pickup_notice(drop['drop_id'],s.account.uid,template=99809))
            reply.append(pickup_inventory_notice(items))
            for e in reply:encode_event(e)
            return reply
        from els_server.storage.fishing_bait_loot import claim as commit
        result=commit(path,c,request,drop,context,s.account.account_id,prepare,validate)
        drop['pickup_committed']=True;s.pickup_receipt=dict(dungeon_run_id=s.reward_run_id,drop_id=drop['drop_id'],replayed=result['replayed'])
        return result['reply']
    except InventoryFull:
        try:
            if _claim_source(s,drop)!=bound:return []
            reply=[Event(0x201,kind=0xd1,payload=struct.pack('>i',-1))]
            for e in reply:encode_event(e)
            return reply if _claim_source(s,drop)==bound else []
        except(ValueError,AttributeError,KeyError,TypeError):return []
    except(ValueError,sqlite3.Error,AttributeError,KeyError,TypeError,StopIteration):return []
