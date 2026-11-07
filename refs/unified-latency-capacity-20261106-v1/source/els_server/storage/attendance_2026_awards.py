"""Selected518 task/stamp/account-mail transactions, explicitly injected only.

Official names are mapped by the user-approved local reward catalog. Normal
claims use the claim day's reward, including ready tasks retained over reset.
Purchase takes a trusted server-selected past day; BA8 carries no index. The selected factory explicitly opts into the user-authorized local earliest
missed-past-day policy; this is not asserted as the original retail order. Mail text/cleanup deadline are explicit
local configuration, never asserted to be recovered retail parameters.
"""
import hashlib
import json
import contextlib
import uuid

from els_server.storage.attendance_2026_tasks import AttendanceTasks
from els_server.storage.activity_2026_rewards import RewardDelivery
from els_server.protocol.attendance_2026_messages import AttendanceState
from els_server.storage.reward_state import validate_balances


TASK_CARRY_POLICY = "selected2026-cn-guide-retain-unclaimed-v1"
LOCAL_EARLIEST_PURCHASE = "selected2026-earliest-past-missed-v1"


class AttendanceAwards(AttendanceTasks):
    @contextlib.contextmanager
    def _transaction(self):
        if not self.db.in_transaction:
            with super()._transaction():
                yield
            return
        # A caught purchase failure must not leak changes into caller's commit.
        name='attendance_awards_'+uuid.uuid4().hex
        self.db.execute('SAVEPOINT '+name)
        try:
            if self.db.execute('SELECT definition_sha256 FROM activity518_campaigns WHERE campaign=?',
                (self.progress.campaign,)).fetchone() != (self.progress.digest,):
                raise ValueError('Campaign definition mismatch')
            actual=tuple(self.db.execute('SELECT period,starts,ends FROM activity518_periods WHERE campaign=? ORDER BY starts',
                (self.progress.campaign,)))
            if actual != tuple((p.key,p.starts,p.ends) for p in self.schedule.periods):
                raise ValueError('Task schedule must match the installed campaign')
            yield
            self.db.execute('RELEASE SAVEPOINT '+name)
        except BaseException:
            self.db.execute('ROLLBACK TO SAVEPOINT '+name)
            self.db.execute('RELEASE SAVEPOINT '+name)
            raise

    def __init__(self, progress, schedule, catalog, *, deadline, sender, title, body, purchase_policy=None, task_policy=None):
        super().__init__(progress, schedule)
        if type(deadline) is not int or not schedule.available_until <= deadline < 2**63:
            raise ValueError('Explicit campaign mail cleanup deadline required')
        from els_server.storage.game_mail import _text
        if purchase_policy not in (None, LOCAL_EARLIEST_PURCHASE):
            raise ValueError("Unknown attendance purchase policy")
        if task_policy not in (None,TASK_CARRY_POLICY):
            raise ValueError("Unknown attendance task carry policy")
        self.task_policy = task_policy
        self.purchase_policy = purchase_policy
        self.deadline = deadline
        self.text = dict(sender=_text(sender,24), title=_text(title,80), body=_text(body,2000))
        self.delivery = RewardDelivery(self.db, catalog)
        config = [progress.digest, catalog.digest, schedule.purpose,
                  [(p.index,p.key,p.starts,p.ends) for p in schedule.periods],
                  deadline, self.text]
        self.config_sha = hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

    def _configuration(self):
        row = self.db.execute('SELECT sha256 FROM activity518_award_config WHERE campaign=?',(self.progress.campaign,)).fetchone()
        if row != (self.config_sha,):
            raise ValueError('Attendance award configuration changed')

    def initialize(self):
        super().initialize()
        with self._transaction():
            self.delivery.initialize()
            self.db.execute('CREATE TABLE IF NOT EXISTS activity518_award_config(campaign TEXT PRIMARY KEY,sha256 TEXT NOT NULL)')
            self.db.execute('''CREATE TABLE IF NOT EXISTS activity518_stamps(
                campaign TEXT NOT NULL,account INTEGER NOT NULL,day_index INTEGER NOT NULL,
                kind TEXT NOT NULL,character INTEGER NOT NULL,accepted_period TEXT,
                mail_id INTEGER NOT NULL,claimed_at INTEGER NOT NULL,
                PRIMARY KEY(campaign,account,day_index))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS activity518_award_operations(
                campaign TEXT NOT NULL,account INTEGER NOT NULL,operation TEXT NOT NULL,
                request_json TEXT NOT NULL,day_index INTEGER NOT NULL,response BLOB NOT NULL,
                PRIMARY KEY(campaign,account,operation))''')
            self.db.execute('INSERT OR IGNORE INTO activity518_award_config VALUES (?,?)',(self.progress.campaign,self.config_sha))
            self._configuration()
            if self.purchase_policy is not None:
                # Separate immutable binding: never invalidate/reset old award rows.
                self.db.execute('CREATE TABLE IF NOT EXISTS activity518_purchase_policy(campaign TEXT PRIMARY KEY,policy TEXT NOT NULL,award_sha256 TEXT NOT NULL)')
                self.db.execute('INSERT OR IGNORE INTO activity518_purchase_policy VALUES (?,?,?)',
                    (self.progress.campaign,self.purchase_policy,self.config_sha))
                self._purchase_configuration()
            if self.task_policy is not None:
                self.db.execute('CREATE TABLE IF NOT EXISTS activity518_task_policy(campaign TEXT PRIMARY KEY,policy TEXT NOT NULL,award_sha256 TEXT NOT NULL)')
                self.db.execute('INSERT OR IGNORE INTO activity518_task_policy VALUES (?,?,?)',
                    (self.progress.campaign,self.task_policy,self.config_sha))
                self._task_configuration()

    def _task_configuration(self):
        row=self.db.execute('SELECT policy,award_sha256 FROM activity518_task_policy WHERE campaign=?',
            (self.progress.campaign,)).fetchone()
        if row != (TASK_CARRY_POLICY,self.config_sha):
            raise ValueError('Attendance task carry policy binding changed')

    def _refresh(self, account, now):
        if self.task_policy is None:return super()._refresh(account,now)
        self.delivery._time(now);self._task_configuration()
        state=self._read(account)
        if state is None:return None
        if now < state['accepted_at']:raise ValueError('Task clock precedes acceptance')
        if state['ready']:
            if now<state['ready_at']:raise ValueError('Task clock precedes observed completion')
            return state
        # CN guide resets COMPLETED tasks. Retaining an unclaimed task and its
        # counters is an explicit source-based inference, not a retail trace.
        # Do not delete/reaccept at midnight/10:00 or synthesize daily facts.
        floor=self.db.execute('SELECT fact_floor FROM activity518_tasks WHERE campaign=? AND account=?',
            (self.progress.campaign,account)).fetchone()[0]
        bounds={p.key:(p.starts,p.ends) for p in self.schedule.periods}
        clears=0;spans=[]
        rows=self.db.execute('SELECT period,payload,payload_sha256 FROM activity518_facts WHERE campaign=? AND account=? AND rowid>?',
            (self.progress.campaign,str(account),floor))
        for period,payload,digest in rows:
            if hashlib.sha256(payload.encode()).hexdigest()!=digest:
                raise ValueError('Attendance fact checksum changed')
            fact=json.loads(payload)
            if period not in bounds or fact['period']!=period:
                raise ValueError('Attendance fact period changed')
            a,b=bounds[period]
            if fact['kind']=='dungeon':
                t=fact['occurred_at']
                if type(t) is not int or not a<=t<b:raise ValueError('Invalid attendance dungeon timestamp')
                clears+=bool(fact['qualifies'] and state['accepted_at']<=t<=now)
            elif fact['kind']=='online':
                start,end=fact['starts'],fact['ends']
                if any(type(t) is not int for t in (start,end)) or not a<=start<end<=b:
                    raise ValueError('Invalid attendance online interval')
                start,end=max(state['accepted_at'],start),min(now,end)
                if fact['qualifies'] and start<end:spans.append((start,end))
            else:raise ValueError('Unknown attendance fact kind')
        seconds,last=0,0
        for a,b in sorted(spans):seconds+=max(0,b-max(a,last));last=max(last,b)
        clears,seconds=min(5,clears),min(3600,seconds)
        if clears<state['clears'] or seconds<state['online_seconds']:
            raise ValueError('Task progress or authoritative clock moved backwards')
        ready=clears>=5 or seconds>=3600
        self.db.execute('UPDATE activity518_tasks SET clears=?,seconds=?,ready_at=? WHERE campaign=? AND account=?',
            (clears,seconds,now if ready else None,self.progress.campaign,account))
        return self._read(account)

    def _purchase_configuration(self):
        if self.purchase_policy != LOCAL_EARLIEST_PURCHASE:
            raise ValueError('Explicit local earliest-missed purchase policy required')
        row = self.db.execute('SELECT policy,award_sha256 FROM activity518_purchase_policy WHERE campaign=?',
            (self.progress.campaign,)).fetchone()
        if row != (self.purchase_policy,self.config_sha):
            raise ValueError('Attendance purchase policy binding changed')

    def purchase_next(self, *, account, character, now, operation, encode):
        """User-authorized LOCAL order: earliest unclaimed completed past day.

        Empty BA8 has no date. Select under the SAME writer transaction as the
        debit/stamp/mail/receipt. Replay the old target before selecting anew.
        """
        if not callable(encode) or type(operation) is not str or not 1 <= len(operation) <= 160:
            raise ValueError('Authenticated purchase operation and encoder required')
        self.delivery._time(now)
        with self._transaction():
            self._owner(account,character);self._configuration();self._purchase_configuration()
            old = self.db.execute('SELECT request_json,day_index FROM activity518_award_operations WHERE campaign=? AND account=? AND operation=?',
                (self.progress.campaign,account,operation)).fetchone()
            if old is not None:
                if old[0] != json.dumps(['purchase',character,old[1]],separators=(',',':')):
                    raise ValueError('Operation identity conflicts with prior request')
                target = old[1]
            else:
                current = self._period(now);state = self._attendance(account)
                target = next((p.index for p in sorted(self.schedule.periods,key=lambda p:p.index)
                    if p.index < current.index and p.ends <= now and not state.daily_mask & (1 << p.index)),None)
                if target is None:
                    raise ValueError('Not an available missed attendance day')
            return self.purchase(account=account,character=character,now=now,operation=operation,
                target_index=target,encode=encode)

    def _attendance(self, account):
        self._configuration()
        mask, purchases = 0, 0
        rows = self.db.execute('SELECT day_index,kind FROM activity518_stamps WHERE campaign=? AND account=?',(self.progress.campaign,account))
        for index,kind in rows:
            if type(index) is not int or not 0 <= index < self.progress.definition.days or kind not in ('normal','purchase'):
                raise ValueError('Invalid persisted attendance stamp')
            mask |= 1 << index
            purchases += kind == 'purchase'
        if purchases > self.progress.definition.max_purchases:
            raise ValueError('Persisted attendance purchase limit exceeded')
        return AttendanceState(mask,0,purchases)

    def state(self, *, account, character):
        with self._transaction():
            self._owner(account,character)
            return self._attendance(account)

    def _period(self, now):
        key = self.schedule.period_at(now)
        if key is None:
            raise ValueError('Campaign is unavailable')
        return next(p for p in self.schedule.periods if p.key == key)

    def accept(self, *, account, character, now):
        period = self._period(now)
        with self._transaction():
            self._owner(account,character)
            if self._attendance(account).daily_mask & (1 << period.index):
                raise ValueError('Claim day already occupied')
            old = self._refresh(account,now)
            if old is not None:
                return old
            floor = self.db.execute('SELECT coalesce(max(rowid),0) FROM activity518_facts').fetchone()[0]
            self.db.execute('INSERT INTO activity518_tasks(campaign,account,accepted_period,accepted_at,fact_floor) VALUES (?,?,?,?,?)',
                (self.progress.campaign,account,period.key,now,floor))
            return self._read(account)

    def _request(self, account, character, operation, kind, target):
        if type(operation) is not str or not 1 <= len(operation) <= 160:
            raise ValueError('Authenticated server operation identity required')
        request = json.dumps([kind,character,target],separators=(',',':'))
        old = self.db.execute('SELECT request_json,day_index,response FROM activity518_award_operations WHERE campaign=? AND account=? AND operation=?',
            (self.progress.campaign,account,operation)).fetchone()
        if old is not None and old[0] != request:
            raise ValueError('Operation identity conflicts with prior request')
        return request, old

    def _encode(self, out, encode):
        response = encode(out)
        if type(response) is not bytes or not 1 <= len(response) <= 65536:
            raise ValueError('Valid committed attendance response required')
        return dict(out,response=response)

    def _balances(self, character):
        return validate_balances(self.db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(character,)).fetchone())

    def _replay(self, account, character, old, encode):
        index = old[1]
        stamp = self.db.execute('SELECT mail_id,claimed_at FROM activity518_stamps WHERE campaign=? AND account=? AND day_index=?',
            (self.progress.campaign,account,index)).fetchone()
        if stamp is None:
            raise ValueError('Missing committed attendance stamp')
        # BA9 carries absolute ED and mask. Re-encode current state on a retry;
        # replaying old bytes after another purchase would regress the client.
        out = dict(replayed=True,day_index=index,reward_id=self.progress.definition.daily_reward_ids[index],
                   mail_id=stamp[0],completed_at=stamp[1],attendance=self._attendance(account),balances=self._balances(character))
        return self._encode(out,encode)

    def _award(self, *, account, character, now, operation, request, period, kind, accepted_period, encode):
        rid = self.progress.definition.daily_reward_ids[period.index]
        delivered = self.delivery.attendance_mail(account=account,character=character,reward_id=rid,
            now=now,deadline=self.deadline,qualified=True,**self.text)
        if delivered['replayed']:
            raise ValueError('Existing reward delivery without this attendance stamp')
        self.db.execute('INSERT INTO activity518_stamps VALUES (?,?,?,?,?,?,?,?)',
            (self.progress.campaign,account,period.index,kind,character,accepted_period,delivered['mail_id'],now))
        out = dict(replayed=False,day_index=period.index,reward_id=rid,mail_id=delivered['mail_id'],completed_at=now,
                   attendance=self._attendance(account))
        out['balances'] = self._balances(character)
        out = self._encode(out,encode)
        self.db.execute('INSERT INTO activity518_award_operations VALUES (?,?,?,?,?,?)',
            (self.progress.campaign,account,operation,request,period.index,out['response']))
        return out

    def claim(self, *, account, character, now, operation, encode):
        if not callable(encode):
            raise ValueError('Attendance response encoder required')
        self.delivery._time(now)
        with self._transaction():
            self._owner(account,character)
            self._configuration()
            request,old = self._request(account,character,operation,'normal',None)
            if old is not None:
                return self._replay(account,character,old,encode)
            period = self._period(now)
            task = self._refresh(account,now)
            if task is None or not task['ready']:
                raise ValueError('Daily task requirements not met')
            if self._attendance(account).daily_mask & (1 << period.index):
                raise ValueError('Claim day already occupied')
            self.db.execute('DELETE FROM activity518_tasks WHERE campaign=? AND account=?',(self.progress.campaign,account))
            return self._award(account=account,character=character,now=now,operation=operation,request=request,
                period=period,kind='normal',accepted_period=task['accepted_period'],encode=encode)

    def purchase(self, *, account, character, now, operation, target_index, encode):
        """Trusted server target, never parsed from the empty BA8 client packet.

        All otherwise valid past unclaimed days are supported. Picking among
        them is intentionally left to a separately verified server policy.
        """
        if type(target_index) is not int or not callable(encode):
            raise ValueError('Trusted purchase target and response encoder required')
        self.delivery._time(now)
        with self._transaction():
            self._owner(account,character)
            self._configuration()
            request,old = self._request(account,character,operation,'purchase',target_index)
            if old is not None:
                return self._replay(account,character,old,encode)
            current = self._period(now)
            target = next((p for p in self.schedule.periods if p.index == target_index),None)
            state = self._attendance(account)
            if (target is None or target.index >= current.index or target.ends > now
                    or state.daily_mask & (1 << target.index)
                    or state.purchased_count >= self.progress.definition.max_purchases):
                raise ValueError('Not an available missed attendance day')
            old_balance = self.db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(character,)).fetchone()
            balance = validate_balances(old_balance)
            if balance['ed'] < self.progress.definition.ed_cost or balance['revision'] == 2**63-1:
                raise ValueError('Insufficient ED or invalid balance revision')
            self.db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=?',
                (balance['ed']-self.progress.definition.ed_cost,balance['revision']+1,character))
            return self._award(account=account,character=character,now=now,operation=operation,request=request,
                period=target,kind='purchase',accepted_period=None,encode=encode)
