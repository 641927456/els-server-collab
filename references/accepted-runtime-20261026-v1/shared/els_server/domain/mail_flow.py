"""Authenticated PostBox operations. GM issuance has no client entry point."""
from els_server.protocol.protocol_codec import Event
from els_server.protocol import mail_attachment_messages as wire
from els_server.storage import game_mail as store
import sqlite3


def handle(session,event):
    if event.event_id!=0x202 or event.kind not in (0x1cc,0x1d2,0x1d4,0x1d6):return None
    kind=event.kind
    def reply(body):return [Event(0x201,kind=kind+1,payload=body)]
    failure={0x1cc:wire.list_ack,0x1d2:wire.read_ack,0x1d4:wire.claim_ack,0x1d6:wire.delete_ack}[kind]
    if (session.client_build!='dx11_260923' or session.role!='game'
            or session.phase!='town_ready' or not session.item_test
            or session.account.store is None):
        return reply(failure(result=-1))
    account=session.account;path=account.store.path;owner=account.account_id;uid=account.uid
    try:
        if kind==0x1cc:
            folder,page,sort,refresh=wire.list_request(event.payload)
            count,rows=store.inbox(path,owner,uid,page=page)
            # Administrative ED mail is shown in the normal inbox; system,
            # wedding and guild tabs are separate client categories.
            if folder!=0:count,rows=0,[]
            return reply(wire.list_ack(rows,count,page,folder))
        if kind==0x1d2:
            mail_id=wire.read_request(event.payload)
            return reply(store.read(path,owner,uid,mail_id,wire.read_ack))
        if kind==0x1d6:
            ids=wire.selection_request(event.payload)
            return reply(store.delete(path,owner,uid,ids,wire.delete_ack))
        ids=wire.selection_request(event.payload,claim=True)
        def encode(ids,ed,changes,awarded):
            # Keep receipt/ED acknowledgement bounded even when each legacy
            # retry returns a full current inventory. The existing105 path
            # applies all absolute rows, including empty historical slots.
            events=reply(wire.claim_ack(ids,ed,changes={mid:changes.get(mid,[]) for mid in awarded},counts=awarded))
            positions={}
            for entries in changes.values():
                for position,item in entries:positions[tuple(position)]=item
            from els_server.storage.inventory_management import _updates
            return events+_updates(list(positions.items()))
        return store.claim(path,owner,uid,ids,encode,include_items=True,include_claim_counts=True)
    except store.MailError as error:
        return reply(failure(result=error.code))
    except (ValueError,OverflowError,sqlite3.OperationalError):
        return reply(failure(result=-1))
