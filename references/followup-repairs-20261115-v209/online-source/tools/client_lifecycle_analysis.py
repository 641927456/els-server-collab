"""Report bounded, causally linked observations without treating absence as failure."""
import json
import math
from functools import lru_cache
from pathlib import Path


def mapping(value):return value if isinstance(value,dict)else {}
def number(value):return type(value)in(int,float)and math.isfinite(value)
def items(value):return [v for v in value if isinstance(v,dict)]if isinstance(value,list)else []


@lru_cache(maxsize=1)
def contracts():
    return json.loads((Path(__file__).parent/'client_trigger_contracts.json').read_bytes())['contracts']


def lifecycle_outcomes(rows,received,returned,sent,entered):
    from client_effect_analysis import outcome
    profile=json.loads((Path(__file__).parent/'client_delivery_profile.json').read_bytes())
    sites={v['role']:v['rva']for v in profile['lifecycle_sites']}
    identity=(received['script_instance'],received['trace_id']);scope=mapping(sent.get('scope'));output=mapping(sent.get('output'))
    native=mapping(returned.get('before'));owner=str(scope.get('uid',''));kind=received['kind']
    records=[v for v in rows if v.get('phase')=='lifecycle_observed'and(v.get('script_instance'),v.get('trace_id'))==identity
             and v.get('kind')==kind and v.get('thread')==returned.get('thread')and type(v.get('sequence'))is int
             and v['sequence']>mapping(entered).get('sequence',returned['sequence'])]
    records.sort(key=lambda v:v['sequence']);result=[]
    if returned.get('result')!=1 or any(type(v)is int and v!=0 for v in(output.get('result'),received.get('response_result'))):return []
    def same_scene(v):
        scene=mapping(v.get('scene'))
        return v.get('owner')==owner and all(type(native.get(k))is int and scene.get(k)==native[k]for k in('handle_index','handle_generation','stage','part'))and scene.get('stage')==scope.get('stage')
    def add(area,status,title,evidence):
        row=outcome(area,status,title,evidence);result.append(row);return row
    windows=[v for v in records if v.get('component')=='collection']
    if kind==0x115:
        applied=[v for v in records if v.get('component')=='buff'and v.get('status')=='applied'
                 and v.get('site_rva')==sites['buff_apply']and v.get('owner')==owner
                 and mapping(entered).get('sequence',0)<v['sequence']<returned['sequence']and isinstance(v.get('observation_id'),str)]
        for start in applied:
            observation_id=start['observation_id'];initial=mapping(start.get('snapshot'));before=mapping(start.get('before'))
            if not all(type(initial.get(k))is int for k in('template','factor')):continue
            if output.get('linked_factor')and initial['factor']!=output['linked_factor']:continue
            later=[v for v in records if v.get('component')=='buff'and v.get('observation_id')==observation_id and v['sequence']>start['sequence']
                   and v.get('site_rva')==sites['game_tick']and same_scene(v)]
            samples=[initial]+[mapping(v.get('snapshot'))for v in later if v.get('status')=='sample']
            status='applied_observed';title='增益效果执行已观察；持续结果仍在采集'
            if any(v.get('status')=='superseded'and v.get('observation_id')==observation_id and v.get('site_rva')==sites['buff_apply'] for v in records):status='superseded';title='增益再次应用，后续结果已转由新请求观察'
            elif any(v.get('status')=='removed'for v in later):status='removed_observed';title='增益已离开角色集合；移除原因尚未确认'
            elif any(s.get('expired')is True for s in samples):status='expiry_flag_observed';title='增益原生到期标记已观察'
            elif any(t.get('paused')is True for s in samples for t in items(s.get('timers'))):status='native_pause_observed';title='增益计时处于原生暂停状态'
            elif len(samples)>1:
                first={t['index']:t for t in items(initial.get('timers'))if type(t.get('index'))is int};last={t['index']:t for t in items(samples[-1].get('timers'))if type(t.get('index'))is int}
                pairs=[(first[i].get('remaining'),last[i].get('remaining'))for i in first.keys()&last.keys()]
                if any(number(a)and number(b)and b<a for a,b in pairs):status='countdown_observed';title='增益剩余时间正在递减'
                elif any(number(a)and number(b)and b>a for a,b in pairs):status='renewal_observed';title='增益剩余时间增加，可能有续期或其他应用'
                else:status='unchanged_observed';title='增益计时未变化；暂停、维持规则与覆盖仍需核对'
            change={k:dict(before=before.get(k),after=initial.get(k))for k in('stack_count','mode','stack_path','stack_decay')if k in before and k in initial and before[k]!=initial[k]}
            timers_before={t['index']:t for t in items(before.get('timers'))if type(t.get('index'))is int}
            missing=(initial.get('unavailable_fields')if isinstance(initial.get('unavailable_fields'),list)else[])+[t.get('unavailable')for t in items(initial.get('timers'))if t.get('unavailable')]
            if missing:add('collection','partial_read','增益计时或叠加字段未完整采集，不能据此判断完整结果',dict(observation_id=observation_id,unavailable=missing))
            refreshed=any(type(t.get('index'))is int and number(t.get('remaining'))and number(timers_before.get(t.get('index'),{}).get('remaining'))and t['remaining']>timers_before[t['index']]['remaining']for t in items(initial.get('timers')))
            add('buff_lifecycle',status,title,dict(observation_id=observation_id,initial=initial,last=samples[-1],application_changes=change,refresh_during_application=refreshed,samples=len(samples),stack_cap_verified=False))
        if output.get('linked_factor')and not applied:add('buff_lifecycle','evidence_missing','关联增益缺少同次原生应用记录；不能判定未生效',dict(factor=output['linked_factor']))
    if kind in(0xb7,0xbd,0xba):
        starts=[v for v in records if v.get('component')=='door'and v.get('status')=='break_enter'and v.get('site_rva')==sites['curtain_break']
                and v.get('owner')==owner and(mapping(entered).get('sequence',0)<v['sequence']<returned['sequence'] or(v.get('association')=='unique_pending_selected_part'and v['sequence']>returned['sequence']and number(v.get('elapsed_ms'))and 0<=v['elapsed_ms']<=30000))]
        created=[v for v in records if v.get('component')=='door'and v.get('status')in('created','factory_empty')and v.get('site_rva')==sites['visual_factory']
                 and any(s['sequence']<v['sequence']and(v['sequence']<returned['sequence']or(v.get('association')=='unique_pending_selected_part'and number(v.get('elapsed_ms'))and 0<=v['elapsed_ms']<=30000))and s.get('geometry_index')==v.get('geometry_index')and s.get('part_index')==v.get('part_index')for s in starts)]
        for event in created:
            samples=[v for v in records if v.get('component')=='door'and v.get('observation_id')==event.get('observation_id')and v.get('status')=='sample'
                     and v.get('site_rva')==sites['visual_tick']and v['sequence']>event['sequence']and v.get('owner')==owner]
            states=[mapping(v.get('snapshot'))for v in samples]
            status='effect_created';title='开门转换特效已创建；画面完成尚未确认'
            if event['status']=='factory_empty':status='factory_empty';title='开门转换已请求，特效工厂未返回实例；需核原生限制和资源'
            elif any(s.get('retired')is True for s in states):status='retirement_observed';title='开门特效已进入原生退役；不等于已确认画面完整播放'
            elif states:
                last=states[-1]
                if last.get('paused')is True:status='native_pause_observed';title='开门特效处于原生暂停状态'
                elif number(last.get('delay'))and last['delay']>0:status='native_delay_observed';title='开门特效仍在等待原生延迟'
                elif len(states)>1 and number(states[0].get('elapsed'))and number(last.get('elapsed'))and last['elapsed']>states[0]['elapsed']:status='animation_progress_observed';title='开门特效原生播放时间正在推进'
            add('door_animation',status,title,dict(observation_id=event.get('observation_id'),geometry_index=event.get('geometry_index'),part_index=event.get('part_index'),association=event.get('association','nested_dispatch'),manager_enabled=event.get('manager_enabled'),manager_limit=event.get('manager_limit'),last=states[-1]if states else None))
        if not starts:add('door_animation','evidence_missing'if kind!=0xba else'awaiting_transition','未观察到同次关卡转换的开门特效；逻辑放行本身不要求立即播放破门特效',{})
        elif not created:add('door_animation','evidence_missing','已进入开门转换，缺少特效创建结果记录',{})
    if kind==0x30c:
        key='/'.join(str(v)for v in(scope.get('dungeon'),scope.get('stage'),scope.get('part'),output.get('trigger')))
        contract=contracts().get(key)
        if not contract or contract.get('source_sha256')!=scope.get('graph_sha256'):
            add('delayed_trigger','coverage_incomplete','缺少匹配当前地图来源的动作与延迟定义',dict(scope_key=key))
        else:
            samples=[v for v in records if v.get('component')=='trigger'and v.get('status')=='sample'and v.get('site_rva')==sites['game_tick']and same_scene(v)
                     and mapping(v.get('snapshot')).get('trigger')==output.get('trigger')and number(v.get('elapsed_ms'))]
            for action in items(contract.get('actions')):
                evidence=dict(action=action,contract_sha256=contract.get('sha256'),line_source_sha256=contract.get('line_source_sha256'))
                delay=action.get('delay')
                if not number(delay)or delay<0:add('delayed_trigger','coverage_incomplete','机关动作延迟定义无法核对',evidence);continue
                eligible=[v for v in samples if v['elapsed_ms']>=delay*1000]
                if not eligible:add('delayed_trigger','evidence_missing'if any(v.get('status')in('scope_ended','window_ended')for v in windows)else'waiting_or_missing','机关动作尚无延迟之后的同场景记录；不能判定失败',evidence);continue
                if action.get('type')!='TRIGGER_LINE_ACTION_TYPE.TAT_LINE_CHANGE_ENABLE' or type(action.get('line_id'))is not int or type(action.get('enabled'))is not bool:
                    add('delayed_trigger','coverage_incomplete','已过定义延迟；该动作的最终消费者状态尚未覆盖',evidence);continue
                same_target=[a for a in items(contract.get('actions'))if a.get('type')==action['type']and a.get('line_id')==action['line_id']]
                if contract.get('repeat')or contract.get('loop')or len(same_target)>1:
                    add('delayed_trigger','ambiguous_action_order','动作存在循环或同目标多次写入，快照不能归因单次动作',evidence);continue
                last=eligible[-1];matches=[v for v in items(mapping(mapping(last.get('snapshot')).get('geometry')).get('lines'))if v.get('id')==action['line_id']]
                evidence.update(elapsed_ms=last['elapsed_ms'],lines=matches,timing_basis='wall_clock_only_not_native_scheduler',client_resource_identity_verified=False,action_conditions_verified=False)
                met=bool(matches)and all(v.get('enabled')==int(action['enabled'])for v in matches)
                add('delayed_trigger','target_state_observed'if met else'target_state_unconfirmed','延迟之后已观察到目标碰撞线状态'if met else'延迟之后目标碰撞线状态未确认；需核触发条件、暂停、动作调度和后续覆盖',evidence)
    gaps=[v for v in records if v.get('status')in('read_unavailable','capacity_omitted','scope_ended','window_ended')]
    if gaps:add('collection','observation_limit','生命周期采集存在边界或结束原因，不作为故障根因',dict(events=[{k:v[k]for k in('component','status','reason','elapsed_ms')if k in v}for v in gaps]))
    return result
