"""Versioned client definitions, shared by domain services (never player state)."""
import bisect
import functools
import hashlib
import json
import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path

CLIENT_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
DATA_DIR=Path(__file__).parent/'data/client'


class ClientData:
    def __init__(self, directory=DATA_DIR):
        self.directory=Path(directory).resolve()
        self.path=self.directory/'catalog.sqlite3'
        self.manifest=json.loads((self.directory/'manifest.json').read_text(encoding='utf8'))
        with self.path.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        if (self.manifest['schema_version']!=1 or self.manifest['client_sha256']!=CLIENT_SHA
                or checksum!=self.manifest['catalog_sha256']):
            raise ValueError('Client data pack identity/checksum mismatch')
        with self.connect() as db:
            if db.execute('PRAGMA user_version').fetchone()!=(1,):raise ValueError('Client data schema')
            self.experience=tuple(db.execute('SELECT level,needed,total FROM experience WHERE playable=1 ORDER BY level'))
        if len(self.experience)!=99:raise ValueError('Experience coverage')
        self.thresholds=tuple(r[2] for r in self.experience)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:yield db
        finally:db.close()

    @functools.lru_cache(maxsize=8192)
    def _definition(self, table, key, value):
        if (table,key) not in {('units','class_id'),('skills','id'),('dungeons','id')}:
            raise ValueError('Unsupported definition table')
        with self.connect() as db:row=db.execute(f'SELECT definition FROM {table} WHERE {key}=?',(value,)).fetchone()
        if row is None:raise ValueError(f'Unknown {table} identity: {value}')
        return row[0]

    def unit(self, class_id):return json.loads(self._definition('units','class_id',class_id))
    def skill(self, skill_id):return json.loads(self._definition('skills','id',skill_id))
    def dungeon(self, dungeon_id):return json.loads(self._definition('dungeons','id',dungeon_id))

    @functools.lru_cache(maxsize=8192)
    def _item(self, item_id):
        with self.connect() as db:
            row=db.execute('SELECT id,name,flags4,flags8,item_type,metadata,equip_position,record,stats,stat_bonus FROM items WHERE id=?',(item_id,)).fetchone()
        if row is None:raise ValueError(f'Unknown client item: {item_id}')
        return row

    def item(self, item_id):
        result=dict(zip(('id','name','flags4','flags8','item_type','metadata','equip_position','record','stats','stat_bonus'),self._item(item_id)))
        result['stats']=struct.unpack('<7f',result['stats'])
        result['stat_bonus']=tuple(result['stat_bonus'])
        return result

    @functools.lru_cache(maxsize=195)
    def _tree(self, class_id):
        self.unit(class_id)
        with self.connect() as db:
            return tuple(db.execute('SELECT skill_id,master_level FROM skill_tree WHERE class_id=? ORDER BY skill_id',(class_id,)))

    def skill_tree(self, class_id):return self._tree(class_id)

    @functools.lru_cache(maxsize=17)
    def _resource(self, name):
        with self.connect() as db:row=db.execute('SELECT tables_json FROM resources WHERE name=?',(name,)).fetchone()
        if row is None:raise ValueError('Unknown client resource: '+name)
        return row[0]

    def resource(self, name):return json.loads(self._resource(name))

    @functools.cached_property
    def npcs(self):
        from els_server.npc_data import NpcData
        enum_sha=next(r['sha256'] for r in self.manifest['sources'] if r['name']=='Enum.lua')
        return NpcData(self.directory,CLIENT_SHA,enum_sha)

    def npc(self, identity):return self.npcs.npc(identity)

    @functools.cached_property
    def enchanting(self):
        from els_server.enchant_data import EnchantData
        return EnchantData(self.directory)

    def rules(self, resource, function=None):
        with self.connect() as db:
            rows=db.execute('SELECT function,definition FROM rules WHERE resource=? ORDER BY ordinal',(resource,)).fetchall()
        return [json.loads(row) for fn,row in rows if function is None or fn==function]

    def level_for_experience(self, experience):
        if type(experience) is not int or not 0<=experience<=2**63-1:raise ValueError('Experience bound')
        return min(99,bisect.bisect_right(self.thresholds,experience))

    def level_progress(self, experience):
        level=self.level_for_experience(experience)
        floor=self.thresholds[level-1]
        ceiling=self.thresholds[level] if level<99 else floor
        return dict(level=level,total=experience,level_start=floor,next_level=ceiling,
                    current=experience-floor if level<99 else 0,required=ceiling-floor)

    def artifact_curve(self, evolution):
        if type(evolution) is not int or not 1<=evolution<=5:raise ValueError('Artifact evolution')
        return sorted((r for r in self.rules('MasterArtifactExpTable.lua') if r['ARTIFACT_EVOLUTION_STEP']==evolution),key=lambda r:r['ARTIFACT_LEVEL'])

    def resonance_curve(self):
        return sorted(self.rules('ElResonanceEXPTable.lua'),key=lambda r:r['ER_LEVEL'])


@functools.lru_cache(maxsize=1)
def client_data():return ClientData()
