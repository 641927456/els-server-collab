"""Native consumable admission bound to the current selected playable owner."""
from els_server.protocol.consumable_messages import acknowledgement

from els_server.domain.equipment_chip_flow import current_lease


def handle(session,event,sequence):
    automatic=event.kind==0x65e
    if (session.role!='game' or session.phase!='dungeon_active'
        or session.account.store is None or session.account.store.uid!=session.account.uid
        or type(sequence) is not int or not 1<=sequence<2**32 or not current_lease(session)):
        return [acknowledgement(result=-1,automatic=automatic)]
    from els_server.domain.apple_consumables import native_stage_ready
    from els_server.domain.consumables import ConsumableCoolingDown
    from els_server.storage.consumables import use
    try:
        return use(session.account.store.path,session.account.uid,event.payload,
            session.shop_session_id+':'+str(session.account.uid)+':'+str(sequence),
            automatic_use=automatic,allow_apples=native_stage_ready(session),
            account_id=session.account.account_id if session.account.characters is not None else None)
    except ConsumableCoolingDown as cooling:
        # Pet automatic and manual presses commit one shared recovery-group
        # ledger, so either can lock out the other. A bare -1 leaves the client
        # guessing; the trailing cooldown float is the field it times from.
        return [acknowledgement(result=-1,cooldown=cooling.remaining,automatic=automatic,slot=cooling.slot)]
    except ValueError:return [acknowledgement(result=-1,automatic=automatic)]
