"""Account character identities and transactional creation receipts."""
import hashlib
import json
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path
from els_server.storage.character_schema import character_uid,migrate_character_schema

# Current client's UNIT_CLASS / UNIT_TYPE enums, also used by the native
# CorrelateUnitClassTemplet. Character type is not a class ID for types 10–15.
BASE_CLASSES={**{n:n for n in range(1,10)},10:200,11:201,12:202,13:203,14:204,15:205}
DEFAULT_CHARACTER=dict(uid=1001,name='LocalElsword',unit_type=1,unit_class=1,
                       level=1,transcendence=False,master=False,revision=0,skill_row_expanded=False,bag_capacities={},skill_seal_groups=())

def validate_name(name):
    if not isinstance(name,str) or not 2<=len(name)<=12:
        raise ValueError('Character name length')
    if sum(2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in name)>12:raise ValueError('Character name length')
    if len(name.encode('utf-16le'))>24 or any(not c.isalnum() for c in name):
        raise ValueError('Character name characters')
    if unicodedata.normalize('NFC',name)!=name:raise ValueError('Noncanonical character name')
    return name

class Characters:
    def __init__(self,path,account_id=1):
        if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('Invalid account identity')
        self.account_id=account_id
        self.path=Path(path)
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE');migrate_character_schema(db)
            db.execute('CREATE TABLE IF NOT EXISTS characters (uid INTEGER PRIMARY KEY CHECK(uid>=1001), name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE, unit_type INTEGER NOT NULL CHECK(unit_type BETWEEN 1 AND 15), unit_class INTEGER NOT NULL, level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99), transcendence INTEGER NOT NULL CHECK(transcendence IN (0,1)), master INTEGER NOT NULL CHECK(master IN (0,1)), revision INTEGER NOT NULL DEFAULT 0)')
            db.execute('INSERT OR IGNORE INTO characters VALUES (1001,?,?,?,?,1,0,0,0)',('LocalElsword','localelsword',1,1))
            # Preserve the original character schema and every legacy row.
            # Only previously unowned roles are adopted by the local account.
            db.execute('CREATE TABLE IF NOT EXISTS character_owners (uid INTEGER PRIMARY KEY REFERENCES characters(uid), account_id INTEGER NOT NULL CHECK(account_id>0))')
            db.execute('INSERT OR IGNORE INTO character_owners SELECT uid,1 FROM characters')
            db.execute('CREATE INDEX IF NOT EXISTS character_owners_account ON character_owners(account_id)')
            db.execute('CREATE TABLE IF NOT EXISTS character_creation_receipts (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, uid INTEGER NOT NULL REFERENCES characters(uid))')
            db.execute('CREATE TABLE IF NOT EXISTS character_artifacts (uid INTEGER PRIMARY KEY REFERENCES characters(uid), template INTEGER NOT NULL CHECK(template BETWEEN 1 AND 15), evolution INTEGER NOT NULL CHECK(evolution BETWEEN 1 AND 5), level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99), experience INTEGER NOT NULL CHECK(experience>=0), potentials TEXT NOT NULL)')

    @staticmethod
    def _row(row):
        if row is None:raise ValueError('Unknown character')
        out=dict(zip(('uid','name','unit_type','unit_class','level','transcendence','master','revision'),row))
        out['transcendence']=bool(out['transcendence']);out['master']=bool(out['master'])
        return out

    def list(self):
        return self._project()

    def _project(self,uid=None):
        # Share the full wire projection, but read only the requested owned
        # identity for get(). No player state survives this connection.
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            query='SELECT c.uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE o.account_id=?'
            parameters=(self.account_id,)
            if uid is not None:
                query+=' AND c.uid=?';parameters+=(uid,)
            rows=[self._row(r) for r in db.execute(query+' ORDER BY c.uid',parameters)]
            from els_server.storage.character_lifecycle import decorate
            rows=decorate(db,rows)
            artifact_query='SELECT a.uid,a.template,a.evolution,a.level,a.experience,a.potentials FROM character_artifacts a JOIN character_owners o ON o.uid=a.uid WHERE o.account_id=?'
            if uid is not None:artifact_query+=' AND a.uid=?'
            visible={r['uid'] for r in rows}
            artifacts={r[0]:dict(template=r[1],evolution=r[2],level=r[3],experience=r[4],potentials=json.loads(r[5])) for r in db.execute(artifact_query,parameters) if r[0] in visible}
            has_dungeon_records=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dungeon_records'").fetchone() is not None
            for row in rows:
                from els_server.storage.resonance_state import snapshot as resonance_snapshot
                row['resonance']=resonance_snapshot(db,row['uid'],self.account_id)
                from els_server.storage.titles import snapshot as title_snapshot,completed_for_equipment
                row['title']=title_snapshot(db,row['uid'])['title']
                from els_server.storage.character_custom import snapshot as custom_snapshot
                row['character_custom']=custom_snapshot(db,row['uid'])
                row['title_completed_quests']=completed_for_equipment(db,row['uid'])
                row['artifact']=artifacts.get(row['uid'])
                row['cleared_dungeons']=tuple(r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=? ORDER BY map_id',(row['uid'],))) if has_dungeon_records else ()
                from els_server.storage.ep_points import balance as ep_balance
                ep=ep_balance(db,row['uid'])
                if ep:row['ep']=ep
                from els_server.storage.skill_expansion import is_expanded
                row['skill_row_expanded']=is_expanded(db,row['uid'])
                from els_server.storage.skill_unlocks import saved_groups
                row['skill_seal_groups']=saved_groups(db,row['uid'])
                from els_server.storage.skill_traits import saved as saved_traits
                from els_server.domain.skill_traits import visible as visible_traits
                traits=saved_traits(db,row['uid'])
                if traits:row['skill_traits']=visible_traits(row,traits)
                from els_server.storage.bag_capacity import saved_capacities
                row['bag_capacities']=saved_capacities(db,row['uid'])
                from els_server.storage.profession_state import snapshot as profession_snapshot
                saved_profession=profession_snapshot(db,row['uid'],self.account_id)
                row['profession']=saved_profession['state']
                row['profession_revision']=saved_profession['revision']
                if row['unit_type']==10:
                    from els_server.storage.luciel_state import state as luciel_state,active_state as luciel_active_state
                    row['luciel_style']=luciel_state(db,row['uid'])['style']
                    row['luciel_active_unit']=luciel_active_state(db,row['uid'])['active_unit']
            return rows

    def identity(self,uid):
        # Eligibility consumers require current owned identity/level only.
        # Keep all extended projections in get()/list() for wire consumers.
        uid=character_uid(uid)
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            row=db.execute('SELECT c.uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(uid,self.account_id)).fetchone()
            value=self._row(row)
            # list()/get() also reject finalized deletions; a narrow read
            # must preserve that owner eligibility boundary.
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_lifecycle'").fetchone():
                state=db.execute('SELECT finalized_at FROM character_lifecycle WHERE uid=?',(uid,)).fetchone()
                if state and state[0]:return self._row(None)
            return value

    def get(self,uid):
        uid=character_uid(uid)
        return next(iter(self._project(uid)),None) or self._row(None)

    def name_available(self,name):
        validate_name(name)
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            return db.execute('SELECT 1 FROM characters WHERE name_key=?',(name.casefold(),)).fetchone() is None

    def create(self,name,unit_type,operation_id):
        validate_name(name)
        if type(unit_type) is not int or unit_type not in BASE_CLASSES:raise ValueError('Unknown character type')
        from els_server.game_data import client_data
        template=client_data().unit(BASE_CLASSES[unit_type])
        if template['unitType']!=unit_type:raise ValueError('Client character template mismatch')
        if not isinstance(operation_id,str) or not 1<=len(operation_id)<=100:raise ValueError('Creation operation identity')
        digest=hashlib.sha256(json.dumps([name,unit_type],ensure_ascii=False).encode()).hexdigest()
        # Cold source imports can parse large pinned client catalogs. Complete
        # these read-only dependencies before acquiring SQLite's sole writer.
        # Ownership, capacity, UID allocation, items and wire validation below
        # still share the original atomic creation transaction.
        from els_server.storage.character_lifecycle import check_creation,current_time,created
        from els_server.storage.bag_capacity import grant_starting_fashion
        from els_server.domain.tutorial_quests import starting_town
        from els_server.storage.role_loadout import grant_loadout
        from els_server.domain.character_rules import default_slots
        from els_server.domain.skill_rules import equippable_skills
        from els_server.domain.skill_state import encode_slots
        from els_server.protocol.character_messages import create_ack
        from els_server.domain.role_progression import catalog as role_catalog
        from els_server.domain.equipment_requirements import catalog as equipment_catalog
        town=starting_town(unit_type);role_catalog();equipment_catalog()
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT request_hash,uid FROM character_creation_receipts WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Conflicting creation retry')
                if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(old[1],)).fetchone()!=(self.account_id,):raise ValueError('Creation receipt belongs to another account')
                uid=old[1]
            else:
                now=current_time();check_creation(db,self.account_id,now)
                if db.execute('SELECT 1 FROM characters WHERE name_key=?',(name.casefold(),)).fetchone():raise ValueError('Character name already exists')
                uid=db.execute('SELECT MAX(uid)+1 FROM characters').fetchone()[0];character_uid(uid)
                db.execute('INSERT INTO characters VALUES (?,?,?,?,?,1,0,0,0)',(uid,name,name.casefold(),unit_type,BASE_CLASSES[unit_type]))
                db.execute('INSERT INTO character_owners VALUES (?,?)',(uid,self.account_id))
                created(db,uid,self.account_id,now)
                starting_bags=grant_starting_fashion(db,uid)
                # New identities and their role-specific starter items commit
                # together; retry receipts never grant a second set.
                db.execute('INSERT INTO location VALUES (?,?,0,0,0,0,0,0)',(uid,town))
                db.execute('INSERT INTO reward_balances VALUES (?,0,0,0)',(uid,))
                character=dict(DEFAULT_CHARACTER,uid=uid,name=name,unit_type=unit_type,unit_class=BASE_CLASSES[unit_type],artifact=None,bag_capacities=starting_bags)
                items=grant_loadout(db,character)
                # Native tutorial skill step admits A/C; sequential A/S
                # left the second starter skill blocked until the next step.
                # Only new rows change. Replays and saved player slots stay put.
                starting_slots=list(default_slots(character))
                starting_slots[3],starting_slots[1]=starting_slots[1],0
                db.execute('INSERT INTO skill_slots VALUES (?,?,0)',(uid,encode_slots(tuple(starting_slots),equippable_skills(character),character)))
                # Refuse an unencodable initial character before committing any
                # identity, equipment, sequence allocation or creation receipt.
                create_ack(character,items=items)
                db.execute('INSERT INTO character_creation_receipts VALUES (?,?,?)',(operation_id,digest,uid))
        return self.get(uid)
