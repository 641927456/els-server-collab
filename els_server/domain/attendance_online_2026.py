"""Independent composition of the existing518 and online-title providers.

No growth, resonance, equipment, pet or nested reward registrars are loaded.
The original providers retain economic decisions and durable receipts.
"""
import struct,weakref,sqlite3
from contextlib import closing
from pathlib import Path
import logging
from els_server.domain.attendance_2026_award_flow import retryable_sqlite_lock
from els_server.domain.attendance_2026_online import selected_local_test_character
from els_server.protocol import attendance_2026_quest as quest_wire
from els_server.protocol.protocol_codec import encode_event

ENROLLMENT_POLICY='selected518-server-task-bootstrap-compatibility-v1' 
from els_server.domain.attendance_2026_campaign import AttendanceCampaign
from els_server.domain.growth_attendance_2026_campaign import reward_rows
from els_server.protocol import activity_2026_entries as entries


class PairClocks:
    def __init__(self,attendance,title):self.attendance,self.title=attendance,title;self.session_ref=None

    def observe(self,s,*,stop=False):
        self.session_ref=None if stop else weakref.ref(s)
        errors=[]
        for clock in (self.attendance,self.title):
            try:clock.observe(s,stop=stop)
            except BaseException as error:errors.append(error)
        if errors:raise errors[0]


class AttendanceOnlineCampaign(AttendanceCampaign):
    def __init__(self,*args,online_title,available,**options):
        super().__init__(*args,**options)
        self.title,self.available=online_title,available
        attendance_clock=self.online;original=attendance_clock.eligibility
        attendance_clock.eligibility=lambda s:original(s) if available(s,self.clock()) else None
        self.online=PairClocks(attendance_clock,online_title)
        self.purchase_available=available
        self.last_entries=None;self.learned_entries={}

    def capture(self,s):
        if self.available(s,self.clock()):super().capture(s)

    def prepare_clear(self,s):
        return super().prepare_clear(s) if self.available(s,self.clock()) else None

    def handle(self,s,event,sequence):
        if not self.enabled(s):return None
        is_quest=(event.event_id==0x202 and event.kind in (0xee,0xf4) and len(event.payload)>=4
                  and struct.unpack_from('>i',event.payload)[0]==166210)
        if not self.available(s,self.clock()) and is_quest:
            from els_server.protocol import quest_messages as ordinary
            if event.kind==0xee:return [ordinary.accept_ack(-1)]
            inv=s.account.get_inventory_snapshot()
            return [ordinary.reward_ack(166210,s.account.character(),s.account.get_location(),s.account.get_skills(),inv['balances'],inv['items'],result=2005)]
        return super().handle(s,event,sequence)

    def _task_enrollment_needed(self,s,db,t,now):
        """Read the same owner/config/task/day gates before and under writer."""
        t._owner(s.account.account_id,s.account.uid);t._configuration();t._validate_binding()
        if t._read(s.account.account_id) is not None:return False
        period=self.schedule.period_at(now)
        day=next(p.index for p in self.schedule.periods if p.key==period)
        return not db.execute('SELECT 1 FROM activity518_stamps WHERE campaign=? AND account=? AND day_index=?',
            (self.campaign,s.account.account_id,day)).fetchone()

    def _ensure_task(self,s):
        # Existing tasks/stamps need no writer; newly eligible enrollment still
        # repeats every source/owner check in its original atomic transaction.
        if s.phase not in ('map_loading','square_accepted','town_ready'):return None
        now=self.clock()
        if not self.available(s,now):return None
        identity=selected_local_test_character(s)
        if identity is None:return None
        try:
            path=Path(s.account.store.path).resolve()
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
                db.execute('BEGIN')
                if not self._task_enrollment_needed(s,db,self._store(db),now):return None
            with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,db:
                db.execute('BEGIN IMMEDIATE');t=self._store(db)
                if not self._task_enrollment_needed(s,db,t,now):return None
                row=t.accept(account=s.account.account_id,character=s.account.uid,now=now)
                message=quest_wire.accepted(**self.view(row,owner_uid=s.account.uid));encode_event(message)
                if selected_local_test_character(s)!=identity:raise ValueError('Attendance enrollment owner changed')
            return message
        except sqlite3.OperationalError as error:
            if not retryable_sqlite_lock(error):raise
            logging.getLogger(__name__).warning('Automatic attendance enrollment deferred by SQLite lock',exc_info=True)
            return None

    def _register_task(self,s):
        # Initial2B alone did not populate the original518 task panel in V124.
        # Send the existing original F0 record once after the native town-ready
        # transition, without accepting again or changing objective counters.
        if s.phase!='town_ready' or not self.available(s,self.clock()):return []
        if selected_local_test_character(s) is None:return []
        task,_,_=self._projection(s)
        if task is None:return []
        signature=(id(s),s.account.uid,task['accepted_at'])
        if getattr(self,'_registered_task',None)==signature:return []
        message=quest_wire.accepted(**self.view(task,owner_uid=s.account.uid))
        encode_event(message)
        self._registered_task=signature
        return [message]

    def finalize(self,s,replies):
        if (not self.enabled(s) or getattr(s,'reward_transaction',None) is not None):return replies
        restoring=any(e.event_id==0x201 and e.kind in (0x2a,0x2b) for e in replies)
        if s.phase not in ('town_ready','dungeon_active') and not restoring:return replies
        # The original attendance provider expects a single authoritative4B6.
        # Retain other producers' rows with the existing strict decoder.
        rewards={};prior_entries=dict(self.learned_entries);retained=[];had_entries=False
        for e in replies:
            if e.event_id==0x201 and e.kind==0x4b6:
                for rid,row in reward_rows(e.payload).items():
                    if rid in rewards and rewards[rid]!=row:raise ValueError('Conflicting reward provider')
                    rewards[rid]=row
            elif e.event_id==0x201 and e.kind==0x4b9:
                had_entries=True
                for code,row in entries.read(e.payload).items():
                    if code==518:continue
                    if code in prior_entries and prior_entries[code]!=row:raise ValueError('Conflicting activity provider')
                    prior_entries[code]=row
            else:retained.append(e)
        if self.available(s,self.clock()):
            accepted=self._ensure_task(s)
            retained=super().finalize(s,retained)
            retained+=self._register_task(s)
        table=next((e for e in retained if e.event_id==0x201 and e.kind==0x4b6),None)
        if table is not None or rewards:
            retained=[e for e in retained if not(e.event_id==0x201 and e.kind==0x4b6)]
            retained.insert(0,self.catalog.notice(existing=rewards))
        c=s.account.character();level=0 if c is None else c['level']
        active=self.available(s,self.clock()) and level>=10
        prior_entries[518]=entries.CodeEntry(active,self.schedule.available_from,self.schedule.available_until)
        notice=entries.notice(prior_entries);signature=(s.account.uid,notice.payload)
        initial=any(e.event_id==0x201 and e.kind==0x2a for e in replies)
        if initial or had_entries or signature!=self.last_entries:retained.append(notice)
        self.last_entries=signature;self.learned_entries={k:v for k,v in prior_entries.items() if k!=518}
        return retained

    def after_reply(self,s,replies):
        self.title.outgoing(replies);extra=self.title.notifications(s)
        if any(e.event_id==0x201 and e.kind==0x1ce for e in extra):
            replies=[e for e in replies if not(e.event_id==0x201 and e.kind==0x1ce)]
        return list(replies)+extra
