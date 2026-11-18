"""Read-only incident summary: evidence, code locations and remaining causal gaps."""
import hashlib
import json
from pathlib import Path


def source_check(frame,root):
    if frame.get('disk_matches_loaded_code') is False:return 'disk_differed_from_loaded_code'
    if root is None:return 'not_checked'
    relative=frame.get('file')
    if not isinstance(relative,str):return 'unavailable'
    root=Path(root).resolve();path=(root/relative).resolve()
    try:path.relative_to(root)
    except ValueError:return 'outside_source_root'
    if not path.is_file():return 'missing'
    expected=frame.get('disk_source_sha256')
    if not expected:return 'recorded_hash_missing'
    return 'matches_recorded_disk' if hashlib.sha256(path.read_bytes()).hexdigest()==expected else 'differs_from_recorded_disk'


def exception_frames(error,source_root=None):
    frames=[]
    for frame in error.get('frames',[]) if isinstance(error,dict) else []:
        if isinstance(frame,dict):frames.append({**frame,'source_check':source_check(frame,source_root)})
    if not frames and isinstance(error,dict) and isinstance(error.get('condition_site'),dict):
        frame=error['condition_site'];frames.append({**frame,'source_check':source_check(frame,source_root)})
    return frames


def exception_chain(error,source_root=None):
    rows=[]
    while isinstance(error,dict) and len(rows)<4:
        rows.append(dict(type=error.get('type'),reason=error.get('reason'),
                         fingerprint=error.get('fingerprint'),frames=exception_frames(error,source_root)))
        error=error.get('cause') or error.get('context')
    return rows


