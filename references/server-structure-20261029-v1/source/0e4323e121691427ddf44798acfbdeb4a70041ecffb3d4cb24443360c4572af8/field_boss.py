"""Roster-bound Drabaki battlefield, separate from ordinary dungeon admission.

Combat reports are authenticated master reports, as in friends dungeons;
this prototype does not simulate damage or retail ranking rewards.
"""
import functools,hashlib,json,math,sqlite3,struct,time,uuid
from contextlib import closing
from dataclasses import dataclass,field
from pathlib import Path
from types import SimpleNamespace
from els_server.game_data import CLIENT_SHA
from els_server.protocol import field_boss_messages as wire
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32


@functools.lru_cache(maxsize=1)
def definition():
    directory=Path(__file__).resolve().parents[1]/'data'
    raw=(directory/'drabaki_field.json').read_bytes()
    manifest=json.loads((directory/'drabaki_field.manifest.json').read_text())
    if manifest['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']:
        raise ValueError('Drabaki field data identity')
    data=json.loads(raw)
    if (data['client_sha256']!=CLIENT_SHA or data['source']['BATTLE_FIELD_ID']!=wire.FIELD
        or data['source']['WORLD_ID']!=804 or data['source']['MAX_JOIN_USER_COUNT']!=8):
        raise ValueError('Drabaki source bounds')
    return data


def population():
    from els_server.domain.dungeon_npcs import resource_dto,encode_npc
    from els_server.domain.dungeon_routes import route_catalog,npc_initialization
    data=definition();base=route_catalog()._data
    catalog=SimpleNamespace(_data=dict(base,npcs=data['npcs']),_formal_field_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'data/drabaki_field.json').read_bytes()).hexdigest())
    entries=[]
    for key,group in enumerate(data['groups']):
        template=group['template'];point=data['positions'][str(group['point'])]
        raw=bytearray.fromhex(base['spawn_seed'])
        struct.pack_into('<iii',raw,0,key,template,0)
        struct.pack_into('<i',raw,0x28,group['point'])
        struct.pack_into('<3f',raw,0x30,0.,0.,0.)
        raw[0xc]=data['source']['STANDARD_MONSTER_LEVEL']
        raw[0x2c]=int(template==6401);raw[0x2d]=int(template==6401)
        raw[0x3c]=1;raw[0x48]=int(point['right']);raw[0x50]=0
        raw[0x44]=int(template==6401);struct.pack_into('<H',raw,0x58,99 if template==6401 else 0)
        dto=bytearray(resource_dto(raw));struct.pack_into('<3f',dto,9,*point['xyz'])
        from els_server.domain.formal_npc_hp import maximum
        hp=maximum(catalog,template,dungeon=wire.FIELD,npc_level=data['source']['STANDARD_MONSTER_LEVEL'],boss=template==6401)
        entries.append(dict(key=key,template=template,hp=hp,wire=encode_npc(dto,0),init=npc_initialization(catalog,template,hp,field_context=(wire.FIELD,data['source']['STANDARD_MONSTER_LEVEL']))))
    payload=struct.pack('>I',len(entries))+b''.join(n['wire'] for n in entries)
    # C50040: empty map<int,int>, scalar, byte vector, then the
    # map<int,2BDEB50 NPC initialization> and two empty ushort maps.
    payload+=bytes(12)+struct.pack('>I',len(entries))+b''.join(i32(n['key'])+n['init'] for n in entries)+bytes(8)
    return entries,Event(0x201,kind=0x3d6,payload=payload)


@dataclass(eq=False)
class FieldRoom:
    members:tuple
    leader:object
    seed:str
    identity:int=wire.FIELD
    phase:str='loading'
    deadline:int=0
    loading_deadline:float=0
    progress:dict=field(default_factory=dict)
    loaded:set=field(default_factory=set)
    defeated:dict=field(default_factory=dict)
    entries:list=field(default_factory=list)
    spawn:object=None


