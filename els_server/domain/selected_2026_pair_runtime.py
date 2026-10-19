"""Default-off local delivery of the selected attendance/online activities.

Growth is unavailable in this delivery. Settings keep their existing three-key
format, but enabling growth is rejected before any write or clock mutation.
Official historical dates and explicit local schedules remain separate.
"""
from contextlib import closing
from datetime import date
from pathlib import Path
import hashlib,json,sqlite3,time,weakref
from els_server.domain.activity_2026_rewards import ActivityRewards
from els_server.domain.attendance_2026 import AttendanceDefinition
from els_server.domain.attendance_2026_schedule import AttendanceSchedule
from els_server.domain.attendance_2026_online import selected_local_test_character
from els_server.domain.attendance_online_2026 import AttendanceOnlineCampaign
from els_server.domain.online_2026_campaign import OnlineTitleCampaign,local_access_record,LOCAL_POLICY
from els_server.domain.online_2026_clock import OnlineTitleClock
from els_server.domain.online_2026_mail_notice import MailNoticePolicy
from els_server.storage.attendance_2026_progress import AttendanceProgress
from els_server.storage.attendance_2026_awards import AttendanceAwards,LOCAL_EARLIEST_PURCHASE,TASK_CARRY_POLICY
from els_server.storage.online_2026_progress import OnlineTitleProgress
from els_server.storage.online_2026_delivery import OnlineTitleDelivery
from els_server.storage.activity_2026_settings import Settings,canonical,request

RESOURCE_KEYS={'attendance','rewards','online_selection','title_link'}
POLICY='selected2026-independent-attendance-online-local-v1'


def from_pack(path,pack_file):
    pack_file=Path(pack_file).resolve();root=pack_file.parent;data=json.loads(pack_file.read_bytes())
    if set(data)!={'configuration','resources'} or set(data['resources'])!=RESOURCE_KEYS:raise ValueError('Independent activity pack fields')
    resources={}
    for key,row in data['resources'].items():
        if type(row) is not dict or set(row)!={'file','sha256'}:raise ValueError('Activity resource identity')
        p=(root/row['file']).resolve()
        if not p.is_relative_to(root):raise ValueError('Activity resource escaped pack')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Activity resource changed')
        resources[key]=raw
    return SelectedAttendanceOnline(path,data['configuration'],resources)