def diagnose(report,members,correlation,source_root=None):
    events=correlation.get('events',[])
    findings=[];missing=[]
    try:client=json.loads(members.get('run/gameplay-errors.json','{}'))
    except ValueError:client={}
    client_rows=client.get('events',[]) if isinstance(client,dict) else []
    if not isinstance(client_rows,list):client_rows=[]
    for event in events:
        kind=event.get('event')
        if kind not in ('business_rejection','worker_error','notification_error','gameplay_result_nonzero','request_timing','gameplay_observation'):continue
        base=dict(server_instance=event.get('server_instance'),connection=event.get('connection'),
                  sequence=event.get('sequence'),time=event.get('time'),request_kind=event.get('kind'),
                  state={key:event[key] for key in ('uid','phase','map','dungeon','stage','part') if key in event},
                  input=event.get('input'),request_state=event.get('request_state'))
        error=event.get('exception')
        if kind in ('business_rejection','worker_error','notification_error') and isinstance(error,dict):
            chain=exception_chain(error,source_root)
            frames=[frame for item in chain for frame in item['frames']]
            title='业务拒绝条件已定位' if kind=='business_rejection' else '服务端异常抛出位置已定位'
            from gameplay_cause_analysis import business_cause
            cause=business_cause(event.get('observations',[]),error,source_root=source_root,
                exact_session=correlation.get('matching')=='authenticated_account_and_client_session_label')
            findings.append(dict(base,title=title,certainty='observed_throw_site',exception=error,exception_chain=chain,
                fingerprint=chain[-1]['fingerprint'] if chain else None,
                observations=event.get('observations',[]),cause_analysis=cause,
                code_locations=frames,root_cause_confirmed=False,
                next_step='按记录版本核对末帧条件与上游输入；复用现有客户端、线上自有角色验证实际入口，判断是合法拒绝还是实现错误。'))
        elif kind=='gameplay_result_nonzero':
            sequence=event.get('request_sequence')
            matches=[e for e in events if e.get('event')=='business_rejection'
                     and e.get('server_instance')==event.get('server_instance')
                     and e.get('connection')==event.get('connection') and e.get('sequence')==sequence]
            if matches and not event.get('blank_text_possible'):continue
            findings.append(dict(base,title='已发送非零业务结果',sequence=sequence,
                result=event.get('result'),response_kind=event.get('response_kind'),
                text_status=event.get('text_status'),blank_text_possible=event.get('blank_text_possible',False),
                certainty='observed_result_only',root_cause_confirmed=False,
                next_step='查看该请求处理函数的返回分支；只有结果码仍不足以证明服务端故障。'))
        elif kind=='gameplay_observation':
            value=event.get('observation',{})
            if value.get('topic') in ('gameplay_progress','gameplay_delivery'):continue
            title={'dungeon_gate':'关卡推进等待／阻塞观测','dungeon_trigger':'副本触发器未通过',
                   'quest_transition':'任务操作完成后的状态',
                   'dungeon_actor':'对象退休报告被拒绝','quest_admission':'任务请求未进入正常流程','request_reply':'请求未生成对应应答'}.get(value.get('topic'),'玩法观测')
            cause=None
            if value.get('topic')=='dungeon_gate':
                from gameplay_cause_analysis import gate_cause
                cause=gate_cause(value.get('details',{}),source_root=source_root,
                    exact_session=correlation.get('matching')=='authenticated_account_and_client_session_label')
                if cause['direct_cause_confirmed']:title='关卡阻塞的直接原因已证实'
            findings.append(dict(base,title=title,certainty='observed_branch_or_state',cause_analysis=cause,
                observations=[value],code_locations=[{**value['site'],'source_check':source_check(value['site'],source_root)}] if value.get('site') else [],
                root_cause_confirmed=False,next_step='核对下面的阻塞原因与条件；未推进观测不等于机制故障，不自动清怪、开门或发任务。'))
        elif kind=='request_timing' and event.get('total_ms',0)>=1000:
            measures=[]
            for call in event.get('calls',[]):
                for name in ('account_wait_ms','world_gate_wait_ms','queue_ms','handler_ms','domain_ms',
                             'sql_begin_wait_ms','sql_writer_held_ms','projection_ms'):
                    value=call.get(name,0)
                    if isinstance(value,(int,float)) and value>0:measures.append((value,name))
            measures.sort(reverse=True)
            findings.append(dict(base,title='请求耗时偏高',certainty='observed_timing',
                total_ms=event['total_ms'],largest_measured_components=[dict(name=n,ms=v)for v,n in measures[:3]],
                root_cause_confirmed=False,
                next_step='耗时项可能重叠，不能相加或直接等同根因；按最大等待项追锁持有者／对应处理函数。'))
    if not correlation.get('events'):missing.append('未找到对应服务端记录；先检查日志保留范围和同次游玩标识。')
    if correlation.get('matching')!='authenticated_account_and_client_session_label':
        missing.append('服务端仅按账号和时间关联，无法排除同账号另一轮启动。')
    if correlation.get('events_omitted'):missing.append('服务端结果超出显示上限，部分事件未显示。')
    if correlation.get('truncated_files'):missing.append('部分日志超过读取上限，中段未读取；必要时按报告标识单独查询原日志。')
    if any(event.get('history_omitted') for event in events):missing.append('服务端快照达到条数或字节上限，较早事件已省略。')
    counters=client.get('counters',{}) if isinstance(client,dict) else {}
    if not isinstance(counters,dict):counters={}
    for key in ('history_omitted','capture_rate_omitted'):
        if counters.get(key):missing.append(f'客户端 {key}={counters[key]}，记录并非完整执行历史。')
    for row in client_rows:
        if not isinstance(row,dict):continue
        signal=row.get('signal')
        context=row.get('context') if isinstance(row.get('context'),dict) else {}
        location=context.get('fault_module')
        finding=dict(title={'native_exception':'原生异常检测点','support_error':'支持脚本错误',
            'native_dialog':'客户端对话框','blank_dialog':'捕获到空文本对话框','abnormal_exit':'游戏非零退出'}.get(signal,'客户端观测'),
            certainty='client_observation',root_cause_confirmed=False,signal=signal,
            fingerprint=row.get('fingerprint'),occurrences=row.get('occurrences',1),
            first_time=row.get('observed_utc'),last_time=row.get('last_observed_utc'),
            code=row.get('code'),description=row.get('description') or row.get('text') or row.get('reason'),
            script_source=row.get('script_source'),script_sha256=row.get('script_sha256'),
            script_frames=row.get('script_frames',[]),fault_module=location,
            recent_client_operations=context.get('recent_client_detail',[]))
        if signal in ('native_exception','observer_crash','abnormal_exit'):
            finding['next_step']='以 EXE／支持脚本 SHA 匹配同次异常现场；核故障指令、对象归属和写入／释放者。检测模块与最后调用不能单独定责。'
            missing.append('原生内存根因需要同次故障上下文、对象不变量或写入／释放历史；本报告不含原始内存和寄存器。')
        else:finding['next_step']='先核脚本 SHA 和行号，再把最近请求与服务端拒绝／异常对照；时间相邻不是因果证明。'
        findings.append(finding)
    for finding in findings:
        if any(f.get('source_check') in ('differs_from_recorded_disk','disk_differed_from_loaded_code') for f in finding.get('code_locations',[])):
            missing.append('所选源码与异常发生时首次记录的源码 SHA 不符，不要直接套用当前行号修复。')
    from gameplay_progress_analysis import progress_findings,repair_hints
    progress=progress_findings(events,source_root,correlation.get('matching')=='authenticated_account_and_client_session_label')
    from client_delivery_analysis import client_chain
    client_delivery=client_chain(events,client,correlation.get('matching')=='authenticated_account_and_client_session_label',source_root)
    if not findings and not progress and not client_delivery:missing.append('尚无足以定位到失败分支的证据；不能仅从退出或断线推断原因。')
    return dict(report_id=report.get('report_id'),account_id=report.get('account_id'),
        diagnostic_session=report.get('summary',{}).get('diagnostic_session'),
        matching=correlation.get('matching'),findings=findings,remaining_evidence=list(dict.fromkeys(missing)),
        direct_causes_verified=sum(bool((f.get('cause_analysis')or{}).get('direct_cause_confirmed'))for f in findings),
        progress=progress,client_delivery=client_delivery,repair_hints=repair_hints(findings),
        root_cause_confirmed=False,read_only=True,
        source_identity_note='code_sha256 identifies loaded Python code; disk_matches_loaded_code compares the first-observed source compilation with that running function.')