class FieldBosses:
    def __init__(self,world):self.world=world;self.rooms={}
    def room(self,s):return self.rooms.get(s)
    def send(self,r,event):
        for m in r.members:
            if self.room(m) is r:self.world.send(m,event)

    def abort(self,r,reason,leaving=None):
        r.phase='failed'
        self.send(r,wire.clock(int(time.time())))
        self.send(r,wire.ended())
        # A failed/abandoned field can always return without a reward.
        for m in r.members:
            if self.room(m) is r:m.field_result=reason

    def detach(self,s):
        r=self.room(s)
        if r is None:return
        aborting=r.phase not in ('clear','failed')
        try:
            if aborting:self.abort(r,'member disconnected',s)
        finally:
            # Only disconnect cleanup: a failed notice must not strand the
            # departing actor or prevent surviving members returning safely.
            if aborting and r.phase=='failed':
                for member in r.members:
                    if self.room(member) is r:member.field_result='member disconnected'
            self.rooms.pop(s,None)
            party=self.world.party_of.get(s)
            if party:party['ready'].clear()

    def periodic(self,s):
        r=self.room(s)
        if r is None or r.leader is not s:return
        if (r.phase in ('loading','ready') and time.monotonic()>=r.loading_deadline
            or r.phase=='active' and time.time()>=r.deadline):self.abort(r,'timeout')

    def request(self,s,event):
        if event.event_id!=0x202:return None
        r=self.room(s);kind=event.kind
        if kind==0x374:
            try:
                request=wire.join_request(event.payload)
                if r is not None:
                    if request['members'] and set(request['members'])!={m.account.uid for m in r.members}:raise ValueError('Field roster changed')
                    return [wire.joined(r.members,r.leader,uuid.UUID(r.seed).int%(2**63),deadline=r.deadline)]
                if not s.application.config.friends_coop_enabled:raise ValueError('Cooperation disabled')
                from els_server.domain.gm_events import require_open
                require_open(wire.FIELD)
                party=self.world.party_of.get(s)
                if party and (party['leader'] is not s or party['run'] is not None or party.get('challenge') or party.get('challenge_pending') or party.get('solo_challenge')):
                    raise ValueError('Field party state')
                members=tuple(party['members']) if party else (s,)
                if not 1<=len(members)<=definition()['local_policy']['max_players']:raise ValueError('Field capacity')
                if request['members'] and set(request['members'])!={m.account.uid for m in members}:raise ValueError('Field participant vector')
                from els_server.domain.region_quests import account_dungeon_allowed
                if len({Path(m.account.store.path).resolve() for m in members})!=1:raise ValueError('Field database')
                if not all(m.role=='game' and m.phase=='town_ready' and m in self.world.members and not m.released
                    and m.population_test and m.reward_test and m.item_test and self.room(m) is None
                    and (m is s or m in party['ready']) and account_dungeon_allowed(m.account,34310) for m in members):
                    raise ValueError('Field participant state')
                r=FieldRoom(members,s,str(uuid.uuid4()),loading_deadline=time.monotonic()+60)
                r.entries,r.spawn=population()
                packet=wire.joined(members,s,uuid.UUID(r.seed).int%(2**63))
                for m in members:
                    self.rooms[m]=r;self.world.leave(m)
                    m.phase='field_active';m.active_map=wire.FIELD;m.dungeon_run=None
                    m.clear_notified=False;m.clear_items_synced=False;m.reward_receipt=None
                    m.reward_run_id=str(uuid.uuid5(uuid.UUID(r.seed),str(m.account.uid)))
                    m.field_result=None
                    self.world.send(m,packet)
                return []
            except (ValueError,AttributeError):
                return [wire.joined((),None,0,result=-1)]
        if r is None:return None
        self.periodic(s)
        if kind==0x91:
            if len(event.payload)!=8:return []
            progress,mode=struct.unpack('>ii',event.payload)
            if not 0<=progress<=100 or mode!=0:return []
            r.progress[s]=max(progress,r.progress.get(s,0))
            self.send(r,Event(0x201,kind=0x93,payload=struct.pack('>Qi',s.account.uid,progress)))
            return [Event(0x201,kind=0x92,payload=struct.pack('>iiI',0,progress,0))]
        if kind==0x37a:
            if event.payload or r.progress.get(s,0)<100 or r.phase not in ('loading','ready','active'):return [wire.ack(0x37b,-1)]
            r.loaded.add(s)
            if len(r.loaded)==len(r.members) and r.phase=='loading':
                r.phase='ready';r.loading_deadline=time.monotonic()+60
                self.send(r,r.spawn)
            return [wire.ack(0x37b)]
        if kind==0x535:
            if len(event.payload)!=4 or not math.isfinite(struct.unpack('>f',event.payload)[0]):return []
            return [wire.schedule(r.deadline or int(time.time())+definition()['local_policy']['time_limit_seconds'])]
        if kind==0x530:
            if event.payload or s is not r.leader or r.phase not in ('ready','active'):return [wire.started(0,-1)]
            if r.phase=='ready':
                r.deadline=int(time.time())+definition()['local_policy']['time_limit_seconds'];r.phase='active'
            return [wire.started(r.deadline)]
        if kind==0x53a:
            if len(event.payload)!=8 or s is not r.leader or r.phase!='active':return []
            # Client clock echoes never move the authoritative deadline.
            self.send(r,wire.clock(r.deadline));return []
        if kind==0x53e:
            return [Event(0x201,kind=0x53f,payload=b'')] if not event.payload and r.phase=='active' else []
        if kind==0x77a:
            try:
                uids=wire.metrics_request(event.payload)
                valid=r.phase in ('active','clear') and uids<={m.account.uid for m in r.members}
            except ValueError:valid=False
            return [wire.ack(0x77b,0 if valid else -1)]
        if kind==0xad:return self.death(r,s,event)
        if kind==0x225:
            if event.payload!=i32(s.account.get_location()['map'])+b'\0':return []
            return self.leave(s)
        if kind==0x67:
            if not 100<=len(event.payload)<=8192 or event.payload[:4]!=i32(0x72):return []
            self.leave(s,enter_town=False)
            from els_server.protocol.dungeon_messages import end_ack
            return [end_ack(),s.saved_user_sync(clear_reward_only=s.clear_notified)]
        # Field reports cannot fall through to dungeon/quest/party mutations.
        if kind in (0x7d4,0x382,0xae2,0xae5,0xae7,0xaea,0xb3,0xbb,0x2ce,0x378):return []
        return None

    def leave(self,s,*,enter_town=True):
        r=self.room(s)
        if r.phase not in ('clear','failed'):self.abort(r,'abandoned')
        self.rooms.pop(s,None);s.phase='map_loading';s.pending_map=None
        s.dungeon_return_pending=True;s.inventory_town_sync_sent=False
        # Reuse the existing town state machine on the next 225 request.
        return s.handle(Event(0x202,kind=0x225,payload=i32(s.account.get_location()['map'])+b'\0')) if enter_town else []

    def death(self,r,s,event):
        from els_server.domain.dungeon_lifecycle import death_report,death_ack,empty_reward_death_notice
        try:d=death_report(event.payload)
        except ValueError:return []
        if s is not r.leader or event.performers!=(0,) or r.phase not in ('active','clear'):return []
        npc=next((n for n in r.entries if n['key']==d['index']),None)
        participants={m.account.uid for m in r.members};hp=struct.unpack('>f',struct.pack('>I',d['hp_bits']))[0]
        if (npc is None or d['flag'] not in (0,1) or any(d[k] not in participants for k in ('source','killer','last_uid'))
            or any(uid not in participants for k in ('contribution','readiness','counters') for uid in d[k])
            or not math.isfinite(hp) or hp<=0):return []
        old=r.defeated.get(npc['key'])
        if old is not None:return [death_ack()] if old==event.payload else []
        if r.phase=='clear':return []
        if npc['template']==6401:self.settle(r,event.payload)
        r.defeated[npc['key']]=event.payload
        self.send(r,empty_reward_death_notice(npc['key'],d['killer']))
        return [death_ack()]

    def settle(self,r,death):
        from els_server.domain.dungeon_flow import local_rewards
        from els_server.protocol.local_messages import client_economy_fields
        rule=local_rewards();receipts=[]
        path=r.leader.account.store.path
        with closing(sqlite3.connect(path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            for m in r.members:
                from els_server.domain.gm_rates import clear_experience
                experience=clear_experience(m,rule['clear_experience'])
                # Native completion status, stored only for idempotency.
                # Battlefield UI has no ordinary dungeon C1 result screen.
                def encode(balances):client_economy_fields(balances);return wire.ack(0x77b).payload
                proof=b'drabaki-field-40046-v1'+struct.pack('>Q',m.account.uid)+uuid.UUID(r.seed).bytes+hashlib.sha256(death).digest()
                receipt=m.account.reward_store.grant(m.reward_run_id,proof,rule['clear_ed'],experience,encode,item_plan=rule['items'] or None,transaction=db)
                receipts.append((m,receipt))
        r.phase='clear'
        for m,receipt in receipts:
            m.reward_receipt={'run_id':m.reward_run_id,**receipt};m.clear_notified=True;m.field_result='clear'
            self.world.send(m,m.saved_user_sync(clear_reward_only=True));m.clear_items_synced=True
