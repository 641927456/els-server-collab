"""Authenticated loopback RPC; every game mutation runs on Application's worker."""
import asyncio
import copy
from collections import deque
from contextlib import closing
import hashlib
import hmac
import json
import logging
import sqlite3
from threading import Lock
import time
import uuid


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def operation(value):
    key = value.get('operation_id')
    if not isinstance(key,str) or str(uuid.UUID(key)) != key:
        raise ValueError('操作编号无效')
    reason = value.get('reason')
    if not isinstance(reason,str) or not 2 <= len(reason.strip()) <= 200:
        raise ValueError('请输入 2–200 字的操作原因')
    return key


def prepare_mailbox(session, events):
    # GM grants retain the actor/mailbox scope through SQL and adoption.
    from els_server.protocol.protocol_codec import encode_event
    box = copy.copy(session.mailbox)
    box.messages = deque(session.mailbox.messages)
    box.moves = dict(session.mailbox.moves)
    for event in events:
        encode_event(event)
        box._append(event,None)
    return box


def publish_mailboxes(boxes):
    wakes = []
    for session, box in boxes:
        if not session.mailbox.messages and box.messages and box.on_pending is not None:
            wakes.append(box.on_pending)
        session.mailbox = box
    for wake in wakes:
        wake(False)


def _player_identities(sources):
    from els_server.domain.local_session import LocalAccount
    from els_server.storage.characters import public_identity_views
    pending=[];identities={}
    for s in sources:
        account=s.account
        if(type(account)is LocalAccount and account.characters is not None
            and getattr(account.character_identity,'__func__',None)is LocalAccount.character_identity
            and getattr(account._character_identity_projection,'__func__',None)is LocalAccount._character_identity_projection):
            pending.append(s)
        else:identities[s]=account.character_identity()
    values=public_identity_views((s.account.characters,s.account.uid)for s in pending)
    identities.update(zip(pending,values))
    return identities


def _player_balances(sources):
    from collections import defaultdict
    from pathlib import Path
    from els_server.domain.local_session import LocalAccount
    from els_server.storage.reward_state import RewardState,validate_balances
    from els_server.storage.initialization_checks import REWARD
    from els_server.storage.read_scope import snapshot_connection
    groups=defaultdict(list);balances={}
    for s in sources:
        account=s.account;store=getattr(account,'reward_store',None)
        if(type(account)is LocalAccount and type(store)is RewardState
            and getattr(account.get_reward_balances,'__func__',None)is LocalAccount.get_reward_balances
            and getattr(account.enable_rewards,'__func__',None)is LocalAccount.enable_rewards
            and getattr(store.balances,'__func__',None)is RewardState.balances
            and getattr(store._connect,'__func__',None)is RewardState._connect):
            groups[Path(store.path)].append((s,store))
        else:balances[s]=account.get_reward_balances()
    for path,entries in groups.items():
        values=None
        with snapshot_connection(path)as db:
            db.execute('BEGIN')
            schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name='reward_balances'").fetchone()
            if schema==(REWARD['reward_balances'],)and db.execute('PRAGMA temp.schema_version').fetchone()==(0,):
                uids=tuple(store.uid for _,store in entries)
                rows={row[0]:row[1:]for row in db.execute('SELECT uid,ed,experience,revision FROM reward_balances WHERE uid IN('+','.join('?'for _ in uids)+')',uids)}
                values={s:validate_balances(rows.get(store.uid))for s,store in entries}
        if values is None:values={s:s.account.get_reward_balances()for s,_ in entries}
        balances.update(values)
    return balances


