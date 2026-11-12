"""Native A89/A8B owned mount selection; no race is created by this UI."""
import struct
from els_server.protocol import mount_racing_messages as wire


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0xa89,0xa8b)or s.client_build!='dx11_260923' or not s.item_test:return None
    try:
        from els_server.domain.equipment_chip_flow import reset_context
        from els_server.domain.tenebros_capacity_flow import selected
        from els_server.storage import mount_races
        from els_server.storage.companion_state import snapshot
        reset_context(s,event,sequence);path,owner,account_id,prepare=selected(s)
        if len(event.payload)!=(8 if event.kind==0xa89 else 9):raise ValueError('Racing selection length')
        uid=struct.unpack_from('>Q',event.payload)[0]
        if event.kind==0xa8b and event.payload[8]>1:raise ValueError('Racing mode flag')
        enabled=bool(event.payload[8])if event.kind==0xa8b else bool(uid)
        mount=mount_races.selected(path,owner,account_id,uid,prepare=prepare)if uid and enabled else None
        if enabled and mount is None:raise ValueError('Select an owned racing mount')
        if event.kind==0xa89:
            mounts=[p for p in snapshot(path,owner)['companions']if p['kind']=='mount']
            answer=[wire.selection(uid=uid,mounts=mounts)]
        else:answer=[wire.mode(uid=uid,enabled=enabled)]
        from els_server.protocol.protocol_codec import encode_event
        for reply in answer:encode_event(reply)
        prepare(None)
        s.racing_selected_mount=mount
        s.racing_mode=enabled if event.kind==0xa8b else getattr(s,'racing_mode',False)
        s._mount_racing_rejection=None
        return answer
    except(ValueError,UnicodeError)as error:
        s._mount_racing_rejection=str(error)
        return[wire.selection(-1)]if event.kind==0xa89 else[wire.mode(-1)]
