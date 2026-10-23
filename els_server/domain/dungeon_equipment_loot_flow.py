"""Solo finite loot, gated by the existing accepted native dungeon lifecycle."""
import copy
import hashlib
import secrets
import struct
from els_server.domain.dungeon_equipment_loot_rules import POLICY,MAPS,catalog,context,inventory_plan,policy_for
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.dungeon_drops import ground_drop_notice,ground_pickup_notice,pickup_inventory_notice
from els_server.domain.dungeon_lifecycle import death_ack,empty_reward_death_notice
from els_server.storage import dungeon_equipment_loot as storage

def current_lease(s):
    app=getattr(s,'application',None)
    if app is None:return True
    identity=getattr(s,'identity',None);account=getattr(s,'account',None)
    if not isinstance(identity,dict) or account is None:return False
    account_id=identity.get('id');uid=account.uid;root=getattr(account,'root',None)
    return bool(s.role=='game' and not getattr(s,'released',False) and app.playing.get(account_id) is s
        and account_id==account.account_id and app.accounts.get(account_id) is root
        and root is not None and root.character_accounts.get(uid) is account
        and account.store is not None and account.store.uid==uid)

def enabled(s):
    run=s.dungeon_run
    from els_server.domain.dungeon_loot_catalog import MAPS as NORMAL_MAPS
    from els_server.domain.dungeon_material_loot_catalog import MAPS as MATERIAL_MAPS
    from els_server.domain.dungeon_source_loot import MAPS as SOURCE_MAPS
    return bool(current_lease(s) and run is not None and run.identity in MAPS|NORMAL_MAPS|MATERIAL_MAPS|SOURCE_MAPS and s.phase=='dungeon_active'
        and s.dungeon_substage_synced and s.reward_test and s.item_test and s.drop_probe
        and s.reward_run_id is not None and getattr(s.account,'store',None) is not None
        and getattr(s,'reward_transaction',None) is None and getattr(s,'active_challenge',None) is None
        and getattr(s,'challenge_deadline',None) is None and not getattr(s,'dungeon_failed',False)
        and frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))==frozenset((s.account.uid,)))

def identity(s,npc_key,source_actor=None):
    run=s.dungeon_run
    value=dict(owner=s.account.uid,run_id=s.reward_run_id,dungeon=run.identity,
               stage=run.stage,part=run.part,visits=run.visits,npc_key=npc_key,graph_sha256=run.graph['source_sha256'])
    if source_actor is not None:
        from els_server.domain.dungeon_source_loot import context as source_context
        return source_context(dict(value,source_template=source_actor['template'],source_index=source_actor['source_index']))
    return context(value)

def encode_replies(reply):
    for event in reply:encode_event(event)

