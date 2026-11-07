"""Current saved character eligibility for player-initiated item mutations.

Internal expiration cleanup remains independent. Caller owns the SQL transaction.
"""
from els_server.storage.character_schema import character_uid
from els_server.storage.character_lifecycle import _states,_state_rows,SCHEMA as LIFECYCLE_SCHEMA
from els_server.storage.initialization_checks import CHARACTERS

def require_active_character(db,owner):
    owner=character_uid(owner)
    if not db.in_transaction:raise ValueError('Item actor requires a transaction')
    tables=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name IN ('characters','character_lifecycle')"))
    if tables.get('characters')==CHARACTERS['characters'] and tables.get('character_lifecycle')==LIFECYCLE_SCHEMA:
        rows=db.execute('SELECT c.uid,l.* FROM characters c LEFT JOIN character_lifecycle l ON l.uid=c.uid WHERE c.uid=?',(owner,)).fetchall()
        if not rows:
            raise ValueError('Item actor character missing')
        state=_state_rows(row[1:]for row in rows if row[1]is not None).get(owner,{})
    else:
        if 'characters' in tables:
            if db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone() is None:
                raise ValueError('Item actor character missing')
        elif owner!=1001:raise ValueError('Unknown legacy item actor')
        state=_states(db,(owner,)).get(owner,{})if 'character_lifecycle'in tables else {}
    if state.get('requested_at') or state.get('finalized_at'):
        raise ValueError('Item actor is pending deletion or finalized')
