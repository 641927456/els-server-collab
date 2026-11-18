"""Native consumable admission bound to the current selected playable owner."""
from els_server.protocol.consumable_messages import acknowledgement

from els_server.domain.equipment_chip_flow import current_lease


DCC_NOT_USE_QUICK_SLOT = 11


def handle(session,event,sequence,*,authorize=None):
    automatic=event.kind==0x65e
    run=session.dungeon_run
    if run is not None and run.identity==38100 and session.phase=='dungeon_active':
        return [acknowledgement(result=500,automatic=automatic)]
    if (session.role!='game' or session.phase not in('town_ready','dungeon_active')
        or session.account.store is None or session.account.store.uid!=session.account.uid
        or type(sequence) is not int or not 1<=sequence<2**32 or not current_lease(session)):
        from els_server.diagnostic_evidence import record_rejection
        record_rejection(ValueError('Consumable admission: role, phase, selected owner or current lease differs'))
        return [acknowledgement(result=2,automatic=automatic)]
    from els_server.domain.apple_consumables import native_stage_ready
    from els_server.domain.consumables import ConsumableCoolingDown
    from els_server.storage.consumables import use
    stage_ready=None
    try:
        if automatic:
            if session.phase != 'dungeon_active' or not session.dungeon_substage_synced:
                raise ValueError('Pet automatic use requires a loaded dungeon')
            from els_server.game_data import client_data
            dungeon = client_data().dungeon(session.dungeon_id)
            if DCC_NOT_USE_QUICK_SLOT in dungeon.get('DUNGEON_CHECK_CONDITION', {}).values():
                raise ValueError('Dungeon disables consumable shortcuts')
        from els_server.domain.random_mission_flow import quick_slot
        mission=quick_slot(session) if not automatic and session.phase=='dungeon_active' else None
        stage_ready=native_stage_ready(session)or session.phase=='town_ready'
        return use(session.account.store.path,session.account.uid,event.payload,
            session.shop_session_id+':'+str(session.account.uid)+':'+str(sequence),
            automatic_use=automatic,allow_apples=stage_ready,
            mount_only=session.phase=='town_ready',
            account_id=session.account.account_id if session.account.characters is not None else None,
            authorize=authorize,after_manual_use=mission)
    except ConsumableCoolingDown as error:
        from els_server.diagnostic_evidence import record_rejection
        record_rejection(error)
        return [acknowledgement(result=1369,automatic=automatic,slot=error.slot,
            cooldown=error.remaining if automatic else -1.0)]
    except ValueError as error:
        from els_server.diagnostic_evidence import record_rejection,record_observation,recording
        record_rejection(error)
        if recording():
            # Values already owned by this request; no database reads or changed
            # eligibility. A generic item-selection error alone loses this gate.
            fields={name:getattr(session,name,None) for name in (
                'phase','dungeon_substage_synced','gate_stage_loading',
                'dungeon_return_pending','part_end_notified','clear_notified',
                'dungeon_failed','dungeon_requested')}
            fields.update(stage_ready=stage_ready,automatic=automatic,
                run_present=run is not None,
                run_identity=getattr(run,'identity',None),
                run_stage=getattr(run,'stage',None),run_part=getattr(run,'part',None),
                run_started=getattr(run,'started_at',None) is not None,
                reward_receipt_present=getattr(session,'reward_receipt',None) is not None,
                end_payload_present=getattr(session,'dungeon_end_payload',None) is not None)
            record_observation('item_use','rejected_scene_state',fields,include_site=False)
        return [acknowledgement(result=500,automatic=automatic)]
