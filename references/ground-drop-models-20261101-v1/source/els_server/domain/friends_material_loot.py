"""User-local34320 per-member material policy, not a claim of retail allocation.

Original map/source actors, native AD/CF/D0 serializers and inventory consumers
are reused. One real writer prepares every member before publishing any state.
"""
import copy,math,secrets,sqlite3,struct,uuid
from els_server.domain.ground_currency import coin_template
from contextlib import closing
from pathlib import Path

SOURCES=frozenset(((2,1,7519,1),(2,1,7520,2),(3,0,7511,1)))


class MaterialRefusal(ValueError):
    """A current owned room/source/region binding refused before commit."""


def _checked(s,*,dispatcher=None,room=None,claim=False):
    from els_server.domain.friends_dungeon import FriendsDungeons,Room
    from els_server.domain.friends_spawns import _checked_static_generation
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    app=s.application
    if dispatcher is None:dispatcher=app.world.dungeons
    if (not isinstance(dispatcher,FriendsDungeons) or dispatcher is not app.world.dungeons
            or dispatcher.world is not app.world):raise MaterialRefusal('Material dispatcher changed')
    if room is None:room=dispatcher.room(s)
    if (not isinstance(room,Room) or room.identity!=34320 or not 2<=len(room.members)<=4
            or s not in room.members or room.phase not in (('active','part_end','clear') if claim else ('active','part_end'))
            or room.party.get('run') is not room
            or any(room.party.get(k) for k in ('raid_party','challenge','challenge_pending','solo_challenge'))
            or room.party.get('difficulty',0)!=0 or room.party.get('mode',0)!=0):
        raise MaterialRefusal('Ordinary material room unavailable')
    seed=uuid.UUID(room.seed)
    if str(seed)!=room.seed or seed.version!=4:raise MaterialRefusal('Material room seed')
    try:generation=_checked_static_generation(dispatcher,room)
    except ValueError as error:raise MaterialRefusal(str(error)) from error
    paths=set()
    for member in room.members:
        account=member.account
        if (member.application is not app or member not in dispatcher.world.members
                or dispatcher.world.party_of.get(member) is not room.party
                or dispatcher.room(member) is not room or not current_lease(member)
                or member.dungeon_run.run_id!=room.seed or account.store is None or account.store.uid!=account.uid
                or not member.reward_test or not member.item_test or not member.drop_probe
                or member.client_build!='dx11_260923' or member.account.characters is None
                or member.reward_run_id!=str(uuid.uuid5(seed,'reward:'+str(account.uid)))
                or getattr(member,'reward_transaction',None) is not None
                or getattr(member,'active_challenge',None) is not None or getattr(member,'challenge_deadline',None) is not None
                or getattr(member,'dungeon_failed',False) or (not claim and member.clear_notified)):
            raise MaterialRefusal('Material member lease changed')
        paths.add(Path(account.store.path).resolve())
    if len(paths)!=1:raise MaterialRefusal('Material room database mismatch')
    return dispatcher,room,generation,next(iter(paths))


def _validate_actor(db,member):
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.bank_state import account_for
    from els_server.storage.seal_quests import load_character,completed_ids
    from els_server.domain.region_quests import region_catalog
    try:
        require_active_character(db,member.account.uid)
        if account_for(db,member.account.uid)!=member.account.account_id:raise ValueError('Material saved owner changed')
        character=load_character(db,member.account.uid,member.account.account_id)
        if not region_catalog().dungeon_allowed(34320,character,completed_ids(db,member.account.uid)):
            raise ValueError('Material original region admission')
    except ValueError as error:raise MaterialRefusal(str(error)) from error
    return character


