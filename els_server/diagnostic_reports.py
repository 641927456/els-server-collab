"""Bounded, authenticated diagnostic reports. Report content is untrusted data."""
import asyncio,collections,datetime,hashlib,io,json,os,re,secrets,sqlite3,stat,threading,time,zipfile
from contextlib import closing,contextmanager
from pathlib import Path

MAX_UPLOAD=2*1024*1024
MAX_EXPANDED=8*1024*1024
MAX_MEMBER=2*1024*1024
MAX_COMPRESSION_RATIO=256
RETENTION_SECONDS=7*86400
ORPHAN_SCAN_BUDGET=1024
ORPHAN_DELETE_BUDGET=64
ALLOWED={'manifest.json','summary.json','attempt.json','system.json','resource-fingerprints.json',
         'logs/client-check.log','logs/game-launch.log','logs/startup-error.json','logs/bridge.log',
         'run/trace.jsonl','run/probe.json','run/client-process.json','windows-events.json'}
SECRET_KEYS=re.compile(r'password|passwd|passphrase|token|authorization|cookie|secret|private.?key|session.?key|login$|argument$|密码|口令|令牌|私钥|密钥',re.I)
RAW_KEYS={'hex','wire_hex','data_hex','payload_hex','encrypted_hex','plaintext','packet','body','text','message','chat','commandline','data','bytes','buffer','content'}

def utc_now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def valid_attempt(value):return isinstance(value,str) and re.fullmatch('[a-f0-9]{32}',value) is not None
def redact_text(value):
    value=re.sub(r'(?i)\b(Basic|Bearer)\s+[A-Za-z0-9._~+/=-]+',r'\1 <redacted>',value)
    value=re.sub(r'(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s"\']+',r'\1<user>',value)
    value=re.sub(r'(?i)(["\']?(?:password|passwd|token|authorization|cookie|secret|login|argument)["\']?\s*[:=]\s*)(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s,;}]+)',r'\1"<redacted>"',value)
    value=re.sub(r'(?i)(--(?:password|token|secret|api-key)\s+)(?:"[^"]*"|\S+)',r'\1<redacted>',value)
    value=re.sub(r'(?i)Bearer\s+[A-Za-z0-9._~+/=-]+','Bearer <redacted>',value)
    value=re.sub(r'(?i)((?:密码|口令|令牌|私钥|密钥|password|passwd|token)(?:\s*[:=：]\s*|\s+(?:is\s+)?|(?:是|为)\s*))(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s,;，。}]+)',r'\1<redacted>',value)
    value=re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----','<private-key-redacted>',value,flags=re.S)
    return value

