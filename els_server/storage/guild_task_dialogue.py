"""Exact current accepted generation FD, without manufacturing membership."""
from contextlib import closing
import hashlib
import json
import sqlite3
from els_server.domain.guild_task35630 import catalog
from els_server.domain.seal_quests import require_eligible
from els_server.storage.seal_quests import load_character,completed_ids,_state
from els_server.storage.inventory_state import load_items
from els_server.protocol import quest_messages,tutorial_dialogue_messages
from els_server.protocol.protocol_codec import encode_event


def interact(store,operation,guard):
    with closing(sqlite3.connect(store.path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');guard()
        from els_server.domain.guild_task35630 import WRITER_ENABLED
        if not WRITER_ENABLED:raise ValueError('New Guild task dialogue is held')
        character=load_character(db,store.uid,store.account_id)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return []
        items=load_items(db,store.uid);state=_state(db,store.uid,items)
        active=next((r for r in state['active'] if r['id']==35630),None)
        if active is None:return []
        saved=db.execute('SELECT town FROM location WHERE uid=?',(store.uid,)).fetchone()
        if saved is None or str(saved[0]) not in catalog()['towns']:raise ValueError('Mu saved scene')
        require_eligible(character,catalog()['quests']['35630'],completed_ids(db,store.uid),items,location=('town',saved[0]))
        if db.execute('SELECT owner,kind FROM quest_actions WHERE rowid=?',(active['generation'],)).fetchone()!=(store.uid,'accept'):
            raise ValueError('Mu dialogue accepted owner/generation')
        raw=json.dumps(dict(quest=35630,npc=10045,town=saved[0],generation=active['generation'],accepted_at=active['accepted_at']),sort_keys=True)
        digest=hashlib.sha256(raw.encode()).hexdigest()
        old=db.execute('SELECT proof_hash,event_json FROM quest_progress_events WHERE owner=? AND event_id=?',(store.uid,operation)).fetchone()
        if old is not None and old!=(digest,raw):raise ValueError('Mu dialogue stale generation replay')
        counts=dict(active['objectives']);counts[35630]=1
        if old is not None and active['objectives']!=counts:raise ValueError('Mu progress receipt/state mismatch')
        if old is None:
            if db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=35630 AND generation=?',
                          (json.dumps(counts,sort_keys=True),store.uid,active['generation'])).rowcount!=1:raise ValueError('Mu acceptance retired')
            db.execute('INSERT INTO quest_progress_events VALUES(?,?,?,?)',(store.uid,operation,digest,raw))
        events=[quest_messages.progress([dict(active,objectives=counts)]),tutorial_dialogue_messages.acknowledgement(35630)]
        for event in events:encode_event(event)
        guard()
        return events
