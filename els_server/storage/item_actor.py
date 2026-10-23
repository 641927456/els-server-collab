"""Current saved character eligibility for player-initiated item mutations.

Internal expiration cleanup remains independent. Caller owns the SQL transaction.
"""
from els_server.storage.character_schema import character_uid
from els_server.storage.character_lifecycle import states

def require_active_character(db,owner):
    owner=character_uid(owner)
    if not db.in_transaction:raise ValueError('Item actor requires a transaction')
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='characters'").fetchone():
        if db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone() is None:
            raise ValueError('Item actor character missing')
    elif owner!=1001:raise ValueError('Unknown legacy item actor')
    state=states(db,(owner,)).get(owner,{})
    if state.get('requested_at') or state.get('finalized_at'):
        raise ValueError('Item actor is pending deletion or finalized')