def accepted_death(s,event,npc,death,expired,*,randbelow=secrets.randbelow):
    from els_server.domain.dungeon_loot_catalog import MAPS as NORMAL_MAPS
    from els_server.domain.dungeon_material_loot_catalog import MAPS as MATERIAL_MAPS
    from els_server.domain import dungeon_source_loot as source_rules
    run=s.dungeon_run
    # An obsolete authenticated lease must not fall back into ordinary AD
    # progression after refusing its finite acquisition transaction.
    if run is not None and run.identity in MAPS|NORMAL_MAPS|MATERIAL_MAPS|source_rules.MAPS and not current_lease(s):return []
    if (not enabled(s) or expired or npc.get('dynamic') or npc['no_drop']
        or npc.get('ally') or npc.get('team',1)==0):return None
    run=s.dungeon_run
    rules=None;existing=False
    if run.identity in MATERIAL_MAPS:
        from els_server.domain.dungeon_material_loot_catalog import accepted_source as material_source
        existing=material_source(run,npc)
    elif run.identity in MAPS:existing=bool(npc['active'])
    elif run.identity in NORMAL_MAPS:
        from els_server.domain.dungeon_loot_catalog import accepted_source
        existing=accepted_source(run,npc)
    if not existing:
        if not source_rules.accepted_source(run,npc):return None
        rules=source_rules
    c=identity(s,npc['key'],npc if rules is not None else None)
    if npc['key'] in run.defeated:raise ValueError('Loot hook requires a newly accepted death')
    from els_server.domain.dungeon_flow import local_rewards,periodic
    rule=local_rewards();amount=rule['boss_ed'] if npc['boss'] else rule['ordinary_ed']
    from els_server.domain.gm_rates import allow_drop
    legacy=[dict(template=rule['coin_template'],quantity=0,ed=amount,option_groups={})] if npc['active'] and amount and allow_drop(s.reward_run_id,run.identity,(run.stage,run.part),npc['key'],npc['boss']) else []
    # Prepare the native gate transition on shadow state. poll_ready mutates
    # next/ready_at and periodic pauses the clock, so neither may run after the
    # issue commits with a still-fallible protocol encoder.
    shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run)
    shadow.dungeon_run.defeated={**run.defeated,npc['key']:bytes(event.payload)}
    shadow.defeated_npcs=shadow.dungeon_run.defeated;shadow.dungeon_clock=copy.copy(s.dungeon_clock)
    gate_reply=periodic(shadow)
    from els_server.domain import legacy_pve_exp as exp_rules
    experience=None
    def accepted_effect(db,replayed):
        nonlocal experience
        from els_server.storage.legacy_pve_exp import commit
        experience=commit(db,s.account.reward_store,exp_rules.identity(s,npc),event.payload,death['killer'],require_existing=replayed)
    def prepare(rows,replayed):
        reply=[death_ack()]
        world=dict(s.world_drops)
        if not replayed:
            from els_server.domain.dungeon_lifecycle import experience_death_notice
            if experience is None:reply.append(empty_reward_death_notice(npc['key'],death['killer']))
            elif not experience['replayed']:reply.append(experience_death_notice(npc['key'],death['killer'],s.account.uid,experience['experience']))
        for row in rows:
            old=world.get(row['drop_id'])
            if old is not None and any(old.get(k)!=row[k] for k in ('owner','run_id','stage','npc_key','template')):raise ValueError('Loot sequence collides with an existing ground item')
            notice=ground_drop_notice(row['drop_id'],row['xyz'],uid=s.account.uid,template=row['template'])
            row['payload_hex']=notice.payload.hex()
            if old is None:world[row['drop_id']]=dict(row)
            if not replayed:reply.append(notice)
        reply.extend(gate_reply);encode_replies(reply)
        return dict(reply=reply,world=world,sequence=max([s.world_drop_sequence,*[r['drop_id']+1 for r in rows]]),
                    last=dict(rows[-1]) if rows else s.world_drop_issued)
    try:
        result=storage.issue(s.account.store.path,c,event.payload,npc['boss'],s.world_drop_sequence,
                             death['xyz'][3:],legacy,prepare,randbelow=randbelow,rules=rules,
                             accepted_effect=accepted_effect if exp_rules.enabled(s) and exp_rules.eligible(npc,expired) else None,
                             account_id=s.account.account_id)
    except storage.LootActorRejected:return []
    # Only ordinary assignments remain after the successful SQL context exit.
    run.defeated=shadow.dungeon_run.defeated;run.next=shadow.dungeon_run.next;run.ready_at=shadow.dungeon_run.ready_at
    s.defeated_npcs=run.defeated;s.part_end_notified=shadow.part_end_notified
    s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
    s.world_drops=result['world'];s.world_drop_sequence=result['sequence'];s.world_drop_issued=result['last']
    return result['reply']

