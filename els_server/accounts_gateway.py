"""Small friends-server registration API on the existing pinned TLS endpoint."""
from collections import deque,OrderedDict
import time


class AccountGateway:
    def __init__(self,config,application=None):
        import threading,weakref
        self.config=config;self.windows=OrderedDict();self.application=application
        self.recovery_flights={};self.recovery_closing=False;self.recovery_stop=threading.Event()
        self.recovery_generations=weakref.WeakKeyDictionary()

    def allow(self,host,operation):
        now=time.monotonic();key=(host,operation)
        seconds,limit=(600,6) if operation=='register' else (60,12)
        window=self.windows.pop(key,deque())
        while window and now-window[0]>=seconds:window.popleft()
        self.windows[key]=window
        while len(self.windows)>4096:self.windows.popitem(last=False)
        if len(window)>=limit:return False
        window.append(now);return True

    def handle(self,registry,document,host):
        op=document.get('op')
        if op=='status' and set(document)=={'op'}:
            return dict(ok=True,api_version=1,registration_enabled=getattr(self.config,'registration_enabled',False))
        if op=='resume' and set(document)=={'op','name','token'}:
            if not self.allow(host,op):return dict(ok=False,error='rate_limited')
            try:
                identity=registry.authenticate(document['name'],document['token'])
                return dict(ok=True,account_id=identity['id'],name=identity['name'])
            except ValueError:return dict(ok=False,error='bad_credentials')
        if op not in ('register','login') or set(document)!={'op','name','password'}:return dict(ok=False,error='invalid_request')
        if not self.allow(host,op):return dict(ok=False,error='rate_limited')
        try:
            if op=='register':
                if not getattr(self.config,'registration_enabled',False):return dict(ok=False,error='registration_closed')
                result=registry.register(document['name'],document['password'],getattr(self.config,'max_registered_accounts',64))
            else:result=registry.password_login(document['name'],document['password'])
            return dict(ok=True,api_version=1,**result)
        except ValueError as error:
            code=str(error)
            if code not in ('invalid_name','invalid_password','name_taken','registration_full','bad_credentials'):code='invalid_request'
            return dict(ok=False,error=code)

    def begin_close(self):
        self.recovery_closing=True;self.recovery_stop.set()

    async def close(self):
        self.begin_close()
        tasks=[v['task'] for v in self.recovery_flights.values() if not v['task'].done()]
        if tasks:
            import asyncio
            await asyncio.gather(*tasks,return_exceptions=True)
        self.recovery_flights.clear()

    def _generation(self,account_id):
        root=self.application.accounts.get(account_id)
        if root is None:return None
        if root not in self.recovery_generations:self.recovery_generations[root]=object()
        return self.recovery_generations[root]

    def _recovery_identity(self,document):
        from els_server.storage.tutorial_recovery import RecoveryError
        if self.recovery_closing or self.application is None:raise RecoveryError('recovery_unavailable')
        if self.config.mode!='friends' or self.config.profile!='integrated_dx11':raise RecoveryError('recovery_unavailable')
        if not isinstance(document.get('name'),str) or not 3<=len(document['name'])<=24 or not isinstance(document.get('token'),str) or not 32<=len(document['token'])<=128:raise RecoveryError('bad_credentials')
        try:identity=self.application.registry.authenticate(document['name'],document['token'])
        except ValueError:raise RecoveryError('bad_credentials') from None
        if identity['id'] in self.application.playing:raise RecoveryError('account_playing')
        return identity

    def _prepare_recovery(self,document,host,rate=True):
        from els_server.storage import tutorial_recovery as recovery
        expected={'op','name','token','offset'} if document.get('op')=='tutorial_recovery_preview' else {'op','name','token','uid','version','operation_id'}
        if document.get('op') not in ('tutorial_recovery_preview','tutorial_recovery_confirm') or set(document)!=expected:raise recovery.RecoveryError('invalid_request')
        recovery.bounded_json(document)
        if rate and not self.allow(host,document['op']):raise recovery.RecoveryError('rate_limited')
        identity=self._recovery_identity(document)
        if document['op']=='tutorial_recovery_preview':return recovery.preview(self.config.state_file,identity['id'],document['offset'])
        result=recovery.prepare(self.config.state_file,identity['id'],document['uid'],document['version'],document['operation_id'],self._generation(identity['id']),self.recovery_stop)
        if isinstance(result,dict):
            from types import SimpleNamespace
            self._refresh_recovery(SimpleNamespace(state_path=self.config.state_file,uid=document['uid'],account_id=identity['id']))
        return result

    def _refresh_recovery(self,ticket):
        from els_server.storage import tutorial_recovery as recovery
        root=self.application.accounts.get(ticket.account_id)
        if root is None:return
        current=recovery.current_location(ticket.state_path,ticket.uid,ticket.account_id)
        accounts=list(root.character_accounts.values()) if hasattr(root,'character_accounts') else []
        if getattr(root,'uid',None)==ticket.uid:accounts.append(root)
        for account in accounts:
            if account.uid==ticket.uid and account.account_id==ticket.account_id:account.location=dict(current)

    def _finish_recovery(self,document,ticket,backup):
        from els_server.storage import tutorial_recovery as recovery
        def guard():
            identity=self._recovery_identity(document)
            if identity['id']!=ticket.account_id or self._generation(ticket.account_id) is not ticket.cache_generation:raise recovery.RecoveryError('recovery_stale')
        guard();reply=recovery.finish(ticket,backup,guard);self._refresh_recovery(ticket);return reply

    async def _complete_recovery(self,document,ticket):
        import asyncio
        from els_server.storage import tutorial_recovery as recovery
        try:
            backup=await asyncio.to_thread(recovery.backup_ticket,ticket)
            return await self.application.call(self._finish_recovery,document,ticket,backup)
        except recovery.RecoveryError as error:return recovery.bounded_json(dict(ok=False,error=str(error)))
        except Exception:return recovery.bounded_json(dict(ok=False,error='recovery_unavailable'))
        finally:document.clear()

    async def recovery(self,document,host):
        import asyncio
        from els_server.storage import tutorial_recovery as recovery
        try:
            if self.application is None:raise recovery.RecoveryError('recovery_unavailable')
            ticket=await self.application.call(self._prepare_recovery,document,host)
            if isinstance(ticket,dict):return ticket
            now=time.monotonic()
            for key,flight in list(self.recovery_flights.items()):
                if flight['task'].done() and now-flight['started']>=120:self.recovery_flights.pop(key)
            key=(ticket.account_id,ticket.operation_id);old=self.recovery_flights.get(key)
            if old is not None:
                if old['hash']!=ticket.request_hash:raise recovery.RecoveryError('recovery_conflict')
                reply=await asyncio.shield(old['task'])
                if reply.get('ok'):
                    current=await self.application.call(self._prepare_recovery,document,host,False)
                    if not isinstance(current,dict):raise recovery.RecoveryError('recovery_stale')
                    return current
                return reply
            active=[v for v in self.recovery_flights.values() if not v['task'].done()]
            if self.recovery_closing or len(active)>=2 or any(v['account_id']==ticket.account_id for v in active):raise recovery.RecoveryError('recovery_unavailable')
            if len(self.recovery_flights)>=32:
                evict=next((k for k,v in self.recovery_flights.items() if v['task'].done()),None)
                if evict is None:raise recovery.RecoveryError('recovery_unavailable')
                self.recovery_flights.pop(evict)
            task=asyncio.create_task(self._complete_recovery(dict(document),ticket))
            self.recovery_flights[key]=dict(task=task,hash=ticket.request_hash,account_id=ticket.account_id,started=now)
            return await asyncio.shield(task)
        except recovery.RecoveryError as error:return recovery.bounded_json(dict(ok=False,error=str(error)))
        except Exception:return recovery.bounded_json(dict(ok=False,error='recovery_unavailable'))
