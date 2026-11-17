"""Bounded evidence for the four unresolved automatic-report groups.

Compose against exact source anchors before launch. Keep the existing guards,
startup order, exception propagation and partial-stack collector unchanged.
"""
from collections import OrderedDict, deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading

KNOWN_EXE='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'


def replace_once(source, old, new):
    if source.count(old)!=1:raise ValueError('Failure evidence source anchor mismatch: '+old[:90])
    return source.replace(old,new,1)


def scene_source():
    return Path(__file__).with_name('native_failure_scene.js').read_text(encoding='utf8')+'\n'


def compose_fatal(source, digest):
    source=replace_once(source,'size:m.size,module_messages_dropped:', 'size:m.size,path:m.path,module_messages_dropped:')
    source=replace_once(source,'   send(out);',
        "   elsEvidenceRead(out,'fault_scene',()=>elsFaultScene(out,"+str(digest==KNOWN_EXE).lower()+"));\n   send(out);")
    source=replace_once(source,"    send({event:'original_fatal_stack',",
        "    const extra={};elsEvidenceRead(extra,'stack_candidates',()=>elsStackCandidates(bytes));\n    send({...extra,event:'original_fatal_stack',")
    return scene_source()+source


def compose_stack(source):
    facts={
        'Anniversary action book allocation outside native offset range':"{displacement,page:page.toString(),page_size:Process.pageSize,strings:strings.toString()}",
        'Anniversary record bounds':"{template:book.template,cursor,record_length:record.length,page_size:Process.pageSize}",
        'Anniversary record ID':"{template:book.template,row:row.toString()}",
        'Anniversary link bounds':"{template:book.template,field,cursor,payload_length:payload.length,page_size:Process.pageSize}",
        'Anniversary record protection':"{page:page.toString(),page_size:Process.pageSize}",
        'Template vector bounds':"{bytes}",
        'Template table count/range':"{count:n,required,bytes}",
        'Native template row bounds':"{count:n,offset,rows:rows.toString()}",
        'Native template row is not readable/writable':"{range:range?{base:range.base.toString(),size:range.size,protection:range.protection}:null}",
        'Native template key/row invariant':"{offset,expected_template:id}",
    }
    for message,fields in facts.items():
        source=replace_once(source,"throw Error('"+message+"')","throw elsGuardError('"+message+"',"+fields+")")
    source=replace_once(source,"          emit({status: 'guard-rejected', error: String(error)});",
        "          const evidence={};elsEvidenceRead(evidence,'guard_context',()=>elsGuardScene(this.manager,this.id,row,this.action,error,image.base));\n          emit({status: 'guard-rejected', error: String(error), ...evidence});")
    return scene_source()+source


def compose_startup(source):
    helper="""
let elsStartupEvidenceSequence=0,elsStartupEvidenceDropped=0;
function elsStartupCheckpoint(name,phase,start){
 try{note({event:'native_startup_checkpoint',name,phase,thread:Process.getCurrentThreadId(),timestamp:Date.now(),sequence:++elsStartupEvidenceSequence,elapsed_ms:Date.now()-start,dropped:elsStartupEvidenceDropped});}
 catch(error){elsStartupEvidenceDropped++;}
}
function elsStartupObserved(name,call){
 const start=Date.now();elsStartupCheckpoint(name,'enter',start);
 try{const value=call();elsStartupCheckpoint(name,'return',start);return value;}
 catch(error){elsStartupCheckpoint(name,'throw',start);throw error;}
}
let elsStartupGateLast=null,elsStartupVisibilityEvidence=null;
function elsStartupGate(){
 let checked=0,mismatch=null;
 const ready=Object.entries(verifiedPrefixes).every(([r,h])=>{
  const actual=Array.from(new Uint8Array(game.base.add(Number(r)).readByteArray(8)),v=>v.toString(16).padStart(2,'0')).join('');
  checked++;if(actual!==h)mismatch={rva:Number(r),expected:h,actual};return actual===h;
 });
 const visibility=ready?elsStartupVisibilityReady():null;
 elsStartupGateLast={checked,first_mismatch:mismatch,visibility_ready:visibility,visibility_first_mismatch:ready?elsStartupVisibilityEvidence:null};
 if(tries===1||tries%50===0||ready&&visibility){
  try{note({event:'native_startup_gate',timestamp:Date.now(),thread:Process.getCurrentThreadId(),tries,...elsStartupGateLast});}catch(error){elsStartupEvidenceDropped++;}
 }
 return ready&&visibility;
}
"""
    source=replace_once(source,'function elsStartupVisibilityReady() {',
        'function elsStartupVisibilityReady() {\n  elsStartupVisibilityEvidence=null;')
    source=replace_once(source,
        '].every(([slot, rva]) => game.base.add(slot).readPointer().equals(game.base.add(rva)));',
        "].every(([slot,rva])=>{const actual=game.base.add(slot).readPointer(),ready=actual.equals(game.base.add(rva));if(!ready)elsStartupVisibilityEvidence={slot,expected_rva:rva,actual:actual.toString()};return ready;});")
    source=replace_once(source,'let tries=0;\nconst timer=setInterval(()=>{',helper+'\nlet tries=0;\nconst timer=setInterval(()=>{')
    gate="Object.entries(verifiedPrefixes).every(([r,h])=>Array.from(new Uint8Array(game.base.add(Number(r)).readByteArray(8)),v=>v.toString(16).padStart(2,'0')).join('')===h)&&elsStartupVisibilityReady()"
    source=replace_once(source,gate,'elsStartupGate()')
    start=source.index('let tries=0;\nconst timer=setInterval(()=>{')
    before,tail=source[:start],source[start:]
    calls=['installElsPartyInactivity()','installElsQuestSkillOwnershipHide()',
           'installElsAccountWeeklyAccept()','installElsResonanceBookUse()',
           'prepareElsNativeSendSerialization()()','installElsChallengeScrollSupport()',
           'installElsActivityGuideLifecycle()','installElsStartupVisibility()',
           'installElsHeroRetryFactors(game)','installElsWearSync()',
           'installElsSparseStages()','installElsGroundModels()','installElsRelationSourceSync()']
    for call in calls:
        tail=replace_once(tail,call+';',"elsStartupObserved('"+call.split('(')[0]+"',()=>"+call+');')
    # Covers the rest of the gate callback, including later hook installation.
    tail=replace_once(tail,'  clearInterval(timer);',"  clearInterval(timer);\n  elsStartupCheckpoint('startup_install_sequence','enter',Date.now());")
    tail=replace_once(tail,"note({event:'updated_login_hooks_ready'", "elsStartupCheckpoint('startup_install_sequence','return',Date.now());note({event:'updated_login_hooks_ready'")
    return before+tail


