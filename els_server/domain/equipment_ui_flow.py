"""Small adapter for recovered equipment UI business requests."""
from els_server.protocol.paid_enhancement_messages import acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.paid_enhancement import enhance


def handle(session,event,sequence):
    if not (session.item_test and session.client_build=='dx11_260923' and event.event_id==0x202 and event.kind in (0x5ff,0x1c4,0x438,0x43a,0x21f,0x221,0xb71)):return None
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
    if event.kind==0x5ff:
        from els_server.protocol.blacksmith_enhancement_messages import is_candidate
        if is_candidate(event.payload):
            from els_server.domain.blacksmith_enhancement_flow import handle as smith_handle
            return smith_handle(session,event,sequence)
    handler=enhance;encoder=acknowledgement;reply=0x600
    if event.kind==0x221:
        from els_server.storage.enhancement_scroll import apply
        from els_server.protocol.equipment_restoration_messages import acknowledgement as scroll_ack
        handler=apply;encoder=scroll_ack;reply=0x222
    if event.kind==0x21f:
        from els_server.storage.equipment_restoration import restore
        from els_server.protocol.equipment_restoration_messages import acknowledgement as restoration_ack
        handler=restore;encoder=restoration_ack;reply=0x220
    if event.kind==0x1c4:
        from els_server.storage.sage_sockets import socket
        from els_server.protocol.socket_messages import acknowledgement as socket_ack
        from els_server.domain.equipment_engrave_flow import current_lease
        # Reuse the established selected-character lease contract. The direct
        # local API has no application and remains supported by that contract.
        try:
            if (not current_lease(session) or session.role!='game' or session.phase!='town_ready'
                    or session.account.characters is None or session.account.store is None
                    or session.account.store.uid!=session.account.uid
                    or type(sequence) is not int or not 1<=sequence<2**32
                    or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
                    or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
                raise ValueError('Socket session admission')
            operation=session.shop_session_id+':'+str(session.account.uid)+':equipment:'+str(sequence)
            return socket(session.account.store.path,session.account.uid,event.payload,operation,
                          account_id=session.account.account_id)
        except ValueError:
            return [Event(0x201,kind=0x1c5,payload=socket_ack(result=-1))]
    if event.kind in (0x438,0x43a):
        from els_server.storage.identification_ui import perform
        from els_server.protocol.identification_messages import acknowledgement as identification_ack
        from els_server.domain.equipment_engrave_flow import current_lease
        ed=0
        try:
            if (not current_lease(session) or session.role!='game' or session.phase!='town_ready'
                    or session.account.characters is None or session.account.store is None
                    or session.account.store.uid!=session.account.uid
                    or type(sequence) is not int or not 1<=sequence<2**32
                    or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
                    or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
                raise ValueError('Identification session admission')
            ed=session.account.get_reward_balances()['ed']
            operation=session.shop_session_id+':'+str(session.account.uid)+':equipment:'+str(sequence)
            if not current_lease(session):raise ValueError('Obsolete identification lease')
            return perform(session.account.store.path,session.account.uid,event.kind,event.payload,operation,
                           account_id=session.account.account_id)
        except ValueError:
            return [Event(0x201,kind=event.kind+1,payload=identification_ack(event.kind,ed,result=-1))]
    if event.kind==0x5ff:
        from els_server.domain.equipment_engrave_flow import current_lease
        ed=0
        try:
            if (not current_lease(session) or session.role!='game' or session.phase!='town_ready'
                    or session.account.characters is None or session.account.store is None
                    or session.account.store.uid!=session.account.uid
                    or type(sequence) is not int or not 1<=sequence<2**32
                    or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
                    or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
                raise ValueError('Enhancement or restoration session admission')
            ed=session.account.get_reward_balances()['ed']
            operation=session.shop_session_id+':'+str(session.account.uid)+':equipment:'+str(sequence)
            if not current_lease(session):raise ValueError('Obsolete equipment lease')
            return handler(session.account.store.path,session.account.uid,event.payload,operation,
                           account_id=session.account.account_id)
        except ValueError:
            return [Event(0x201,kind=reply,payload=encoder(ed,result=-1))]
    if event.kind in (0x21f,0x221):
        from els_server.domain.equipment_engrave_flow import current_lease
        ed=0
        try:
            if (not current_lease(session) or session.role!='game' or session.phase!='town_ready'
                    or session.account.characters is None or session.account.store is None
                    or session.account.store.uid!=session.account.uid
                    or type(sequence) is not int or not 1<=sequence<2**32
                    or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
                    or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
                raise ValueError('Enhancement or restoration session admission')
            ed=session.account.get_reward_balances()['ed']
            operation=session.shop_session_id+':'+str(session.account.uid)+':equipment:'+str(sequence)
            if not current_lease(session):raise ValueError('Obsolete equipment lease')
            if event.kind==0x221:
                actor=session.account;store=actor.store;identity=(actor.uid,actor.account_id,session.shop_session_id,store.path)
                def prepare_scroll():
                    if (session.account is not actor or actor.store is not store
                            or (actor.uid,actor.account_id,session.shop_session_id,store.path)!=identity
                            or session.role!='game' or session.phase!='town_ready' or store.uid!=actor.uid
                            or not current_lease(session)):
                        raise ValueError('Enhancement scroll actor or lease changed')
                return handler(store.path,actor.uid,event.payload,operation,account_id=actor.account_id,prepare=prepare_scroll)
            return handler(session.account.store.path,session.account.uid,event.payload,operation,
                           account_id=session.account.account_id)
        except ValueError:
            return [Event(0x201,kind=reply,payload=encoder(ed,result=-1))]
    def failure():return [Event(0x201,kind=reply,payload=encoder(session.account.get_reward_balances()['ed'],result=-1))]
    if session.role!='game' or session.phase!='town_ready' or type(sequence) is not int or not 1<=sequence<2**32:return failure()
    operation=session.shop_session_id+':'+str(session.account.uid)+':equipment:'+str(sequence)
    try:return handler(session.account.store.path,session.account.uid,event.payload,operation)
    except ValueError:return failure()
