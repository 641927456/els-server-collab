"""Match actual frame fingerprints, then follow the same native dispatch call."""
import hashlib
import json
from pathlib import Path


def trusted_observer(rows,runtime):
    from client_delivery_support import source
    raw=(Path(__file__).resolve().parent/'client_delivery_profile.json').read_bytes()
    profile=json.loads(raw);client=profile['client_sha256'];script=hashlib.sha256(source(client).encode()).hexdigest()
    if runtime.get('client_sha256')!=client:return {}
    return {r['script_instance']:script for r in rows if r.get('phase')=='ready' and r.get('read_only')is True
        and r.get('client_sha256')==client and r.get('profile_sha256')==hashlib.sha256(raw).hexdigest()
        and r.get('script_sha256')==script and isinstance(r.get('script_instance'),str)}


def client_chain(server_events,document,exact_session,source_root=None):
    if not isinstance(document,dict):document={}
    delivery=document.get('client_delivery',{})
    if not isinstance(delivery,dict):delivery={}
    supplied=delivery.get('events',[])
    if not isinstance(supplied,list):supplied=[]
    rows=[r for r in supplied[:264]if isinstance(r,dict)and type(r.get('sequence'))is int
        and type(r.get('trace_id',0))is int and type(r.get('kind',0))is int
        and type(r.get('site_rva',0))is int and type(r.get('thread',0))is int
        and isinstance(r.get('script_instance'),str)]
    runtime=document.get('runtime',{})
    if not isinstance(runtime,dict):runtime={}
    trusted=trusted_observer(rows,runtime)
    findings=[]
    if not exact_session:return findings
    rows=[r for r in rows if r.get('script_instance')in trusted and r.get('script_sha256')==trusted[r['script_instance']]]
    losses=any(mapping.get('observation',{}).get('details',{}).get('observations_omitted')for mapping in server_events if isinstance(mapping,dict))or bool(delivery.get('omitted'))or len(rows)!=len(supplied)or any(r.get('dropped',0)or r.get('phase')=='observer_error'for r in rows)
    profile=json.loads((Path(__file__).parent/'client_delivery_profile.json').read_bytes())
    dispatch_sites={s['rva']for s in profile['sites']if s['role'].endswith('dispatch')}
    decodes=[r for r in rows if r.get('phase')=='event_decoded' and r.get('receive_scope')is True
        and type(r.get('trace_id'))is int and r['trace_id']>0]
    for event in server_events:
        if not isinstance(event,dict):continue
        observation=event.get('observation',{});sent=observation.get('details',{})
        if observation.get('topic')!='gameplay_delivery' or observation.get('reason')!='server_write_completed':continue
        if not isinstance(sent,dict):continue
        output=sent.get('output',{})
        if not isinstance(output,dict):continue
        kind=output.get('kind');digest=sent.get('payload_sha256')
        matching=[r for r in decodes if r.get('kind')==kind and r.get('payload_sha256')==digest
            and r.get('frame_sha256')in (sent.get('frame_sha256'),sent.get('secure_body_sha256'))
            and r.get('frame_sha256') is not None]
        base=dict(wire_sequence=sent.get('wire_sequence'),request_sequence=sent.get('request_sequence'),server_operation=sent.get('operation'),kind=kind,observation_loss=losses,
            account_scope=sent.get('scope'),server_handler=sent.get('handler'),root_cause_confirmed=False,defect_confirmed=False)
        if not trusted:
            findings.append(dict(base,status='client_observer_unverified',title='服务器已写出，客户端观察器生效证据不足',
                next_step='核本次客户端、观察器和配置 SHA 及 ready 记录；旧报告或版本不匹配不能用于判断客户端执行。'))
            continue
        if len(matching)!=1:
            failures=[r for r in rows if r.get('phase')in ('event_decode_failed','frame_without_event')
                and r.get('receive_scope')is True and r.get('frame_sha256')is not None
                and r.get('frame_sha256')in (sent.get('frame_sha256'),sent.get('secure_body_sha256'))]
            if not matching and len(failures)==1:
                failed=failures[0];decode_failed=failed['phase']=='event_decode_failed'
                findings.append(dict(base,status='client_event_decode_failed'if decode_failed else'client_frame_without_event',receive=failed,
                    title='客户端已收到同一帧，事件解析返回失败'if decode_failed else'客户端已收到同一帧，接收路径未进入事件解析',
                    next_step='按已记录帧和双方版本核对封包、校验及解析路径；当前观测仍不能单独证明是哪一端造成数据不一致。'))
                continue
            findings.append(dict(base,status='client_receive_evidence_missing'if not matching else'client_receive_ambiguous',
                title='服务器写出后，缺少唯一客户端接收记录',
                next_step='核同次客户端观察器是否启动、是否省略事件；缺记录不能直接认定网络丢包。'))
            continue
        received=matching[0];identity=(received.get('script_instance'),received.get('trace_id'))
        calls=[r for r in rows if (r.get('script_instance'),r.get('trace_id'))==identity and r.get('phase')in ('dispatch_enter','dispatch_return')]
        enters=[r for r in calls if r['phase']=='dispatch_enter'and r.get('kind')==kind
            and r.get('site_rva')in dispatch_sites and r.get('sequence',0)>received.get('sequence',0)]
        enter=enters[0]if len(enters)==1 else None
        returned=[r for r in calls if r['phase']=='dispatch_return' and enter is not None
            and r.get('kind')==kind and r.get('site_rva')==enter.get('site_rva') and r.get('thread')==enter.get('thread')
            and r.get('sequence',0)>enter.get('sequence',0)]
        base.update(client_trace=received['trace_id'],receive=received,dispatch_enter=enter)
        if enter is None:
            findings.append(dict(base,status='decoded_without_dispatch_evidence',title='客户端已解析应答，未观察到匹配分发',
                next_step='查客户端排队、当前状态分派或未覆盖消费者；需排除事件省略。'));continue
        if len(returned)!=1:
            findings.append(dict(base,status='dispatch_return_not_observed',title='客户端已进入分发，未观察到返回',
                next_step='结合同线程异常／退出记录检查该原生消费者；缺返回可能来自采集丢失，不能直接判死锁。'));continue
        end=returned[0];base['dispatch_return']=end
        from client_effect_analysis import outcomes
        base['outcomes']=outcomes(rows,received,end,sent,enter)
        from client_lifecycle_analysis import lifecycle_outcomes
        lifecycle=lifecycle_outcomes(rows,received,end,sent,enter)
        if lifecycle:
            base['outcomes']=[v for v in base['outcomes']if v['area']not in('gate_completion','trigger_completion')and not(v['area']=='item_effect'and v['title'].startswith('关联增益存在'))]
            for value in base['outcomes']:
                if value['status']=='post_state_evidence_missing':value.update(area='collection',title='常规执行后快照缺失；已记录的生命周期结果单独列出')
            base['outcomes']+=lifecycle
        status='native_dispatch_returned';title='客户端已解析并完成匹配分发返回'
        after=end.get('after');before=end.get('before')
        same_object=(isinstance(before,dict)and isinstance(after,dict)and
            type(before.get('handle_index'))is int and type(before.get('handle_generation'))is int and
            (before.get('handle_index'),before.get('handle_generation'))==(after.get('handle_index'),after.get('handle_generation')))
        expected=sent.get('scope',{})
        if not isinstance(expected,dict):expected={}
        matching_stage=same_object and type(expected.get('stage'))is int and after.get('stage')==expected['stage']
        if end.get('result')==1 and kind in (0xb7,0xbd) and matching_stage and after.get('part')==output.get('part'):
            status='native_expected_part_observed';title='客户端已分发，预期关卡段状态已观察到'
            if kind==0xb7:title='客户端已选择预期关卡段；开门状态需独立核对'
            base['state_changed']=isinstance(before,dict)and before.get('part')!=after.get('part')
        if end.get('result')==0:status='native_dispatch_declined';title='客户端已收到应答，但该分发器返回未处理'
        findings.append(dict(base,status=status,title=title,next_step='核回包结果、读取游标和执行后状态；原生返回不代表画面或全部玩法完成。'))
    from gameplay_chain_routes import annotate_chains
    return annotate_chains(findings,source_root)