def render(result):
    lines=[f"诊断报告：{result['report_id']}",f"账号：{result['account_id']}  游玩标识：{result.get('diagnostic_session') or '未记录'}",
           f"关联方式：{result.get('matching') or '缺少服务端日志'}",
           f"已证实直接原因：{result.get('direct_causes_verified',0)} 项；是否属于实现缺陷需继续核规则与实际入口。",'']
    for index,finding in enumerate(result['findings'],1):
        lines.append(f"{index}. {finding['title']} [{finding['certainty']}]")
        if 'request_kind' in finding:lines.append(f"   请求：{finding.get('request_kind')}  序号：{finding.get('sequence')}  连接：{finding.get('connection')}")
        if finding.get('state'):lines.append('   当时状态：'+json.dumps(finding['state'],ensure_ascii=False))
        if finding.get('request_state'):lines.append('   收到请求时：'+json.dumps(finding['request_state'],ensure_ascii=False))
        if finding.get('input'):lines.append('   输入摘要：'+json.dumps(finding['input'],ensure_ascii=False))
        for observed in finding.get('observations',[]):
            lines.append('   条件观测：'+str(observed.get('topic'))+' / '+str(observed.get('reason')))
            lines.append('   '+json.dumps(observed.get('details',{}),ensure_ascii=False))
            if observed.get('topic')=='quest_history':
                for action in observed.get('details',{}).get('actions',[]):
                    lines.append(f"   该任务此前完成的操作：{action['action']}（请求 {action['sequence']}），active={action['active']}，completed={action['completed']}")
        cause=finding.get('cause_analysis')
        if cause:
            lines.append('   原因核对：'+cause['status']+'；范围：'+cause['scope'])
            for link in cause.get('links',[]):
                lines.append(f"   对象 {link['actor']}，原请求序号 {link['rejected_sequence']}：{link['chain']}")
                lines.append('   上游拒绝：'+link['reason']+'；事实：'+json.dumps(link['facts'],ensure_ascii=False))
            for check in cause.get('checks',[]):
                lines.append('   已执行的拒绝条件：'+check['reason']+'；事实：'+json.dumps(check['details'],ensure_ascii=False))
            for missing in cause['missing']:lines.append('   待补证据：'+missing)
            lines.append('   是否属于实现缺陷：未自动确认。')
        error=finding.get('exception')
        if isinstance(error,dict):lines.append(f"   {error.get('type')}: {error.get('reason')}")
        for cause in finding.get('exception_chain',[])[1:]:lines.append(f"   内层原因：{cause.get('type')}: {cause.get('reason')}")
        if finding.get('fingerprint'):lines.append('   分组指纹：'+finding['fingerprint'])
        if finding.get('description'):lines.append('   '+str(finding['description']).replace('\n',' '))
        for frame in finding.get('code_locations',[]):
            lines.append(f"   {frame.get('file')}:{frame.get('line')} {frame.get('function')} [{frame.get('source_check')}]")
        for frame in finding.get('script_frames',[]):
            lines.append(f"   {frame.get('file')}:{frame.get('line')}:{frame.get('column')}")
        if finding.get('script_sha256'):lines.append('   脚本 SHA256：'+finding['script_sha256'])
        if finding.get('fault_module'):lines.append('   异常模块观测：'+json.dumps(finding['fault_module'],ensure_ascii=False))
        if finding.get('occurrences'):lines.append(f"   发生次数：{finding['occurrences']}")
        if 'result' in finding:lines.append(f"   结果码：{finding['result']}，响应：{finding.get('response_kind')}")
        if finding.get('blank_text_possible'):lines.append('   此错误码缺少可用原生文本；白框仅为可能结果，需对应客户端观测确认。')
        if 'total_ms' in finding:lines.append('   耗时：'+str(round(finding['total_ms'],2))+' ms；主要项：'+json.dumps(finding['largest_measured_components'],ensure_ascii=False))
        lines.extend(['   下一步：'+finding['next_step'],''])
    for progress in result.get('progress',[]):
        lines.extend([progress['title']+' ['+progress['status']+']',
            '   证据：'+json.dumps(progress['evidence'],ensure_ascii=False),
            '   下一步：'+progress['next_step'],''])
    for chain in result.get('client_delivery',[]):
        received=chain.get('receive',{})
        reception=chain.get('client_trace','帧已匹配'if received else'未匹配')
        lines.extend([chain['title']+' ['+chain['status']+']',
            f"   请求 {chain['request_sequence']} → 服务器操作 {chain['server_operation']} → 线序号 {chain['wire_sequence']} → 客户端接收 {reception} → 应答 {chain['kind']}"])
        if type(received.get('response_result'))is int:
            lines.append('   客户端实际解析的业务结果码：'+str(received['response_result']))
        if chain.get('observation_loss'):lines.append('   采集存在省略／读取缺口，不能从缺记录推断未执行。')
        if chain.get('last_verified_step'):lines.append('   已确认到：'+chain['last_verified_step'])
        if chain.get('unresolved_step'):lines.append('   卡点／待证实：'+chain['unresolved_step'])
        if any(o.get('verification_level')=='direction_or_cap_only'for o in chain.get('outcomes',[])):lines.append('   回复效果目前只核对变化方向或上限，具体回复量公式尚未验收。')
        for location in chain.get('code_locations',[]):lines.append('   查代码：'+location)
        returned=chain.get('dispatch_return')
        if returned:lines.append('   分发返回／状态：'+json.dumps(returned,ensure_ascii=False))
        for outcome in chain.get('outcomes',[]):
            lines.append('   执行后结果：'+outcome['title']+' ['+outcome['status']+']')
            if 'changed_in_scope'in outcome:lines.append('   本次观察到状态变化：'+('是'if outcome['changed_in_scope']else'未证实；可能此前已符合预期'))
            lines.append('   状态证据：'+json.dumps(outcome['evidence'],ensure_ascii=False))
            if outcome.get('next_step'):lines.append('   此项下一步：'+outcome['next_step'])
        lines.extend(['   下一步：'+chain['next_step'],''])
    if result.get('repair_hints'):
        lines.append('建议检查的修复位置（根据已证实原因，未自动修改玩法）：')
        for hint in result['repair_hints']:
            lines.append('- '+hint['area']+'：'+hint['action'])
            code=hint.get('code')or{}
            if code:lines.append(f"  {code.get('file')}:{code.get('line')} {code.get('function')}")
            lines.append('  验证：'+hint['validation'])
        lines.append('')
    lines.append('仍缺的证据：')
    lines.extend('- '+text for text in result['remaining_evidence'])
    if not result['remaining_evidence']:lines.append('- 未自动确认业务规则正确性；需按上述输入和分支验证。')
    lines.extend(['','抛出位置、异常检测点和最后操作均不自动等于根因；本工具不执行修复或重放交易。'])
    return '\n'.join(lines)+'\n'
