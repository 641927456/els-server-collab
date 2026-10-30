"""Durable, transactional location and HUD for the single local test character."""
import math,sqlite3,struct
from contextlib import contextmanager
from pathlib import Path
from els_server.storage.character_schema import character_uid,migrate_character_schema
from els_server.storage.sqlite_timing import write_transaction
from els_server.domain.ui_layout import DEFAULT_LAYOUT,encode_layout,decode_layout
from els_server.domain.key_bindings import DEFAULT_BINDINGS,validate_bindings
from els_server.domain.skill_state import DEFAULT_SLOTS,encode_slots,decode_slots

# Measured StageManager map-to-scene table, 20261012-182806-702371.
TOWN_SCENES={20000:258,20001:263,20002:262,20003:265,20004:326,
             20005:268,20006:417,20007:491,20008:582,20009:636,
             20010:778,20011:894,20012:1004,20013:1023,20014:1106,1008:637,1009:851,1010:964,1011:1131,1012:1214,1500:725}
DEFAULT_LOCATION={'map':20000,'board':0,'progress':0,'xyz':(0.,0.,0.),'revision':0}

def validate_location(map_id,board,progress,xyz):
    if map_id not in TOWN_SCENES or not 0<=board<255 or not 0<=progress<=100:
        raise ValueError('Unsupported town location')
    if len(xyz)!=3 or any(not math.isfinite(v) or abs(v)>1_000_000 for v in xyz):
        raise ValueError('Invalid location coordinates')

def scene_ready_location(payload):
    if len(payload)!=15:raise ValueError('Invalid scene-ready payload size')
    x,y,z,board,progress=struct.unpack('>fffBH',payload)
    return board,progress,(x,y,z)

def movement_location(payload,client_build='legacy'):
    # 20d7ba0: xyz, vector<pair<byte,byte>>, bool, board, ushort progress,
    # byte, two int32, bool. 2ff6080 writes the vector count and byte pairs.
    if client_build not in ('legacy','dx11_260923'):raise ValueError('Unknown movement schema')
    if len(payload)<30:raise ValueError('Truncated town movement')
    count=struct.unpack_from('>I',payload,12)[0]
    if client_build=='dx11_260923':
        # Updated native writer 21152A0 appends int32 from DTO+32 after
        # the final bool at DTO+31. Its meaning is not used as save data.
        if count>512 or len(payload)!=34+2*count:raise ValueError('Invalid updated movement vector size')
        payload=payload[:-4]
    if count>512 or len(payload)!=30+2*count:raise ValueError('Invalid movement vector size')
    offset=16+2*count
    flag,board,progress=struct.unpack_from('>BBH',payload,offset)
    if flag not in (0,1) or payload[-1] not in (0,1):raise ValueError('Invalid movement bool')
    return board,progress,struct.unpack_from('>fff',payload)

