"""Prepare shared storage without allocating any account or character state."""
from contextlib import closing
import sqlite3
from els_server.storage.local_state import ensure_local_tables
from els_server.storage.reward_state import ensure_reward_tables
from els_server.storage.inventory_state import ensure_inventory
from els_server.storage.sqlite_timing import write_transaction

def prepare(path):
    with closing(sqlite3.connect(path,timeout=10))as db,write_transaction(db):
        ensure_local_tables(db)
        ensure_reward_tables(db)
        ensure_inventory(db)