def _claim_run_matches(s,c):
    run=s.dungeon_run
    if run.run_id==c['run_id']:return True
    # A shared source run keeps its UUID4; each owned issue uses the original
    # UUID5(seed, reward:uid). Never accept an arbitrary UUID mismatch.
    if c['dungeon']!=34320 or c['owner']!=s.account.uid:return False
    from els_server.domain.friends_dungeon import FriendsDungeons,Room
    from els_server.domain.friends_spawns import _checked_static_generation
    import uuid
    try:
        dispatcher=s.application.world.dungeons
        if not isinstance(dispatcher,FriendsDungeons):return False
        room=dispatcher.room(s)
        if (not isinstance(room,Room) or room.identity!=34320
                or not 2<=len(room.members)<=4 or s not in room.members
                or room.phase not in ('active','part_end') or room.party.get('run') is not room
                or room.seed!=run.run_id
                or any(room.party.get(k) for k in ('raid_party','challenge','challenge_pending','solo_challenge'))):return False
        seed=uuid.UUID(room.seed)
        if str(seed)!=room.seed or seed.version!=4:return False
        _checked_static_generation(dispatcher,room)
        for member in room.members:
            if (member not in dispatcher.world.members
                    or dispatcher.world.party_of.get(member) is not room.party
                    or dispatcher.room(member) is not room
                    or member.dungeon_run is None or member.dungeon_run.run_id!=room.seed
                    or not current_lease(member)
                    or member.reward_run_id!=str(uuid.uuid5(seed,'reward:'+str(member.account.uid)))):return False
        return c['run_id']==s.reward_run_id==str(uuid.uuid5(seed,'reward:'+str(c['owner'])))
    except (ValueError,AttributeError,KeyError,TypeError):return False


def _claim_context(s,drop,rules):
    c=identity(s,drop['npc_key'],dict(template=drop['source_template'],source_index=drop['source_index']) if rules is not None else None)
    from els_server.domain.dungeon_material_loot_catalog import POLICY as MATERIAL_POLICY,map_rule
    if rules is not None or drop.get('source')!=MATERIAL_POLICY or c['dungeon']!=34320 or drop.get('part')==c['part']:
        return c
    # The server-owned issued row keeps its original SQL identity when the
    # loaded Stage2 advances from its two Bosses to the exit part.
    issued=context({k:drop[k] for k in c})
    if (c['stage']!=2 or c['part']!=2 or issued['part']!=1
        or any(issued[k]!=c[k] for k in c if k!='part')
        or not _claim_run_matches(s,c)):
        raise ValueError('Material pickup left its issued stage/visit/run')
    run=s.dungeon_run
    npc=next((n for n in run.parts[1]['npcs'] if n['key']==issued['npc_key']),None)
    if (npc is None or npc.get('dynamic') or not npc['active'] or not npc['boss']
        or npc['no_drop'] or npc.get('ally') or npc.get('team',1)==0
        or dict(stage=2,part=1,template=npc['template'],source_index=npc['source_index']) not in map_rule(34320)['accepted_boss_sources']
        or hashlib.sha256(run.defeated.get(npc['key'],b'')).hexdigest()!=drop['death_proof_sha256']):
        raise ValueError('Material pickup lost its original accepted Boss proof')
    return issued

