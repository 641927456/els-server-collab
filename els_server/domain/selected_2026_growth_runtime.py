"""Native selected678 extension over the delivered attendance/online manager.

Keeps the original pair binding, flags, clocks and reward identities. Growth
has its own immutable calendar/resource binding and one activation receipt.
No retired clear/ground XP writer, client UI, timer or formula is installed.
"""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3
from els_server.domain.selected_2026_pair_runtime import SelectedAttendanceOnline
from els_server.domain.activity_2026_rewards import ActivityRewards
from els_server.domain.boosting_2026_join_flow import BoostingJoinFlow
from els_server.domain.boosting_2026_chain import ChainGrowthBinding
from els_server.storage.resonance_2026_profiles import NEW_PROFILE_POLICY
from els_server.domain.resonance_allocation_flow import definitions
from els_server.storage.activity_2026_settings import canonical
from els_server.protocol import activity_2026_entries as entries
from els_server.domain.growth_attendance_2026_campaign import reward_rows

ACTIVATION='c0a14574-c91c-5729-a350-7987432b62a2'
KEYS={'growth','growth_items','growth_chain_items','avatar_policy','avatar_metadata','avatar_definitions','avatar_membership','avatar_registry'}

def extend(pair,pack):
    raw=pack.read_bytes();data=json.loads(raw)
    if set(data)!={'configuration','resources'} or set(data['resources'])!=KEYS:raise ValueError('Growth pack fields')
    configuration=data['configuration']
    if configuration!={'starts':1792375200,'ends':1796004000,'timezone':'Asia/Shanghai','purpose':'explicit_local_test','user_answer':'按签到同期开启（推荐）'}:
        raise ValueError('User-authorized growth reproduction calendar changed')
    resources={}
    for key,row in data['resources'].items():
        if set(row)!={'file','sha256'}:raise ValueError('Growth resource identity')
        p=(pack.parent/row['file']).resolve()
        if not p.is_relative_to(pack.parent.resolve()):raise ValueError('Growth resource escaped pack')
        value=p.read_bytes()
        if hashlib.sha256(value).hexdigest()!=row['sha256']:raise ValueError('Growth resource changed')
        resources[key]=value
    return SelectedGrowth(pair.path,pair.config,pair.resources,growth_configuration=configuration,growth_resources=resources)

