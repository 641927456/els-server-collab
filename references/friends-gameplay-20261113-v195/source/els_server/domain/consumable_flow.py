"""Native consumable admission bound to the current selected playable owner."""
from els_server.protocol.consumable_messages import acknowledgement

from els_server.domain.equipment_chip_flow import current_lease


DCC_NOT_USE_QUICK_SLOT = 11


def handle(session,event,sequence,*,authorize=None):
    from els_server.domain.henir_flow import use as henir_use
    special=henir_use(session,event,sequence)
    if special is not None:return special
    automatic=event.kind==0x65e
    if (session.role!='game' or session.phase not in('town_ready','dungeon_active')
        or session.account.store is None or session.account.store.uid!=session.account.uid
        or type(sequence) is not int or not 1<=sequence<2**32 or not current_lease(session)):
        return [acknowledgement(result=2,automatic=automatic)]
    from els_server.domain.apple_consumables import native_stage_ready
    from els_server.domain.consumables import ConsumableCoolingDown
    from els_server.storage.consumables import use
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
        return use(session.account.store.path,session.account.uid,event.payload,
            session.shop_session_id+':'+str(session.account.uid)+':'+str(sequence),
            automatic_use=automatic,allow_apples=native_stage_ready(session)or session.phase=='town_ready',
            mount_only=session.phase=='town_ready',
            account_id=session.account.account_id if session.account.characters is not None else None,
            authorize=authorize,after_manual_use=mission)
    except ConsumableCoolingDown as error:return [acknowledgement(result=1369,automatic=automatic,slot=error.slot)]
    except ValueError:return [acknowledgement(result=500,automatic=automatic)]