class LocalState:
    def __init__(self,path,uid=1001):
        self.uid=character_uid(uid)
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db,write_transaction(db):
            migrate_character_schema(db)
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1):raise ValueError('Unsupported local save version')
            db.execute('CREATE TABLE IF NOT EXISTS location (uid INTEGER PRIMARY KEY CHECK(uid>=1001), town INTEGER NOT NULL, board INTEGER NOT NULL CHECK(board>=0 AND board<255), progress INTEGER NOT NULL CHECK(progress>=0 AND progress<=100), x REAL NOT NULL, y REAL NOT NULL, z REAL NOT NULL, revision INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO location VALUES (?,20000,0,0,0,0,0,0)',(self.uid,))
            db.execute('CREATE TABLE IF NOT EXISTS ui_layout (uid INTEGER PRIMARY KEY CHECK(uid>=1001), payload BLOB NOT NULL, revision INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS key_bindings (uid INTEGER PRIMARY KEY CHECK(uid>=1001), payload BLOB NOT NULL, revision INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS skill_slots (uid INTEGER PRIMARY KEY CHECK(uid>=1001), payload BLOB NOT NULL, revision INTEGER NOT NULL)')
            db.execute('PRAGMA user_version=1')
        self.load()  # Existing invalid state is refused, never silently overwritten.
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def load(self):
        with snapshot_connection(self.path) as db:r=db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(self.uid,)).fetchone()
        if r is None:raise ValueError('Missing local character state')
        validate_location(r[0],r[1],r[2],r[3:6])
        return {'map':r[0],'board':r[1],'progress':r[2],'xyz':tuple(r[3:6]),'revision':r[6]}
    def load_layout(self):
        with snapshot_connection(self.path) as db:r=db.execute('SELECT payload FROM ui_layout WHERE uid=?',(self.uid,)).fetchone()
        return decode_layout(r[0]) if r else DEFAULT_LAYOUT
    def load_bindings(self):
        with snapshot_connection(self.path) as db:r=db.execute('SELECT payload FROM key_bindings WHERE uid=?',(self.uid,)).fetchone()
        return validate_bindings(r[0]) if r else DEFAULT_BINDINGS
    def load_skills(self):
        with snapshot_connection(self.path) as db:
            return self._load_skills(db,self._skill_character(db))
    def _load_skills(self,db,character):
        from els_server.domain.character_rules import default_slots
        from els_server.domain.skill_rules import equippable_skills,upgraded_slots
        r=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(self.uid,)).fetchone()
        if r:
            if len(r[0])!=88:raise ValueError('Invalid saved skill slots size')
            old=struct.unpack('>22i',r[0])
            occupied=[s for s in old if s]
            from els_server.domain.skill_expansion import unlocked_indices
            if len(set(occupied))!=len(occupied) or any(s for i,s in enumerate(old) if i not in unlocked_indices(character)):raise ValueError('Invalid persisted skill layout')
            # Verify persisted IDs against this class/base tree before applying
            # explicit upgrade edges. Corrupt or foreign IDs are never erased.
            from els_server.game_data import client_data
            from els_server.domain.character_rules import CLASSES
            cls=character['unit_class'] if character else 1
            from els_server.domain.role_progression import known_skills
            known=known_skills(cls)
            if any(s and s not in known for s in old):raise ValueError('Unknown persisted skill')
            return decode_slots(struct.pack('>22i',*upgraded_slots(old,character)),equippable_skills(character),character)
        return default_slots(character)
    def skill_character(self):
        with snapshot_connection(self.path) as db:return self._skill_character(db)
    def _skill_character(self,db):
        # All ownership, relation and slot sources share this caller snapshot.
        # The existing read-scope owner rolls it back on exit.
        if not db.in_transaction:db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='characters'").fetchone():return None
        row=db.execute('SELECT unit_class,level,transcendence,master FROM characters WHERE uid=?',(self.uid,)).fetchone()
        if row:
            from els_server.storage.skill_expansion import is_expanded
            from els_server.storage.skill_unlocks import saved_groups
            from els_server.storage.boosting_2026_force_inventory import saved as force_owned
            from els_server.storage.boosting_2026_force_equipment import saved as force_slots
            from els_server.domain.relationship_skills import saved as relationship_saved
            return dict(zip(('unit_class','level','transcendence','master'),row),uid=self.uid,relationship=relationship_saved(db,self.uid),skill_row_expanded=is_expanded(db,self.uid),skill_seal_groups=saved_groups(db,self.uid),force_inventory=force_owned(db,self.uid),force_slots=force_slots(db,self.uid))
        return None
    def _skill_actor(self,db,account_id):
        from els_server.storage.item_actor import require_active_character
        require_active_character(db,self.uid)
        # A supplied account is mandatory at the authenticated network boundary.
        # None retains the pre-existing trusted local/legacy storage API.
        if account_id is not None:
            if type(account_id) is not int or not 0<account_id<2**63:
                raise ValueError('Skill layout account identity')
            if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(self.uid,)).fetchone()!=(account_id,):
                raise ValueError('Skill layout character owner')
        return self._skill_character(db)
    def _save_skills(self,db,slots,character,*,source_slots=None,touched=()):
        from els_server.domain.skill_rules import equippable_skills
        visible_payload=encode_slots(slots,equippable_skills(character),character)
        visible=decode_slots(visible_payload,equippable_skills(character),character)
        if source_slots is None:
            # Validate the existing row in this same writer snapshot before
            # retaining any hidden source; never overwrite corrupt storage.
            LocalState._load_skills(self,db,character)
            row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(self.uid,)).fetchone()
            source_slots=struct.unpack('>22i',row[0])if row else (0,)*22
        from els_server.domain.relationship_skills import persisted_slots
        payload=struct.pack('>22i',*persisted_slots(source_slots,visible,character,touched=touched))
        db.execute('INSERT INTO skill_slots VALUES (?, ?,1) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload, revision=revision+1 WHERE payload<>excluded.payload',(self.uid,payload,))
        return visible
    def save_skills(self,slots,*,account_id=None):
        with self.connect() as db,write_transaction(db):
            character=self._skill_actor(db,account_id)
            return self._save_skills(db,slots,character)
    def equip_skill(self,payload,*,account_id=None):
        from els_server.domain.skill_rules import equippable_skills
        from els_server.domain.skill_state import equip_request
        with self.connect() as db,write_transaction(db):
            character=self._skill_actor(db,account_id)
            slots,ack=equip_request(payload,self._load_skills(db,character),equippable_skills(character),character)
            return self._save_skills(db,slots,character,touched=(struct.unpack_from('>i',payload)[0],)),ack
    def save_bindings(self,payload):
        payload=validate_bindings(payload)
        with self.connect() as db:
            db.execute('INSERT INTO key_bindings VALUES (?, ?,1) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload, revision=revision+1 WHERE payload<>excluded.payload',(self.uid,payload,))
        return self.load_bindings()
    def save_layout(self,values):
        payload=encode_layout(values)
        with self.connect() as db:
            db.execute('INSERT INTO ui_layout VALUES (?, ?,1) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload, revision=revision+1 WHERE payload<>excluded.payload',(self.uid,payload,))
        return self.load_layout()
    def save(self,map_id,board,progress,xyz):
        validate_location(map_id,board,progress,xyz)
        values=(map_id,board,progress,*xyz)
        with self.connect() as db:
            old=db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(self.uid,)).fetchone()
            if old!=values:
                # Exact committed no-ops need no writer reservation. Changed
                # locations still acquire the original writer and re-read.
                with write_transaction(db):
                    old=db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(self.uid,)).fetchone()
                    if old!=values:db.execute('UPDATE location SET town=?,board=?,progress=?,x=?,y=?,z=?,revision=revision+1 WHERE uid=?',(*values,self.uid))
        return self.load()

from els_server.storage.read_scope import snapshot_connection
