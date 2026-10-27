"""Authenticated loopback RPC; every game mutation runs on Application's worker."""
import asyncio
import copy
from collections import deque
from contextlib import closing
import hashlib
import hmac
import json
import sqlite3
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
    from els_server.protocol.protocol_codec import encode_event
    box = copy.copy(session.mailbox)
    box.messages = deque(session.mailbox.messages)
    box.moves = dict(session.mailbox.moves)
    for event in events:
        encode_event(event)
        box.append(event)
    return box


class Runtime:
    def __init__(self, app, server, audit_path):
        self.app, self.server, self.audit_path = app, server, audit_path
        self.scheduled = []
        self.listener = None

    def players(self):
        result = []
        for s in self.app.playing.values():
            if s.released or s.role != 'game':
                continue
            c = s.account.character()
            if c is None:
                continue
            result.append(dict(uid=c['uid'],name=c['name'],level=c['level'],unit_type=c['unit_type'],
                unit_class=c['unit_class'],**self.career_labels(c),
                account_id=s.identity['id'],account=s.identity['name'],phase=s.phase,
                map=getattr(s,'active_map',None),session=s.shop_session_id,
                ed=s.account.get_reward_balances()['ed']))
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
        with closing(sqlite3.connect(self.app.config.state_file,timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
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
            db.commit()
            s.mailbox = box
            return receipt

    def announce(self,value):
        operation(value)
        from els_server.protocol.gm_messages import scrolling_notice
        text = value.get('text')
        event = scrolling_notice(text)
        repeat, interval = value.get('repeat',1), value.get('interval',60)
        if type(repeat) is not int or not 1 <= repeat <= 20 or type(interval) is not int or not 10 <= interval <= 3600:
            raise ValueError('公告次数为 1–20，间隔为 10–3600 秒')
        targets = [s for s in self.app.playing.values() if not s.released and s.role=='game' and not s.social_overflow and not s.coop_error]
        boxes = {s:prepare_mailbox(s,[event]) for s in targets}
        if repeat > 1:
            if len(self.scheduled) >= 20:
                raise ValueError('公告计划已满')
            self.scheduled.append(dict(id=value['operation_id'],event=event,text=text,
                remaining=repeat-1,interval=interval,next=time.monotonic()+interval))
        for s,box in boxes.items():s.mailbox=box
        return dict(recipients=len(boxes),repeat=repeat,operation_id=value['operation_id'])

    def tick(self):
        now=time.monotonic()
        for job in list(self.scheduled):
            if now<job['next']:continue
            targets=[s for s in self.app.playing.values() if not s.released and s.role=='game' and not s.social_overflow and not s.coop_error]
            try:boxes={s:prepare_mailbox(s,[job['event']]) for s in targets}
            except ValueError:boxes={}
            for s,box in boxes.items():s.mailbox=box
            job['remaining']-=1;job['next']=now+job['interval']
            if not job['remaining']:self.scheduled.remove(job)

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
        if self.app.config.mode=='local' and action not in ('selected2026-status','selected2026'):
            raise ValueError('本地活动管理接口只开放本次签到和在线活动')
        if action in ('selected2026-status','selected2026'):
            manager=getattr(self.app,'activity2026_manager',None)
            if manager is None:raise ValueError('本机未启用2026活动运行配置')
            return manager.snapshot() if action=='selected2026-status' else manager.update(value)
        if action=='status':
            from els_server.domain.gm_rates import snapshot
            from els_server.domain.gm_events import snapshot as event_snapshot
            return dict(players=self.players(),rates=snapshot(),events=event_snapshot(),announcements=[{k:v for k,v in j.items() if k!='event'} for j in self.scheduled])
        if action=='give':return self.give(value)
        if action in ('level-preview','set-level'):
            from els_server.storage.gm_levels import preview,set_level
            fn=preview if action=='level-preview' else set_level
            return fn(self.app.config.state_file,value,self.level_offline_guard)
        if action=='announce':return self.announce(value)
        if action=='rates':
            operation(value)
            from els_server.domain.gm_rates import update
            return update(value['settings'],value['expected_revision'])
        if action=='events':
            operation(value)
            from els_server.domain.gm_events import update
            return update(value['events'],value['expected_revision'])
        if action=='cancel-announcement':
            operation(value)
            self.scheduled=[j for j in self.scheduled if j['id']!=value.get('id')]
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
                if not isinstance(e,ValueError) and isinstance(locals().get('request'),dict) and request.get('action')=='cash-credit':reply['outcome_unknown']=True
            try:
                writer.write((canonical(reply)+'\n').encode());await writer.drain()
            finally:
                writer.close();await writer.wait_closed()
        self.listener=await asyncio.start_server(handle,'127.0.0.1',port,limit=32769)

    async def close(self):
        if self.listener:self.listener.close();await self.listener.wait_closed()
