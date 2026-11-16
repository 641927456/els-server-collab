"""Locate the earliest evidenced gap from committed handler state to server write."""
from gameplay_cause_analysis import verified_site


def same_operation(first,second):
    a=first.get('observation',{}).get('details',{});b=second.get('observation',{}).get('details',{})
    return (type(a.get('operation'))is int and a.get('operation')==b.get('operation')
        and a.get('scope')==b.get('scope') and a.get('scope',{}).get('uid') is not None
        and first.get('server_instance') is not None and first.get('server_instance')==second.get('server_instance')
        and first.get('connection') is not None and first.get('connection')==second.get('connection'))


def progress_findings(events,source_root,exact_session):
    findings=[]
    for event in events:
        observed=event.get('observation',{})
        if observed.get('topic')!='gameplay_progress':continue
        details=observed.get('details',{});scope=details.get('scope',{})
        if not exact_session or not verified_site(details.get('handler'),source_root):continue
        delivery=[e['observation']for e in events if e.get('observation',{}).get('topic')=='gameplay_delivery' and same_operation(event,e)]
        for decision in details.get('decisions',[]):
            value=decision.get('details',{});state=details.get('gate_state',{})
            before=details.get('before')or{}
            if value.get('scope')!=scope or not verified_site(decision.get('site'),source_root):continue
            kind=value.get('expected_kind');part=value.get('expected_part')
            prior=before.get('gate_state')or{}
            if kind==0xba:applied=state.get('part_end')is True and not state.get('cleared') and prior.get('part_end')is False
            elif kind==0xb7:
                target=state.get('next')or{}
                old_target=prior.get('next')or{}
                applied=(target.get('kind')==0 and target.get('part')==part and target.get('curtain_opened')is True
                    and not old_target.get('curtain_opened'))
            else:continue
            if not applied or before.get('scope')!=scope:continue
            generated=[o for o in details.get('generated',[])if o.get('kind')==kind and o.get('part')==part]
            basis=dict(operation=details['operation'],scope=scope,expected_kind=kind,expected_part=part,
                decision_site=decision['site'],handler=details['handler'])
            if not generated:
                if details.get('outputs_omitted'):continue
                findings.append(dict(title='已推进的关卡状态缺少对应通知',status='server_output_gap_confirmed',
                    evidence=basis,next_step='检查已记录判定分支到处理函数最终返回之间的过滤、替换与预备状态采用。',
                    defect_confirmed=False))
                continue
            sent=[o['details']for o in delivery if o['reason']=='server_write_completed'
                and o['details'].get('output')in generated
                and o['details'].get('observed_monotonic',-1)>=details.get('observed_monotonic',0)]
            failed=[o['details']for o in delivery if o['reason']=='server_write_failed']
            if sent:
                findings.append(dict(title='关卡通知已完成服务器写出',status='server_write_confirmed',
                    evidence=dict(basis,delivery=sent),next_step='继续对齐该线序号的客户端接收与原生消费；服务器写出不证明客户端收到。',
                    defect_confirmed=False))
            elif failed:
                findings.append(dict(title='关卡通知生成后写出失败',status='server_write_failure_confirmed',
                    evidence=dict(basis,failure=failed),next_step='检查同连接的出站队列、超时或关闭原因，保留已经写出的部分。',
                    defect_confirmed=False))
            else:
                findings.append(dict(title='关卡通知已生成，缺少写出证据',status='delivery_evidence_missing',
                    evidence=basis,next_step='先补齐本操作的写出记录或发送失败记录，不能据日志缺失认定网络丢包。',
                    defect_confirmed=False))
    return findings


REPAIRS={
    'story_retirement_quest_stage':('剧情对象退休资格','核对 required_any_quest 的来源与该副本允许进入的任务阶段；核标准后修资格生成或任务状态来源。'),
    'story_source_rule_not_unique':('剧情对象来源映射','核对资源 SHA、关卡、source_index 与规则集合，修重复或缺失映射。'),
    'scene_source_rule_mismatch':('场景对象来源校验','核对资源 SHA、对象声明及原生退休数据，定位不匹配字段。'),
    'raid_controller_source_rule_mismatch':('团本控制器来源校验','核对控制器资源、脚本 SHA 和实例映射。'),
    'item_locked':('物品锁定状态','核对锁定截止时间与本次检查时间；若状态错误，追对应锁定写入流程。'),
    'item_expired':('物品有效期','核对有效期来源、事件截止时间和服务端时钟。'),
    'quest_level':('任务等级条件','核对实际等级、配置上下限及任务资格数据来源。'),
    'quest_predecessor':('前置任务状态','查询所列前置任务的接取、完成或放弃记录及对应资格规则。'),
    'quest_prerequisite_item':('任务条件物品','核对该模板的实际数量与条件要求，追领取或消耗流程。')}


def repair_hints(findings):
    rows=[];seen=set()
    for finding in findings:
        cause=finding.get('cause_analysis')or{}
        if not cause.get('direct_cause_confirmed'):continue
        entries=[(c['reason'],c.get('site'),c.get('details',{}))for c in cause.get('checks',[])]
        entries += [(c['reason'],c.get('rejection_site'),c.get('facts',{}))for c in cause.get('links',[])]
        for reason,site,facts in entries:
            if reason not in REPAIRS or reason in seen:continue
            seen.add(reason);area,action=REPAIRS[reason]
            rows.append(dict(area=area,action=action,code=site,facts=facts,
                validation='复用现有线上自有角色，从真实入口验证同一失败条件及合法成功条件；不得靠跳过资格或补成功应答消除报错。'))
    return rows
