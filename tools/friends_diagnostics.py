"""Opt-in diagnostic collection/upload and SSH-local administrator inspection."""
import argparse,asyncio,collections,datetime,hashlib,io,json,os,platform,re,ssl,subprocess,sys,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.diagnostic_reports import (MAX_UPLOAD,MAX_MEMBER,MAX_COMPRESSION_RATIO,ReportStore,classify,redact_text,sanitize,utc_now,valid_attempt)
from els_server.friends_wire import read_json,write_json

def inside(path,root):
    path=Path(path);root=Path(root).resolve()
    resolved=path.resolve()
    try:resolved.relative_to(root)
    except ValueError:raise ValueError('Diagnostic path escapes the launcher directory')
    current=path
    while current!=root and current!=current.parent:
        if current.is_symlink() or (hasattr(current,'is_junction') and current.is_junction()):raise ValueError('Diagnostic links are not followed')
        current=current.parent
    return resolved

def encode(value):return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf8')
def clean_text(text,secrets):
    text=redact_text(text)
    for value in secrets:
        if isinstance(value,str) and len(value)>=3:text=text.replace(value,'<redacted>')
    return text

def bounded_read(path,root,limit=MAX_MEMBER):
    path=inside(path,root)
    with path.open('rb') as stream:
        head=stream.read(limit//2);size=path.stat().st_size
        if size>limit:
            stream.seek(-limit//2,os.SEEK_END)
            return head+b'\n[diagnostic middle omitted: file exceeded limit]\n'+stream.read(limit//2)
        return head+stream.read(limit-len(head))

def log_text(raw,secrets):
    try:text=raw.decode('utf-8-sig')
    except UnicodeError:text=raw.decode('gb18030','replace')
    text=redact_text(text);lines=[];previous=None;repeats=0
    for line in text.splitlines():
        if len(line)>16000:line=line[:12000]+' [long diagnostic line omitted sha256='+hashlib.sha256(line.encode()).hexdigest()+']'
        try:line=json.dumps(sanitize(json.loads(line)),ensure_ascii=False,separators=(',',':'))
        except ValueError:line=redact_text(line)
        if line==previous:
            repeats+=1;continue
        if repeats:lines.append('[previous line repeated '+str(repeats)+' additional times]');repeats=0
        previous=line
        lines.append(clean_text(line,secrets))
    if repeats:lines.append('[previous line repeated '+str(repeats)+' additional times]')
    return '\n'.join(lines).encode('utf8')

def trace_text(path,root,secrets):
    path=inside(path,root);important=collections.deque();ordinary=collections.deque(maxlen=1200);groups={};bytes_seen=0;count=0
    with path.open('rb') as stream:
        while True:
            if bytes_seen>=32*1024*1024:break
            read_limit=min(128*1024,32*1024*1024-bytes_seen)
            line=stream.readline(read_limit);bytes_seen+=len(line)
            if not line or bytes_seen>32*1024*1024 or count>=100000:break
            count+=1
            if not line.endswith(b'\n') and len(line)>=read_limit:
                # Skip a partial/oversize JSON line without treating its tail as a record.
                if not stream.closed:
                    while line and not line.endswith(b'\n') and bytes_seen<32*1024*1024:line=stream.readline(min(128*1024,32*1024*1024-bytes_seen));bytes_seen+=len(line)
                continue
            try:record=json.loads(line)
            except (ValueError,UnicodeError):continue
            if not isinstance(record,dict):continue
            value=record.get('payload',{});event=value.get('event','') if isinstance(value,dict) else ''
            cleaned=sanitize(record)
            if event.startswith('graphics_'):
                key=(event,value.get('api'),value.get('name'),value.get('result'),value.get('caller'))
                group=groups.setdefault(key,dict(first=cleaned,last=cleaned,count=0));group['last']=cleaned;group['count']+=1
            elif record.get('type') in ('error','extension_error') or re.search(r'error|fatal|exception|exit|timeout|unavailable|ready|not_matched|redirect|disconnect',event):
                important.append(cleaned)
                while len(important)>2500:important.popleft()
            else:ordinary.append(cleaned)
    graphic_rows=[]
    for group in list(groups.values())[:128]:
        graphic_rows.append(group['first'])
        if group['count']>1:graphic_rows.append(dict(type='diagnostic_repeat_summary',count=group['count'],last=group['last']))
    priority=list(important)[:25]+list(important)[-250:]+list(reversed(ordinary))+graphic_rows
    rows=[];used=0;seen=set();omitted=0
    for row in priority:
        encoded=encode(row);digest=hashlib.sha256(encoded).digest()
        if digest in seen:continue
        seen.add(digest)
        if used+len(encoded)+1>MAX_MEMBER:omitted+=1;continue
        used+=len(encoded)+1;rows.append(row)
    def timestamp(row):
        value=row.get('payload',{}).get('timestamp',0) if isinstance(row.get('payload'),dict) else 0
        return value if type(value) in (int,float) else 0
    rows.sort(key=timestamp)
    output=b'\n'.join(encode(row) for row in rows)
    return clean_text(output.decode('utf8'),secrets).encode('utf8'),dict(input_lines=count,input_bytes_read=bytes_seen,output_records=len(rows),graphics_repeat_groups=len(groups),byte_budget_omissions=omitted)

def windows_events(start,end,pid=None):
    if os.name!='nt':return dict(status='not_windows',events=[])
    # Application Error/WER only, same launch time window, selected named fields.
    script=r'''$ErrorActionPreference='Stop';[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);$wantedPid=__PID__;$rows=@();Get-WinEvent -FilterHashtable @{LogName='Application';ID=1000,1001;StartTime=[datetime]::Parse('__START__');EndTime=[datetime]::Parse('__END__')} -MaxEvents 100 -ErrorAction SilentlyContinue | ForEach-Object {$x=[xml]$_.ToXml();$d=@{};foreach($p in $x.Event.EventData.Data){if($p.Name){$d[[string]$p.Name]=[string]$p.'#text'}};$matchPid=$true;if($wantedPid -gt 0){$candidate=0;try{if($d.ProcessId -like '0x*'){$candidate=[Convert]::ToInt64($d.ProcessId.Substring(2),16)}else{$candidate=[long]$d.ProcessId}}catch{};$matchPid=$candidate -eq $wantedPid};if($matchPid -and $d.AppName -match '(^|[\\/])x2(_dx11)?\.exe$'){$r=@{event_id=$_.Id;time=$_.TimeCreated.ToUniversalTime().ToString('o')};foreach($k in @('AppName','ModuleName','ExceptionCode','FaultingOffset','ProcessId')){if($d.ContainsKey($k)){$r[$k]=$d[$k]}};$rows+=$r}};ConvertTo-Json -Compress -Depth 5 -InputObject @{status='read';events=@($rows|Select-Object -First 20)}'''
    script=script.replace('__START__',start).replace('__END__',end).replace('__PID__',str(pid if type(pid) is int and 0<pid<2**32 else 0))
    import base64
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode==0:
            result=sanitize(json.loads(result.stdout.decode('utf-8-sig')));result['pid_filter']=pid if type(pid) is int and 0<pid<2**32 else None;return result
    except (OSError,subprocess.TimeoutExpired,ValueError):pass
    return dict(status='unavailable',events=[])

def collect(request,output):
    data=Path(request['data_root']).resolve();payload=inside(request['payload_root'],data/'versions')
    attempt=request.get('attempt_id');members={};omissions=[];secrets_list=[request.get('token','')]
    if attempt is not None and not valid_attempt(attempt):raise ValueError('Invalid diagnostic attempt')
    logs=inside(data/'logs/attempts'/attempt,data) if attempt else data/'logs'
    meta={}
    if attempt:
        try:meta=json.loads(bounded_read(logs/'attempt.json',data))
        except (OSError,ValueError):omissions.append('attempt_metadata_unavailable')
        if not isinstance(meta,dict):meta={};omissions.append('attempt_metadata_invalid')
        if meta.get('attempt_id') not in (None,attempt):raise ValueError('Diagnostic attempt metadata differs')
    def add(name,path,kind='log'):
        try:
            raw=bounded_read(path,data,256*1024 if kind=='json' else 512*1024)
            if kind=='json':raw=encode(sanitize(json.loads(raw)))
            else:raw=log_text(raw,secrets_list)
            raw=clean_text(raw.decode('utf8'),secrets_list).encode('utf8')
            if len(raw)>MAX_MEMBER:omissions.append(name+':sanitized_size');return
            members[name]=raw
        except (OSError,ValueError):omissions.append(name+':unavailable')
    for name in ('client-check.log','game-launch.log'):
        add('logs/'+name,logs/name)
    if meta:members['attempt.json']=encode(sanitize(meta))
    if not attempt:add('logs/startup-error.json',data/'logs/startup-error.json','json')
    launch=members.get('logs/game-launch.log',b'').decode('utf8')
    # Select paths from this attempt's original, bounded launch log only.
    try:original=bounded_read(logs/'game-launch.log',data).decode('utf-8-sig','replace')
    except OSError:original=''
    run=None;bridge=None;report=None
    for line in original.splitlines():
        if line.startswith('ELS_DIAGNOSTIC_BRIDGE: '):
            try:
                value=json.loads(line.split(': ',1)[1])
                if value.get('attempt_id')==attempt:bridge=inside(payload/value['path'],data)
            except (ValueError,KeyError):pass
        elif line.startswith('{'):
            try:
                candidate=json.loads(line)
                if isinstance(candidate,dict) and 'file_sha256' in candidate:report=candidate
            except ValueError:pass
        elif re.search(r'[\\/]analysis[\\/]client-[a-f0-9]{8}[\\/][0-9]{8}-[0-9]{6}$',line.strip()):
            try:
                selected=inside(Path(line.strip()),data)
                if attempt and meta.get('started_utc'):
                    when=datetime.datetime.strptime(selected.name,'%Y%m%d-%H%M%S').astimezone()
                    earliest=datetime.datetime.fromisoformat(meta['started_utc'])-datetime.timedelta(seconds=5)
                    latest=datetime.datetime.fromisoformat(meta.get('ended_utc',utc_now()))+datetime.timedelta(seconds=5)
                    if not earliest<=when<=latest:raise ValueError('Different diagnostic run time')
                run=selected
            except ValueError:pass
    if run:
        # The exact path logged by this run wins; never glob the newest trace.
        for name in ('probe.json','client-process.json'):add('run/'+name,run/name,'json')
        try:
            trace,stats=trace_text(run/'trace.jsonl',data,secrets_list);members['run/trace.jsonl']=trace
        except (OSError,ValueError):omissions.append('run/trace.jsonl:unavailable');stats={}
    else:stats={};omissions.append('run_directory_not_recorded')
    if report and 'run/probe.json' not in members:members['run/probe.json']=encode(sanitize(report))
    if bridge:add('logs/bridge.log',bridge/'bridge.log')
    else:
        candidates=[]
        try:
            start_dt=datetime.datetime.fromisoformat(meta['started_utc']);end_dt=datetime.datetime.fromisoformat(meta.get('ended_utc',utc_now()))
            for path in (payload/'state/friends-client').iterdir():
                try:
                    # Existing folder names use local wall time; compare to the
                    # same player's UTC->local attempt window, never to file copy time.
                    stamp=datetime.datetime.strptime(path.name,'%Y%m%d-%H%M%S-%f').astimezone()
                    if start_dt-datetime.timedelta(seconds=1)<=stamp<=end_dt+datetime.timedelta(seconds=1):candidates.append(inside(path,data))
                except (ValueError,OSError):pass
        except (KeyError,OSError,ValueError):pass
        if len(candidates)==1:add('logs/bridge.log',candidates[0]/'bridge.log')
        else:omissions.append('bridge_directory_ambiguous' if candidates else 'bridge_directory_not_recorded')
    members['system.json']=encode(dict(os=platform.system(),version=platform.version(),machine=platform.machine(),python=platform.python_version()))
    # Fingerprint only the selected small compatibility archives; never upload them.
    fingerprints=[];client_path=Path(request['client_path']) if request.get('client_path') else None
    for name in ('data036.kom','datai015.kom'):
        if client_path:
            path=client_path.parent/name
            try:
                entry=dict(file=name,size=path.stat().st_size)
                if entry['size']<=64*1024*1024:
                    with path.open('rb') as stream:entry['sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
                else:entry['hash_status']='size_only_over_64MiB'
                fingerprints.append(entry)
            except OSError:fingerprints.append(dict(file=name,status='unavailable'))
    members['resource-fingerprints.json']=encode(fingerprints)
    start=meta.get('started_utc');end=meta.get('ended_utc',utc_now())
    # Parse and normalize before embedding times in the fixed event-log query.
    try:
        if start is None:raise ValueError('Missing attempt time')
        start_time=datetime.datetime.fromisoformat(start);end_time=datetime.datetime.fromisoformat(end)
        if end_time<start_time or (end_time-start_time).total_seconds()>86400:raise ValueError()
        event_report=report or json.loads(members.get('run/client-process.json',b'{}'))
        members['windows-events.json']=encode(windows_events((start_time-datetime.timedelta(seconds=5)).isoformat(),(end_time+datetime.timedelta(seconds=5)).isoformat(),event_report.get('pid')))
    except (ValueError,TypeError):omissions.append('windows_events:invalid_or_missing_time_window')
    summary=dict(schema=1,attempt_id=attempt,created_utc=utc_now(),payload=payload.name,description=clean_text(str(request.get('description',''))[:2000],secrets_list),classification=classify(members),omissions=omissions,trace_reduction=stats,collection='explicit_player_action',raw_binaries_included=False)
    members['summary.json']=encode(summary)
    members['manifest.json']=encode(dict(schema=1,files={k:hashlib.sha256(v).hexdigest() for k,v in members.items()}))
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        import zlib
        for name,raw in sorted(members.items()):
            compressor=zlib.compressobj(9,wbits=-15);compressed=compressor.compress(raw)+compressor.flush()
            method=zipfile.ZIP_STORED if len(raw)>max(1,len(compressed))*MAX_COMPRESSION_RATIO else zipfile.ZIP_DEFLATED
            archive.writestr(name,raw,compress_type=method)
    body=buffer.getvalue()
    if len(body)>MAX_UPLOAD:raise ValueError('压缩后诊断包超过2 MiB，请保留本地文件联系房主。')
    from els_server.diagnostic_reports import validate_archive
    validate_archive(body)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(body)
    return dict(ok=True,archive=str(output),sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),expanded_bytes=sum(map(len,members.values())),files=sorted(members),classification=summary['classification'],omissions=omissions)

async def upload(request,archive,request_id):
    body=Path(archive).read_bytes();context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname=False;context.verify_mode=ssl.CERT_NONE;context.minimum_version=ssl.TLSVersion.TLSv1_2
    writer=None
    try:
        async with asyncio.timeout(45):
            reader,writer=await asyncio.open_connection(request['host'],int(request.get('port',19400)),ssl=context,server_hostname=request['host'])
            certificate=writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
            if hashlib.sha256(certificate).hexdigest()!=request['certificate_sha256']:raise ValueError('Server certificate fingerprint mismatch')
            await write_json(writer,dict(op='diagnostic_upload',name=request['name'],token=request['token'],size=len(body),sha256=hashlib.sha256(body).hexdigest(),request_id=request_id))
            ready=await read_json(reader)
            if not ready.get('ready'):return ready
            for offset in range(0,len(body),65536):
                writer.write(body[offset:offset+65536]);await writer.drain()
            return await read_json(reader)
    finally:
        if writer:
            writer.close()
            try:await asyncio.wait_for(writer.wait_closed(),5)
            except (OSError,TimeoutError):pass

def correlate_server(report,members,folder):
    try:
        meta=json.loads(members['attempt.json']);start=datetime.datetime.fromisoformat(meta['started_utc'])-datetime.timedelta(seconds=10)
        end=datetime.datetime.fromisoformat(meta.get('ended_utc') or report['summary'].get('created_utc'))+datetime.timedelta(seconds=10)
        if end<start or (end-start).total_seconds()>86400:raise ValueError()
    except (KeyError,ValueError,TypeError):return dict(status='attempt_time_unavailable',events=[])
    rows=[];root=Path(folder)
    for name in ['server.jsonl']+['server.jsonl.'+str(n) for n in range(1,5)]:
        try:raw=bounded_read(root/name,root,6*1024*1024).decode('utf8','replace')
        except (OSError,ValueError):continue
        for line in raw.splitlines():
            try:
                event=json.loads(line);at=datetime.datetime.fromisoformat(event['time'])
                if start<=at<=end:rows.append(event)
            except (ValueError,KeyError,TypeError):continue
    ids={e['connection'] for e in rows if e.get('event')=='authenticated' and e.get('account_id')==report['account_id'] and 'connection' in e}
    kinds={'authenticated','business_phase','protocol_error','connection_error','worker_error','connection_timeout','connection_finished','relay_opened','relay_closed','relay_heartbeat_timeout'}
    selected=[sanitize(e) for e in rows if e.get('event') in kinds and (e.get('connection') in ids or e.get('account_id')==report['account_id'])]
    selected.sort(key=lambda e:e['time'])
    return dict(status='matched_account_and_time' if ids else 'no_authenticated_identity_in_retained_window',connection_ids=sorted(ids),events=selected[-1000:],unrelated_connections_excluded=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    make=sub.add_parser('collect');make.add_argument('--request',type=Path,required=True);make.add_argument('--output',type=Path,required=True);make.add_argument('--receipt',type=Path,required=True);make.add_argument('--upload',action='store_true')
    listing=sub.add_parser('list');listing.add_argument('--root',type=Path,required=True);listing.add_argument('--limit',type=int,default=20)
    show=sub.add_parser('show');show.add_argument('--root',type=Path,required=True);show.add_argument('--id',required=True);show.add_argument('--file',choices=sorted(__import__('els_server.diagnostic_reports',fromlist=['ALLOWED']).ALLOWED));show.add_argument('--max-chars',type=int,default=60000);show.add_argument('--server-logs',type=Path)
    send=sub.add_parser('send');send.add_argument('--request',type=Path,required=True);send.add_argument('--archive',type=Path,required=True);send.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='list':print(json.dumps(ReportStore(args.root).list(args.limit),ensure_ascii=True));return 0
    if args.action=='show':
        report=ReportStore(args.root).read(args.id);members=report.pop('members');report['files']={k:len(v.encode('utf8')) for k,v in members.items()}
        if args.server_logs:report['server_correlation']=correlate_server(report,members,args.server_logs)
        if args.file:
            content=members.get(args.file,'');limit=max(1000,min(args.max_chars,200000));report.update(selected_file=args.file,content=content[:limit],truncated=len(content)>limit)
        print(json.dumps(report,ensure_ascii=True));return 0
    request=json.loads(args.request.read_text(encoding='utf-8-sig'));result={}
    try:
        if args.action=='send':
            from els_server.diagnostic_reports import validate_archive
            validate_archive(args.archive.read_bytes());result=dict(ok=True,archive=str(args.archive))
        else:result=collect(request,args.output)
        sending=args.action=='send' or args.upload
        if sending:
            # One stable UUID for both transmission attempts, so an uncertain
            # acknowledgement cannot create duplicate server reports.
            for attempt in range(2):
                try:
                    reply=asyncio.run(upload(request,args.archive if args.action=='send' else args.output,request['request_id']));break
                except (OSError,TimeoutError,asyncio.IncompleteReadError):
                    if attempt:raise
            result['upload']=reply
            if not reply.get('ok'):result['upload_failed']=True
    except Exception as error:
        result.update(ok=False,error=type(error).__name__,upload_failed=bool(args.action=='send' or getattr(args,'upload',False)))
    args.receipt.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
    return 0 if result.get('ok') and not result.get('upload_failed') else 2

if __name__=='__main__':raise SystemExit(main())
