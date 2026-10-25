"""Persistent GM supervisor. Never discovers/kills arbitrary OS processes."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time

from els_server.config import ServerConfig
from els_server.gm_runtime import operation, canonical

RECOVERY_LIMIT=3
RECOVERY_WINDOW=600
RECOVERY_BACKOFF=(1,2,4)
HEALTHY_RESET=120
START_TIMEOUT=120
STOP_WARNING=90


class Service:
    def __init__(self,root,config,home,runtime_port=18766):
        self.root=Path(root).resolve();self.config_path=Path(config).resolve()
        self.config=ServerConfig.load(self.config_path)
        self.home=Path(home).resolve();self.home.mkdir(parents=True,exist_ok=True)
        # New private state only. Game/account credentials never enter the UI.
        self.key_path=self.home/'access.key'
        if not self.key_path.exists():
            fd=os.open(self.key_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w',encoding='ascii') as f:f.write(secrets.token_urlsafe(48))
        self.key=self.key_path.read_text(encoding='ascii').strip()
        if len(self.key)<40:raise ValueError('GM access key is invalid')
        self.token=secrets.token_urlsafe(48);self.runtime_port=runtime_port
        self.child=None;self.stop_file=None;self.phase='stopped';self.started=None
        self.message='游戏服务尚未由 GM 启动';self.lock=threading.RLock()
        self.log_handle=None
        self.gate=None
        self.generation=0;self.recovery_starts=[]
        self.shutting_down=False;self.shutdown_event=threading.Event()
        self.stop_file=self.root/'run/server.stop'
        self.audit=self.home/'audit.sqlite3'
        with closing(sqlite3.connect(self.audit)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, action TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL, result TEXT, time REAL NOT NULL)')

    def rpc(self,action,value=None):
        with socket.create_connection(('127.0.0.1',self.runtime_port),timeout=3) as sock:
            sock.settimeout(20)
            sock.sendall((canonical(dict(token=self.token,action=action,value=value or {}))+'\n').encode())
            with sock.makefile('rb') as stream:raw=stream.readline(2*1024*1024)
        try:answer=json.loads(raw)
        except (UnicodeError,json.JSONDecodeError):
            if action in ('coupon-issue','coupon-revoke','cash-credit'):raise OSError('Ledger RPC result unknown; inspect original operation') from None
            raise
        if action in ('coupon-issue','coupon-revoke','cash-credit') and (not isinstance(answer,dict) or answer.get('outcome_unknown')is True):
            raise OSError('Ledger RPC result unknown; inspect original operation')
        if not answer.get('ok'):raise ValueError(answer.get('error','管理操作失败'))
        return answer['result']

    def running(self):
        return self.child is not None and self.child.poll() is None

    def listening(self,port):
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.3):return True
        except OSError:return False

    def status(self):
        owned=self.running();ready=False;players=[];announcements=[];rates=None;events=None
        if owned:
            try:
                reply=self.rpc('status');ready=True
                players=reply['players'];rates=reply['rates'];announcements=reply['announcements']
                events=reply['events']
            except (OSError,ValueError):pass
        if rates is None:
            from els_server.domain import gm_rates
            gm_rates.configure(self.home/'rates.json');rates=gm_rates.snapshot()
        if events is None:
            from els_server.domain import gm_events
            gm_events.configure(self.home/'events.json');events=gm_events.snapshot()
        from els_server.domain.paid_enhancement import RATES
        return dict(phase=self.phase,ready=ready,owned=owned,players=players,rates=rates,events=events,
            defaults=[r[0] for r in RATES],announcements=announcements,
            mode=self.config.mode,game_host=self.config.host,game_port=self.config.port,message=self.message,
            started=self.started,pid=self.child.pid if owned else None,
            shutting_down=self.shutting_down,recovery_starts=len(self.recovery_starts),
            external_listener=not owned and self.listening(self.config.port),
            time=datetime.now(timezone.utc).isoformat(),version='GM 0.2',
            scope='普通/BOSS/宝箱：El Tree 原有物品掉落分支；ED：现有静态副本与 El Tree 落地 ED 出现率。经验倍率：已实现副本及战场通关的角色经验，不改变神器经验或固定通关 ED，不创建未实现的装备掉落池。')

    def accounts(self,query='',offset=0):
        from gm_console.accounts import directory
        players=[];online_available=not self.running()
        if self.running():
            try:players=self.rpc('status')['players'];online_available=True
            except (OSError,ValueError):pass
        return dict(directory(self.config,query,offset,players),online_available=online_available)

    def desired_running(self):
        path=self.home/'desired.json'
        if not path.exists():return True
        try:return json.loads(path.read_text(encoding='utf8')).get('running') is True
        except (OSError,ValueError):return False

    def _blocked(self):
        if self.shutting_down:return '管理器正在正常停止'
        if not self.desired_running():return '已明确关服'
        if self.stop_file.exists():return '存在正常停服标记，恢复已暂停'
        if (self.root/'run/release.lock').exists() and self.gate is None:return '存在发布锁，恢复已暂停'
        return None

    def _ports_drained(self):
        return not any(self.listening(p) for p in
            {self.config.port,self.config.client_probe_port,self.runtime_port})

    def start(self,value):
        if value.get('confirm')!='开服':raise ValueError('请输入“开服”确认')
        if self.shutting_down:raise ValueError('管理器正在正常停止')
        if self.config.mode!='friends':raise ValueError('此页面管理朋友服，请使用 friends 配置')
        if self.running() or self.phase in ('starting','stopping','recovering'):raise ValueError('游戏服务正在运行或切换状态')
        if not self._ports_drained():raise ValueError('端口已被其他服务占用；请由统筹先完成运行方式切换')
        self.stop_file.parent.mkdir(parents=True,exist_ok=True)
        self.stop_file.unlink(missing_ok=True)
        self.recovery_starts.clear()
        return self._launch(False)

    def _launch(self,recovery):
        self.write_desired(True)
        log=(self.home/'game.log').open('ab',buffering=0)
        env=os.environ.copy();env['ELS_GM_RUNTIME_TOKEN']=self.token
        env['PYTHONUNBUFFERED']='1'
        try:
            child=subprocess.Popen([sys.executable,'-m','els_server','--config',str(self.config_path),
                '--stop-file',str(self.stop_file),'--gm-runtime-port',str(self.runtime_port),'--gm-home',str(self.home)],
                cwd=self.root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except BaseException:log.close();raise
        self.child=child;self.log_handle=log;self.generation+=1
        if recovery:self.recovery_starts.append(time.monotonic())
        self.phase='starting';self.started=time.time();self.message='正在加载配表及存档'
        threading.Thread(target=self._watch_child,args=(child,self.generation,log,self.gate),daemon=True).start()
        return dict(message='已请求开服，请等待状态显示运行中',pid=child.pid)

    def _watch_child(self,child,generation,log,gate):
        begun=time.monotonic();ready_at=None;warned=False
        while True:
            with self.lock:
                if self.child is not child or self.generation!=generation:return
                exited=child.poll() is not None
                if self.stop_file.exists() or self.shutting_down:
                    if self.phase!='stopping':self.phase='stopping';begun=time.monotonic()
                if exited and self._ports_drained():
                    log.close()
                    if self.log_handle is log:self.log_handle=None
                    self.phase='stopped'
                    # No mutation can be in flight while this lock is held.
                    # This includes a later explicit-stop gate for this child.
                    self.release_gate()
                    reason=self._blocked()
                    if reason:self.message=reason;return
                    now=time.monotonic()
                    self.recovery_starts[:]=[t for t in self.recovery_starts if now-t<RECOVERY_WINDOW]
                    if len(self.recovery_starts)>=RECOVERY_LIMIT:
                        self.message='异常恢复次数已耗尽（10分钟内最多3次）；请检查日志后明确开服';return
                    delay=RECOVERY_BACKOFF[len(self.recovery_starts)]
                    self.phase='recovering';self.message=f'游戏进程意外退出，{delay}秒后尝试恢复'
                    break
                if (exited or self.phase=='stopping') and time.monotonic()-begun>=STOP_WARNING:
                    self.message='关服或监听排空尚未完成；管理器继续等待，未强制结束进程'
                check_ready=not exited and self.phase=='starting'
            if check_ready:
                try:self.rpc('status');ready=True
                except (OSError,ValueError):ready=False
                with self.lock:
                    if self.child is not child or self.generation!=generation:return
                    if ready and self.phase=='starting':
                        self.phase='running';self.message='游戏服务运行中';ready_at=time.monotonic()
                        if self.gate is gate and gate is not None:self.release_gate()
                    elif not warned and time.monotonic()-begun>=START_TIMEOUT:
                        self.message='启动超时；管理器继续监护，发布锁保留至正常退出或就绪';warned=True
            with self.lock:
                if self.child is not child or self.generation!=generation:return
                if ready_at is not None and time.monotonic()-ready_at>=HEALTHY_RESET:
                    self.recovery_starts.clear();ready_at=None
            time.sleep(.5)
        if self.shutdown_event.wait(delay):return
        with self.lock:
            if self.child is not child or self.generation!=generation:return
            reason=self._blocked()
            if reason:self.phase='stopped';self.message=reason;return
            if not self._ports_drained():self.phase='stopped';self.message='监听尚未关闭，恢复已暂停';return
            acquired=None
            try:
                self.acquire_gate();acquired=self.gate
                # Recheck after CreateNew, so an external stop request wins.
                reason=self._blocked()
                if reason:raise ValueError(reason)
                self._launch(True)
            except Exception as e:
                self.phase='stopped';self.message='异常恢复未启动：'+str(e)
                if acquired is not None and self.gate is acquired:self.release_gate()

    def stop(self,value):
        if value.get('confirm')!='关服':raise ValueError('请输入“关服”确认')
        # Persist intent before publishing the stop marker or waiting on a child.
        self.write_desired(False)
        if not self.running():
            self.phase='stopped';self.message='已明确关服，自动恢复已取消'
            self.release_gate()
            return dict(message=self.message)
        self.stop_file.parent.mkdir(parents=True,exist_ok=True)
        self.stop_file.touch(exist_ok=True)
        self.phase='stopping';self.message='正在正常断开连接、落盘并关闭监听'
        return dict(message='已请求正常关服，页面将继续运行')

    def write_desired(self,running):
        temporary=self.home/'desired.tmp'
        with temporary.open('w',encoding='utf8') as stream:
            stream.write(canonical(dict(running=running)));stream.flush();os.fsync(stream.fileno())
        temporary.replace(self.home/'desired.json')

    def boot(self):
        with self.lock:
            reason=self._blocked()
            if reason:self.message=reason;return
            import uuid
            self.mutate('start',dict(operation_id=str(uuid.uuid4()),reason='管理服务随计划任务启动',confirm='开服'))

    def request_shutdown(self):
        """Publisher-safe: no mutate/CreateNew; never terminate the game."""
        with self.lock:
            self.shutting_down=True;self.shutdown_event.set()
            if self.running():
                self.stop_file.parent.mkdir(parents=True,exist_ok=True)
                self.stop_file.touch(exist_ok=True)
                self.phase='stopping';self.message='管理器等待自有游戏正常退出及监听排空'
            else:self.message='管理器正在等待监听排空'

    def shutdown_ready(self):
        with self.lock:
            if not self.shutting_down or self.running() or not self._ports_drained():return False
            if self.log_handle:self.log_handle.close();self.log_handle=None
            self.release_gate()
            return True

    def acquire_gate(self):
        """Same CreateNew sentinel as the coordinator's production deployer."""
        path=self.root/'run/release.lock';path.parent.mkdir(parents=True,exist_ok=True)
        if self.gate is not None:raise ValueError('上次服务切换尚未完成')
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
        except FileExistsError as e:raise ValueError('正在发布或维护，GM 操作已暂停') from e
        identity=secrets.token_hex(24).encode()
        os.write(fd,identity);os.fsync(fd)
        self.gate=(path,fd,identity)

    def release_gate(self):
        if self.gate is None:return
        path,fd,identity=self.gate
        os.lseek(fd,0,os.SEEK_SET)
        if os.read(fd,100)!=identity or not path.exists() or path.read_bytes()!=identity or os.fstat(fd).st_ino!=path.stat().st_ino:
            raise ValueError('发布锁身份发生变化，请核实')
        os.close(fd)
        # The exclusively-created sentinel blocks every other CreateNew owner
        # until this non-recursive unlink. Never remove a foreign stale lock.
        path.unlink();self.gate=None

    def backup(self):
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        destination=self.home/'backups'/stamp;destination.mkdir(parents=True)
        rows=[]
        for name,source in [('game',self.config.state_file),('accounts',self.config.accounts_file)]:
            if source is None or not source.is_file():raise ValueError('数据库不存在，备份未完成')
            with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=10)) as src:
                with closing(sqlite3.connect(destination/(name+'.sqlite3'))) as dst:
                    src.backup(dst)
                    if dst.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('备份完整性检查失败')
            rows.append(name+'.sqlite3')
        (destination/'config.toml').write_bytes(self.config_path.read_bytes())
        settings=[]
        for name in ('rates.json','events.json','desired.json'):
            path=self.home/name
            if path.is_file():(destination/('gm-'+name)).write_bytes(path.read_bytes());settings.append('gm-'+name)
        return dict(message='双库及服务配置备份完成',directory=str(destination),files=rows,gm_settings=settings)

    def history(self):
        with closing(sqlite3.connect(self.audit)) as db:
            return [dict(id=r[0],action=r[1],request=json.loads(r[2]),status=r[3],
                result=json.loads(r[4]) if r[4] else None,time=r[5]) for r in db.execute(
                    'SELECT id,action,request,status,result,time FROM operations ORDER BY time DESC LIMIT 100')]

    def level_offline_guard(self, account_id):
        with closing(sqlite3.connect(self.config.accounts_file.as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute('SELECT enabled FROM accounts WHERE id=?',(account_id,)).fetchone() != (1,):
                raise ValueError('账号不存在或已停用')

    def set_level(self, value):
        from els_server.storage.gm_levels import preview,set_level,validate
        from els_server.storage.lifecycle import SaveLease
        validate(value)
        pointer=self.home/'level-backups'/(value['operation_id']+'.json')
        def recorded(result):
            saved=json.loads(pointer.read_text('utf8')) if pointer.is_file() else {}
            return dict(result,backup=saved.get('directory'),message='等级与经验已保存，下次进入角色生效')
        def backed_up():
            if pointer.is_file():
                previous=json.loads(pointer.read_text('utf8'))
                directory=Path(previous['directory']).resolve()
                if (not directory.is_relative_to((self.home/'backups').resolve())
                        or not all((directory/name).is_file() for name in ('game.sqlite3','accounts.sqlite3'))):
                    raise ValueError('原操作备份无法核实，请查看操作记录')
                return previous
            backup=self.backup()
            pointer.parent.mkdir(exist_ok=True)
            with pointer.open('x',encoding='utf8') as stream:
                stream.write(canonical(backup));stream.flush();os.fsync(stream.fileno())
            return backup
        if self.running():
            checked=self.rpc('level-preview',value)
            if checked.get('replayed'):return recorded(checked)
            backup=backed_up()
            result=self.rpc('set-level',value)
        else:
            if self.phase!='stopped' or not self._ports_drained():
                raise ValueError('服务正在切换或由其他进程运行，请稍后刷新')
            with SaveLease(self.config.state_file):
                checked=preview(self.config.state_file,value,self.level_offline_guard)
                if checked.get('replayed'):return recorded(checked)
                backup=backed_up()
                result=set_level(self.config.state_file,value,self.level_offline_guard)
        return dict(result,backup=backup['directory'],message='等级与经验已保存，下次进入角色生效')

    def logs(self):
        path=self.home/'game.log'
        if not path.exists():return dict(text='尚无游戏运行日志')
        with path.open('rb') as f:
            f.seek(max(0,path.stat().st_size-16000));raw=f.read()
        # The server's structured logger excludes credentials and wire payloads.
        return dict(text=raw.decode('utf8','replace'))

    @staticmethod
    def public_coupon_result(result):
        # Raw bearer codes never enter operations.audit/history, even on replay.
        return {k:v for k,v in result.items()if k!='codes'}

    def coupon_read(self,action,value=None):
        if action not in ('coupon-rewards','coupon-list','coupon-operation'):raise ValueError('Coupon read action')
        if not self.running():raise ValueError('游戏服务未启动，无法核查兑换码')
        return self.rpc(action,value)

    def cash_read(self,action,value):
        if action not in ('cash-balance','cash-operation'):raise ValueError('Cash read action')
        if not self.running():raise ValueError('游戏服务未启动，无法核查独立账号现金')
        return self.rpc(action,value)

    def mutate(self,action,value):
        # Coupon requests have no raw-code field. Reject unknown fields before
        # generic audit persistence, rather than recording an accidental secret.
        if action in ('coupon-issue','coupon-revoke'):
            fields={'operation_id','reason','count','max_redemptions','starts_at','expires_at','account_id','rewards'} if action=='coupon-issue' else {'operation_id','reason','batch_id'}
            if not isinstance(value,dict) or set(value)!=fields:raise ValueError('Coupon management fields')
            if action=='coupon-issue' and (not isinstance(value['rewards'],list) or any(not isinstance(r,dict) or set(r)!={'template','quantity'} for r in value['rewards'])):raise ValueError('Coupon reward fields')
        if action=='cash-credit':
            if not isinstance(value,dict) or set(value)!={'operation_id','account_id','amount','expected_balance','reason'}:raise ValueError('Cash management fields')
        key=operation(value);digest=hashlib.sha256(canonical([action,value]).encode()).hexdigest()
        with self.lock:
            if self.shutting_down:raise ValueError('管理器正在正常停止，管理写入已暂停')
            with closing(sqlite3.connect(self.audit)) as db,db:
                old=db.execute('SELECT digest,status,result FROM operations WHERE id=?',(key,)).fetchone()
                if old:
                    if old[0]!=digest:raise ValueError('操作编号与已提交内容冲突')
                    if old[1]=='done':
                        if action=='cash-credit':
                            found=self.cash_read('cash-operation',dict(operation_id=key,account_id=value['account_id']))
                            if not found['committed']:raise ValueError('充值回执暂不可核实；不创建替代充值')
                            return dict(found['receipt'],replayed=True)
                        if action=='coupon-issue':
                            found=self.coupon_read('coupon-operation',dict(operation_id=key,action=action))
                            if not found['committed']:raise ValueError('发行回执暂不可核实；未创建替代码')
                            return dict(found['receipt'],replayed=True)
                        return dict(json.loads(old[2]),replayed=True)
                    if action=='cash-credit' and old[1]in('unknown','pending','failed'):
                        # Only an explicit same-UUID POST may inspect, then retry.
                        found=self.cash_read('cash-operation',dict(operation_id=key,account_id=value['account_id']))
                        if found['committed']:
                            receipt=dict(found['receipt'],replayed=True)
                            db.execute('UPDATE operations SET status=?,result=? WHERE id=?',('done',canonical(receipt),key))
                            return receipt
                        db.execute('UPDATE operations SET status=?,result=NULL WHERE id=?',('pending',key))
                    elif action in ('coupon-issue','coupon-revoke')and old[1]in('unknown','pending','failed'):
                        # An explicit original POST first inspects the durable
                        # decision. No failure path auto-resends or changesUUID.
                        found=self.coupon_read('coupon-operation',dict(operation_id=key,action=action))
                        if found['committed']:
                            receipt=dict(found['receipt'],replayed=True)
                            db.execute('UPDATE operations SET status=?,result=? WHERE id=?',('done',canonical(self.public_coupon_result(receipt)),key))
                            return receipt
                        # Explicit original POST only: the same worker has now
                        # crossed every earlier mutation and proved no receipt.
                        # The original UUID/digest remains the only retry key.
                        db.execute('UPDATE operations SET status=?,result=NULL WHERE id=?',('pending',key))
                    elif action not in ('give','set-level') or old[1]!='unknown':raise ValueError('该操作已记录为 '+old[1]+'，请查看操作日志')
                else:
                    db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?)',(key,digest,action,canonical(value),'pending',None,time.time()))
            try:
                self.acquire_gate()
                if action=='start':result=self.start(value)
                elif action=='stop':result=self.stop(value)
                elif action=='backup':result=self.backup()
                elif action=='set-level':result=self.set_level(value)
                elif action in ('give','announce','rates','events','cancel-announcement','coupon-issue','coupon-revoke','cash-credit'):
                    if not self.running():raise ValueError('游戏服务未启动，在线管理操作不可用')
                    result=self.rpc(action,value)
                else:raise ValueError('未知操作')
            except Exception as e:
                unknown=isinstance(e,(OSError,TimeoutError))
                result=dict(error='请求结果未确认，请查询操作日志后使用原操作编号重试' if unknown else str(e))
                with closing(sqlite3.connect(self.audit)) as db,db:
                    db.execute('UPDATE operations SET status=?,result=? WHERE id=?',('unknown' if unknown else 'failed',canonical(result),key))
                if self.gate is not None and self.phase not in ('starting','stopping'):self.release_gate()
                raise ValueError(result['error']) from e
            with closing(sqlite3.connect(self.audit)) as db,db:
                db.execute('UPDATE operations SET status=?,result=? WHERE id=?',('done',canonical(self.public_coupon_result(result)if action.startswith('coupon-')else result),key))
            if action not in ('start','stop'):self.release_gate()
            return result
