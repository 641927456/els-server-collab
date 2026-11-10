"""Restore and replace the selected character's native checklist favorites."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from els_server.domain.equipment_chip_flow import current_lease
from els_server.domain.quest_flow import enabled
from els_server.protocol import adventure_checklist_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.read_scope import snapshot_connection
from els_server.storage.sqlite_timing import write_transaction


def _capture(session):
    account = session.account
    store = account.store
    owner, account_id = account.uid, account.account_id

    def guard(db):
        if (session.role != 'game' or not enabled(session) or getattr(session, 'released', False)
                or session.account is not account or account.store is not store
                or (account.uid, account.account_id) != (owner, account_id)
                or store.uid != owner or not current_lease(session)):
            raise ValueError('Adventure checklist requires a current selected character')
        require_owner(db, owner, account_id)
        require_active_character(db, owner)

    return store.path, owner, guard


def _read(db, owner):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='adventure_checklist_favorites'").fetchone():
        return {}
    return {
        category: tuple(json.loads(ids))
        for category, ids in db.execute(
            'SELECT category, ids FROM adventure_checklist_favorites WHERE owner=?', (owner,)
        )
    }


def initialization(session):
    if session.role != 'game' or not enabled(session):
        return []
    path, owner, guard = _capture(session)
    with snapshot_connection(path) as db:
        db.execute('BEGIN')
        guard(db)
        answer = wire.initialization(_read(db, owner))
        guard(db)
        return [answer]


def handle(session, event, sequence):
    try:
        if (session.role != 'game' or not enabled(session) or event.performers not in ((), (0,))
                or event.uid != 2**64 - 1 or event.target_uid != 2**64 - 1
                or event.payload_mode != 0 or type(sequence) is not int or not 1 <= sequence < 2**32):
            raise ValueError('Invalid adventure checklist request envelope')
        category, ids = wire.request(event.payload)
        path, owner, guard = _capture(session)
        uri = Path(path).resolve().as_uri() + '?mode=rw'
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            with write_transaction(db):
                guard(db)
                favorites = _read(db, owner)
                if favorites.get(category, ()) != ids:
                    db.execute('''CREATE TABLE IF NOT EXISTS adventure_checklist_favorites (
                        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
                        category INTEGER NOT NULL CHECK(category BETWEEN 1 AND 3),
                        ids TEXT NOT NULL,
                        PRIMARY KEY(owner, category))''')
                    db.execute('''INSERT INTO adventure_checklist_favorites VALUES (?,?,?)
                        ON CONFLICT(owner, category) DO UPDATE SET ids=excluded.ids''',
                        (owner, category, json.dumps(ids)))
                    favorites[category] = ids
                answer = wire.acknowledgement(favorites)
                encode_event(answer)
                guard(db)
        return [answer]
    except (ValueError, sqlite3.Error):
        return [wire.acknowledgement({}, result=-1)]