def sanitize(value,depth=0):
    if depth>12:return '<depth-limit>'
    if isinstance(value,dict):
        result={}
        event=value.get('event','')
        preserve_text=bool(re.search('error|fatal|exception|dialog',str(event))) or value.get('type')=='error'
        for key,item in list(value.items())[:128]:
            key=str(key)[:100]
            if SECRET_KEYS.search(key):result[key]='<redacted>'
            elif (key.lower() in RAW_KEYS or (key.lower()=='payload' and not isinstance(item,dict))) and not (key.lower() in ('text','message') and preserve_text):
                encoded=json.dumps(item,ensure_ascii=True).encode()
                result[key+'_summary']={'bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()}
            else:result[key]=sanitize(item,depth+1)
        return result
    if isinstance(value,list):return [sanitize(x,depth+1) for x in value[:512]]
    if isinstance(value,str):return redact_text(value[:12000])
    if value is None or type(value) in (bool,int,float):return value
    return '<unsupported>'

def classify(members):
    text='\n'.join(v.decode('utf8','replace') for k,v in members.items() if k.endswith(('.log','.jsonl')))
    result={'code':'insufficient_evidence','certainty':'unknown','reason':'现有记录尚不足以确定原因。'}
    if 'Relay already connected' in text or 'RelayBusyError' in text:
        return dict(code='relay_busy',certainty='confirmed',reason='服务器拒绝重复中继；需结合连接生命周期判断残留或仍在线。')
    if 'fingerprint mismatch' in text:return dict(code='certificate_pin_mismatch',certainty='confirmed',reason='服务器证书指纹与登录器固定值不一致。')
    if 'Account authentication failed' in text:return dict(code='authentication_rejected',certainty='confirmed',reason='账号连接认证被拒绝。')
    # Use the current attempt's final structured preflight record, not free text
    # or an earlier failed check followed by a successful retry.
    try:attempt=json.loads(members.get('attempt.json',b'{}'))
    except (ValueError,UnicodeError,RecursionError):attempt={}
    if isinstance(attempt,dict) and attempt.get('phase')=='preflight_failed':
        latest=None
        for line in members.get('logs/client-check.log',b'')[:MAX_MEMBER].decode('utf-8-sig','replace').splitlines():
            if not line.startswith('ELS_CLIENT_COMPATIBILITY: '):continue
            latest=None
            if len(line)>16000:continue
            raw=line[len('ELS_CLIENT_COMPATIBILITY: '):]
            try:value=json.loads(raw)
            except (ValueError,RecursionError):
                # V22 decoded UTF-8 using the Windows code page; an error's
                # closing quote can be lost. Only recover the intact ASCII
                # metadata prefix emitted before that final free-text field.
                prefix,separator,_=raw.partition(',"error":')
                if not separator or not prefix.isascii() or len(prefix)>1024:continue
                try:value=json.loads(prefix+'}')
                except (ValueError,RecursionError):continue
                if not isinstance(value,dict) or set(value)!={'schema_version','phase','status','gameplay_accepted','native_live_checks_required','executable_sha256'} or value.get('gameplay_accepted') is not False or value.get('native_live_checks_required') is not True:continue
                value['legacy_error_text_unreadable']=True
            if isinstance(value,dict) and type(value.get('schema_version')) is int and value['schema_version']==1 and value.get('phase')=='disk-preflight':latest=value
        if latest is not None and latest.get('status')=='native-contract-review-required':
            result=dict(code='client_native_contract_review_required',certainty='confirmed_stage',reason='当前客户端 EXE 尚未完成原生接口适配审核，预检已阻止启动；这不等于已确认客户端损坏或不兼容。请提供该 EXE 的原始副本进行版本核对。')
            digest=latest.get('executable_sha256')
            if isinstance(digest,str) and re.fullmatch('[a-f0-9]{64}',digest):result['executable_sha256']=digest
            if latest.get('legacy_error_text_unreadable'):result['legacy_error_text_unreadable']=True
            return result
    native_ready='updated_login_hooks_ready' in text
    for name in ('run/probe.json','run/client-process.json'):
        try:
            value=json.loads(members[name]);native_ready=native_ready or value.get('local_artifact_scene_restore') is True or value.get('local_ed_shop_bridge') is True
        except (KeyError,ValueError,AttributeError):pass
    if 'hooks_unavailable' in text and not native_ready:
        return dict(code='native_interface_not_ready',certainty='confirmed_stage',reason='原生登录接口未在等待期内就绪；具体版本或加载原因仍需核对。')
    for name in ('run/probe.json','run/client-process.json'):
        try:report=json.loads(members[name])
        except (KeyError,ValueError):continue
        if not isinstance(report,dict):continue
        code=report.get('exit_before_cleanup')
        if isinstance(code,int) and code!=0:
            return dict(code='game_exit_nonzero',certainty='observed',reason='游戏返回非零退出码；仅凭退出码不能确定崩溃原因。',exit_code=code)
    try:events=json.loads(members.get('windows-events.json',b'{}'))
    except ValueError:events={}
    if isinstance(events,dict) and events.get('events'):result=dict(code='windows_application_error',certainty='observed',reason='存在同次启动时段的游戏应用程序错误，请核对异常代码及故障模块。')
    return result

def validate_archive(body):
    if not 1<=len(body)<=MAX_UPLOAD:raise ValueError('report_size')
    members={};total=0
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            infos=archive.infolist()
            if not 2<=len(infos)<=len(ALLOWED):raise ValueError('report_members')
            for entry in infos:
                if entry.filename not in ALLOWED or entry.filename in members or entry.flag_bits&1:raise ValueError('report_member')
                if stat.S_ISLNK(entry.external_attr>>16):raise ValueError('report_member')
                if entry.compress_type not in (zipfile.ZIP_DEFLATED,zipfile.ZIP_STORED):raise ValueError('report_compression')
                if entry.file_size>max(1,entry.compress_size)*MAX_COMPRESSION_RATIO:raise ValueError('report_compression_ratio')
                total+=entry.file_size
                if entry.file_size>MAX_MEMBER or total>MAX_EXPANDED:raise ValueError('report_expanded_size')
                raw=archive.read(entry);raw.decode('utf8',errors='strict');members[entry.filename]=raw
        manifest=json.loads(members['manifest.json']);summary=json.loads(members['summary.json'])
        if type(manifest.get('schema')) is not int or manifest['schema']!=1 or type(summary.get('schema')) is not int or summary['schema']!=1:raise ValueError('report_schema')
        if set(manifest.get('files',{}))!=set(members)-{'manifest.json'}:raise ValueError('report_manifest')
        for name,raw in members.items():
            if name!='manifest.json' and manifest['files'][name]!=hashlib.sha256(raw).hexdigest():raise ValueError('report_digest')
        if not valid_attempt(summary.get('attempt_id')) and summary.get('attempt_id') is not None:raise ValueError('report_attempt')
    except (zipfile.BadZipFile,KeyError,UnicodeError,json.JSONDecodeError,RuntimeError,RecursionError,AttributeError,TypeError) as error:raise ValueError('invalid_report') from error
    # Never extract paths or interpret report text as commands/templates.
    return members,summary

class ReportStore:
    def __init__(self,root):
        self.root=Path(root);self._scan=None;self._scan_lock=threading.Lock()

    @staticmethod
    def _stat(path):
        try:return path.lstat()
        except FileNotFoundError:return None

    @staticmethod
    def _regular(value):
        return value is not None and stat.S_ISREG(value.st_mode) and not getattr(value,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400)

    def _check_paths(self,create=False):
        if create:self.root.mkdir(parents=True,exist_ok=True)
        root=self._stat(self.root)
        if root is None:raise FileNotFoundError(self.root)
        if not stat.S_ISDIR(root.st_mode) or getattr(root,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):raise ValueError('invalid_report_root')
        index=self._stat(self.root/'index.sqlite3')
        if index is not None and not self._regular(index):raise ValueError('invalid_report_index')

    @staticmethod
    def _fingerprint(value):
        return (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)

    def _unlink_regular(self,path,expected,cutoff=None):
        current=self._stat(path)
        if not self._regular(current) or self._fingerprint(current)!=self._fingerprint(expected):return False
        if cutoff is not None and current.st_mtime>=cutoff:return False
        try:path.unlink()
        except FileNotFoundError:return False
        return True

    def close(self):
        with self._scan_lock:
            if self._scan is not None:self._scan.close();self._scan=None

    @contextmanager
    def database(self):
        self._check_paths(create=True)
        db=sqlite3.connect(self.root/'index.sqlite3',timeout=10)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,account_id INTEGER,request_id TEXT,digest TEXT,size INTEGER,created REAL,summary TEXT,UNIQUE(account_id,request_id))')
            with db:yield db
        finally:db.close()

    def accept(self,account_id,request_id,digest,body):
        if not valid_attempt(request_id) or hashlib.sha256(body).hexdigest()!=digest:raise ValueError('report_digest')
        members,summary=validate_archive(body)
        server_summary=dict(schema=1,attempt_id=summary.get('attempt_id'),created_utc=summary.get('created_utc'),
                            payload=summary.get('payload'),classification=classify(members),description=sanitize(summary.get('description','')))
        target=None;created=None
        try:
            with self.database() as db:
                db.execute('BEGIN IMMEDIATE')
                self._purge(db)
                old=db.execute('SELECT id,digest FROM reports WHERE account_id=? AND request_id=?',(account_id,request_id)).fetchone()
                if old:
                    if old[1]!=digest:raise ValueError('request_conflict')
                    if not self._regular(self._stat(self.root/(old[0]+'.zip'))):raise ValueError('stored_report_missing')
                    return dict(ok=True,report_id=old[0],duplicate=True)
                now=time.time()
                if db.execute('SELECT count(*) FROM reports WHERE account_id=? AND created>?',(account_id,now-3600)).fetchone()[0]>=5:raise ValueError('report_rate_limited')
                count,physical_size=self._physical_usage()
                used=max(db.execute('SELECT coalesce(sum(size),0) FROM reports').fetchone()[0],physical_size)
                if used+len(body)>256*1024*1024 or max(count,db.execute('SELECT count(*) FROM reports').fetchone()[0])>=512 or db.execute('SELECT count(*) FROM reports WHERE account_id=?',(account_id,)).fetchone()[0]>=50:raise ValueError('report_storage_full')
                report_id='D'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')+'-'+secrets.token_hex(8)
                target=self.root/(report_id+'.zip')
                with target.open('xb') as out:
                    value=os.fstat(out.fileno());created=(value.st_dev,value.st_ino)
                    out.write(body);out.flush();os.fsync(out.fileno())
                db.execute('INSERT INTO reports VALUES(?,?,?,?,?,?,?)',(report_id,account_id,request_id,digest,len(body),now,json.dumps(server_summary,ensure_ascii=True)))
        except BaseException as error:
            if created is not None:
                try:self._compensate(target,created,report_id,account_id,request_id,digest)
                except Exception:error.add_note('Diagnostic ZIP retained: transaction outcome or file cleanup could not be verified.')
            raise
        return dict(ok=True,report_id=report_id,duplicate=False)

    def _physical_usage(self):
        count=0;size=0
        with os.scandir(self.root) as entries:
            for scanned,entry in enumerate(entries,1):
                if scanned>ORPHAN_SCAN_BUDGET:raise ValueError('report_storage_full')
                if not re.fullmatch(r'D[0-9]{8}-[a-f0-9]{16}\.zip',entry.name):continue
                value=self._stat(self.root/entry.name)
                if value is None:continue
                if not self._regular(value):raise ValueError('invalid_report_storage_entry')
                count+=1;size+=value.st_size
                if count>=512:break
        return count,size

    def _compensate(self,target,created,report_id,account_id,request_id,digest):
        self._check_paths()
        # A COMMIT may have succeeded before an exit/close error was raised.
        # No matching durable row means the new owned file may be removed.
        uri=(self.root/'index.sqlite3').resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri,uri=True,timeout=10)) as db:
            row=db.execute('SELECT account_id,request_id,digest FROM reports WHERE id=?',(report_id,)).fetchone()
        if row==(account_id,request_id,digest):return
        if row is not None:raise ValueError('report_compensation_ownership_unknown')
        value=self._stat(target)
        if self._regular(value) and (value.st_dev,value.st_ino)==created:self._unlink_regular(target,value)

    def list(self,limit=20):
        with self.database() as db:
            return [dict(report_id=r[0],account_id=r[1],uploaded_utc=datetime.datetime.fromtimestamp(r[2],datetime.timezone.utc).isoformat(),summary=json.loads(r[3])) for r in db.execute('SELECT id,account_id,created,summary FROM reports WHERE created>=? ORDER BY created DESC LIMIT ?',(time.time()-RETENTION_SECONDS,max(1,min(limit,100))))]

    def _purge(self,db):
        cutoff=time.time()-RETENTION_SECONDS
        expired=db.execute('SELECT id FROM reports WHERE created<? ORDER BY created,id LIMIT ?',(cutoff,ORPHAN_DELETE_BUDGET)).fetchall()
        removed=0
        for (report_id,) in expired:
            if not re.fullmatch(r'D[0-9]{8}-[a-f0-9]{16}',report_id):raise ValueError('invalid_stored_report_id')
            path=self.root/(report_id+'.zip');value=self._stat(path)
            if value is not None:
                if not self._regular(value):continue
                if not self._unlink_regular(path,value) and self._stat(path) is not None:continue
            db.execute('DELETE FROM reports WHERE id=? AND created<?',(report_id,cutoff));removed+=1
        return removed+self._purge_orphans(db,cutoff,ORPHAN_DELETE_BUDGET-removed)

    def _purge_orphans(self,db,cutoff,budget):
        if budget<=0:return 0
        removed=0
        with self._scan_lock:
            if self._scan is None:self._scan=os.scandir(self.root)
            try:
                for _ in range(ORPHAN_SCAN_BUDGET):
                    try:entry=next(self._scan)
                    except StopIteration:self._scan.close();self._scan=None;break
                    if not re.fullmatch(r'D[0-9]{8}-[a-f0-9]{16}\.zip',entry.name):continue
                    path=self.root/entry.name;value=self._stat(path)
                    if not self._regular(value) or value.st_mtime>=cutoff:continue
                    if db.execute('SELECT 1 FROM reports WHERE id=?',(entry.name[:-4],)).fetchone():continue
                    if self._unlink_regular(path,value,cutoff):removed+=1
                    if removed>=budget:break
            except BaseException:
                self._scan.close();self._scan=None;raise
        return removed

    def purge_expired(self):
        if self._stat(self.root) is None:return 0
        self._check_paths()
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE');return self._purge(db)

    def read(self,report_id):
        if not re.fullmatch(r'D[0-9]{8}-[a-f0-9]{16}',report_id):raise ValueError('invalid_report_id')
        with self.database() as db:row=db.execute('SELECT account_id,digest,summary FROM reports WHERE id=? AND created>=?',(report_id,time.time()-RETENTION_SECONDS)).fetchone()
        if row is None:raise ValueError('report_not_found')
        body=(self.root/(report_id+'.zip')).read_bytes()
        if hashlib.sha256(body).hexdigest()!=row[1]:raise ValueError('stored_report_digest')
        members,_=validate_archive(body)
        return dict(untrusted_report_content=True,report_id=report_id,account_id=row[0],summary=json.loads(row[2]),members={k:v.decode('utf8') for k,v in members.items() if k!='manifest.json'})

