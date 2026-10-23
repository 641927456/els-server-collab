"""User-local34320 per-member material policy, not a claim of retail allocation.

Original map/source actors, native AD/CF/D0 serializers and inventory consumers
are reused. One real writer prepares every member before publishing any state.
"""
import copy,math,secrets,sqlite3,struct,uuid
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


def claim_enabled(s,drop):
    from els_server.domain.dungeon_material_loot_catalog import POLICY
    if (s.dungeon_run is None or s.dungeon_run.identity!=34320 or drop.get('source')!=POLICY
            or drop.get('owner')!=s.account.uid or drop.get('run_id')!=s.reward_run_id):return False
    try:_checked(s,claim=True)
    except (ValueError,AttributeError,KeyError,TypeError):return False
    return True


def claim_guard(s):
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
                legacy=[dict(template=local_rule['coin_template'],quantity=0,ed=amount,option_groups={})] if amount and allow_drop(member.reward_run_id,34320,(run.stage,run.part),npc['key'],True) else []
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
                issued=storage.issue(bound[3],c,event.payload,True,member.world_drop_sequence,death['xyz'][3:],legacy,prepare,
                    randbelow=randbelow,account_id=member.account.account_id,transaction=db)
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
