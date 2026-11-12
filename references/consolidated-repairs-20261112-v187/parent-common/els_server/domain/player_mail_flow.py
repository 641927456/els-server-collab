"""Authenticated ordinary send entry; no client-selected GM capability."""
from els_server.protocol.protocol_codec import Event
from els_server.protocol import player_mail_messages as wire
from els_server.protocol import mail_attachment_messages as attachment_wire
from els_server.storage import player_mail as store
from els_server.storage.game_mail import MailError
import sqlite3


def handle(session,event,request_sequence=None):
    if event.event_id!=0x202 or event.kind!=0x1cf:return None
    def reply(raw):return [Event(0x201,kind=0x1d0,payload=raw)]
    if (session.client_build!='dx11_260923' or session.role!='game' or session.phase!='town_ready'
            or not session.item_test or session.account.store is None
            or type(request_sequence) is not int or not 1<=request_sequence<2**32
            or not isinstance(getattr(session,'shop_session_id',None),str) or not session.shop_session_id):
        return reply(wire.send_ack(result=-1))
    a=session.account
    try:
        request=wire.send_request(event.payload)
        operation=session.shop_session_id+':'+str(a.uid)+':player-mail:'+str(request_sequence)
        def encode(result):
            events=reply(wire.send_ack(result['ed'],result['recipient']))
            if result['changes']:
                events.append(Event(0x201,kind=0x105,payload=attachment_wire.refresh(result['changes'])))
            return events
        return store.send(a.store.path,a.account_id,a.uid,request,operation,encode)
    except MailError as error:return reply(wire.send_ack(result=error.code))
    except (ValueError,OverflowError,sqlite3.OperationalError):return reply(wire.send_ack(result=-1))
