"""Observe completed handlers and writes, with the scene captured at generation time."""
from collections import deque
import hashlib
import struct
import time

from els_server.diagnostic_evidence import recording,record_observation,code_identity,observation_omissions

TRACKED_REQUESTS=frozenset((0x113,0x65e,0xb3,0xb8,0xbb,0x471,0x30a,0xee,0xfa,0xf4,0x219,0x196,0x559))
GATE_MESSAGES=frozenset((0xb2,0xb7,0xba,0xbd,0x30c))


def scope(session):
    run=getattr(session,'dungeon_run',None)
    result=dict(uid=session.account.uid,phase=session.phase)
    if run is not None:result.update(run_id=run.run_id,dungeon=run.identity,stage=run.stage,part=run.part,visit=run.visits,
                                   graph_sha256=run.graph.get('source_sha256'))
    return result


def output_projection(messages):
    from els_server.gameplay_diagnostics import result_code
    rows=[]
    for index,message in enumerate(messages):
        if message.event_id!=0x201:continue
        code=result_code(message)
        from els_server.client_effect_projection import EFFECT_MESSAGES,targets
        if message.kind not in GATE_MESSAGES and message.kind not in EFFECT_MESSAGES and code is None:continue
        row=dict(index=index,kind=message.kind)
        if code is not None:row['result']=code
        if message.kind in (0xb7,0xba,0xbd) and message.payload:row['part']=struct.unpack_from('>b',message.payload)[0]
        elif message.kind==0xb2 and len(message.payload)>=8:row.update(zip(('stage','metadata'),struct.unpack_from('>ii',message.payload)))
        elif message.kind==0x30c and len(message.payload)==4:row['trigger']=struct.unpack('>i',message.payload)[0]
        row.update(targets(message.kind,message.payload))
        rows.append(row)
    return rows


def output_digest(messages):
    digest=hashlib.sha256()
    for message in messages:
        digest.update(struct.pack('>IIQQI',message.event_id,message.kind,message.uid,message.target_uid,len(message.payload)))
        digest.update(message.payload)
    return digest.hexdigest()


def gate_state(session):
    run=getattr(session,'dungeon_run',None)
    if run is None:return None
    return dict(part_end=bool(session.part_end_notified),cleared=bool(session.clear_notified),
        next={k:run.next[k]for k in ('kind','stage','part','curtain_opened')if k in run.next} if run.next else None)


def handler_started(session,function):
    if session is None or function.__name__ not in ('handle','periodic_notifications')or not hasattr(session,'account'):return None
    return dict(scope=scope(session),gate_state=gate_state(session))


def handler_finished(session,function,args,kwargs,messages,observations=(),before=None):
    if not recording() or session is None or function.__name__ not in ('handle','periodic_notifications') or not hasattr(session,'account') or not isinstance(messages,(list,tuple)):return
    event=args[0] if function.__name__=='handle' and args else None
    selected=event is not None and event.event_id==0x202 and event.kind in TRACKED_REQUESTS
    outputs=output_projection(messages)
    from els_server.client_effect_projection import EFFECT_MESSAGES
    if not selected and not any(row['kind']in GATE_MESSAGES|EFFECT_MESSAGES for row in outputs) and not any(o.get('topic')=='gate_decision'for o in observations):return
    operation=getattr(session,'_diagnostic_operation',0)+1;session._diagnostic_operation=operation
    details=dict(operation=operation,scope=scope(session),origin=function.__name__,
        request_kind=event.kind if selected else None,request_sequence=kwargs.get('request_sequence'),
        generated=outputs[:24],outputs_omitted=max(0,len(outputs)-24),output_sha256=output_digest(messages),
        total_messages=len(messages),observed_monotonic=time.monotonic(),
        handler=code_identity(function.__func__.__code__ if hasattr(function,'__func__')else function.__code__))
    details['before']=before
    details['observations_omitted']=observation_omissions()+int(len(observations)>=8)
    details['decisions']=[dict(details=o['details'],site=o['site'])for o in observations
                         if o.get('topic')=='gate_decision' and o.get('site')]
    run=getattr(session,'dungeon_run',None)
    if run is not None:
        details['gate_state']=gate_state(session)
    if function.__name__=='periodic_notifications':
        batches=deque(getattr(session,'_diagnostic_periodic_batches',()),maxlen=8)
        batches.append((messages,dict(details,_delivery_outputs=outputs)));session._diagnostic_periodic_batches=batches
    record_observation('gameplay_progress','handler_completed',details,include_site=False)


def matching_receipt(observations,messages):
    observed=[o['details']for o in observations if o.get('topic')=='gameplay_progress']
    if not observed:return None
    outputs=output_projection(messages);projections=outputs[:24];digest=output_digest(messages)
    candidates=[r for r in observed if r['total_messages']==len(messages) and r['generated']==projections and r['output_sha256']==digest]
    # An ambiguous periodic handoff must not attach the latest scene to an older output.
    return dict(candidates[0],_delivery_outputs=outputs) if len(candidates)==1 else None


def periodic_receipt(session,messages):
    batches=getattr(session,'_diagnostic_periodic_batches',())
    matched=[receipt for result,receipt in batches if result is messages]
    session._diagnostic_periodic_batches=deque(((result,receipt)for result,receipt in batches if result is not messages),maxlen=8)
    return matched[0] if len(matched)==1 else None


def delivered_row(receipt,index,wire_sequence):
    if receipt is None:return None
    output=next((r for r in receipt.get('_delivery_outputs',receipt['generated'])if r['index']==index),None)
    if output is None:return None
    return dict(operation=receipt['operation'],scope=receipt['scope'],output=output,
        wire_sequence=wire_sequence,request_sequence=receipt['request_sequence'],
        handler=receipt.get('handler'),observed_monotonic=time.monotonic(),meaning='server_write_completed_not_client_consumption')


def failed_delivery(receipt,error):
    if receipt is None:return None
    from els_server.diagnostic_evidence import exception_evidence
    return dict(operation=receipt['operation'],scope=receipt['scope'],error_type=type(error).__name__,
        exception=exception_evidence(error),
        observed_monotonic=time.monotonic(),meaning='outbox_submit_failed_or_cancelled')


def quest_completed(session,kind,qid,result,sequence):
    if not recording():return
    state=result['state'];active=next((r for r in state['active']if r['id']==qid),None)
    completed=any(r['id']==qid for r in state['completed'])
    details=dict(quest=qid,action=kind,active=active is not None,completed=completed,
        replayed=bool(result['replayed']),sequence=sequence,scope=scope(session),
        observed_monotonic=time.monotonic(),basis='action_returned_after_its_transaction')
    history=deque(getattr(session,'_diagnostic_quest_history',()),maxlen=32)
    history.append(details);session._diagnostic_quest_history=tuple(history)
    record_observation('quest_transition','action_completed',details,stacklevel=2)


def quest_history(session,qid):
    if not recording():return
    rows=[r for r in getattr(session,'_diagnostic_quest_history',())if r['quest']==qid and r['scope']['uid']==session.account.uid]
    if rows:record_observation('quest_history','previous_completed_actions',dict(quest=qid,actions=rows[-8:]),include_site=False)
