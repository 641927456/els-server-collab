"""Small adapter for recovered equipment UI business requests."""
from els_server.protocol.paid_enhancement_messages import acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.paid_enhancement import enhance


def handle(session,event,sequence):
    if not (session.item_test and session.client_build=='dx11_260923' and event.event_id==0x202 and event.kind in (0x5ff,0x1c4,0x438,0x43a,0x21f,0xb71)):return None
    if event.kind==0xb71:
        from els_server.protocol.enhancement_configuration_messages import acknowledgement as configuration_ack
        # Read-only login configuration can arrive before character/town setup.
        # Reply only to the original request; an unsolicited B72 has no native wait.
        phases=('game_authenticated','port_ready','session_ready','terms_ready',
                'characters_ready','channels_ready','player_initialized','skill_ui_ready',
                'initialization_confirmed','map_loading','square_accepted','town_ready',
                'dungeon_loading','dungeon_active')
        valid=(session.role=='game' and session.phase in phases and not event.payload
               and type(sequence) is int and 1<=sequence<2**32)
        return [configuration_ack(0 if valid else -1)]
    handler=enhance;encoder=acknowledgement;reply=0x600
    if event.kind==0x21f:
        from els_server.storage.equipment_restoration import restore
        from els_server.protocol.equipment_restoration_messages import acknowledgement as restoration_ack
        handler=restore;encoder=restoration_ack;reply=0x220
    if event.kind==0x1c4:
        from els_server.storage.sage_sockets import socket
        from els_server.protocol.socket_messages import acknowledgement as socket_ack
        handler=socket;encoder=socket_ack;reply=0x1c5
    if event.kind in (0x438,0x43a):
        from els_server.storage.identification_ui import perform
        from els_server.protocol.identification_messages import acknowledgement as identification_ack
        handler=lambda path,owner,payload,operation:perform(path,owner,event.kind,payload,operation)
        encoder=lambda ed,result:identification_ack(event.kind,ed,result=result)
        reply=event.kind+1
    def failure():return [Event(0x201,kind=reply,payload=encoder(session.account.get_reward_balances()['ed'],result=-1))]
    if session.role!='game' or session.phase!='town_ready' or type(sequence) is not int or not 1<=sequence<2**32:return failure()
    operation=session.shop_session_id+':'+str(session.account.uid)+':equipment:'+str(sequence)
    try:return handler(session.account.store.path,session.account.uid,event.payload,operation)
    except ValueError:return failure()
