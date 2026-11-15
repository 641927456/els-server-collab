"""Concrete code routes; addresses describe this pinned client, never fault attribution."""
from pathlib import Path
from gameplay_cause_analysis import verified_site

ROUTES={
 'buff_lifecycle':('tools/observe_client_lifecycles.js','buffState','查 0x11AF4F0 增益应用、0x11B0130 叠加/到期分支、0x119B540 计时暂停与递减；先核本服维持时长规则，不把不递减或叠加不变直接算错误。'),
 'door_animation':('tools/observe_client_lifecycles.js','visualState','查 0x1041040 → 0x1076D00 → 0xE01F50 转换特效，0x45A2D0 工厂限制/资源和 0x464890 播放状态；逻辑放行、创建、退役、画面完成分别核对。'),
 'delayed_trigger':('tools/client_lifecycle_analysis.py','lifecycle_outcomes','先核客户端实际加载资源的 line_source_sha256，再查固定资源的 TRIGGER_DATA/DELAY_TIME，再查 0x1ADA630 激活及 0x43E440 碰撞线写入；循环/多次写入/墙钟延迟不替代原生调度证据。'),
 'item_inventory':('tools/observe_client_effects.js','itemState','核同一位置的物品 UID、模板、数量及后续库存更新；查 consumable_messages.acknowledgement / fashion_state.record。'),
 'item_effect':('tools/observe_client_effects.js','actorState','查 x2_dx11.exe+0x1AB9D20 对应效果分支及服务端 consumables.ordinary；对照 effect_index、定义 SHA 和缺失字段。'),
 'quest':('tools/observe_client_effects.js','questState','查任务回包目标及 objectives；核 quest_flow.handle、quest_messages 的任务同步编码和原生任务写入 0xDFC350。'),
 'gate':('tools/observe_client_effects.js','gateState','查 x2_dx11.exe+0x1040D10 的 stage/target 查找和 dungeon_flow 的 gate_decision；逻辑门标志不代表动画完成。'),
 'trigger':('tools/observe_client_effects.js','triggerState','查 native_line_triggers.prepare 规则和 0x1ADA630 → 0x1B59EB0 激活集合；继续追具体机关动作的消费者。'),
 'collision_line':('tools/observe_client_effects.js','geometryState','查 x2_dx11.exe+0x43E440 的 line_id、requested_enabled；分别核调用前后目标线数量与启用数量。'),
 'collection':('tools/observe_client_effects.js','readPart','先核 unavailable 字段、对象归属与场景代数；采集缺失不能定为玩法失败。'),
}
NATIVE={
 'client_event_decode_failed':('客户端帧已接收','事件解析返回失败','x2_dx11.exe+0x680CA0 / 接收范围 0x6817E0'),
 'client_frame_without_event':('客户端帧已接收','未进入事件解析','x2_dx11.exe+0x6817E0'),
 'decoded_without_dispatch_evidence':('客户端事件已解析','解析到分发之间缺证据','x2_dx11.exe+0x3154DC0 / 0x1382280'),
 'dispatch_return_not_observed':('客户端分发已进入','分发返回缺证据','x2_dx11.exe+0x3154DC0 / 0x1382280'),
 'native_dispatch_declined':('客户端分发已返回','当前分发器未处理','x2_dx11.exe+0x3154DC0 / 0x1382280'),
}


def source_line(root,file,name):
    # Navigation hints in the selected source, not the loaded fault location.
    if root is None:return file+' :: '+name+' [源码未选择]'
    root=Path(root).resolve();path=(root/file).resolve()
    if not path.is_relative_to(root):return '[源码路径超出所选目录]' 
    try:
        for number,line in enumerate(path.read_text('utf8').splitlines(),1):
            if line.startswith('def '+name+'(')or line.startswith('function '+name+'('):
                return str(path)+':'+str(number)+' :: '+name+' [所选源码导航]'
    except OSError:pass
    return file+' :: '+name+' [所选源码缺失]'


def annotate_chains(rows,root):
    for row in rows:
        status=row['status'];locations=[]
        if status in NATIVE:
            row['last_verified_step'],row['unresolved_step'],native=NATIVE[status];locations.append(native)
        elif status.startswith('native_'):
            row['last_verified_step']='服务器写出 → 客户端接收 → 解析 → 分发返回'
            problems=[o for o in row.get('outcomes',[])if o['status']!='expected_state_observed'or o.get('verification_level')=='direction_or_cap_only']
            row['unresolved_step']=('只观察到分发返回，最终结果尚未覆盖'if not row.get('outcomes')else'执行后结果存在未匹配项或覆盖缺口'if problems else'已覆盖状态符合预期；未证明画面与全部玩法结果')
            locations.append('x2_dx11.exe+'+hex((row.get('dispatch_enter')or{}).get('site_rva',0)))
            lifecycle=[o for o in row.get('outcomes',[])if o['area']in('buff_lifecycle','door_animation','delayed_trigger')]
            observed=[o for o in lifecycle if o['status']in('applied_observed','native_pause_observed','countdown_observed','renewal_observed','expiry_flag_observed','removed_observed','effect_created','retirement_observed','native_delay_observed','animation_progress_observed','target_state_observed')]
            if observed:row['last_verified_step']+=' → '+observed[-1]['title']
            if lifecycle:row['unresolved_step']='；'.join(dict.fromkeys(o['title']for o in lifecycle))[:900]
        else:
            row['last_verified_step']='服务器写出完成'
            row['unresolved_step']='客户端接收或观察器身份缺少唯一证据'
            locations.append(source_line(root,'tools/observe_client_delivery.js','eventView'))
        for o in row.get('outcomes',[]):
            route=ROUTES.get(o['area'])
            if route:
                file,name,hint=route;o['next_step']=hint;locations.append(source_line(root,file,name))
            elif o['area'].endswith('_completion'):
                o['next_step']='继续补该机关动作／门动画的消费者和物理结果证据；不能用激活集合或逻辑标志代替。'
        handler=row.get('server_handler')
        if isinstance(handler,dict):
            status='运行源码已核对'if verified_site(handler,root)else'运行源码未核对，勿直接套当前行号'
            locations.append(source_line(root,handler.get('file',''),handler.get('function',''))+' ['+status+']')
        domain={0x115:('els_server/domain/consumables.py','ordinary'),0x30c:('els_server/domain/native_line_triggers.py','prepare'),0xf0:('els_server/domain/quest_flow.py','handle'),0xf3:('els_server/domain/quest_flow.py','handle'),0xf5:('els_server/domain/quest_flow.py','handle'),0x21a:('els_server/protocol/career_messages.py','use_ack'),0xad8:('els_server/protocol/ice_messages.py','result_events')}.get(row.get('kind'))
        if domain:locations.append(source_line(root,*domain))
        row['code_locations']=list(dict.fromkeys(locations))
        row['next_step']='按未匹配项检查对应代码；保留同一请求、线序号、trace_id 和定义 SHA。'+row['next_step']
    return rows
