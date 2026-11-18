"""Evidence per expected result. Gaps and state changes do not establish root cause."""
import json
import math
from pathlib import Path


def mapping(value):return value if isinstance(value,dict)else {}
def values_list(value):return value if isinstance(value,list)else []
def entries(value):return [v for v in value if isinstance(v,dict)]if isinstance(value,list)else []
def number(value):return type(value)in(int,float)and math.isfinite(value)
def integer(value):return type(value)is int
def uid(value):return isinstance(value,str)and value.isdecimal()and len(value)<=20


def outcome(area,status,title,evidence=None,**extra):
    return dict(area=area,status=status,title=title,evidence=evidence or {},changed_in_scope=False,
                root_cause_confirmed=False,visual_result_confirmed=False,**extra)


def outcomes(rows,received,returned,sent,entered=None):
    identity=(received['script_instance'],received['trace_id']);kind=received['kind']
    profile=json.loads((Path(__file__).parent/'client_delivery_profile.json').read_bytes())
    sites={r['role']:r['rva']for r in profile['effect_sites']}
    start=mapping(entered).get('sequence',received['sequence'])
    records=sorted([r for r in rows if (r.get('script_instance'),r.get('trace_id'))==identity
        and r.get('kind')==kind and r.get('thread')==returned.get('thread')
        and ((r.get('phase')=='state_observed'and r.get('sequence',0)>returned['sequence']
              and r.get('checkpoint')in('dispatch_return','after_250ms','after_1200ms'))
          or(r.get('phase')=='effect_observed'and start<r.get('sequence',0)<returned['sequence']
             and r.get('effect')in sites and r.get('site_rva')==sites[r['effect']]))],key=lambda r:r['sequence'])
    output=mapping(sent.get('output'));scope=mapping(sent.get('scope'));owner=str(scope.get('uid',''))
    if returned.get('result')!=1:return [outcome('execution','dispatcher_not_handled','分发未处理，不能据当前状态认定本次操作生效')]
    client_code=received.get('response_result');server_code=output.get('result')
    if integer(client_code)and integer(server_code)and client_code!=server_code:
        return [outcome('execution','business_result_conflict','双方记录的业务结果码不一致',dict(server=server_code,client=client_code))]
    if (integer(server_code)and server_code!=0)or(integer(client_code)and client_code!=0):
        return [outcome('execution','business_rejected','业务返回拒绝；既有状态不能证明本次成功',dict(server=server_code,client=client_code))]
    if not records and kind in(0x197,0x55a,0x10a,0x18d,0x205,0x810):
        return [outcome('execution','coverage_incomplete','该类回包已追踪到分发，最终玩法状态尚未覆盖')]
    if not records:
        return [outcome('execution','post_state_evidence_missing','缺少执行后状态记录，不能确认实际效果')]if kind in(0xad8,0x105,0x21a,0x114,0x65f,0x115,0xf0,0xf3,0xf5,0x2b,0xba,0x30c)else []
    samples=[(r,mapping(r['snapshot']))for r in records if r['phase']=='state_observed'
             and isinstance(r.get('snapshot'),dict)and r['snapshot'].get('owner')==owner]
    result=[]
    unavailable=[r['unavailable']for r in records if r.get('unavailable')]
    unavailable += [mapping(r.get(side)).get('unavailable')for r in records for side in('before','after')if mapping(r.get(side)).get('unavailable')]
    unavailable += [v for _,s in samples for v in values_list(s.get('unavailable_fields'))if isinstance(v,str)]
    def compared(area,title,expected,observed,met,baseline=None,checkpoint=None):
        row=outcome(area,'expected_state_observed'if met else'observed_state_not_confirmed',
            title if met else title+'：尚未符合预期',dict(expected=expected,observed=observed,checkpoint=checkpoint))
        row['changed_in_scope']=baseline is not None and observed is not None and baseline!=observed
        result.append(row);return row
    def values(key,valid=lambda s:True):return [(r,s[key])for r,s in samples if isinstance(s.get(key),dict)and valid(s)]
    def baseline(key):
        for r in records:
            b=mapping(mapping(r.get('before')).get('snapshot'))
            if b.get('owner')==owner and key in b:return b[key]
    def scene_ok(s):
        scene=mapping(s.get('scene'));native=mapping(returned.get('before'))
        return integer(scope.get('stage'))and scene.get('stage')==scope['stage']and all(
            integer(native.get(k))and scene.get(k)==native[k]for k in('handle_index','handle_generation'))
    expected=mapping(output.get('item'))
    if expected:
        observed=[(r,item)for r,item in values('item')if (item.get('group'),item.get('slot'))==(expected.get('group'),expected.get('slot'))]
        valid_expected=uid(expected.get('uid'))and all(integer(expected.get(k))for k in('template','count','group','slot'))
        if observed and valid_expected:
            r,item=observed[-1]
            def matches(v):
                return (expected['uid']=='0'and v.get('present')is False)or(
                    v.get('present')is True and uid(v.get('uid'))and all(integer(v.get(k))for k in('template','count'))
                    and all(v.get(k)==expected[k]for k in('uid','template','count')))
            row=compared('item_inventory','客户端库存符合回包数量',expected,item,matches(item),baseline('item'),r.get('checkpoint'))
            if not matches(item)and any(matches(v)for _,v in observed[:-1]):row.update(status='state_regressed',title='库存曾匹配，后续检查点出现变化；需核后续操作')
        else:result.append(outcome('item_inventory','evidence_missing','缺少指定库存位置的完整结果',dict(expected=expected)))
    if output.get('item_projection_unavailable'):result.append(outcome('item_inventory','coverage_incomplete','库存更新结构未能投影，不能推断是否入库'))
    if 'items'in output:
        # Each absolute slot is independent; one matched reward cannot hide a missing one.
        for expected_item in entries(output['items']):
            item_samples=[]
            for record,snapshot in samples:
                item=next((v for v in entries(snapshot.get('items'))if (v.get('group'),v.get('slot'))==(expected_item.get('group'),expected_item.get('slot'))),None)
                if item is not None:item_samples.append(dict(record,snapshot=dict(owner=owner,item=item)))
            nested_output=dict(output);nested_output.pop('items');nested_output['item']=expected_item
            nested_sent=dict(sent,output=nested_output)
            nested=outcomes(item_samples,received,returned,nested_sent,entered)
            for item_result in nested:
                item_result['area']='item_inventory';result.append(item_result)
        if output.get('items_omitted'):result.append(outcome('item_inventory','coverage_incomplete','库存目标超过采集上限',dict(omitted=output['items_omitted'])))
    if kind==0x21a:result.append(outcome('item_semantics','coverage_incomplete','通用道具已核库存；转职、扩展及其他角色效果需各自状态消费者证据'))
    if kind==0x197:result.append(outcome('item_inventory','coverage_incomplete','该回包用于奖励展示；实际入库须核对应 AD8 库存更新'))
    if kind==0x2b:result.append(outcome('quest','coverage_incomplete','全量任务包的已完成历史集合尚未逐项核对'))
    if kind in(0xf0,0xf3,0xf5,0x2b):
        ids={q for q in output.get('quests',[])if integer(q)}if isinstance(output.get('quests'),list)else set()
        if integer(output.get('quest')):ids.add(output['quest'])
        old=baseline('quests');old=entries(old)
        if kind==0x2b:ids.update(q['quest']for q in old if integer(q.get('quest')))
        for qid in sorted(ids):
            qs=[(r,q)for r,s in samples for q in entries(s.get('quests'))if q.get('quest')==qid
                and type(q.get('active'))is bool and type(q.get('completed'))is bool
                and(not q['active']or q.get('record_owner')==owner)]
            expected_state=next((s for s in entries(output.get('quest_states'))if s.get('quest')==qid),None)
            if not qs:
                result.append(outcome('quest','evidence_missing','该任务缺少可归属的执行后记录',dict(quest=qid)));continue
            r,q=qs[-1];listed=qid in values_list(output.get('quests'))
            if kind==0xf5:met=q['completed']
            elif kind==0x2b and not listed and output.get('quests_omitted'):
                result.append(outcome('quest','coverage_incomplete','任务投影被截断，不能判断该任务应保留还是移除',dict(quest=qid,observed=q)));continue
            elif kind==0x2b:met=q['active']==listed
            else:met=q['active']
            if expected_state is not None:met=met and q.get('record_owner')==expected_state.get('owner')and q.get('objectives')==expected_state.get('objectives')
            compared('quest','客户端任务状态符合回包预期',expected_state or dict(quest=qid),q,met,
                     next((v for v in old if v.get('quest')==qid),None),r.get('checkpoint'))
        if output.get('quests_omitted')or any(r.get('quest_enumeration_unavailable')for r in records):
            result.append(outcome('quest','coverage_incomplete','任务集合未完整覆盖',dict(omitted=output.get('quests_omitted',0))))
    for area,key,target in [('gate','gate','part'),('trigger','trigger','trigger')]:
        if target not in output or kind not in(0xba,0x30c):continue
        current=values(key,scene_ok)
        current=[(r,v)for r,v in current if v.get('target'if area=='gate'else'trigger')==output[target]]
        # Native call observations may supplement a missing checkpoint, within this exact dispatch only.
        calls=[r for r in records if r['phase']=='effect_observed'and r.get('effect')==area+'_apply']
        if current:r,state=current[-1]
        elif calls and integer(scope.get('stage'))and mapping(returned.get('before')).get('stage')==scope.get('stage'):r=calls[-1];state=mapping(r.get('after'))
        else:
            result.append(outcome(area,'evidence_missing','缺少同一场景与目标的执行后记录',dict(target=output[target])));continue
        met=(state.get('target')==output[target]and state.get('stage')==scope.get('stage')and state.get('known')is True and state.get('passage_enabled')is True)if area=='gate'else(
            state.get('trigger')==output[target]and state.get('definition_present')is True and state.get('active')is True)
        row=compared(area,'客户端门通道逻辑标志已启用'if area=='gate'else'机关已进入客户端激活集合',dict(target=output[target]),state,met,
                 baseline(key),r.get('checkpoint','native_return'))
        if area=='trigger'and not met and any(mapping(v.get('after')).get('active')is True for v in calls):
            row.update(status='activation_then_removed',title='机关曾进入激活集合，后续已移除；不能据此判断成功或失败')
        result.append(outcome(area+'_completion','coverage_incomplete','门动画／可通行结果仍待观测'if area=='gate'else'激活集合不等于机关后续动作完成'))
    calls=[r for r in records if r.get('effect')=='geometry_write'and integer(scope.get('stage'))and mapping(returned.get('before')).get('stage')==scope.get('stage')]
    for r in calls:
        a=mapping(r.get('after'));b=mapping(r.get('before'));enabled=r.get('requested_enabled')
        met=integer(r.get('line_id'))and integer(a.get('geometry_count'))and a['geometry_count']>0 and integer(a.get('geometry_enabled'))and(
            a['geometry_enabled']==a['geometry_count']if enabled==1 else a['geometry_enabled']==0 if enabled==0 else False)
        row=compared('collision_line','本次调用目标碰撞线已更新',dict(line_id=r.get('line_id'),enabled=enabled),a,met,b,'native_return')
        row['writer_rva']=r['site_rva']
    if kind==0x115:
        calls=[r for r in records if r.get('effect')=='item_effect'and output.get('effect_owner')==owner and mapping(r.get('before')).get('owner')==owner==mapping(r.get('after')).get('owner')]
        later=values('actor');after=later[-1][1]if later else(mapping(calls[-1].get('after'))if calls else{})
        before=mapping(calls[0].get('before'))if calls else mapping(baseline('actor'))
        valid_contract=False
        for c in calls:
            definition=mapping(mapping(c.get('definition')).get('definition'))
            if definition.get('definition_sha256')==output.get('effect_definition_sha256')and output.get('effect_definition_sha256'):
                valid_contract=definition.get('effect_vector')==output.get('effect_vector')and definition.get('linked_factor')==output.get('linked_factor')
        if not calls and not before and not after:
            result.append(outcome('item_effect','evidence_missing','缺少当前角色的道具效果记录'))
            return result
        vector=output.get('effect_vector')
        if not isinstance(vector,list)or not valid_contract:
            change={k:dict(before=before[k],after=after[k])for k in('hp','max_hp','mp','max_mp','buffs','temporary_weapon','mount')if k in before and k in after and before[k]!=after[k]}
            row=outcome('item_effect','state_change_observed'if change else'effect_call_without_observed_change',
                        '道具观察窗口内角色状态发生变化'if change else'已观察道具执行路径，采集字段未见变化',change or after)
            row['changed_in_scope']=bool(change);result.append(row)
            result.append(outcome('item_effect','coverage_incomplete','缺少匹配的道具效果定义证据，不能认定全部生效'))
        else:
            # A later unrelated hit/heal cannot stand in for the nested native call.
            after=mapping(calls[-1].get('after'));before=mapping(calls[0].get('before'))
            for index,e in enumerate(vector):
                if not isinstance(e,list)or len(e)!=6 or not all(integer(v)for v in e):continue
                effect=e[0];key={1:'hp',13:'hp',2:'mp',19:'mp',18:'temporary_weapon',39:'mount'}.get(effect)
                if effect==18 and e[3]!=1:key=None
                if key is None:
                    result.append(outcome('item_effect','coverage_incomplete','该效果最终状态尚未覆盖',dict(effect_index=index,effect_type=effect)));continue
                a=after.get(key);b=before.get(key)
                if effect in(1,13,2,19):
                    max_key='max_hp'if key=='hp'else'max_mp';cap=after.get(max_key)
                    met=number(a)and number(b)and number(cap)and(a>b or a==b==cap)
                elif effect==18:met=integer(a)and a==e[2]
                else:met=isinstance(a,dict)and isinstance(b,dict)and uid(a.get('uid'))and a.get('uid')==b.get('uid')and number(a.get('stamina'))and number(b.get('stamina'))and a['stamina']>b['stamina']
                row=compared('item_effect','道具效果对应字段符合观察条件',dict(effect_index=index,effect_type=effect,field=key),a,met,b)
                row['verification_level']='direction_or_cap_only'if effect in(1,13,2,19)else'field_value'
                row['evidence']['basis']='恢复方向／上限或原生目标字段；不代替全部数值公式验收'
            if output.get('linked_factor'):result.append(outcome('item_effect','coverage_incomplete','关联增益存在，持续时间与叠加结果尚未覆盖',dict(linked_factor=output['linked_factor'])))
        unavailable += [v for v in values_list(after.get('unavailable_fields'))if isinstance(v,str)]
    if unavailable:result.append(outcome('collection','partial_read','部分采集字段不可用，其余结果单独保留',dict(unavailable=unavailable)))
    for r,s in samples:
        if not scene_ok(s):continue
        before=mapping(baseline('trigger'));after=mapping(s.get('trigger'))
        b=mapping(before.get('geometry'))or before;a=mapping(after.get('geometry'))or after
        if b.get('geometry_sha256')and a.get('geometry_sha256')and b['geometry_sha256']!=a['geometry_sha256']:
            result.append(outcome('trigger_geometry','state_change_observed','观察窗口地图碰撞状态发生变化；尚未归属具体机关',dict(before=b,after=a)));break
    if not result:result.append(outcome('execution','observed_state_not_confirmed','执行后采集完成，尚未确认预期结果',dict(expected=output,unavailable=unavailable)))
    return result