def bounded(value, depth=0):
    """Internal structured metadata only; reject unbounded/opaque payloads."""
    if depth>7:return '[depth omitted]'
    if value is None or type(value) in (bool,int,float):return value
    if isinstance(value,str):return value[:240]
    if isinstance(value,list):return [bounded(v,depth+1) for v in value[:32]]
    if isinstance(value,dict):
        return {str(k)[:64]:bounded(v,depth+1) for k,v in list(value.items())[:40]
                if k not in ('path','hex','raw_stack','password','token')}
    return None


def capture_host_failure(pid,created,thread=0):
    if type(pid) is not int or type(created) not in (int,float) or created<=0:
        return dict(status='identity_unavailable',samples=[])
    command=[sys.executable,str(Path(__file__).with_name('windows_failure_snapshot.py')),str(pid),str(created),str(thread or 0)]
    status='completed';output=b''
    try:
        result=subprocess.run(command,capture_output=True,timeout=3,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        output=result.stdout
        if result.returncode:status='helper_failed'
    except subprocess.TimeoutExpired as error:
        status='helper_timeout';output=error.stdout or b''
    except OSError as error:
        return dict(status='helper_unavailable',error_type=type(error).__name__,samples=[])
    samples=[]
    for line in output[:32768].splitlines()[:12]:
        try:samples.append(bounded(json.loads(line)))
        except (ValueError,UnicodeDecodeError):samples.append(dict(status='invalid_helper_record'))
    return dict(status=status,samples=samples,limit_seconds=3,privileges_changed=False,threads_suspended=False)


def module_identity(path):
    """Identity of the disk file named by the module observer, not memory bytes."""
    result=dict(status='unavailable',source='observed_loaded_module_path',memory_identity_proven=False)
    try:
        target=Path(path);before=target.stat()
        if not 0<before.st_size<=128*1024*1024:return dict(result,status='size_limit',size=before.st_size)
        digest=hashlib.sha256()
        with target.open('rb') as stream:
            header=stream.read(4096);digest.update(header)
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
            if header[:2]!=b'MZ':raise ValueError('not_pe')
            pe=struct.unpack_from('<I',header,0x3c)[0]
            if not 0<=pe<=1024*1024:raise ValueError('pe_header_limit')
            stream.seek(pe);image=stream.read(88)
        after=target.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
            return dict(result,status='file_changed_during_read')
        if image[:4]!=b'PE\0\0':raise ValueError('not_pe')
        result.update(status='read',size=before.st_size,sha256=digest.hexdigest(),
                      pe_timestamp=struct.unpack_from('<I',image,8)[0],image_size=struct.unpack_from('<I',image,80)[0])
    except (OSError,ValueError,struct.error) as error:result['error_type']=type(error).__name__
    return result


def capture_module_identity(path):
    # The NVIDIA fault module is about 90 MiB. A cold/remote disk read must not
    # hold the existing report worker past its final-upload deadline.
    try:
        result=subprocess.run([sys.executable,str(Path(__file__)),'--module-identity',str(path)],
            capture_output=True,timeout=3,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:return dict(status='identity_helper_failed')
        return bounded(json.loads(result.stdout))
    except subprocess.TimeoutExpired:return dict(status='identity_read_timeout',limit_seconds=3)
    except (OSError,ValueError) as error:return dict(status='identity_unavailable',error_type=type(error).__name__)


class FailureEvidence:
    def __init__(self):
        self.lock=threading.RLock();self.startup=deque(maxlen=32);self.gate=None
        self.modules=OrderedDict();self.identities={};self.host=None
        self.event_samples=[]

    def observe(self,message):
        value=message.get('payload') if isinstance(message,dict) else None
        if not isinstance(value,dict):return
        event=value.get('event')
        if event not in ('native_startup_checkpoint','native_startup_gate','module_loaded'):return
        with self.lock:
            if event=='native_startup_checkpoint':
                self.startup.append(bounded({k:value[k] for k in ('name','phase','thread','timestamp','sequence','elapsed_ms','dropped') if k in value}))
            elif event=='native_startup_gate':self.gate=bounded(value)
            elif event=='module_loaded' and all(isinstance(value.get(k),str) for k in ('base','path','name')):
                self.modules[value['base']]=dict(path=value['path'],name=value['name'])
                if len(self.modules)>256:self.modules.popitem(last=False)

    def capture_host(self,runtime):
        with self.lock:
            if self.host is not None:return
            thread=self.startup[-1].get('thread',0) if self.startup else (self.gate or {}).get('thread',0)
        result=capture_host_failure(runtime.get('process_id'),runtime.get('process_created'),thread)
        with self.lock:self.host=result

    def snapshot(self,message):
        value=message.get('payload') if isinstance(message.get('payload'),dict) else message
        result={}
        with self.lock:
            for key in ('fault_scene','guard_context','read_errors'):
                if key in value:result[key]=bounded(value[key])
            if message.get('script_source')=='host_probe' or value.get('event')=='native_startup_failed':
                result.update(startup_checkpoints=list(self.startup)[-16:],startup_gate=self.gate,host_failure=self.host)
        return deepcopy(result)

    def enrich(self,document, runtime):
        rows=document.get('events',[])
        relevant=[r for r in rows if r.get('signal') in ('native_exception','abnormal_exit','observer_crash')
                  or r.get('event') in ('component_attach_failed','component_process_query_failed')
                  or r.get('script_source')=='host_probe']
        if not relevant:return
        from friends_diagnostics import windows_events
        # At most two bounded event-log reads per launch. Final exit can have a
        # later Windows event than the first fatal report; no periodic polling.
        latest=max(r['observed_utc'] for r in relevant)
        if len(self.event_samples)<2 and (not self.event_samples or latest>self.event_samples[-1]['through_utc']):
            created=runtime.get('process_created');pid=runtime.get('process_id')
            if type(created) in (int,float) and created>0 and type(pid) is int and pid>0:
                end=datetime.now(timezone.utc);start=datetime.fromtimestamp(max(created,end.timestamp()-60),timezone.utc)
                events=windows_events(start.isoformat(),end.isoformat(),pid)
                self.event_samples.append(dict(through_utc=end.isoformat(),association='same_pid_and_launch_time_window',**bounded(events)))
            else:self.event_samples.append(dict(through_utc=latest,status='identity_unavailable',events=[]))
        for row in relevant:
            evidence=row.setdefault('context',{}).setdefault('failure_evidence',{})
            evidence['windows_events']=deepcopy(self.event_samples[-1])
            scene=evidence.get('fault_scene',{});module=scene.get('module',{})
            with self.lock:loaded=self.modules.get(module.get('base'))
            if loaded and loaded['name']==module.get('name'):
                path=loaded['path']
                if path not in self.identities and len(self.identities)<2:self.identities[path]=capture_module_identity(path)
                evidence['module_file']=self.identities.get(path,dict(status='identity_limit'))
            elif row.get('signal')=='native_exception':evidence['module_file']=dict(status='loaded_path_unavailable')


def bound_row(row):
    """Preserve the failure scene before older routine context if near 16 KiB."""
    def size():return len(json.dumps(row,ensure_ascii=True,separators=(',',':')).encode())
    if size()<=16000:return
    context=row.get('context',{});context.pop('recent_client_detail',None);row['component_calls']=[]
    row['details_omitted_for_size']=True
    evidence=context.get('failure_evidence',{})
    if size()>16000 and 'startup_checkpoints' in evidence:
        evidence['startup_checkpoints']=evidence['startup_checkpoints'][-4:]
    if size()>16000 and 'windows_events' in evidence:
        evidence['windows_events']=dict(status='omitted_for_row_limit')
    if size()>16000:
        evidence['omitted_fields']=[]
        for key in ('host_failure','stack_candidates','fault_scene','guard_context'):
            if size()<=16000:break
            if key in evidence:evidence.pop(key);evidence['omitted_fields'].append(key)


if __name__=='__main__' and len(sys.argv)==3 and sys.argv[1]=='--module-identity':
    print(json.dumps(module_identity(sys.argv[2]),separators=(',',':')),flush=True)
