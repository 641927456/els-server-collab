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
    # Tutorial sources keep their original spawn-seed level.
    # Ordinary route level/HP capabilities do not apply to tutorial graphs.
    return SimpleNamespace(_data=data,static_npc_level=lambda identity,graph,stage,part,source:None)

class TutorialRun(DungeonRun):
    def __init__(self,identity):
        self.catalog=catalog();data=self.catalog._data
        self.graph=json.loads(json.dumps(data['graphs'][data['maps'][str(identity)]['source']]))
        self.identity=identity;self.run_id=str(uuid.uuid4());self.clock=time.monotonic
        self.hp_context=None # Preserve the existing tutorial HP policy.
        self.stage=0;self.part=0;self.encounter=None;self.completed_stages=set();self.visits=0
        self.round=0;self.rotation=[];self.dynamic_requests={};self.completed_transition=None
        self.defeated={};self.parts={};self.stage_wires={};self.next=None;self.ready_at=None
        self.started_at=None;self.portal_requested=False
        self._load_stage(0)
