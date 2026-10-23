"""Own679 type1 only; preserve sixSELECT and40272 routes and native UI."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.cartridge_recipe679_messages import acknowledgement
from els_server.domain.cartridge_exchange_flow import _selected, _context
from els_server.domain.cartridge_recipe679_rules import _RecipeAuthority, request
from els_server.storage.cartridge_recipe679 import exchange
from els_server.storage.reward_state import validate_balances

WRITER_ENABLED = True


def _failed(session):
    if not _selected(session):
        return [Event(0x201,kind=0x224,payload=acknowledgement(0,result=-1))]
    path = Path(session.account.store.path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(path,uri=True,timeout=10)) as db:
        value = db.execute('SELECT b.ed,b.experience,b.revision FROM reward_balances b '
            'JOIN character_owners o ON o.uid=b.uid JOIN characters c ON c.uid=b.uid '
            'WHERE b.uid=? AND o.account_id=?',(session.account.uid,session.account.account_id)).fetchone()
    return [Event(0x201,kind=0x224,payload=acknowledgement(validate_balances(value)['ed'],result=-1))]


def handle(session,event,sequence):
    if not (session.item_test and session.client_build=='dx11_260923'
            and event.event_id==0x202 and event.kind==0x223):return None
    # Only the exact House/type namespace is claimed, not another recipe/type.
    if (type(event.payload) is not bytes or len(event.payload)<28
            or struct.unpack_from('>i',event.payload)[0]!=40326
            or struct.unpack_from('>i',event.payload,24)[0]!=1):return None
    if (not WRITER_ENABLED or not _context(session)
            or type(sequence) is not int or not 1<=sequence<2**32
            or event.performers!=(0,) or event.uid!=0xffffffffffffffff
            or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return _failed(session)
    operation=session.shop_session_id+':'+str(session.account.uid)+':cartridge-recipe679:'+str(sequence)
    try:
        request(event.payload)
        authority=_RecipeAuthority(session,event,sequence,operation,lambda:_context(session))
        return exchange(authority.path,authority.owner,event.payload,operation,
                        account_id=authority.account_id,authorize=authority)
    except (ValueError,sqlite3.Error):return _failed(session)
