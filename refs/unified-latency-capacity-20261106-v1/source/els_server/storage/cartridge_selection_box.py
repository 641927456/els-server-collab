"""Consume one existing owned119335, one exact choice, original atomic factory/codec."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import struct
from els_server.domain.cartridge_selection_box import BOX, OUTPUTS, request, plain_box, _BoxAuthority, _BoxSource
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances

WRITER_ENABLED = True


def _context(db, owner, account_id, authorize):
    if (not WRITER_ENABLED or type(authorize) is not _BoxAuthority or authorize() is not True
            or authorize.owner != owner or authorize.account_id != account_id or not db.in_transaction):
        raise ValueError('Cartridge selection obsolete authority')
    main = [r[2] for r in db.execute('PRAGMA database_list') if r[1] == 'main']
    if len(main) != 1 or Path(main[0]).resolve() != authorize.path:
        raise ValueError('Cartridge selection original store')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone() != (account_id,):
        raise ValueError('Cartridge selection foreign account')
    require_active_character(db,owner)
    from els_server.storage.character_lifecycle import states
    state = states(db,(owner,)).get(owner)
    if state and state['account_id'] != account_id:
        raise ValueError('Cartridge selection lifecycle account mismatch')


def _history(db, owner, operation, value, positions):
    row = db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',
                     (operation,)).fetchone()
    if row is None or row[:2] != (owner,0x196):
        raise ValueError('Cartridge selection receipt owner/kind')
    try:
        before, after = (json.loads(raw) for raw in row[2:])
        from els_server.domain.inventory_items import inventory_payload
        if type(before) is not list or type(after) is not list:
            raise ValueError('Cartridge selection history arrays')
        from els_server.domain.cartridge_selection_box import read_existing_box
        for rows in (before,after):
            inventory_payload([read_existing_box(r) if type(r) is dict and r.get("template")==BOX else r for r in rows])
        b, a = {r['uid']:r for r in before}, {r['uid']:r for r in after}
        old = b.get(value.uid)
        if not plain_box(old) or value.uid in a or len(b) != len(before) or len(a) != len(after):
            raise ValueError('Cartridge selection history source')
        new = [r for uid,r in a.items() if uid not in b]
        if (len(new) != 1 or set(new[0]) != {'uid','template','metadata','group','slot','count'}
                or (new[0]['template'],new[0]['metadata'],new[0]['group'],new[0]['count']) != (value.choices[0],0,4,1)
                or {uid:r for uid,r in b.items() if uid != value.uid} != {uid:r for uid,r in a.items() if uid in b}):
            raise ValueError('Cartridge selection historical output transition')
        expected = list(dict.fromkeys([(old['group'],old['slot']),(new[0]['group'],new[0]['slot'])]))
        if positions != expected:
            raise ValueError('Cartridge selection receipt positions')
    except (KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('Cartridge selection history structure') from exc


def open_box(path, owner, payload, operation, *, account_id, authorize):
    if not WRITER_ENABLED:
        raise ValueError('Cartridge selection writer closed')
    value = request(payload)
    if type(account_id) is not int or not 1 <= account_id < 2**63:
        raise ValueError('Cartridge selection account identity')
    owner, digest = _identity(owner,0x196,struct.pack('>Qi',account_id,BOX)+payload,operation)
    if type(authorize) is not _BoxAuthority or authorize.operation != operation or authorize.payload != payload:
        raise ValueError('Cartridge selection request authority')
    uri = Path(path).resolve().as_uri() + '?mode=rw'
    with closing(sqlite3.connect(uri,uri=True,timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON'); db.execute('BEGIN IMMEDIATE')
        _context(db,owner,account_id,authorize)
        balance = validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
        previous = _previous(db,operation,digest)
        before = load_items(db,owner)
        if previous is not None:
            _history(db,owner,operation,value,previous)
            answer = result(balance['ed'],current_changes(db,operation,owner,0x196,previous,before))
            for event in answer:
                encode_event(event)
            _context(db,owner,account_id,authorize)
            return answer
        item = next((i for i in before if i['uid'] == value.uid),None)
        if not plain_box(item):
            raise ValueError('Cartridge selection requires owned plain singleton')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item); require_unlocked(item)
        if balance['revision'] >= 2**63-1:
            raise ValueError('Cartridge selection wallet revision overflow')
        source = _BoxSource(db,owner,account_id,payload,operation,authorize)
        try:
            remove(db,owner,item)
            source.debit_complete()
            grants = grant_items(db,[dict(template=value.choices[0],metadata=0,group=4,quantity=1)],owner,
                                 cartridge_box_source=source)
        finally:
            source.close()
        if (len(grants) != 1 or set(grants[0]) != {'uid','template','metadata','group','slot','count'}
                or (grants[0]['template'],grants[0]['metadata'],grants[0]['group'],grants[0]['count']) != (value.choices[0],0,4,1)
                or grants[0]['uid'] in {i['uid'] for i in before}):
            raise ValueError('Cartridge selection original singleton factory mismatch')
        after = load_items(db,owner)
        positions = list(dict.fromkeys([(item['group'],item['slot']),*[(i['group'],i['slot']) for i in grants]]))
        current = {(i['group'],i['slot']):i for i in after}
        answer = result(balance['ed'],[(p,current.get(p)) for p in positions],[(value.choices[0],1)])
        for event in answer:
            encode_event(event)
        if db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=? AND revision=?',
                      (owner,balance['revision'])).rowcount != 1:
            raise ValueError('Cartridge selection wallet changed')
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        _context(db,owner,account_id,authorize)
        return answer
