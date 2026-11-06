"""Original blacklist/refresh requests and periodic PostBox notices."""
import sqlite3
import time
from els_server.protocol.protocol_codec import Event
from els_server.protocol import mailbox_extras as wire
from els_server.storage import mailbox_extras as store
from els_server.storage.game_mail import MailError
_maintenance_after={}


def eligible(session):
    return (session.client_build == 'dx11_260923' and session.role == 'game'
            and session.phase in ('town_ready','dungeon_active') and session.item_test
            and session.account.store is not None)


def handle(session, event, request_sequence=None):
    if event.event_id != 0x202 or event.kind not in (0x20d,0x20f,0x211,0xc09,0x1cf):
        return None
    kind = event.kind
    def reply(raw):
        return [Event(0x201,kind=kind+1,payload=raw)]
    def fail(result=-1):
        if kind == 0x20d: return reply(wire.blacklist_ack())
        if kind == 0xc09: return reply(wire.refresh_ack(result))
        if kind == 0x1cf:
            # Native nonzero-result branch never applies balance/inventory.
            return reply(wire.send_failure(0,result))
        return reply(wire.change_ack(result=result))
    if not eligible(session) or session.phase != 'town_ready':
        return fail()
    a = session.account
    try:
        if kind == 0x1cf:
            # Explicit native failure releases the pending send UI. Never
            # interpret opaque send fields as administrative privileges.
            return fail()
        if kind == 0xc09:
            wire.empty_request(event.payload)
            notice = periodic(session,force=True)
            return reply(wire.refresh_ack()) + notice
        if kind == 0x20d:
            wire.empty_request(event.payload)
            return reply(wire.blacklist_ack(store.blacklist(a.store.path,a.account_id,a.uid)))
        if (type(request_sequence) is not int or not 1 <= request_sequence < 2**32
                or not getattr(session,'shop_session_id',None)):
            raise ValueError('Blacklist mutation requires authenticated sequence')
        target = wire.name_request(event.payload) if kind == 0x20f else wire.uid_request(event.payload)
        operation = session.shop_session_id + ':' + str(a.uid) + ':mail-extra:' + str(request_sequence)
        def encode(row,result,rows):
            return reply(wire.change_ack(row,result)) + [Event(0x201,kind=0x20e,payload=wire.blacklist_ack(rows))]
        return store.change(a.store.path,a.account_id,a.uid,target,added=kind==0x20f,
                            operation=operation,encode=encode)
    except MailError as error:
        return fail(error.code)
    except (ValueError,OverflowError,UnicodeError,sqlite3.OperationalError):
        return fail()


def periodic(session, *, force=False):
    if not eligible(session): return []
    a = session.account; key = (a.account_id,a.uid)
    now = time.monotonic()
    if not force and getattr(session,'mailbox_poll', (None,0))[0] == key and now < session.mailbox_poll[1]:
        return []
    session.mailbox_poll = (key,now+2)
    try:
        path=str(a.store.path)
        if now>=_maintenance_after.get(path,0):
            from els_server.storage.player_mail import maintenance
            maintenance(a.store.path)
            _maintenance_after[path]=now+60
        status = store.status(a.store.path,a.account_id,a.uid)
    except (sqlite3.OperationalError,MailError):
        # A transient busy database cannot disconnect an otherwise healthy
        # client. Do not mark a failed read delivered; retry on the next poll.
        if force: raise
        return []
    marker = (key,status)
    if not force and getattr(session,'mailbox_status',None) == marker: return []
    session.mailbox_status = marker
    return [Event(0x201,kind=0x1ce,payload=wire.notification(status[1]))]