def _clear_claim_checked(s):
    """An issued owner's in-flight D0 may follow peer clear/detach, never an active abort."""
    from els_server.domain.friends_dungeon import FriendsDungeons,Room
    from els_server.domain.dungeon_equipment_loot_flow import current_lease,identity
    from els_server.domain.dungeon_material_loot_catalog import accepted_source
    app=s.application;dispatcher=app.world.dungeons;room=dispatcher.room(s);run=s.dungeon_run
    if (not isinstance(dispatcher,FriendsDungeons) or dispatcher.world is not app.world
            or not isinstance(room,Room) or room.identity!=34320 or room.phase!='clear'
            or not 2<=len(room.members)<=4 or s not in room.members or s not in app.world.members
            or room.party.get('run') is not room or room.party.get('difficulty',0)!=0 or room.party.get('mode',0)!=0
            or any(room.party.get(k) for k in ('raid_party','challenge','challenge_pending','solo_challenge'))
            or not current_lease(s) or not app.registry.enabled(s.account.account_id)
            or s.phase!='dungeon_active' or not s.dungeon_substage_synced or not s.clear_notified
            or s.coop_error or s.social_overflow or getattr(s,'dungeon_failed',False)
            or not s.reward_test or not s.item_test or not s.drop_probe or not s.drop_test
            or s.client_build!='dx11_260923' or s.account.characters is None
            or getattr(s,'reward_transaction',None) is not None
            or getattr(s,'active_challenge',None) is not None or getattr(s,'challenge_deadline',None) is not None
            or run is None or run.identity!=34320 or (run.stage,run.part)!=(3,0)
            or not isinstance(run.next,dict) or run.next.get('kind')!=4):
        raise MaterialRefusal('Material clear owner unavailable')
    seed=uuid.UUID(room.seed)
    if (str(seed)!=room.seed or seed.version!=4 or run.run_id!=room.seed
            or s.reward_run_id!=str(uuid.uuid5(seed,'reward:'+str(s.account.uid)))):
        raise MaterialRefusal('Material clear owner epoch changed')
    connection=(s,s.shop_session_id,s.account.uid)
    origin=getattr(room,'static_actor_origin',None)
    generation=(room.seed,34320,run.run_id,run.stage,run.part,run.visits)
    if (not isinstance(origin,tuple) or len(origin)!=5 or origin[0] is not room
            or origin[2:4]!=(room.seed,34320) or not isinstance(origin[4],tuple)
            or len(origin[4])!=len(room.members)
            or not isinstance(origin[1],tuple) or len(origin[1])!=3
            or any(not isinstance(entry,tuple) or len(entry)!=3
                or not isinstance(entry[0],tuple) or len(entry[0])!=3 for entry in origin[4])
            or any(entry[0][0] is not member for entry,member in zip(origin[4],room.members))
            or origin[1][0] is not room.leader
            or [entry for entry in origin[4] if entry[0][0] is s]!=[(connection,run,run.run_id)]
            or getattr(room,'static_actor_generation',None)!=generation
            or s.dungeon_participants!=frozenset(entry[0][2] for entry in origin[4])):
        raise MaterialRefusal('Material clear original owner generation changed')
    party=room.party;members=party.get('members');current=app.world.party_of.get(s)
    if current is not None:
        if (current is not party or not isinstance(members,list) or s not in members
                or not 2<=len(members)<=len(room.members) or any(m not in room.members for m in members)
                or app.world.parties.get(party['id']) is not party):
            raise MaterialRefusal('Material clear current party changed')
    elif (members!=[s] or party.get('ready') or 'admission' in party
            or party['id'] in app.world.parties):
        raise MaterialRefusal('Material clear party was not normally dissolved')
    npcs=[n for n in run.current['npcs'] if n['template']==7511 and n['source_index']==1]
    if len(npcs)!=1 or not accepted_source(run,npcs[0]):
        raise MaterialRefusal('Material clear original final Boss changed')
    npc=npcs[0];proof=run.defeated.get(npc['key'])
    if not isinstance(proof,bytes) or not proof or len(proof)>8192:
        raise MaterialRefusal('Material clear accepted death missing')
    c=identity(s,npc['key']);path=Path(s.account.store.path).resolve()
    if path!=Path(app.config.state_file).resolve() or path!=Path(s.account.characters.path).resolve():
        raise MaterialRefusal('Material clear owner database is outside this application')
    # Include concrete mutable identity/proof/party projections in the callback
    # binding, not only references to objects whose contents can change.
    return (dispatcher,room,generation,path,connection,origin,c,proof,
        tuple(members),current is party,s.account,s.account.root,s.account.store)


