"""Original true-ending reward actor, existing ground issue/pickup writer.

The current Solace script kills2368 only from its true-ending callback.
Its invisible/invincible actor is a reward witness, not another combat kill.
The existing approved local display-completion rate also applies here; it is
not an official drop probability. Native AI/ending selection remains client-owned.
"""
import functools,hashlib,json,math,secrets,sqlite3,struct,sys,uuid
from contextlib import closing
from pathlib import Path

POLICY='native-true-ending-ground-reward-v1'
TEMPLATES=frozenset((30572,))
GRAPH_SHA='e4bb437fbd97673d8b17024b07013afab1c2baad334f85835da540d800ffb5e4'
FIELDS={'owner','run_id','dungeon','stage','part','visits','npc_key','graph_sha256','source_template','source_index'}


def context(value):
    from els_server.storage.character_schema import character_uid
    if not isinstance(value,dict) or set(value)!=FIELDS:raise ValueError('Script reward context')
    character_uid(value['owner'])
    if not isinstance(value['run_id'],str) or str(uuid.UUID(value['run_id']))!=value['run_id']:raise ValueError('Script reward UUID')
    if any(type(value[k]) is not int or not 0<=value[k]<2**31 for k in FIELDS-{'owner','run_id','graph_sha256'}):raise ValueError('Script reward bounds')
    if (value['dungeon'],value['stage'],value['part'],value['source_template'],value['source_index'],value['graph_sha256'])!=(33891,4,0,2368,6,GRAPH_SHA):raise ValueError('Script reward original source')
    return dict(value)


def policy_for(value):context(value);return POLICY


@functools.lru_cache(maxsize=1)
def descriptor(template):
    from els_server.game_data import client_data
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    if type(template) is not int or template not in TEMPLATES:raise ValueError('Script reward template')
    item=client_data().item(template)
    if (item['item_type'],item['equip_position'],VERIFIED_TEMPLATES[template],TEMPLATE_BAG_GROUPS[template],TEMPLATE_MAX_STACKS[template])!=(3,21,0,2,1):raise ValueError('Script reward current accessory reader')
    return dict(template=template,kind='native-accessory',record_sha256=hashlib.sha256(item['record']).hexdigest(),state=dict(metadata=0,group=2,max_stack=1))


def plans(identity,boss,randbelow,*,drop_bp=0):
    context(identity)
    if boss is not False or type(drop_bp) is not int or not 0<=drop_bp<=15000:raise ValueError('Script reward draw identity')
    from els_server.domain.formal_pve_economy import policy
    scale=100000000;threshold=min(scale,policy()['local']['current_boss_display_completion_bp']*(10000+drop_bp))
    draw=randbelow(scale)
    if type(draw) is not int or not 0<=draw<scale:raise ValueError('Script reward random bound')
    return [dict(template=30572,quantity=1,option_groups={},instance_descriptor=descriptor(30572))] if draw<threshold else []


def _actor(run,key=None):
    if (run is None or run.identity!=33891 or (run.stage,run.part)!=(4,0)
            or run.graph['source_sha256']!=GRAPH_SHA or run.graph!=run.catalog.graph(33891)):raise ValueError('Script reward original room')
    actors=[n for n in run.current['npcs'] if n['template']==2368 and n['source_index']==6]
    if len(actors)!=1:raise ValueError('Script reward original actor')
    npc=actors[0]
    if (key is not None and npc['key']!=key or npc.get('dynamic') or not npc['active'] or npc['boss']
            or npc['no_drop'] or npc.get('ally') or npc.get('team',1)!=1):raise ValueError('Script reward actor changed')
    return npc


def identity(s,key):
    run=s.dungeon_run;npc=_actor(run,key)
    return context(dict(owner=s.account.uid,run_id=s.reward_run_id,dungeon=33891,stage=4,part=0,visits=run.visits,npc_key=key,
                        graph_sha256=GRAPH_SHA,source_template=npc['template'],source_index=npc['source_index']))


