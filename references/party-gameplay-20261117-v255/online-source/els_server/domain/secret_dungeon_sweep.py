"""Original sweep window request, current actor and native CP qualification."""
import sqlite3
import time
from els_server.protocol.secret_dungeon_sweep import request,acknowledgement


def handle(s,event,sequence):
    if(event.event_id,event.kind)!=(0x202,0xc0f):return None
    from els_server.domain.housing_access_flow import capture
    from els_server.domain.raid_native_power import request as power_request,basis
    from els_server.storage.secret_dungeon_sweep import sweep
    from els_server.game_data import client_data
    from els_server.storage.seal_quests import completed_ids,load_character
    from els_server.domain.region_quests import region_catalog
    try:
        same,guard=capture(s)
        if(event.performers not in((),(0,)) or event.uid!=event.target_uid or event.uid!=2**64-1
           or event.payload_mode or type(sequence)is not int or not 1<=sequence<2**32):
            raise ValueError('Secret sweep native envelope')
        payload=power_request(s,event.payload,fresh=True)
        request(payload)
        proof=getattr(s,'_raid_native_power',None)
        if proof is None:raise ValueError('Secret sweep needs current native CP report')
        def qualify(db,dungeon):
            character=load_character(db,s.account.uid,s.account.account_id)
            if not region_catalog().dungeon_allowed(dungeon,character,completed_ids(db,s.account.uid)):
                raise ValueError('Secret sweep saved native eligibility')
            # Sweep's original106FAB0 compares full CP, without the raid95% tolerance.
            required=client_data().dungeon(dungeon).get('limitCombatCapability',0)
            if proof[0]!=basis(s) or proof[1]<required:
                raise ValueError('Secret sweep native combat power requirement')
        operation=f'{s.shop_session_id}:secret-sweep:{s.account.uid}:{sequence}'
        result=sweep(s.account.store.path,s.account.uid,s.account.account_id,payload,operation,
                     s.account.reward_store,guard,qualify,int(time.time()))
    except(ValueError,sqlite3.Error,OverflowError) as error:
        from els_server.diagnostic_evidence import record_rejection
        record_rejection(error)
        return [acknowledgement(result=500)] if 'same' in locals() and same() else []
    from els_server.domain.gameplay_announcements import publish
    publish(s,result['announcements'])
    return result['events']


def synchronize_counts(s,events):
    from els_server.domain.secret_clear_rewards import _week
    if(s.role!='game' or s.client_build!='dx11_260923' or not s.item_test
       or s.account.store is None or s.account.characters is None):return events
    now=int(time.time());key=(s.account.uid,s.account.account_id,_week(now))
    if any(e.event_id==0x201 and e.kind in(0x2a,0x861) for e in events):
        # Login's existing Ariel synchronization supplies the complete map.
        s.secret_count_week=key
        return events
    if s.phase!='town_ready' or getattr(s,'secret_count_week',None)==key:return events
    from els_server.domain.ariel_attendance_flow import authority
    from els_server.storage.ariel_daily_special import snapshot
    notice=snapshot(s.account.store.path,s.account.account_id,s.account.uid,
                    validate=lambda:authority(s),now=lambda:now)
    s.secret_count_week=key
    return [*events,notice]