def claim(s,request,drop):
    group_validate=None
    # Shared34320 retains UUID4 run identity and owner UUID5 reward identity.
    # Detaching must not turn its remaining issued drops into solo claims.
    if (not enabled(s) or s.dungeon_run is not None and s.dungeon_run.identity==34320
            and s.reward_run_id!=s.dungeon_run.run_id):
        from els_server.domain.friends_material_loot import claim_enabled,claim_guard
        if not claim_enabled(s,drop):return []
        try:group_validate=claim_guard(s)
        except (ValueError,AttributeError,KeyError,TypeError):return []
    from els_server.domain import dungeon_source_loot as source_rules
    rules=source_rules if drop.get('source')==source_rules.POLICY else None
    try:c=_claim_context(s,drop,rules)
    except (ValueError,KeyError):return []
    if drop.get('source')!=(rules.policy_for(c) if rules is not None else policy_for(c)):return []
    if any(drop.get(k)!=c[k] for k in c) or request['template']!=drop['template'] or request['drop_id']!=drop['drop_id']:return []
    def prepare(items,replayed):
        reply=[Event(0x201,kind=0xd1,payload=struct.pack('>i',0))]
        if not replayed:reply.append(ground_pickup_notice(drop['drop_id'],s.account.uid,template=drop['template']))
        if rules is None or source_rules.descriptor(drop['template'])['kind']!='immediate-food':reply.append(pickup_inventory_notice(items))
        encode_replies(reply)
        return dict(reply=reply,replayed=replayed,items=items)
    from els_server.storage.inventory_state import InventoryFull
    try:
        if group_validate is None:
            result=storage.claim(s.account.store.path,c,request['drop_id'],request['template'],prepare,rules=rules,account_id=s.account.account_id)
        else:
            result=storage.claim(s.account.store.path,c,request['drop_id'],request['template'],prepare,rules=rules,account_id=s.account.account_id,validate=group_validate)
    except InventoryFull:return [Event(0x201,kind=0xd1,payload=struct.pack('>i',-1))]
    except ValueError:return []
    drop['pickup_committed']=True
    s.pickup_receipt={'dungeon_run_id':s.reward_run_id,'drop_id':drop['drop_id'],**result}
    return result['reply']

def clear_rewards(s,rule):
    # The fragment clear branch belongs exclusively to the original four maps.
    if not enabled(s):return None
    if s.clear_notified:return []
    if s.dungeon_run.identity not in MAPS:return None
    run=s.dungeon_run;identity(s,0)
    if run.next is None or run.next['kind']!=4 or not s.part_end_notified:return None
    from els_server.domain.dungeon_clear import reward_clear_notice,clear_identity_payload
    from els_server.protocol.local_messages import client_economy_fields
    from els_server.domain.local_artifact_rules import assess_run,clear_base
    elapsed=s.dungeon_clock.seconds();assessment=assess_run(run,elapsed)
    deaths=hashlib.sha256()
    for key,value in sorted(run.defeated.items()):deaths.update(struct.pack('>iI',key,len(value))+value)
    proof=(b'local-static-clear-v2'+struct.pack('>Qiii',s.account.uid,run.identity,run.stage,run.part)
           +bytes.fromhex(run.graph['source_sha256'])+deaths.digest())
    def encode(balances,best,economy):
        client_economy_fields(balances)
        return reward_clear_notice(economy['ed'],economy['experience'],s.account.uid,elapsed_seconds=elapsed,best_seconds=best,map_id=run.identity).payload
    arguments=dict(run_id=s.reward_run_id,proof=proof,ed=rule['clear_ed'],experience=rule['clear_experience'],response_builder=encode,
        item_plan=[*rule['items'],inventory_plan(118445,catalog()['values']['fragment_on_validated_clear'])],
        dungeon_clear=(run.identity,elapsed),clear_assessment=assessment,artifact_base=clear_base(run.identity),title_economy='clear',attendance_clear=s.activity2026_awards.prepare_clear(s) if getattr(s,'activity2026_awards',None) is not None else None)
    from els_server.domain.legacy_pve_exp import enabled as exp_enabled,experience_limit
    if exp_enabled(s):arguments.update(experience_limit=experience_limit(),resonance_source='clear')
    def prepare(receipt,current):
        reply=[]
        if receipt.get('items') and not s.clear_items_synced:reply.append(pickup_inventory_notice(current))
        committed=receipt.get('local_rules')
        if committed:
            a=committed['assessment'];reply.append(Event(0x201,kind=0x66b,payload=struct.pack('>ii',a['rank'],a['score'])))
        reply.append(Event(0x201,kind=0xc1,payload=clear_identity_payload(receipt['response'],run.identity)));encode_replies(reply)
        return reply
    receipt,reply=storage.clear_reward(s.account.store.path,s.account.uid,s.account.reward_store,arguments,prepare)
    s.reward_receipt={'run_id':s.reward_run_id,**receipt}
    if receipt.get('items'):s.clear_items_synced=True
    s.clear_notified=True
    return reply