def _bound(s,dispatcher=None,room=None):
    from els_server.domain.dungeon_hp_c1 import _lease,_solo
    from els_server.domain.friends_dungeon import FriendsDungeons,Room
    from els_server.domain.friends_spawns import _checked_static_generation
    app=getattr(s,'application',None) or getattr(s,'_c1_local_application',None)
    if app is None or not _lease(s):raise ValueError('Script reward actual lease')
    actual=app.world.dungeons.room(s)
    if room is None:room=actual
    if room is None:
        if dispatcher is not None or not _solo(s):raise ValueError('Script reward solo changed')
        members=(s,);generation=None
    else:
        if dispatcher is None:dispatcher=app.world.dungeons
        if (not isinstance(dispatcher,FriendsDungeons) or dispatcher is not app.world.dungeons or actual is not room
                or not isinstance(room,Room) or room.identity!=33891 or not 2<=len(room.members)<=4 or s not in room.members
                or room.phase not in ('active','part_end','clear') or room.party.get('run') is not room
                or room.party.get('difficulty',0)!=0 or room.party.get('mode',0)!=0
                or any(room.party.get(k) for k in ('raid_party','challenge','challenge_pending','solo_challenge'))):raise ValueError('Script reward shared room')
        generation=_checked_static_generation(dispatcher,room);members=tuple(room.members)
    roster=frozenset(m.account.uid for m in members);paths=set();captured=[]
    for m in members:
        run=m.dungeon_run;npc=_actor(run)
        if ((getattr(m,'application',None) or getattr(m,'_c1_local_application',None)) is not app or not _lease(m) or m.phase!='dungeon_active' or not m.dungeon_substage_synced or m.gate_stage_loading
                or m.dungeon_id!=33891 or m.client_build!='dx11_260923' or m.dungeon_participants!=roster
                or not m.reward_test or not m.item_test or not m.drop_probe or not m.drop_test
                or getattr(m,'reward_transaction',None) is not None or getattr(m,'active_challenge',None) is not None
                or getattr(m,'challenge_deadline',None) is not None or getattr(m,'dungeon_failed',False)
                or getattr(m,'coop_error',None) or getattr(m,'social_overflow',False) or npc['key'] in m.summon_keys):raise ValueError('Script reward live owner')
        seed=uuid.UUID(run.run_id)
        if str(seed)!=run.run_id or seed.version!=4:raise ValueError('Script reward server epoch')
        if room is None:
            if m.reward_run_id!=run.run_id:raise ValueError('Script reward solo epoch')
        elif (run.run_id!=room.seed or m.reward_run_id!=str(uuid.uuid5(seed,'reward:'+str(m.account.uid)))
                or dispatcher.room(m) is not room or dispatcher.world.party_of.get(m) is not room.party
                or bool(m.clear_notified)!=(room.phase=='clear')):raise ValueError('Script reward shared epoch')
        path=Path(m.account.store.path).resolve()
        if path!=Path(app.config.state_file).resolve() or path!=Path(m.account.characters.path).resolve():raise ValueError('Script reward owner database')
        paths.add(path)
        captured.append((m,m.account,m.account.store,m.shop_session_id,id(run),id(npc),identity(m,npc['key']),bytes(run.defeated.get(npc['key'],b'')),
                         bool(m.clear_notified),tuple(sorted((k,v) for k,v in run.defeated.items() if k!=npc['key']))))
    if len(paths)!=1:raise ValueError('Script reward shared database')
    return (app,room,generation,next(iter(paths)),tuple(captured))