class SelectedAttendanceOnline:
    def __init__(self,path,configuration,resources,*,epoch=time.time,monotonic=time.monotonic):
        if set(resources)!=RESOURCE_KEYS or any(type(v) is not bytes for v in resources.values()):
            raise ValueError('Pinned attendance/online resources required')
        self.path,self.resources=path,dict(resources);self.config=json.loads(canonical(configuration))
        if (set(self.config)!={'policy','purpose','attendance','online'} or self.config['policy']!=POLICY
                or self.config['purpose']!='explicit_local_test'):raise ValueError('Explicit independent local calendar required')
        self.clock=lambda:int(epoch());self.epoch,self.monotonic=epoch,monotonic
        self.definition=AttendanceDefinition.from_original(json.loads(resources['attendance']))
        self.digest=hashlib.sha256(resources['attendance']).hexdigest()
        self.catalog=ActivityRewards(resources['rewards'],scope='attendance')
        a,o=self.config['attendance'],self.config['online']
        if set(a)!={'campaign','first_date','starts','ends','mail'} or set(o)!={'campaign','weeks','mail'}:
            raise ValueError('Independent local calendar fields')
        if a['campaign']!='combined-518' or o['campaign']!='three-online-2026':raise ValueError('Stable reward identities required')
        self.schedule=AttendanceSchedule.build(purpose=self.config['purpose'],first_date=date.fromisoformat(a['first_date']),available_from=a['starts'],available_until=a['ends'])
        if type(o['weeks']) is not list or len(o['weeks'])!=4:raise ValueError('Four explicit online windows required')
        previous=0
        for week,row in enumerate(o['weeks'],1):
            if (type(row) is not list or len(row)!=3 or row[0]!=week or any(type(v) is not int for v in row)
                    or not 0<row[1]<row[2]<=4102444800 or row[1]<previous):raise ValueError('Nonoverlapping weekly windows required')
            previous=row[2]
        for text,end in ((a['mail'],a['ends']),(o['mail'],previous)):
            if type(text) is not dict or set(text)!={'sender','title','body','deadline'}:raise ValueError('Explicit mail policy required')
            if any(type(text[k]) is not str or not 1<=len(text[k])<=200 for k in ('sender','title','body')):raise ValueError('Mail text bounds')
            if type(text['deadline']) is not int or not end<=text['deadline']<2**31:raise ValueError('Mail deadline bounds')
        binding=dict(policy=POLICY,configuration=self.config,resources={k:hashlib.sha256(resources[k]).hexdigest() for k in sorted(resources)})
        self.settings=Settings(path,binding);self.state=None;self.flows=weakref.WeakSet();self.app=None

    def _attendance(self,db):
        a=self.config['attendance']
        return AttendanceAwards(AttendanceProgress(db,self.definition,campaign_id=a['campaign'],definition_sha256=self.digest),self.schedule,self.catalog,purchase_policy=LOCAL_EARLIEST_PURCHASE,task_policy=TASK_CARRY_POLICY,**a['mail'])

    def install(self):
        self.settings.initialize()
        if self.settings.snapshot()['enabled']['growth']:raise ValueError('Unsupported saved growth switch')
        self.catalog.register_inventory()
        # Owned reward usability is independent of campaign enrollment/switches.
        from els_server.domain.published_2026_bundles import enable
        enable((Path(__file__).resolve().parents[1]/'data/published2026-bundles.json').read_bytes())
        from els_server.domain.boosting_2026_force_rewards import register as register_owned_force
        register_owned_force()
        with closing(sqlite3.connect(self.path)) as db:
            t=self._attendance(db);t.progress.initialize();self.schedule.install(t.progress);t.initialize()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');p=OnlineTitleProgress(db,self.resources['online_selection'],campaign=self.config['online']['campaign']);p.initialize()
            for week,start,end in self.config['online']['weeks']:
                p.register_period(week=week,starts=start,ends=end,purpose=self.config['purpose'],provenance='Explicit local schedule, not CN historical maintenance time')
            d=OnlineTitleDelivery(p,self.resources['title_link']);d.initialize()
            d.register_policy(**self.config['online']['mail'],purpose=self.config['purpose'],provenance='Explicit local texts/deadline')
        self.state=self.settings.snapshot()
        if self.state['enabled']['growth']:raise ValueError('Unsupported saved growth switch')

    def attach(self,app):
        if app.config.state_file!=self.path or self.app is not None:raise ValueError('Activity save mismatch or already attached')
        self.app=app;app.activity2026_manager=self

    def __call__(self,account):
        if self.state is None:raise ValueError('Install activities before accepting sessions')
        r=self.resources;a,o=self.config['attendance'],self.config['online']
        timer=OnlineTitleClock(r['online_selection'],campaign=o['campaign'],eligibility=selected_local_test_character,monotonic=self.monotonic,epoch=self.epoch)
        title=OnlineTitleCampaign(timer,title_link=r['title_link'],record=local_access_record(),enabled=lambda s:self.state['enabled']['online'],mail_identity=selected_local_test_character,mail_policy=MailNoticePolicy(False,10),local_policy=LOCAL_POLICY)
        flow=AttendanceOnlineCampaign(self.definition,campaign=a['campaign'],definition_sha256=self.digest,schedule=self.schedule,
            clock=self.clock,catalog=self.catalog,anchor_value=a['starts'],other_reward_rows={},eligibility=selected_local_test_character,
            monotonic=self.monotonic,epoch=self.epoch,purchase_policy=LOCAL_EARLIEST_PURCHASE,task_policy=TASK_CARRY_POLICY,**a['mail'],
            online_title=title,available=lambda s,t:self.state['enabled']['attendance'] and a['starts']<=t<a['ends'])
        flow.bootstrap_clock=self.clock;self.flows.add(flow);return flow

    def snapshot(self):
        if self.state is None:raise ValueError('Selected activities unavailable')
        return dict(json.loads(canonical(self.state)),local_only=True,rules_locked=True,available_scopes=['attendance','online'],configuration=self.config,
            names=dict(growth='战斗力助力活动（候选未安装）',attendance='胡巴的签到（2026-06-17期）',online='2026共存的庆典-称号发放（2026-10-07期）'),
            reward_summary=dict(growth='成长任务链仍未安装，开关禁用；已有723635消耗包可按本期官网开箱。',attendance='42天官网奖励；补签21次/每次7000万ED；最早漏签日自动补（本地规则）',online='每角色/每周累计在线30分钟，邮件称号券723809×1；使用起7日'))

    def update(self,value):
        value=request(value)
        if value['enabled']['growth']:raise ValueError('本次只安装签到和在线活动，成长开关不可启用')
        if self.app is None:raise ValueError('GM requires the owning application worker')
        review=self.settings.review(value)
        if review['revision']!=self.state['revision']:raise ValueError('活动配置被外部改动，请正常重启后读取')
        if review['replayed']:return dict(self.snapshot(),operation_id=review['operation_id'],operation_revision=review['operation_revision'],replayed=True)
        sessions=[s for s in self.app.playing.values() if not getattr(s,'released',False) and getattr(s,'activity2026_awards',None) in self.flows]
        if self.app.config.mode=='local':
            # Local mode has no authenticated friends playing lease. Track
            # only the already observed owned local flow, so GM off/on cannot
            # count an unobserved disabled interval at the next packet.
            for flow in self.flows:
                s=flow.online.session_ref() if flow.online.session_ref is not None else None
                if s is not None and selected_local_test_character(s) is not None and s not in sessions:sessions.append(s)
        for s in sessions:s.activity2026_awards.online.observe(s)
        applied=self.settings.update(value);self.state={k:applied[k] for k in ('revision','enabled','binding_sha256')};errors=[]
        for s in sessions:
            try:s.activity2026_awards.online.observe(s)
            except Exception as e:errors.append(type(e).__name__)
        return dict(self.snapshot(),operation_id=applied['operation_id'],operation_revision=applied['revision'],replayed=False,clock_refresh_errors=errors)