class SelectedGrowth(SelectedAttendanceOnline):
    supports_growth=True

    def __init__(self,*args,growth_configuration,growth_resources,**kwargs):
        super().__init__(*args,**kwargs)
        self.growth_configuration=dict(growth_configuration);self.growth_resources=dict(growth_resources)
        self.growth_binding=canonical(dict(policy='selected678-canonical-native-extension-v1',calendar=self.growth_configuration,
            resources={k:hashlib.sha256(v).hexdigest()for k,v in sorted(self.growth_resources.items())}))
        self.growth_catalog=ActivityRewards(self.resources['rewards'])
        self.curve,self.stats=definitions()
        self._growth(lambda s,t:False) # Validate pinned original catalogs before listeners.

    def _growth(self,opened):
        r=self.growth_resources
        return ChainGrowthBinding(r['growth'],clock=self.clock,campaign_open=opened,
            catalogs={k:r['avatar_'+k]for k in ('policy','metadata','definitions','membership','registry')},curve=self.curve,stats=self.stats)

    def _joined(self,db):
        from els_server.storage.boosting_2026_complete_join import CompleteJoinedParticipation
        return CompleteJoinedParticipation(db,self.growth_resources['growth'],self.curve,self.growth_catalog,self.stats,new_profile_policy=NEW_PROFILE_POLICY)

    def install(self):
        super().install()
        # Pair clocks/schedules/reward ledgers are unchanged. New binding cannot
        # overwrite an existing growth calendar or reward history.
        with closing(sqlite3.connect(self.path,timeout=10))as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS selected2026_growth_binding(
                id INTEGER PRIMARY KEY CHECK(id=1),binding_json TEXT NOT NULL,binding_sha256 TEXT NOT NULL)''')
            value=(self.growth_binding,hashlib.sha256(self.growth_binding.encode()).hexdigest())
            old=db.execute('SELECT binding_json,binding_sha256 FROM selected2026_growth_binding WHERE id=1').fetchone()
            if old is not None and old!=value:raise ValueError('Saved growth calendar/resources differ')
            db.execute('INSERT OR IGNORE INTO selected2026_growth_binding VALUES (1,?,?)',value)
            self._joined(db).initialize()
            from els_server.storage.boosting_2026_first_rewards import FirstRewards
            FirstRewards(db,self.growth_resources['growth']).initialize()
        from els_server.domain.boosting_2026_participation_gear import register as register_gear
        from els_server.domain.boosting_2026_fashion_rewards import register as register_fashion
        register_gear();register_fashion()
        from els_server.domain.boosting_2026_nested_capacity import register as register_capacity
        register_capacity()
        from els_server.domain.boosting_2026_title_rewards import register as register_title_rewards
        register_title_rewards()
        from els_server.domain.boosting_2026_force_extraction import register as register_extraction
        register_extraction()
        from els_server.domain.boosting_2026_limited_pet import enable as enable_limited_pet
        enable_limited_pet()
        from els_server.domain.boosting_2026_accessories import register as register_accessories
        register_accessories()
        self.growth_catalog.register_inventory()
        from els_server.domain.boosting_2026_reward_items import register_verified
        from els_server.domain.boosting_2026_chain_items import register_verified as register_chain
        register_verified(self.growth_resources['growth_items']);register_chain(self.growth_resources['growth_chain_items'])
        with closing(sqlite3.connect(self.path))as db:
            activated=db.execute('SELECT 1 FROM selected2026_settings_operations WHERE operation_id=?',(ACTIVATION,)).fetchone()
        if activated is None:
            current=self.settings.snapshot()
            flags=dict(current['enabled'],growth=True)
            if current['revision']==0 and getattr(self,'_friends_initial_pair',False):flags.update(attendance=True,online=True)
            self.settings.update(dict(operation_id=ACTIVATION,expected_revision=current['revision'],
                reason='用户授权接通成长链路，并沿用签到同期的本地复刻排期',enabled=flags))
        self.state=self.settings.snapshot()

    def __call__(self,account):
        pair=super().__call__(account)
        # Only the wrapper belongs to the manager's clock/GM session set.
        self.flows.discard(pair)
        g=self.growth_configuration
        opened=lambda s,t:self.state['enabled']['growth'] and g['starts']<=t<g['ends']
        join=BoostingJoinFlow(self.growth_resources['growth'],self.curve,self.growth_catalog,self.stats,
            clock=self.clock,campaign_open=opened,new_profile_policy=NEW_PROFILE_POLICY)
        flow=GrowthExtensionFlow(pair,join,self._growth(opened),self.growth_catalog,g,opened)
        flow.bootstrap_clock=self.clock;self.flows.add(flow);return flow

    def snapshot(self):
        value=super().snapshot();value['available_scopes']=['attendance','online','growth']
        value['growth_configuration']=dict(self.growth_configuration)
        value['names']['growth']='战斗力助力活动（2026-07-29期复刻）'
        value['reward_summary']['growth']='原生报名与20任务直接奖；共鸣保底共用正式账本。未知723618固定属性及国服影子预设暂缓。'
        return value

class GrowthExtensionFlow:
    def __init__(self,pair,participation,growth,catalog,configuration,opened):
        self.pair,self.participation,self.growth,self.catalog=pair,participation,growth,catalog
        self.online=pair.online;self.configuration=configuration;self.opened=opened;self.last_entries=None

    def capture(self,s):
        self.pair.capture(s)
        if self.opened(s,self.participation.clock()):self.growth.capture(s)

    def observe_avatar_apply(self,db,s,rows,side,operation):
        # Called only for a new committed formal BFC operation, inside its
        # ownership/lease/selection save transaction. A transport replay does
        # not acquire a new task credit or seed an old candidate preset store.
        if not self.opened(s,self.participation.clock()) or not self.growth._participant(db,s):return []
        t=self.growth._store(db);task=t.snapshot(account=s.account.account_id,character=s.account.uid)
        if task is None or task['count'] or t.definition.task(task['id']).condition_kind!=116:return []
        from els_server.storage.avatar_current_equipment_2026 import snapshot_current
        from els_server.domain.avatar_equipped_counts_2026 import count_admitted
        from els_server.domain.avatar_accessory_effects_2026 import project_active_sets
        a=self.growth.avatar
        try:
         _,admitted=snapshot_current(db,owner=s.account.uid,side=side,category77=a['category77'],owner_7bd=False,
             policy=a['policy'],metadata=a['metadata'],now=self.participation.clock())
         equipped=count_admitted(instances=admitted,selected=rows,context2912=0,side=side,
             membership=a['membership'],selector_overrides={},include_flag7=False)
         active,_=project_active_sets(records=rows,context2912=0,side=side,equipped=equipped,definitions=a['definitions'])
        except ValueError:
            # Unknown activity evidence cannot disable an otherwise valid
            # native selection. Keep the task pending without invented credit.
            return []
        if not active:return []
        from els_server.protocol.boosting_2026_quest import progress
        from els_server.protocol.protocol_codec import encode_event
        changed=dict(task,count=1);message=progress(t.definition,changed,owner_uid=s.account.uid);encode_event(message)
        db.execute('UPDATE boosting2026_active_task SET count=1 WHERE account=? AND character=? AND quest=? AND count=0',
            (s.account.account_id,s.account.uid,task['id']))
        db.execute('''CREATE TABLE IF NOT EXISTS boosting2026_avatar_task_receipts(
            operation TEXT PRIMARY KEY,account INTEGER NOT NULL,character INTEGER NOT NULL,
            quest INTEGER NOT NULL,accepted_at INTEGER NOT NULL,selection_sha256 TEXT NOT NULL)''')
        db.execute('INSERT INTO boosting2026_avatar_task_receipts VALUES (?,?,?,?,?,?)',
            (operation,s.account.account_id,s.account.uid,task['id'],task['accepted_at'],hashlib.sha256(canonical(rows).encode()).hexdigest()))
        return [message]

    def prepare_clear(self,s):return self.pair.prepare_clear(s)
    def after_reply(self,s,replies):return self.pair.after_reply(s,replies)

    def handle(self,s,event,sequence):
        if event.event_id==0x202 and event.kind==0xd2a and self.participation.enabled(s):
            if (s.phase not in ('town_ready','dungeon_active') or type(sequence)is not int or not 1<=sequence<2**32
                    or event.performers!=(0,) or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):return []
            try:entries.window_request(event.payload)
            except ValueError:return []
            from els_server.domain.quest_flow import initialization
            out=[initialization(s)]+self.growth.refresh_for_window(s)
            return self.finalize(s,out)+[entries.window_reply()]
        for provider in (self.participation,self.growth,self.pair):
            reply=provider.handle(s,event,sequence)
            if reply is not None:return reply
        return None

    def finalize(self,s,replies):
        if not self.participation.enabled(s) or getattr(s,'reward_transaction',None)is not None:return replies
        restoring=any(e.event_id==0x201 and e.kind in (0x2a,0x2b)for e in replies)
        if s.phase not in ('town_ready','dungeon_active') and not restoring:return replies
        rows={};code_rows={};had_table=had_entries=False
        def collect(events):
            nonlocal had_table,had_entries
            output=[]
            for e in events:
                if e.event_id==0x201 and e.kind==0x4b6:
                    had_table=True
                    for rid,row in reward_rows(e.payload).items():
                        if rid in rows and rows[rid]!=row:raise ValueError('Conflicting growth reward producer')
                        rows[rid]=row
                elif e.event_id==0x201 and e.kind==0x4b9:
                    had_entries=True
                    for code,row in entries.read(e.payload).items():
                        if code!=678:code_rows[code]=row
                else:output.append(e)
            return output
        out=collect(replies)
        # First enrollment follows a successful native join/ready, never a
        # completed clear. Subsequent stages follow only committed F5 rewards.
        self.growth._enroll_next(s)
        for provider in (self.participation,self.growth,self.pair):out=collect(provider.finalize(s,out))
        if had_table or any(e.event_id==0x201 and e.kind==0x2a for e in replies):
            table=self.catalog.notice(existing=rows)
            if len(table.payload)>65536:raise ValueError('Growth reward table bound')
            out.insert(0,table)
        # Eligibility needs only the current owned identity, not bank/force/wardrobe DTOs.
        c=None if s.account.uid is None else s.account.character_identity();level=0 if c is None else c['level'];g=self.configuration
        code_rows[678]=entries.CodeEntry(self.opened(s,self.participation.clock()) and level>=99,g['starts'],g['ends'])
        notice=entries.notice(code_rows);signature=(s.account.uid,notice.payload)
        if restoring or had_entries or signature!=self.last_entries:out.append(notice)
        self.last_entries=signature
        # A window's inner projection and outer session finalizer can meet.
        seen=set();unique=[]
        for e in out:
            key=(e.kind,e.payload)if e.event_id==0x201 and e.kind in (0xd29,0x610,0xba5,0x4b6,0x4b9,0xf0)else None
            if key is not None:
                if key in seen:continue
                seen.add(key)
            unique.append(e)
        return unique
