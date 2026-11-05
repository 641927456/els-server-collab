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
        # Prepare receipt search paths before accepting players. Partial JSON
        # indexes keep unrelated coin/EXP receipts out of these history reads.
        db.execute("""CREATE INDEX IF NOT EXISTS reward_receipts_challenge_owner_time
            ON reward_receipts(COALESCE(json_extract(grant_json,'$.owner'),1001),
                               json_extract(grant_json,'$.challenge_clear.now'))
            WHERE json_extract(grant_json,'$.challenge_clear.now') IS NOT NULL""")
        db.execute("""CREATE INDEX IF NOT EXISTS reward_receipts_story_owner_map
            ON reward_receipts(json_extract(grant_json,'$.owner'),
                               json_extract(grant_json,'$.dungeon_clear[0]'))
            WHERE json_extract(grant_json,'$.dungeon_clear[0]') IS NOT NULL""")