def _validate(db,s,bound):
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.bank_state import account_for
    from els_server.storage.seal_quests import load_character,completed_ids
    from els_server.domain.region_quests import region_catalog
    if _bound(s)!=bound:raise ValueError('Script reward authority changed')
    attached=db.execute('PRAGMA database_list').fetchall()
    if (not db.in_transaction or [r[1] for r in attached if r[1] not in ('main','temp')]
            or Path(next(r[2] for r in attached if r[1]=='main')).resolve()!=bound[3]):raise ValueError('Script reward writer changed')
    for entry in bound[4]:
        m=entry[0];require_active_character(db,m.account.uid)
        if account_for(db,m.account.uid)!=m.account.account_id:raise ValueError('Script reward saved owner')
        character=load_character(db,m.account.uid,m.account.account_id)
        if not region_catalog().dungeon_allowed(33891,character,completed_ids(db,m.account.uid)):raise ValueError('Script reward original admission')
        if m.clear_notified:
            run=m.dungeon_run
            bosses=[n for n in run.current['npcs'] if n['template']==2363 and n['source_index']==1 and n['boss']]
            if (len(bosses)!=1 or not run.defeated.get(bosses[0]['key']) or not m.part_end_notified
                    or not isinstance(run.next,dict) or run.next.get('kind')!=4
                    or not db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(m.reward_run_id,)).fetchone()):raise ValueError('Script reward committed clear witness')
    return True


def accepted_death(s,event,*,dispatcher=None,room=None,randbelow=None):
    if event.event_id!=0x202 or event.kind!=0xad:return None
    run=s.dungeon_run
    if run is None or run.identity!=33891 or (run.stage,run.part)!=(4,0):return None
    from els_server.domain.dungeon_lifecycle import death_report,death_ack,empty_reward_death_notice
    try:death=death_report(event.payload)
    except ValueError:return []
    actor=next((n for n in run.current['npcs'] if n['key']==death['index']),None)
    if actor is None or actor['template']!=2368:return None
    try:
        bound=_bound(s,dispatcher,room);members=tuple(row[0] for row in bound[4]);room=bound[1]
        if (room is not None and s is not room.leader or event.performers!=(0,) or event.uid!=2**64-1
                or event.target_uid!=2**64-1 or event.payload_mode!=0):return []
        participants=frozenset(m.account.uid for m in members);identities=participants|frozenset((0,2**64-1))
        hp=struct.unpack('>f',struct.pack('>I',death['hp_bits']))[0]
        if (death['flag'] not in (0,1) or not math.isfinite(hp) or hp<=0
                or any(death[k] not in identities for k in ('source','killer','last_uid'))
                or any(uid not in participants for name in ('contribution','readiness','counters') for uid in death[name])):return []
        key=_actor(run,death['index'])['key']
        previous=[m.dungeon_run.defeated.get(key) for m in members]
        if any(p is not None for p in previous):return [death_ack()] if all(p==event.payload for p in previous) else []
        from els_server.storage import dungeon_equipment_loot as storage
        from els_server.domain.dungeon_drops import ground_drop_notice
        from els_server.domain.pve_economy_flow import _prepare_mailboxes,_mailboxes_unchanged
        prepared={};deliveries={}
        with closing(storage.connect(bound[3])) as db,db:
            db.execute('BEGIN IMMEDIATE');_validate(db,s,bound)
            for m in members:
                def prepare(rows,replayed):
                    if replayed:raise ValueError('Script reward fresh actor has persisted issue')
                    world=dict(m.world_drops);reply=([death_ack()] if m is s else [])+[empty_reward_death_notice(key,death['killer'])]
                    for row in rows:
                        if row['drop_id'] in world:raise ValueError('Script reward ground sequence collision')
                        notice=ground_drop_notice(row['drop_id'],row['xyz'],uid=m.account.uid,template=row['template'])
                        row['payload_hex']=notice.payload.hex();world[row['drop_id']]=dict(row);reply.append(notice)
                    return dict(reply=reply,world=world,sequence=max([m.world_drop_sequence,*[r['drop_id']+1 for r in rows]]),last=dict(rows[-1]) if rows else m.world_drop_issued)
                prepared[m]=storage.issue(bound[3],identity(m,key),event.payload,False,m.world_drop_sequence,death['xyz'][3:],[],prepare,
                    rules=sys.modules[__name__],account_id=m.account.account_id,transaction=db,randbelow=randbelow or secrets.randbelow)
                deliveries[m]=prepared[m]['reply']
            if room is not None:boxes,snapshots=_prepare_mailboxes([(m,deliveries[m]) for m in members],s)
            else:
                from els_server.protocol.protocol_codec import encode_event
                for reply_event in deliveries[s]:encode_event(reply_event)
                boxes,snapshots={},[]
            _validate(db,s,bound);_mailboxes_unchanged(snapshots)
        for m in members:
            m.dungeon_run.defeated={**m.dungeon_run.defeated,key:bytes(event.payload)};m.defeated_npcs=m.dungeon_run.defeated
            m.world_drops=prepared[m]['world'];m.world_drop_sequence=prepared[m]['sequence'];m.world_drop_issued=prepared[m]['last']
        for m,box in boxes.items():m.mailbox=box
        return deliveries[s]
    except (ValueError,AttributeError,KeyError,TypeError,sqlite3.Error):return []


