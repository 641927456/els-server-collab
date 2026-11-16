"""Body-free gameplay observations; observations are not root-cause verdicts."""
from collections import Counter, deque, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
import traceback
import struct
from copy import deepcopy
import json

SIGNALS = frozenset(('native_exception', 'native_dialog', 'blank_dialog', 'support_error',
                     'support_fault', 'abnormal_exit', 'observer_crash'))

# Only layouts whose result field is defined by the current message encoders.
# Do not guess that the first integer in every native response is a status.
RESULT_FIELDS = {0x114:0, 0x65f:0, 0x10a:0, 0x556:-4,
                 0x18d:0, 0x205:0, 0x810:0, 0x105:-4,
                 0x21a:0,0x197:0,0x55a:0,0xef:0,0xf5:0,0x472:0,0x30b:0,0xb9:0,0xbc:0}
REPLY_CONTRACTS={0x219:0x21a,0x559:0x55a,0x196:0x197,
                 0xee:0xef,0xf4:0xf5,0x30a:0x30b,0x471:0x472,0xb8:0xb9,0xbb:0xbc}


def reply_gap(event,replies):
    expected=REPLY_CONTRACTS.get(event.kind) if event.event_id==0x202 else None
    if expected is None or any(reply.event_id==0x201 and reply.kind==expected for reply in replies):return None
    return dict(topic='request_reply',reason='expected_reply_not_generated',
                details=dict(request_kind=event.kind,expected_kind=expected,
                             generated_kinds=[reply.kind for reply in replies][:16],
                             meaning='observed output gap; may be an intentional rejection or route mismatch'))


def result_code(message):
    offset=RESULT_FIELDS.get(message.kind)
    if message.event_id != 0x201 or offset is None or len(message.payload)<4:
        return None
    return struct.unpack_from('>i',message.payload,len(message.payload)+offset if offset<0 else offset)[0]


def result_text_status(code):
    from els_server.result_messages import result_messages
    catalog=result_messages()
    if code<0 or code>=len(catalog._texts):return dict(text_status='outside_native_table',blank_text_possible=True)
    text=catalog.text(code)
    if '\ufffd' in text:return dict(text_status='extracted_text_decode_uncertain',blank_text_possible=False)
    return dict(text_status='mapped_text' if text.strip() else 'empty_native_text',
                blank_text_possible=not bool(text.strip()))


def report_summary(document):
    if not isinstance(document, dict) or type(document.get('schema')) is not int or document['schema'] != 1:
        return None
    rows = document.get('events')
    if not isinstance(rows, list):
        return None
    counts = Counter(row['signal'] for row in rows[:32]
                     if isinstance(row, dict) and isinstance(row.get('signal'),str) and row['signal'] in SIGNALS)
    if not counts:
        return None
    return dict(signals=dict(counts), observations=sum(counts.values()),
                source='client_observation', root_cause_confirmed=False)


def context(session):
    if session is None:
        return {}
    result = dict(uid=session.account.uid, phase=session.phase,
                  role=session.role, map=session.active_map)
    run = getattr(session, 'dungeon_run', None)
    if run is not None:
        result.update(dungeon=run.identity, stage=run.stage, part=run.part)
    return result


def request_details(event):
    """Use only the input shapes defined by the existing request readers."""
    data=event.payload;result=dict(payload_bytes=len(data))
    if event.event_id!=0x202:return result
    if event.kind in (0x113,0x65e) and len(data)==5:
        slot,mode,party,special=struct.unpack('>HBBB',data)
        result.update(slot=slot,mode=mode,party=party,special=special)
    elif event.kind==0x219 and len(data)==29:
        uid,target,a,b,n,flag=struct.unpack('>QQiiIB',data)
        result.update(item_uid=uid,target_uid=target,option=a,secondary_option=b,string_units=n,flag=flag)
    elif event.kind in (0xee,0xf4,0xfa) and len(data)>=4:
        result['quest']=struct.unpack_from('>i',data)[0]
        if len(data)>=8:result['npc']=struct.unpack_from('>i',data,4)[0]
    elif event.kind==0x30a and len(data)==4:result['trigger']=struct.unpack('>i',data)[0]
    elif event.kind in (0xb8,0xbb) and len(data)==1:result['part']=struct.unpack('>b',data)[0]
    elif event.kind==0x471 and len(data)>=14:
        stage,part,_,count=struct.unpack_from('>iiHI',data)
        result.update(stage=stage,part=part,condition_count=count)
    elif event.kind==0x559 and len(data)>=10:
        template,count=struct.unpack_from('>iI',data);result.update(template=template,choice_count=count)
    elif event.kind==0x196 and len(data)>=19:
        result['item_uid']=struct.unpack_from('>Q',data)[0]
    elif event.kind==0x104 and len(data)==11:
        sg,ss,dg,ds,flag=struct.unpack('>BiBiB',data)
        result.update(source=[sg,ss],destination=[dg,ds],flag=flag)
    elif event.kind==0x555 and len(data)==14:
        sg,ss,dg,ds,quantity=struct.unpack('>BiBii',data)
        result.update(source=[sg,ss],destination=[dg,ds],quantity=quantity)
    elif event.kind==0x109 and len(data)==12:
        uid,quantity=struct.unpack('>Qi',data);result.update(item_uid=uid,quantity=quantity)
    elif event.kind==0x204 and len(data)==10:
        uid,slot,target=struct.unpack('>QBB',data);result.update(item_uid=uid,slot=slot,target=target)
    elif event.kind==0x18c and len(data)>=10:
        count=struct.unpack_from('>I',data)[0]
        result['item_count']=count
        if len(data)==10+8*count:
            a,b,form=struct.unpack_from('>BBi',data,4+8*count);result.update(flag_a=a,flag_b=b,form=form)
    return result


