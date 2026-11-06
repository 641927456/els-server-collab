"""Read-only, account-authorized snapshots of another character's private bank."""
import sqlite3
from contextlib import closing
from els_server.protocol.bank_view_messages import request,acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.bank_state import account_for,capacity,load


def contents(path,owner,payload):
    name=request(payload)
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute('BEGIN')
        account=account_for(db,owner)
        if db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('characters','character_owners')").fetchone()[0]!=2:
            raise ValueError('Bank browser needs an account character roster')
        target=db.execute('SELECT c.uid,c.name FROM characters c JOIN character_owners o ON o.uid=c.uid '
            'WHERE c.name_key=? AND o.account_id=?',(name.casefold(),account)).fetchone()
        # Selecting the current character is handled locally by 238F668; it
        # restores the owned group 8 instead of duplicating UIDs in group 14.
        if target is None or target[0]==owner:raise ValueError('Unknown other account character')
        uid,actual_name=target
        wire=acknowledgement(uid,actual_name,capacity(db,uid,8),load(db,uid))
        return [Event(0x201,kind=0x72f,payload=wire)]