class UploadService:
    def __init__(self,root):self.store=ReportStore(root);self.windows=collections.OrderedDict();self.active=0;self.task=None

    def start(self):
        async def maintain():
            while True:
                try:await asyncio.to_thread(self.store.purge_expired)
                except (OSError,sqlite3.Error,ValueError):pass
                await asyncio.sleep(3600)
        self.task=asyncio.create_task(maintain(),name='diagnostic-retention')

    async def close(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        await asyncio.to_thread(self.store.close)

    def allow(self,key):
        now=time.monotonic();window=self.windows.pop(key,collections.deque())
        while window and window[0]<now-3600:window.popleft()
        self.windows[key]=window
        while len(self.windows)>2048:self.windows.popitem(last=False)
        if len(window)>=12:return False
        window.append(now);return True

    async def handle(self,application,reader,writer,document,host):
        from els_server.friends_wire import write_json
        reply=dict(ok=False,error='invalid_report_request')
        required={'op','name','token','size','sha256','request_id'}
        if set(document)!=required or type(document.get('size')) is not int or not 1<=document['size']<=MAX_UPLOAD or not isinstance(document.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',document['sha256']) or not valid_attempt(document.get('request_id')):
            await write_json(writer,reply);return
        if not self.allow(('host',host)):
            await write_json(writer,dict(ok=False,error='report_rate_limited'));return
        try:identity=await asyncio.wait_for(application.call(application.registry.authenticate,document['name'],document['token']),8)
        except (ValueError,TypeError):
            await write_json(writer,dict(ok=False,error='bad_credentials'));return
        if self.active>=2 or not self.allow(('account',identity['id'])):
            await write_json(writer,dict(ok=False,error='report_rate_limited'));return
        self.active+=1
        try:
            await write_json(writer,dict(ok=True,ready=True,max_bytes=MAX_UPLOAD))
            async def receive():
                chunks=[];remaining=document['size']
                while remaining:
                    part=await reader.readexactly(min(65536,remaining));chunks.append(part);remaining-=len(part)
                return b''.join(chunks)
            body=await asyncio.wait_for(receive(),30)
            try:reply=await asyncio.to_thread(self.store.accept,identity['id'],document['request_id'],document['sha256'],body)
            except ValueError as error:reply=dict(ok=False,error=str(error))
            except (OSError,sqlite3.Error):reply=dict(ok=False,error='report_storage_unavailable')
            await write_json(writer,reply)
            return reply
        finally:self.active-=1
