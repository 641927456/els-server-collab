"""Native companion requests admitted on the saved-inventory DX11 route."""
import struct,uuid
from els_server.protocol import companion_messages as wire
from els_server.storage import companion_state as state
from els_server.domain.equipment_chip_flow import current_lease

KINDS={0x2e8,0x2ea,0x2ec,0x432,0x42a,0x42c,0x42f}

def handle(session,event,sequence):
    from els_server.domain.mount_flow import handle as mount_handle
    mount_reply=mount_handle(session,event,sequence)
    if mount_reply is not None:return mount_reply
    from els_server.domain.pet_progression_flow import handle as progression
    progression_reply=progression(session,event,sequence)
    if progression_reply is not None:return progression_reply
    from els_server.domain.pet_actions import handle as pet_action
    action_reply=pet_action(session,event,sequence)
    if action_reply is not None:return action_reply
    if event.event_id!=0x202 or event.kind not in KINDS or session.client_build!='dx11_260923' or not session.item_test:return None
    kind=event.kind;owner=session.account.uid
    if kind==0x42a:
        if session.role!='game' or len(event.payload)!=1 or event.payload[0]>1:return [wire.mount_list(-1)]
        mounts=[p for p in state.snapshot(session.account.store.path,owner)['companions'] if p['kind']=='mount']
        return [wire.mount_list(0,mounts)]
    if kind==0x2ea:
        # 30AB9B0, captured 9-byte original request: page i32, category i32,
        # bool. Page zero refreshes the whole cache. 30A7E30 reads the response.
        if session.role!='game' or len(event.payload)!=9:return [wire.pet_list(-1)]
        page,category,flag=struct.unpack('>iiB',event.payload)
        if page<0 or page>1000 or category not in (0,1,2) or flag>1:return [wire.pet_list(-1)]
        pets=[p for p in state.snapshot(session.account.store.path,owner)['companions'] if p['kind']=='pet']
        pets=[p for p in pets if (20000<=p['unit']<25000)==(category==2)]
        pages=max(1,(len(pets)+5)//6);current=min(max(1,page),pages)
        # Page zero is the original complete-list cache restore (UI+188).
        return [wire.pet_list(0,pets if page==0 else pets[(current-1)*6:current*6],pages=pages,page=current)]
    typ='pet' if kind in (0x2e8,0x2ec) else 'mount'
    def failure():
        if kind in (0x2e8,0x432):return wire.activation_ack(typ,-1)
        if kind==0x2ec:return wire.pet_summon(-1)
        return wire.mount_summon(-1,owner) if kind==0x42c else wire.mount_ride(-1,owner)
    allowed=('town_ready',) if kind in (0x2e8,0x432) else ('town_ready','dungeon_active')
    if (session.role!='game' or session.phase not in allowed or session.account.store is None
        or session.account.store.uid!=owner or not current_lease(session)):return [failure()]
    operation=session.shop_session_id+':'+(str(sequence) if sequence is not None else str(uuid.uuid4()))
    try:return [state.handle(session.account.store.path,owner,kind,event.payload,operation,account_id=session.account.account_id if session.account.characters is not None else None)]
    except (ValueError,UnicodeError):return [failure()]
