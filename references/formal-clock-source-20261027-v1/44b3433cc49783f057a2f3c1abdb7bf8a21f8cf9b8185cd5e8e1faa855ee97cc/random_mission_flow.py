"""Original loaded barriers and the existing ordinary full-clear writer only."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,struct,time
from els_server.domain import random_mission_rules as rules
from els_server.storage import random_missions as store
from els_server.protocol import random_mission_messages as wire
from els_server.protocol.protocol_codec import encode_event

_SEAL=object()
class _Origin:
    __slots__=('seal','owner','fatigue','policy')
    def __init__(self,s):self.seal=_SEAL;self.owner=s;self.fatigue=s._normal_fatigue_origin;self.policy=rules.policy()['identity']

def bind(s):
    s._random_mission_origin=None
    r=getattr(s,'dungeon_run',None)
    if not rules.enabled()or r is None or rules.route(r.identity,r)is None or not getattr(s,'_normal_fatigue_origin',None):return
    s._random_mission_origin=_Origin(s)

def _origin(s):
    o=getattr(s,'_random_mission_origin',None)
    if o is None:return None
    if type(o)is not _Origin or o.seal is not _SEAL or o.owner is not s or o.fatigue!=getattr(s,'_normal_fatigue_origin',None)or o.policy!=rules.policy()['identity']:raise ValueError('Mission original admission seal')
    run=s.dungeon_run
    if run is None or rules.route(run.identity,run)is None:raise ValueError('Mission admitted source changed')
    from els_server.domain.normal_fatigue_flow import _stage
    native=_stage(s)
    if native is None:raise ValueError('Mission missing original run epoch')
    return native[1]

def _context(s):
    c=_origin(s)
    if c is None:return None
    return dict(owner=s.account.uid,account=s.account.account_id,reward_run=s.reward_run_id,epoch=c['epoch'],dungeon=c['dungeon'],graph_sha256=c['graph_sha256'],stage=c['stage'],part=c['part'],visits=c['visits'],roster=sorted(s.dungeon_participants),policy=rules.policy()['identity'])

def in_loading_writer(db,path,members,event,room,prepare):
    """Called inside the existing all-roster fatigue SQL writer, before encode."""
    if not rules.enabled()or event.kind!=0xb3:return{}
    members=tuple(members);contexts=[_context(s)for s in members]
    if not any(c is not None and c['visits']==2 for c in contexts):return{}
    if not all(c is not None and c['visits']==2 and not s.dungeon_substage_synced for c,s in zip(contexts,members)):raise ValueError('Mission partial second-stage source')
    def guard(writer):
        prepare(writer)
        if [_context(s)for s in members]!=contexts:raise ValueError('Mission source changed in writer')
    rows=store.stage(db,path,contexts,guard)
    notices={s:([wire.assignment(r)]if r['found']else[])for s,r in zip(members,rows)}
    for events in notices.values():
        for e in events:encode_event(e)
    guard(db);return notices

class _ClearPermit:
    __slots__=('seal','session','row','base','bonus','path','members','room','bound','origin')
    def __init__(self,seal,s,row,base,path,members,room,bound):
        if seal is not _SEAL:raise ValueError('Private mission clear source')
        self.seal=seal;self.session=s;self.row=row;self.base=base;self.bonus=base*row['percent']//100;self.path=path;self.members=members;self.room=room;self.bound=bound;self.origin=s._random_mission_origin
    def identity(self):
        return dict(owner=self.row['owner'],reward_run=self.row['reward_run'],context_sha256=self.row['context_sha256'],mission=self.row['mission'],percent=self.row['percent'],buff=self.row['buff'],base_experience=self.base,bonus_experience=self.bonus)
    def validate(self,db):
        from els_server.domain.pve_economy_flow import _guard
        _guard(self.members,self.room,'part_end',self.bound,db);store._writer(db,self.path)
        s=self.session
        if self.seal is not _SEAL or s not in self.members or s._random_mission_origin is not self.origin:raise ValueError('Mission clear generation')
        c=_origin(s);saved=store.saved(db,s.reward_run_id,s.account.uid)
        if saved is not None:
            original=json.loads(saved['context_json'])
            if original['account']!=s.account.account_id or original['roster']!=sorted(s.dungeon_participants):raise ValueError('Mission original account/roster differs')
        if saved is None or(saved['context_sha256'],saved['mission'],saved['percent'],saved['buff'])!=(self.row['context_sha256'],self.row['mission'],self.row['percent'],self.row['buff'])or c is None or(c['epoch'],c['reward_run'],c['dungeon'],c['graph_sha256'])!=(json.loads(saved['context_json'])['epoch'],saved['reward_run'],json.loads(saved['context_json'])['dungeon'],json.loads(saved['context_json'])['graph_sha256']):raise ValueError('Mission original clear assignment')

def prepare_clear(s,db,base,members,room,bound):
    if not rules.enabled()or getattr(s,'_random_mission_origin',None)is None:return None
    from els_server.domain.pve_economy_flow import _guard
    members=tuple(members);_guard(members,room,'part_end',bound,db)
    c=_origin(s);row=store.saved(db,s.reward_run_id,s.account.uid)
    if row is None or not row['found']:return None
    if type(base)is not int or not 0<=base<2**63:raise ValueError('Mission original clear base')
    # Old receipts are never topped up when a previously unmarked source is read.
    old=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(s.reward_run_id,)).fetchone()
    if old is not None and 'random_mission'not in json.loads(old[0]):return None
    permit=_ClearPermit(_SEAL,s,row,base,Path(s.account.store.path).resolve(),members,room,bound);permit.validate(db);return permit

def require_permit(permit,owner,reward_run,base,db=None):
    if type(permit)is not _ClearPermit or permit.seal is not _SEAL or(permit.row['owner'],permit.row['reward_run'],permit.base)!=(owner,reward_run,base):raise ValueError('Typed original mission clear required')
    if db is not None:permit.validate(db)
    return permit

def finish_clear(permit,db):
    if permit is None:return[]
    require_permit(permit,permit.row['owner'],permit.row['reward_run'],permit.base,db);s=permit.session
    saved=db.execute('SELECT proof_sha256,grant_json FROM reward_receipts WHERE run_id=?',(s.reward_run_id,)).fetchone()
    if saved is None or json.loads(saved[1]).get('random_mission')!=permit.identity():raise ValueError('Mission original grant omitted source')
    # Exactly the existing native clear's proof, independently matched to its
    # actual receipt. This is not a client completion report or invented death.
    run=s.dungeon_run;deaths=hashlib.sha256()
    for key,value in sorted(run.defeated.items()):deaths.update(struct.pack('>iI',key,len(value))+value)
    proof=b'local-static-clear-v2'+struct.pack('>Qiii',s.account.uid,run.identity,run.stage,run.part)+bytes.fromhex(run.graph['source_sha256'])+deaths.digest()
    if hashlib.sha256(proof).hexdigest()!=saved[0]:raise ValueError('Mission real clear proof differs')
    row=store.complete(db,permit.path,s.account.uid,s.account.account_id,s.reward_run_id,proof,permit.base,permit.validate)
    if not permit.row['completed']:store.apply_effect(db,permit.path,row,permit.validate)
    from els_server.storage.world_elixirs import _state
    from els_server.domain.elixir_flow import prepare
    events=prepare(s,cold=True)(db,_state(db,s.account.uid,store._clock()),None)
    for e in events:encode_event(e)
    permit.validate(db);return events

def handle(s,event):
    if event.event_id!=0x202 or event.kind!=0x49c:return None
    try:
        mission=wire.request(event.payload)
        from els_server.domain.equipment_chip_flow import reset_authority,current_lease
        reset_authority(s)
        if not current_lease(s)or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0 or s.phase!='dungeon_active':raise ValueError('Mission completion actor/envelope')
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            db.execute('BEGIN');store._actor(db,s.account.uid,s.account.account_id);row=store.saved(db,s.reward_run_id,s.account.uid)
            if row is None or row['mission']!=mission or not row['completed']or not s.clear_notified:raise ValueError('Mission uncommitted completion')
            receipt=db.execute('SELECT proof_sha256 FROM reward_receipts WHERE run_id=?',(s.reward_run_id,)).fetchone()
            if receipt!=(row['clear_sha256'],)or not current_lease(s):raise ValueError('Mission committed source')
        return[wire.completion(0,mission)]
    except(ValueError,sqlite3.Error):return[]

def periodic(s):
    from els_server.domain.elixir_flow import enabled,ready,prepare
    if not rules.enabled()or not enabled(s)or not ready(s):return[]
    tick=time.monotonic()
    if tick<getattr(s,'_mission_poll_after',0.):return[]
    s._mission_poll_after=tick+1.
    try:
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            db.execute('BEGIN');store._actor(db,s.account.uid,s.account.account_id);rows=store.effects(db,s.account.uid)
        signature=tuple((r['template'],r['stacks'],r['start'],r['end'])for r in rows)
        if signature==getattr(s,'_mission_effect_sent',()):return[]
        from els_server.storage.world_elixirs import _state
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            db.execute('BEGIN');store._actor(db,s.account.uid,s.account.account_id);events=prepare(s)(db,_state(db,s.account.uid,store._clock()),None)
            for e in events:encode_event(e)
        s._mission_effect_sent=signature;return events
    except(ValueError,sqlite3.Error):
        # Keep the previous successful signature; a valid source can retry.
        return[]
