"""Send the persisted return input after the native festival scene is ready."""
from contextlib import closing
import sqlite3,struct
from els_server.protocol.protocol_codec import Event
from els_server.storage.festival_origins import saved

def ready(s):
    if s.active_map!=1503:return []
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        town=saved(db,s.account.uid,s.account.account_id)
    return []if town is None else [Event(0x201,kind=0x7ffe,payload=struct.pack('>BQi',1,s.account.uid,town))]