def _clear_claim_validate(db,s,bound):
    from els_server.storage import dungeon_equipment_loot as storage
    from els_server.domain.dungeon_material_loot_catalog import POLICY,validate_issued
    import hashlib,json
    if _clear_claim_checked(s)!=bound:raise MaterialRefusal('Material clear owner changed before commit')
    attached=db.execute('PRAGMA database_list').fetchall()
    main=[row[2] for row in attached if row[1]=='main']
    if (len(main)!=1 or not main[0] or Path(main[0]).resolve()!=bound[3]
            or any(row[1] not in ('main','temp') for row in attached)):
        raise MaterialRefusal('Material clear pickup database changed')
    _validate_actor(db,s)
    c,proof=bound[6:8]
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dungeon_equipment_loot_issues'").fetchone():
        raise MaterialRefusal('Material clear issue was not committed')
    issued=storage.lookup(db,c)
    if issued is None or issued[:3]!=(34320,storage.digest(c,proof),POLICY):
        raise MaterialRefusal('Material clear issue proof changed')
    saved=json.loads(issued[3])
    if not isinstance(saved,list) or any(not isinstance(row,dict) for row in saved):
        raise MaterialRefusal('Material clear saved issue shape changed')
    rows=[row for row in saved if row.get('source')==POLICY]
    if not rows:raise MaterialRefusal('Material clear owner has no material issue')
    for row in rows:
        if (any(row.get(k)!=c[k] for k in c)
                or row.get('death_proof_sha256')!=hashlib.sha256(proof).hexdigest()):
            raise MaterialRefusal('Material clear issued context changed')
        validate_issued(row,c)


def claim_enabled(s,drop):
    from els_server.domain.dungeon_material_loot_catalog import POLICY
    if (s.dungeon_run is None or s.dungeon_run.identity!=34320 or drop.get('source')!=POLICY
            or drop.get('owner')!=s.account.uid or drop.get('run_id')!=s.reward_run_id):return False
    try:
        if getattr(s.application.world.dungeons.room(s),'phase',None)=='clear':_clear_claim_checked(s)
        else:_checked(s,claim=True)
    except (ValueError,AttributeError,KeyError,TypeError):return False
    return True


def claim_guard(s):
    if getattr(s.application.world.dungeons.room(s),'phase',None)=='clear':
        original=_clear_claim_checked(s)
        def validate_clear(db):_clear_claim_validate(db,s,original)
        return validate_clear
    original=_checked(s,claim=True)
    def validate(db):
        current=_checked(s,claim=True)
        if current!=original:raise MaterialRefusal('Material pickup room changed')
        if Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()!=original[3]:
            raise MaterialRefusal('Material pickup database changed')
        # Claim grants only this owner. Every current member's lease/loaded
        # source is checked above; this owner's saved identity is checked here.
        _validate_actor(db,s)
    return validate


