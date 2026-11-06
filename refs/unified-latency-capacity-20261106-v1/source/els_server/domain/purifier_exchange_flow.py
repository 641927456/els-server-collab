"""Authenticated native town exchange; original UI/effects remain client-owned."""
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.protocol.protocol_codec import Event
from els_server.protocol.purifier_exchange_messages import acknowledgement
from els_server.storage.purifier_exchange import exchange
from els_server.storage.reward_state import validate_balances


def handle(session,event,sequence):
    if not (session.item_test and session.client_build=='dx11_260923'
            and event.event_id==0x202 and event.kind==0x223):
        return None
    if (session.role!='game' or 0x28 not in session.completed
            or session.account.store is None or session.account.characters is None):
        # No selected actor exists to own an absolute-currency acknowledgement.
        # Fail protocol order without reading a default role or creating state.
        raise ValueError('Purifier exchange before owned character selection')
    def failed():
        # This is a read-only owned lookup, not the lazy RewardState getter
        # which could initialize tables/balances during a malformed request.
        uri=Path(session.account.store.path).resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri,uri=True,timeout=10)) as db:
            row=db.execute('''SELECT b.ed,b.experience,b.revision FROM reward_balances b
                JOIN character_owners o ON o.uid=b.uid WHERE b.uid=? AND o.account_id=?''',
                (session.account.uid,session.account.account_id)).fetchone()
        ed=validate_balances(row)['ed']
        return [Event(0x201,kind=0x224,payload=acknowledgement(ed,result=-1))]
    if not (session.role=='game' and session.phase=='town_ready'
            and session.active_map==20013 and session.account.store is not None
            and session.account.characters is not None and type(sequence) is int and 1<=sequence<2**32
            and event.performers==(0,) and event.uid==event.target_uid==0xffffffffffffffff
            and event.payload_mode==0):
        return failed()
    operation=session.shop_session_id+':'+str(session.account.uid)+':purifier-exchange:'+str(sequence)
    try:
        return exchange(session.account.store.path,session.account.uid,
                        session.account.get_location()['map'],event.payload,operation,
                        account_id=session.account.account_id)
    except (ValueError,sqlite3.Error):
        return failed()
