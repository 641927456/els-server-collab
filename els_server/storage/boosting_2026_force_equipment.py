"""Selected-force loadout, native full-preset ACK and current-state retries."""
import json,sqlite3,struct
from contextlib import closing
from els_server.domain.boosting_2026_force_equipment import request,changed,slots,acknowledgement
from els_server.storage.boosting_2026_force_inventory import saved as saved_owned,initialize as initialize_owned
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.protocol.protocol_codec import encode_event

def saved(db,owner):
    owner=character_uid(owner);result=[(0,0)]*3
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='selected_2026_force_slots'").fetchone():
        for index,skill,rank in db.execute('SELECT slot,skill,rank FROM selected_2026_force_slots WHERE owner=? ORDER BY slot',(owner,)):
            if index not in range(3):raise ValueError('Saved force slot index')
            result[index]=(skill,rank)
    return slots(dict(force_inventory=saved_owned(db,owner),force_slots=result))

def snapshot(path,owner):
    with closing(sqlite3.connect(path)) as db:return saved(db,owner)

def _character(db,owner,account):
    from els_server.storage.characters import Characters
    row=db.execute('SELECT c.uid,c.name,c.unit_type,c.unit_class,c.level,c.transcendence,c.master,c.revision FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(owner,account)).fetchone()
    if row is None:raise ValueError('Force loadout character owner')
    character=Characters._row(row)
    artifact=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(owner,)).fetchone()
    character['artifact']=dict(zip(('template','evolution','level','experience','potentials'),artifact)) if artifact else None
    if artifact:character['artifact']['potentials']=json.loads(artifact[4])
    from els_server.storage.skill_expansion import is_expanded
    from els_server.storage.skill_unlocks import saved_groups
    from els_server.storage.skill_traits import saved as saved_traits
    character.update(skill_row_expanded=is_expanded(db,owner),skill_seal_groups=saved_groups(db,owner),skill_traits=saved_traits(db,owner),force_inventory=saved_owned(db,owner),force_slots=saved(db,owner))
    return character

def _preset(db,character):
    from els_server.domain.character_rules import default_slots
    from els_server.domain.skill_rules import upgraded_slots,equippable_skills
    from els_server.domain.role_progression import known_skills
    from els_server.domain.skill_state import preset_payload
    row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(character['uid'],)).fetchone()
    if row:
        if len(row[0])!=88:raise ValueError('Saved normal skill preset size')
        normal=struct.unpack('>22i',row[0]);known=known_skills(character['unit_class'])
        if any(s and s not in known for s in normal):raise ValueError('Unknown saved ordinary skill')
        normal=upgraded_slots(normal,character)
    else:normal=default_slots(character)
    return preset_payload(normal,equippable_skills(character),character)

def action(path,owner,account,payload,operation):
    request(payload)
    if not isinstance(operation,str):raise ValueError('Force slot operation identity')
    operation='force-slot:'+operation;owner,digest=_identity(owner,0x6d0,payload,operation)
    if type(account) is not int or not 0<account<2**63:raise ValueError('Force equipment account')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');character=_character(db,owner,account);old=_previous(db,operation,digest)
        if old is not None:
            if db.execute('SELECT owner,kind FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()!=(owner,0x6d0):raise ValueError('Force equipment retry owner/kind')
            event=acknowledgement(_preset(db,character));encode_event(event);return event
        before=character['force_slots'];after=changed(character,payload);modified=after!=before
        if modified and character['revision']>=2**63-1:raise ValueError('Force character revision overflow')
        event=acknowledgement(_preset(db,dict(character,force_slots=after)));encode_event(event)
        initialize_owned(db)
        db.execute('''CREATE TABLE IF NOT EXISTS selected_2026_force_slots (
            owner INTEGER NOT NULL,slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 2),
            skill INTEGER NOT NULL,rank INTEGER NOT NULL,PRIMARY KEY(owner,slot),UNIQUE(owner,skill),
            FOREIGN KEY(owner,skill,rank) REFERENCES selected_2026_force_inventory(owner,skill,rank))''')
        if modified:
            db.execute('DELETE FROM selected_2026_force_slots WHERE owner=?',(owner,))
            db.executemany('INSERT INTO selected_2026_force_slots VALUES (?,?,?,?)',[(owner,i,s,r) for i,(s,r) in enumerate(after) if s])
            db.execute('UPDATE characters SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x6d0,[],[list(p) for p in before],[list(p) for p in after])
        assert saved(db,owner)==after
        return event
