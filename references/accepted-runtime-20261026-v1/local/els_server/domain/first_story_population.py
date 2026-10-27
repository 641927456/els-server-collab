"""Original tutorial actors/parts, using the existing local NPC stat policy."""
from pathlib import Path
from types import SimpleNamespace
import json,hashlib,functools,uuid,time
from els_server.game_data import DATA_DIR,CLIENT_SHA
from els_server.domain.dungeon_routes import DungeonRun

@functools.lru_cache(maxsize=1)
def catalog():
    path=DATA_DIR/'first_story.json';raw=path.read_bytes()
    manifest=json.loads(path.with_suffix('.manifest.json').read_bytes())
    if hashlib.sha256(raw).hexdigest()!=manifest['sha256']:raise ValueError('Tutorial source identity')
    data=json.loads(raw)
    if data['client_sha256']!=CLIENT_SHA or len(data['maps'])!=15:raise ValueError('Tutorial client/map identity')
    # Current first-story native NPClevel1 supplies the formal initialization policy.
    return _Catalog(data)

class _Catalog:
    def __init__(self,data):self._data=data;self.manifest={'source_sha256':data['sources']}
    def static_npc_level(self,identity,graph,stage,part,source):
        from els_server.domain.formal_npc_hp import level,source_map
        if source_map(self,identity)['graph_sha256']!=graph['source_sha256']:
            raise ValueError('Tutorial HP original graph identity')
        return level(self,identity)
    def graph(self,identity,*,internal=False):
        row=self._data['maps'].get(str(identity))
        if row is None:raise ValueError('Tutorial HP original map')
        return json.loads(json.dumps(self._data['graphs'][row['source']]))

class TutorialRun(DungeonRun):
    def __init__(self,identity):
        self.catalog=catalog();data=self.catalog._data
        self.graph=json.loads(json.dumps(data['graphs'][data['maps'][str(identity)]['source']]))
        self.identity=identity;self.run_id=str(uuid.uuid4());self.clock=time.monotonic
        self.stage=0;self.part=0;self.encounter=None;self.completed_stages=set();self.visits=0
        self.round=0;self.rotation=[];self.dynamic_requests={};self.completed_transition=None
        self.defeated={};self.parts={};self.stage_wires={};self.next=None;self.ready_at=None
        self.started_at=None;self.portal_requested=False
        self.hp_context=None;self.legacy_experience=None;self.secret_clear_policy=None
        self._load_stage(0)