def accepted_death(dispatcher,room,s,event,*,randbelow=secrets.randbelow):
    if room.identity!=34320 or not 2<=len(room.members)<=4 or s.dungeon_run is None:return None
    from els_server.domain.dungeon_lifecycle import death_report,death_ack,empty_reward_death_notice
    try:death=death_report(event.payload)
    except ValueError:return []
    run=s.dungeon_run;npc=next((n for n in run.current['npcs'] if n['key']==death['index']),None)
    if npc is None:return None
    from els_server.domain.dungeon_material_loot_catalog import accepted_source
    if (run.stage,run.part,npc['template'],npc['source_index']) not in SOURCES or not accepted_source(run,npc):return None
    try:
        bound=_checked(s,dispatcher=dispatcher,room=room)
        if (s is not room.leader or event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,)
                or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):return []
        participants=frozenset(member.account.uid for member in room.members)
        hp=struct.unpack('>f',struct.pack('>I',death['hp_bits']))[0]
        if (death['flag'] not in (0,1) or any(death[k] not in participants for k in ('source','killer','last_uid'))
                or any(uid not in participants for name in ('contribution','readiness','counters') for uid in death[name])
                or not math.isfinite(hp) or hp<=0 or any(npc['key'] in m.summon_keys for m in room.members)):return []
        for member in room.members:
            actor=next((n for n in member.dungeon_run.current['npcs'] if n['key']==npc['key']),None)
            if actor is None or actor!=npc or not accepted_source(member.dungeon_run,actor):return []
    except (MaterialRefusal,ValueError,AttributeError,KeyError,TypeError):return []
    previous=run.defeated.get(npc['key'])
    if previous is not None:return [death_ack()] if previous==event.payload else []
    if room.phase!='active':return []
    from els_server.domain.dungeon_equipment_loot_flow import identity
    from els_server.domain.dungeon_flow import local_rewards,periodic
    from els_server.domain.dungeon_drops import ground_drop_notice
    from els_server.domain.gm_rates import allow_drop
    from els_server.domain.quest_flow import store
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.storage import dungeon_equipment_loot as storage
    local_rule=local_rewards();base=run.run_id+':'+str(run.stage)+':'+str(run.part)+':kill:'+str(npc['key'])
    staged={};deliveries={};issues={};seen={}
    for member in room.members:
        shadow=copy.copy(member);shadow.dungeon_run=copy.copy(member.dungeon_run)
        shadow.dungeon_run.defeated={**member.dungeon_run.defeated,npc['key']:bytes(event.payload)}
        shadow.defeated_npcs=shadow.dungeon_run.defeated;shadow.dungeon_clock=copy.copy(member.dungeon_clock)
        staged[member]=shadow;seen[member]=set(getattr(member,'_quest_seen_events',None) or ())|{base}
    def validate(db):
        if _checked(s,dispatcher=dispatcher,room=room)!=bound:raise MaterialRefusal('Material room generation changed')
        return {member:_validate_actor(db,member) for member in room.members}
    try:
        with closing(sqlite3.connect(bound[3],timeout=10)) as db,db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            characters=validate(db)
            for member in room.members:
                c=identity(member,npc['key']);shadow=staged[member]
                witness=dict(kind='kill',dungeon=34320,npc=npc['template'],level=characters[member]['level'])
                notices=store(member).record(base,witness,event.payload,validate=validate,transaction=db)
                amount=local_rule['boss_ed']
                legacy=[dict(template=coin_template(amount),quantity=0,ed=amount,option_groups={})] if amount and allow_drop(member.reward_run_id,34320,(run.stage,run.part),npc['key'],True) else []
                def prepare(rows,replayed):
                    reply=[death_ack()] if member is s else []
                    if not replayed:reply.append(empty_reward_death_notice(npc['key'],death['killer']))
                    world=dict(member.world_drops)
                    for row in rows:
                        old=world.get(row['drop_id'])
                        if old is not None and any(old.get(k)!=row[k] for k in ('owner','run_id','stage','npc_key','template')):
                            raise ValueError('Material issue sequence collides with current ground item')
                        notice=ground_drop_notice(row['drop_id'],row['xyz'],uid=member.account.uid,template=row['template'])
                        row['payload_hex']=notice.payload.hex()
                        if old is None:world[row['drop_id']]=dict(row)
                        if not replayed:reply.append(notice)
                    reply.extend(notices);reply.extend(periodic(shadow))
                    return dict(reply=reply,world=world,sequence=max([member.world_drop_sequence,*[r['drop_id']+1 for r in rows]]),last=dict(rows[-1]) if rows else member.world_drop_issued)
                from els_server.domain.fishing_bait_loot import source as bait_source
                issued=storage.issue(bound[3],c,event.payload,True,member.world_drop_sequence,death['xyz'][3:],legacy,prepare,
                    randbelow=randbelow,account_id=member.account.account_id,transaction=db,bait=bait_source(member,next(n for n in member.dungeon_run.current['npcs'] if n['key']==npc['key']),dispatcher=dispatcher,room=room))
                issues[member]=issued;deliveries[member]=issued['reply']
            boxes=_prepared_boxes([(member,deliveries[member]) for member in room.members if member is not s],deliveries[s])
            validate(db)
    except (MaterialRefusal,storage.LootActorRejected):return []
    # No fallible encoders, quota checks, database calls or source resolvers
    # remain after the one outer writer successfully commits all members.
    for member,shadow in staged.items():
        for name in ('defeated','next','ready_at'):setattr(member.dungeon_run,name,getattr(shadow.dungeon_run,name))
        member.defeated_npcs=member.dungeon_run.defeated;member.part_end_notified=shadow.part_end_notified
        member.dungeon_clock=shadow.dungeon_clock;member._quest_seen_events=seen[member]
        member.world_drops=issues[member]['world'];member.world_drop_sequence=issues[member]['sequence'];member.world_drop_issued=issues[member]['last']
    for member,box in boxes.items():member.mailbox=box
    dispatcher.part_wait(room)
    return deliveries[s]
