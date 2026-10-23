"""Original House40326 manual exchange only; no menu, effects or timers."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol.protocol_codec import Event
from els_server.protocol.purifier_exchange_messages import acknowledgement
from els_server.storage.cartridge_exchange import exchange
from els_server.storage.reward_state import validate_balances
from els_server.domain.cartridge_exchange_rules import _SelectAuthority

WRITER_ENABLED = True


def _local_selected(session):
    from uuid import UUID
    from els_server.application import Application
    from els_server.domain.local_session import LocalAccount,LocalSession
    from els_server.storage.local_state import LocalState
    from els_server.storage.characters import Characters
    account=getattr(session,'account',None);root=getattr(account,'root',None)
    app=getattr(session,'_cartridge40326_local_application',None)
    if (type(session) is not LocalSession or type(app) is not Application
        or getattr(session,'_cartridge40326_local_live',None) is not True
        or app.config.mode!='local' or type(account) is not LocalAccount
        or type(root) is not LocalAccount or root.root is not root or app.account is not root
        or type(root.account_id) is not int or root.account_id!=1
        or root.character_accounts.get(account.uid) is not account
        or type(account.store) is not LocalState or account.store.uid!=account.uid
        or type(root.store) is not LocalState or root.store.uid!=root.uid
        or type(account.characters) is not Characters or root.characters is not account.characters
        or account.account_id!=root.account_id or account.characters.account_id!=account.account_id
        or session.role!='game' or 0x28 not in session.completed):
        return False
    path=Path(account.store.path).resolve()
    if (Path(root.store.path).resolve()!=path or Path(account.characters.path).resolve()!=path
        or Path(app.config.state_file).resolve()!=path):return False
    token=session.shop_session_id
    try:return type(token) is str and str(UUID(token))==token and UUID(token).version==4
    except ValueError:return False



def _selected(session):
    if getattr(session, 'application', None) is None:return _local_selected(session)
    return bool(getattr(session, 'application', None) is not None and current_lease(session)
                and session.role == 'game' and 0x28 in session.completed
                and session.account.characters is not None and session.account.store is not None
                and session.account.store.uid == session.account.uid)


def _context(session):
    from els_server.storage.local_state import TOWN_SCENES
    return bool(_selected(session) and session.phase == 'town_ready'
                and session.active_map == 1012 and TOWN_SCENES.get(1012) == 1214)


def _failed(session):
    if not _selected(session):
        raise ValueError('Cartridge exchange without a current owned character')
    path = Path(session.account.store.path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(path, uri=True, timeout=10)) as db:
        value = db.execute('''SELECT b.ed,b.experience,b.revision FROM reward_balances b
            JOIN character_owners o ON o.uid=b.uid JOIN characters c ON c.uid=b.uid
            WHERE b.uid=? AND o.account_id=?''',
            (session.account.uid, session.account.account_id)).fetchone()
    ed = validate_balances(value)['ed']
    return [Event(0x201, kind=0x224, payload=acknowledgement(ed, result=-1))]


def handle(session, event, sequence):
    if not (session.item_test and session.client_build == 'dx11_260923'
            and event.event_id == 0x202 and event.kind == 0x223):
        return None
    # Preserve the existing purifier and every other shared223 route.
    if not isinstance(event.payload, bytes) or len(event.payload) < 4:
        return None
    if struct.unpack_from('>i', event.payload)[0] != 40326:
        return None
    if not _selected(session):
        raise ValueError('Cartridge exchange before owned character selection')
    if (not WRITER_ENABLED or not _context(session)
            or type(sequence) is not int or not 1 <= sequence < 2**32
            or event.performers != (0,) or event.uid != 0xffffffffffffffff
            or event.target_uid != 0xffffffffffffffff or event.payload_mode != 0):
        return _failed(session)
    operation = (session.shop_session_id + ':' + str(session.account.uid)
                 + ':cartridge-exchange40326:' + str(sequence))
    authority = _SelectAuthority(session, event, sequence, operation, lambda: _context(session))
    try:
        return exchange(authority.path, authority.owner,
                        event.payload, operation, account_id=authority.account_id,
                        authorize=authority)
    except (ValueError, sqlite3.Error):
        return _failed(session)