class IncidentHistory:
    """Retain bounded relevant server evidence across disconnect/log rotation."""
    def __init__(self):self.sessions=OrderedDict();self.omitted={}

    def record(self,event,fields):
        account=fields.get('account_id');session=fields.get('diagnostic_session')
        if not account or not session:return
        if event=='request_timing' and not fields.get('failed') and fields.get('total_ms',0)<1000:return
        if event not in ('authenticated','business_phase','worker_error','protocol_error','connection_error',
                         'connection_eof','connection_timeout','connection_finished','notification_error',
                         'business_rejection','gameplay_result_nonzero','request_timing','gameplay_observation'):return
        key=(account,session)
        rows=self.sessions.setdefault(key,deque());self.sessions.move_to_end(key)
        while len(self.sessions)>128:
            old,_=self.sessions.popitem(last=False);self.omitted.pop(old,None)
        row=dict(event=event,time=datetime.now(timezone.utc).isoformat(),**fields)
        if 'recent_requests' in row:row['recent_requests']=row['recent_requests'][-8:]
        if 'calls' in row:row['calls']=[{k:v for k,v in call.items() if k!='rejections'} for call in row['calls'][-4:]]
        # Detailed recent request lists already accompany terminal errors.
        size=len(json.dumps(row,ensure_ascii=True).encode())
        if size>65536:
            self.omitted[key]=self.omitted.get(key,0)+1;return
        while rows and (len(rows)>=32 or sum(size for size,_ in rows)+size>65536):
            rows.popleft();self.omitted[key]=self.omitted.get(key,0)+1
        rows.append((size,deepcopy(row)))

    def snapshot(self,account,session):
        key=(account,session)
        rows=[row for _,row in list(self.sessions.get(key,()))[-24:]]
        if rows:rows[-1]={**rows[-1],'history_omitted':self.omitted.get(key,0)}
        return deepcopy(rows)


class SessionDiagnostics:
    def __init__(self, connection):
        self.connection = connection
        self.recent = deque(maxlen=32)
        self.requests_seen = 0
        self.results = Counter()
        self.result_logs = 0
        self.result_codes_omitted = 0
        self.rejections=Counter()
        self.observations=Counter()

    def observation(self,value):
        if value.get('topic')in('gameplay_progress','gameplay_delivery'):return True
        details=value.get('details',{})
        if value.get('topic')=='dungeon_actor':
            details={k:details.get(k)for k in ('scene','actor','reason','facts')}
        elif value.get('topic')=='dungeon_gate':
            details={**{k:v for k,v in details.items()if k not in ('condition_checks','actor_rejections')},
                'rejection_reasons':sorted({(r.get('actor'),r.get('reason'))for r in details.get('actor_rejections',[])})}
        elif value.get('topic') in ('gameplay_progress','gameplay_delivery'):
            details={k:details.get(k)for k in ('scope','origin','request_kind','generated','output')}
        elif value.get('topic')=='quest_transition':
            details={k:details.get(k)for k in ('quest','action','active','completed','scope')}
        key=(value.get('topic'),value.get('reason'),json.dumps(details,sort_keys=True))
        if key not in self.observations and len(self.observations)>=64:return False
        self.observations[key]+=1
        return self.observations[key]==1 or self.observations[key]%64==0

    def rejection(self,evidence):
        key=evidence.get('fingerprint')
        if key is None:return 1
        if key not in self.rejections and len(self.rejections)>=32:return None
        self.rejections[key]+=1
        count=self.rejections[key]
        return count if count==1 or count%64==0 else None

    def response(self,message):
        code=result_code(message)
        if code in (None,0):
            return None
        key=(message.kind,code)
        if key not in self.results and len(self.results)>=32:
            self.result_codes_omitted+=1
            return None
        self.results[key]+=1
        count=self.results[key]
        if self.result_logs>=64 or count!=1 and count%64:
            return None
        self.result_logs+=1
        result=dict(response_kind=message.kind,result=code,observed_count=count,
                    result_meaning='nonzero_native_result; handler semantics apply')
        try:result.update(result_text_status(code))
        except (OSError,ValueError):result['text_status']='catalog_unavailable'
        return result

    def request(self, session, event, sequence, size):
        self.requests_seen += 1
        self.recent.append(dict(time=datetime.now(timezone.utc).isoformat(),
                                sequence=sequence, event_id=event.event_id,
                                kind=event.kind, size=size, input=request_details(event), **context(session)))

    def details(self,sequence):
        return next((row['input'] for row in reversed(self.recent) if row['sequence']==sequence),None)

    def state(self,sequence):
        row=next((row for row in reversed(self.recent) if row['sequence']==sequence),{})
        return {key:row[key] for key in ('uid','phase','map','dungeon','stage','part') if key in row}

    def snapshot(self, session, identity, reason, error=None):
        result = dict(connection=self.connection, reason=reason,
                      account_id=identity['id'] if identity else None,
                      requests_seen=self.requests_seen,
                      requests_omitted=max(0, self.requests_seen-len(self.recent)),
                      nonzero_results=[dict(kind=kind,result=code,count=count)
                                       for (kind,code),count in self.results.items()],
                      result_codes_omitted=self.result_codes_omitted,
                      recent_requests=list(self.recent), **context(session))
        if error is not None:
            from els_server.diagnostic_evidence import exception_evidence
            result['exception']=exception_evidence(error)
            result['error_type'] = type(error).__name__
            result['source_stack'] = [dict(file=Path(f.filename).name,
                                           line=f.lineno, function=f.name)
                                      for f in traceback.extract_tb(error.__traceback__)[-12:]]
        return result