class Runtime:
    def __init__(self, app, server, audit_path):
        self.app, self.server, self.audit_path = app, server, audit_path
        self.scheduled = []
        self._announcement_deadline = None
        self._announcement_deadline_lock = Lock()
        self.announcement_history = deque(maxlen=20)
        self.listener = None

    def players(self):
        result = []
        sources=tuple(s for s in self.app.playing.values()if not s.released and s.role=='game')
        identities=_player_identities(sources)
        balances=_player_balances(s for s in sources if identities[s]is not None)
        for s in sources:
            c = identities[s]
            if c is None:
                continue
            result.append(dict(uid=c['uid'],name=c['name'],level=c['level'],unit_type=c['unit_type'],
                unit_class=c['unit_class'],**self.career_labels(c),
                account_id=s.identity['id'],account=s.identity['name'],phase=s.phase,
                map=getattr(s,'active_map',None),session=s.shop_session_id,
                ed=balances[s]['ed']))
        return result

    @staticmethod
    def career_labels(character):
        from els_server.domain.career_labels import labels
        return labels(character['unit_type'],character['unit_class'])

    def level_offline_guard(self, account_id):
        if account_id in self.app.playing:
            raise ValueError('该账号仍有角色在线，请先返回角色选择或退出游戏，再刷新资料')
        if not self.app.registry.enabled(account_id):
            raise ValueError('账号不存在或已停用')

    def session(self, value):
        uid = value.get('uid')
        if type(uid) is not int:
            raise ValueError('角色编号无效')
        s = next((s for s in self.app.playing.values() if not s.released and s.account.uid == uid and s.role == 'game'),None)
        if s is None or s.shop_session_id != value.get('session'):
            raise ValueError('玩家已离线或重新登录，请刷新在线列表')
        if s.social_overflow or s.coop_error or not self.app.registry.enabled(s.identity['id']):
            raise ValueError('玩家连接暂时不可写入')
        if s.phase not in ('town_ready','dungeon_active'):
            raise ValueError('玩家正在切换场景，请稍后刷新再发放')
        return s

    def give(self, value):
        from els_server.domain.reward_rules import item_plan
        from els_server.storage.inventory_state import grant_items, InventoryFull
        from els_server.domain.dungeon_drops import pickup_inventory_notice
        key = operation(value)
        template, quantity = value.get('template'), value.get('quantity')
        if type(template) is not int or type(quantity) is not int or not 1 <= quantity <= 99:
            raise ValueError('每次发放数量为 1–99')
        plan = item_plan(template,quantity)
        digest = hashlib.sha256(canonical(value).encode()).hexdigest()
        with closing(sqlite3.connect(self.app.config.state_file,timeout=10)) as db, write_transaction(db):
            db.execute('CREATE TABLE IF NOT EXISTS gm_item_receipts (operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, receipt TEXT NOT NULL)')
            old = db.execute('SELECT digest,receipt FROM gm_item_receipts WHERE operation_id=?',(key,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('同一操作编号不能用于不同发货内容')
                return dict(json.loads(old[1]),replayed=True)
            s = self.session(value)
            # D3 is the proven incremental bag updater. Prepare bounded mail
            # before commit, then publish with one reference assignment.
            try:changed = grant_items(db,[plan],s.account.uid)
            except InventoryFull as e:raise ValueError('玩家背包空间不足，未发放任何物品') from e
            events = [pickup_inventory_notice(changed)]
            box = prepare_mailbox(s,events)
            receipt = dict(operation_id=key,uid=s.account.uid,name=s.account.character()['name'],
                template=template,quantity=quantity,reason=value['reason'],time=time.time(),replayed=False,
                delivery='committed-and-queued')
            db.execute('INSERT INTO gm_item_receipts VALUES (?,?,?)',(key,digest,canonical(receipt)))
        publish_mailboxes([(s, box)])
        return receipt

    def announce(self,value):
        key = operation(value)
        from els_server.protocol.gm_messages import notice_text
        from els_server.protocol.server_announcement_messages import announcement
        text = notice_text(value.get('text'))
        sender = '系统公告'
        event = announcement(sender, text)
        repeat, interval = value.get('repeat',1), value.get('interval',60)
        if type(repeat) is not int or not 1 <= repeat <= 20 or type(interval) is not int or not 10 <= interval <= 3600:
            raise ValueError('公告次数为 1–20，间隔为 10–3600 秒')
        if repeat > 1 and len(self.scheduled) >= 20:
            raise ValueError('公告计划已满')
        delivered,failed = self.broadcast(event,key)
        now = time.time()
        job = dict(id=key, event=event, sender=sender, text=text, total=repeat,
                   remaining=repeat-1, interval=interval, last_at=now,
                   recipients=delivered, failed_recipients=failed)
        if repeat > 1:
            job.update(deadline=time.monotonic()+interval, next_at=now+interval)
            self.scheduled.append(job)
            self._publish_announcement_deadline()
        else:
            self._finish_announcement(job, 'completed')
        return dict(recipients=delivered,failed_recipients=failed,repeat=repeat,operation_id=key)

    @staticmethod
    def _public_announcement(job):
        return {key: value for key, value in job.items() if key not in ('event', 'deadline')}

    def _finish_announcement(self, job, state):
        self.announcement_history.appendleft(dict(self._public_announcement(job), state=state, next_at=None))

    def broadcast(self,event,operation_id):
        from els_server.protocol.protocol_codec import encode_event
        encode_event(event)
        targets = [s for s in self.app.playing.values() if not s.released and s.role=='game'
                   and s.phase in ('town_ready', 'dungeon_active')
                   and not s.social_overflow and not s.coop_error]
        delivered=failed=0
        for s in targets:
            # The existing sender resolves the current mailbox after locking;
            # an announcement never replaces a concurrent dungeon mailbox.
            self.app.world.send(s,event)
            if s.social_overflow:failed+=1
            else:delivered+=1
        if failed:
            logging.getLogger(__name__).warning('GM announcement %s: %d recipient mailboxes full',operation_id,failed)
        return delivered,failed

    def _publish_announcement_deadline(self):
        # Only the world worker reads or changes the schedule. Publish the
        # next deadline for the server loop without exposing mutable jobs.
        deadline = min((job['deadline'] for job in self.scheduled), default=None)
        with self._announcement_deadline_lock:
            self._announcement_deadline = deadline

    def announcement_due(self):
        with self._announcement_deadline_lock:
            deadline = self._announcement_deadline
        return deadline is not None and time.monotonic() >= deadline

    def tick(self):
        now=time.monotonic()
        for job in list(self.scheduled):
            if now < job['deadline']:
                continue
            delivered, failed = self.broadcast(job['event'], job['id'])
            sent_at = time.time()
            job.update(remaining=job['remaining']-1, last_at=sent_at, recipients=delivered,
                       failed_recipients=failed, deadline=now+job['interval'], next_at=sent_at+job['interval'])
            if not job['remaining']:
                self.scheduled.remove(job)
                self._finish_announcement(job, 'completed')
        self._publish_announcement_deadline()

    def coupon(self,action,value):
        from els_server.storage import coupon_codes as store
        path=self.app.config.state_file
        if action=='coupon-rewards':
            return dict(rows=store.available_rewards(value.get('template')))
        if action=='coupon-list':return store.batches(path,value.get('offset',0))
        if action=='coupon-operation':
            result=store.issuer_operation(path,value.get('operation_id'),value.get('action'))
            return dict(committed=result is not None,receipt=result)
        operation(value)
        if action=='coupon-revoke':return store.revoke(path,value)
        if action!='coupon-issue':raise ValueError('Unknown coupon issuer action')
        def validate(bound):
            if bound is not None and not self.app.registry.enabled(bound):raise ValueError('Coupon account unavailable')
        return store.issue(path,value,validate=validate)

    def ariel_cash(self,action,value):
        from els_server.storage import ariel_cash as store
        def validate(account):
            store.account_id(account)
            if self.app.config.mode=='local':
                if account!=1:raise ValueError('Local cash belongs only to account1')
                return
            if not self.app.registry.enabled(account):raise ValueError('Cash target account unavailable')
        account=value.get('account_id');validate(account)
        path=self.app.config.state_file
        if action=='cash-balance':
            if set(value)!={'account_id'}:raise ValueError('Cash balance fields')
            return dict(account_id=account,**store.snapshot(path,account,validate=lambda:validate(account)))
        if action=='cash-operation':
            if set(value)!={'account_id','operation_id'}:raise ValueError('Cash receipt fields')
            return store.credit_receipt(path,account,value['operation_id'],validate=validate)
        if action!='cash-credit':raise ValueError('Unknown cash GM action')
        operation(value)
        return store.credit(path,value,validate=validate)

    def execute(self, request):
        action, value = request.get('action'), request.get('value',{})
        if action in ('cash-balance','cash-operation','cash-credit'):return self.ariel_cash(action,value)
        if action in ('coupon-rewards','coupon-list','coupon-operation','coupon-issue','coupon-revoke'):return self.coupon(action,value)
        if action in ('selected2026-status','selected2026'):
            manager=getattr(self.app,'activity2026_manager',None)
            if manager is None:raise ValueError('Selected reproduction runtime unavailable')
            return manager.snapshot() if action=='selected2026-status' else manager.update(value)
        if action=='status':
            from els_server.domain.gm_rates import snapshot, formal_snapshot
            from els_server.domain.gm_events import live_calendar, snapshot as event_snapshot
            return dict(players=self.players(),rates=snapshot(),formal_drops=formal_snapshot(),events=event_snapshot(),
                        batch_give_available=True,announcements=[self._public_announcement(j) for j in self.scheduled],
                        announcement_history=list(self.announcement_history),activity_calendar=live_calendar())
        if action=='give':return self.give(value)
        if action in ('batch-give-preview','batch-give','batch-give-operation'):
            from els_server import gm_item_batch
            handler = {'batch-give-preview': gm_item_batch.preview, 'batch-give': gm_item_batch.apply,
                       'batch-give-operation': gm_item_batch.inspect}[action]
            return handler(self, value)
        if action in ('level-preview','set-level'):
            from els_server.storage.gm_levels import preview,set_level
            fn=preview if action=='level-preview' else set_level
            return fn(self.app.config.state_file,value,self.level_offline_guard)
        if action=='announce':return self.announce(value)
        if action=='rates':
            operation(value)
            from els_server.domain.gm_rates import update
            return update(value['settings'],value['expected_revision'])
        if action=='formal-drops':
            operation(value)
            from els_server.domain.gm_rates import update_formal
            return update_formal(value['multiplier_bp'],value['expected_revision'])
        if action=='events':
            operation(value)
            from els_server.domain.gm_events import update
            return update(value['events'],value['expected_revision'])
        if action=='cancel-announcement':
            operation(value)
            job = next((job for job in self.scheduled if job['id'] == value.get('id')), None)
            if job is None:
                raise ValueError('这条公告已结束或已取消')
            self.scheduled.remove(job)
            self._finish_announcement(job, 'cancelled')
            self._publish_announcement_deadline()
            return dict(cancelled=True)
        raise ValueError('未知管理操作')

    async def start(self,port,token):
        if not isinstance(token,str) or len(token)<40:raise ValueError('GM runtime token required')
        async def handle(reader,writer):
            try:
                async with asyncio.timeout(15):
                    raw=await reader.readline()
                    if len(raw)>32768:raise ValueError('请求过大')
                    request=json.loads(raw)
                    if not hmac.compare_digest(str(request.pop('token','')),token):raise ValueError('管理认证失败')
                    result=await self.app.call(self.execute,request)
                    reply=dict(ok=True,result=result)
            except Exception as e:
                reply=dict(ok=False,error=str(e) if isinstance(e,ValueError) else '服务端管理操作失败，请检查日志')
                # Cancellation/SQL/internal errors can race a durable commit.
                # Coupon recovery must inspect the original worker receipt.
                if not isinstance(e,ValueError) and isinstance(locals().get('request'),dict) and request.get('action')in('coupon-issue','coupon-revoke','cash-credit','batch-give','give'):
                    reply['outcome_unknown']=True
            try:
                writer.write((canonical(reply)+'\n').encode());await writer.drain()
            finally:
                writer.close();await writer.wait_closed()
        self.listener=await asyncio.start_server(handle,'127.0.0.1',port,limit=32769)

    async def close(self):
        if self.listener:self.listener.close();await self.listener.wait_closed()

from els_server.storage.sqlite_timing import write_transaction