def grant(db,row,c):
    """Use the existing typed acquisition factory; generic30572 stays closed."""
    from els_server.storage import dungeon_equipment_loot as storage
    from els_server.domain.reward_rules import item_plan
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.storage.inventory_state import grant_items
    context(c)
    if (row['template']!=30572 or row['quantity']!=1 or row['option_groups']!={}
            or row['instance_descriptor']!=descriptor(30572)):raise ValueError('Script reward saved item')
    def guard(writer):
        saved=storage.lookup(writer,c)
        return bool(saved is not None and saved[0]==33891 and saved[2]==POLICY and row in json.loads(saved[3]) and row['claimed_uids'] is None)
    operation='script-reward:'+str(uuid.uuid5(uuid.UUID(c['run_id']),str(row['drop_id'])))
    plan=[item_plan(30572,1)]
    source=_issue_source(db,c['owner'],operation,'ordinary',dict(c,death_proof_sha256=row['death_proof_sha256'],reward_source=POLICY),plan,guard)
    awarded=grant_items(db,plan,c['owner'],raid_reward_source=source)
    if len(awarded)!=1 or (awarded[0]['template'],awarded[0]['metadata'],awarded[0]['group'],awarded[0]['count'])!=(30572,0,2,1):raise ValueError('Script reward native factory result')
    return awarded


def claim(s,request,drop):
    from els_server.storage import dungeon_equipment_loot as storage
    from els_server.storage.inventory_state import InventoryFull
    from els_server.domain.dungeon_drops import ground_pickup_notice,pickup_inventory_notice
    from els_server.protocol.protocol_codec import Event,encode_event
    try:
        bound=_bound(s);c=identity(s,drop['npc_key']);proof=s.dungeon_run.defeated.get(c['npc_key'])
        if (drop.get('source')!=POLICY or any(drop.get(k)!=v for k,v in c.items()) or not isinstance(proof,bytes)
                or hashlib.sha256(proof).hexdigest()!=drop['death_proof_sha256']
                or request['template']!=drop['template'] or request['drop_id']!=drop['drop_id']):return []
        def validate(db):_validate(db,s,bound)
        def prepare(items,replayed):
            reply=[Event(0x201,kind=0xd1,payload=bytes(4))]
            if not replayed:reply.append(ground_pickup_notice(drop['drop_id'],s.account.uid,template=30572))
            reply.append(pickup_inventory_notice(items))
            for event in reply:encode_event(event)
            return dict(reply=reply,replayed=replayed,items=items)
        result=storage.claim(s.account.store.path,c,request['drop_id'],request['template'],prepare,rules=sys.modules[__name__],account_id=s.account.account_id,validate=validate)
    except InventoryFull:return [Event(0x201,kind=0xd1,payload=struct.pack('>i',-1))]
    except (ValueError,AttributeError,KeyError,TypeError,sqlite3.Error):return []
    drop['pickup_committed']=True;s.pickup_receipt={'dungeon_run_id':s.reward_run_id,'drop_id':drop['drop_id'],**result}
    return result['reply']
