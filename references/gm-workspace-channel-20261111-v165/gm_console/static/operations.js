'use strict';
function uiIcon(name){
    const paths={
        overview:['M3 3h7v7H3z','M14 3h7v7h-7z','M3 14h7v7H3z','M14 14h7v7h-7z'],
        players:['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2','M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8','M17 4a4 4 0 0 1 0 8','M22 21v-2a4 4 0 0 0-3-3.87'],
        accounts:['M4 4h16v16H4z','M8 9h8','M8 13h8','M8 17h4'],
        events:['M4 5h16v16H4z','M16 3v4','M8 3v4','M4 11h16','m9 16 2 2 4-4'],
        items:['M3 8h18v4H3z','M5 12v9h14v-9','M12 8v13','M12 8H7.5A2.5 2.5 0 1 1 10 5.5L12 8Z','M12 8h4.5A2.5 2.5 0 1 0 14 5.5L12 8Z'],
        announcements:['m3 10 15-6v16L3 14z','M3 10v4','m7 15 2 6h3l-2-5','M21 9v6'],
        rates:['M4 21V14','M10 21V8','M16 21V3','M22 21V11'],
        history:['M3 11a9 9 0 1 1 2.6 7','M3 4v7h7','M12 7v5l3 2'],
        maintenance:['M14 5a5 5 0 0 0-6 6L3 16l5 5 5-5a5 5 0 0 0 6-6l-4 4-4-4z'],
        settings:['M4 6h16','M4 12h16','M4 18h16','M8 3v6','M16 9v6','M10 15v6'],
        cash:['M3 6h18v14H3z','M3 6V4h15','M16 11h5v5h-5z'],
        coupons:['M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4z','M15 5v3','M15 11v2','M15 16v3'],
        backup:['M4 4h16v16H4z','M8 4v6h8V4','M8 20v-6h8v6'],
        refresh:['M20 7a9 9 0 0 0-15-2L2 8','M2 2v6h6','M4 17a9 9 0 0 0 15 2l3-3','M22 22v-6h-6'],
        chevron:['m9 5 7 7-7 7'],search:['M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15','m16 16 5 5'],
        start:['m8 4 12 8-12 8z'],stop:['M5 5h14v14H5z']
    };
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');svg.classList.add('ui-icon');
    for(const d of paths[name]||paths.settings){const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',d);svg.append(path)}
    return svg;
}
for(const button of $$('nav [data-tab]')){button.title=tabs[button.dataset.tab];button.setAttribute('aria-label',button.title);button.querySelector('span')?.replaceChildren(uiIcon(button.dataset.tab))}
for(const node of $$('.search>span'))node.replaceChildren(uiIcon('search'));
for(const button of $$('.quick-actions button')){button.querySelector('span')?.replaceChildren(uiIcon(button.dataset.jump||'backup'));button.querySelector('b')?.remove()}
$$('.stat-label i').forEach((node,index)=>node.replaceChildren(uiIcon(['overview','players','settings','rates'][index])));
for(const [selector,name] of [['.start-action','start'],['.stop-action','stop'],['.backup-action:not(.quick-actions button)','backup'],['.refresh-action','refresh'],['#refresh','refresh'],['#refreshAccounts','refresh']]){
    for(const button of $$(selector)){for(const node of [...button.childNodes])if(node.nodeType===Node.TEXT_NODE)node.textContent=node.textContent.replace(/[▶■◫↻]/g,'').trim();button.prepend(uiIcon(name))}
}
for(const button of $$('[data-jump]'))for(const node of [...button.childNodes])if(node.nodeType===Node.TEXT_NODE)node.textContent=node.textContent.replace(/[↗→]/g,'').trim();

const operationDirectory=[
    ['accounts','账号与角色','账号名、角色名、精确编号、在线筛选与角色背包','只读查询'],
    ['accounts','提升角色等级','离线角色调级，自动备份并保存等级与经验','下次进入角色'],
    ['cash','账号现金充值','账号共享余额、明确金额、原编号回执核查','在线落账'],
    ['items','物品发放','名称、编号、分类和收藏检索，向在线角色发货','在线生效'],
    ['items','全服道具发放','当前在线角色直发、全部有效角色邮件、启用账号共享邮件','预览后确认'],
    ['coupons','兑换码管理','设置奖励、数量、名额、绑定账号与期限；查询或撤销','在线生效'],
    ['events','活动副本与战场','四项既有活动的入场开关、开始和结束时间','后续入场'],
    ['events','签到、在线称号与战斗力助力','按实际已安装范围设置开关，沿用已批准排期和奖励','在线生效'],
    ['rates','角色通关经验倍率','0–100倍，原经验与结算账本继续复用','后续结算'],
    ['rates','物品与ED掉落率','普通副本随机掉落倍率、指定来源的物品与ED掉落概率','后续判定'],
    ['rates','普通装备强化成功率','+0至+13，保留原有失败分配、保护与保底规则','后续强化'],
    ['announcements','全服公告','滚动公告、重复次数、间隔与取消后续发送','在线生效'],
    ['settings','注册与运行参数','注册开关、账号与连接上限、超时、装备入口和日志','关服后保存'],
    ['maintenance','开服、正常关服与备份','服务控制、双库备份和运行日志','维护操作'],
    ['history','操作记录与回执','按操作编号核对结果与配置变更','只读查询']
];
function renderOperationDirectory(){const query=$('#operationSearch').value.trim().toLowerCase(),box=$('#operationDirectory');box.replaceChildren();for(const [target,title,description,effect] of operationDirectory){if(query&&!(title+' '+description).toLowerCase().includes(query))continue;const button=el('button','operation-card');button.append(uiIcon(target),el('strong','',title),el('small','',description),el('span','badge',effect));button.onclick=()=>showTab(target);box.append(button)}if(!box.children.length)empty(box,'没有匹配功能','尝试搜索：账号、现金、经验或活动。')}
$('#operationSearch').oninput=renderOperationDirectory;renderOperationDirectory();

let cashSnapshot=null,cashPending=null,cashGeneration=0;
function cashLocked(){for(const id of ['cashAccount','cashAmount','cashReason'])$('#'+id).disabled=!!cashPending;$('#cashSubmit').disabled=!!cashPending||!cashSnapshot;$('#cashRetry').disabled=!cashPending;$('#cashRelease').disabled=true}
function openCashAccount(account){if(cashPending){error(Error('先核实当前充值请求，账号尚未切换'));return}$('#cashAccount').value=account;cashSnapshot=null;cashLocked();loadCashBalance()}
async function loadCashBalance(){const generation=++cashGeneration,account=Number($('#cashAccount').value);cashSnapshot=null;cashLocked();try{const result=await api('cash-balance?'+new URLSearchParams({account_id:account}));if(generation!==cashGeneration)return;cashSnapshot=result;$('#cashBalance').textContent='账号 #'+result.account_id+' · 当前现金 '+result.balance.toLocaleString();cashLocked()}catch(e){if(generation===cashGeneration){$('#cashBalance').textContent='余额未核实，请重新查询。';error(e)}}}
$('#cashAccount').oninput=()=>{cashGeneration++;cashSnapshot=null;$('#cashBalance').textContent='账号已变化，请重新查询余额。';cashLocked()};
$('#cashLoad').onclick=e=>action(e.currentTarget,loadCashBalance);
function showCashReceipt(result){$('#cashReceipt').textContent=JSON.stringify(result,null,2)}
async function submitCashPending(){const result=await api('cash-credit',cashPending);showCashReceipt(result);cashPending=null;cashSnapshot=null;cashLocked();await loadCashBalance();toast('账号现金已落账')}
$('#cashForm').onsubmit=e=>{e.preventDefault();action($('#cashSubmit'),async()=>{if(cashPending||!cashSnapshot)throw Error('请先查询当前余额');const account=Number($('#cashAccount').value),amount=Number($('#cashAmount').value);if(!Number.isSafeInteger(amount)||amount<1||amount+cashSnapshot.balance>2147483647)throw Error('金额超出可用余额上限');if(account!==cashSnapshot.account_id)throw Error('账号已变化，请重新查询');const approval=await confirm('确认账号现金充值','账号 #'+account+'：'+cashSnapshot.balance.toLocaleString()+' → '+(cashSnapshot.balance+amount).toLocaleString()+'，增加 '+amount.toLocaleString()+' 现金。','',$('#cashReason').value);if(!approval)return;cashPending={operation_id:approval.operation_id,reason:approval.reason,account_id:account,amount,expected_balance:cashSnapshot.balance};$('#cashOperation').value=cashPending.operation_id;showCashReceipt({operation_id:cashPending.operation_id,status:'等待确认结果，请保留此编号'});cashLocked();await submitCashPending()}).finally(cashLocked)};
$('#cashInspect').onclick=e=>action(e.currentTarget,async()=>{const account=cashPending?.account_id||Number($('#cashAccount').value),operation=$('#cashOperation').value.trim();const result=await api('cash-operation?'+new URLSearchParams({account_id:account,operation_id:operation}));showCashReceipt(result);if(cashPending?.operation_id!==operation)return;if(result.committed){cashPending=null;cashLocked();await loadCashBalance()}else{const history=await api('history');$('#cashRelease').disabled=!history.some(row=>row.id===operation&&row.action==='cash-credit'&&row.status==='failed')}});
$('#cashRetry').onclick=e=>action(e.currentTarget,async()=>{if(!cashPending)throw Error('本页没有保留的原请求，请按原编号查询');await submitCashPending()}).finally(cashLocked);
$('#cashRelease').onclick=()=>{cashPending=null;cashSnapshot=null;cashLocked();$('#cashBalance').textContent='原请求已确认失败，请重新查询余额后再创建充值。'};

let selectedActivities=null,selectedActivitiesDirty=false,selectedActivitiesPending=null,selectedLoading=false;
function activityWindow(scope,data){const config=scope==='growth'?data.growth_configuration:data.configuration?.[scope];if(!config)return '沿用已批准活动排期';const format=stamp=>new Date(stamp*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});if(config.starts&&config.ends)return format(config.starts)+' — '+format(config.ends)+'（UTC+8）';if(config.weeks)return config.weeks.map(w=>'第'+w[0]+'周：'+format(w[1])+' — '+format(w[2])).join('；');return '沿用已批准活动排期'}
async function loadSelectedActivities(force=false){if(selectedLoading||(!force&&(selectedActivitiesDirty||selectedActivitiesPending)))return;selectedLoading=true;try{const data=await api('selected2026');selectedActivities=data;selectedActivitiesDirty=false;$('#selectedActivitiesState').textContent=data.available?'当前运行版本已安装 · 配置 v'+data.revision+' · 时间均为 UTC+8':data.message;$('#selectedActivitiesFields').disabled=!data.available;const box=$('#selectedActivitiesCards');box.replaceChildren();if(!data.available)return;for(const scope of ['attendance','online','growth']){const available=data.available_scopes.includes(scope),card=el('div','job'),label=el('label','setting-toggle'),input=el('input');input.type='checkbox';input.checked=data.enabled[scope];input.disabled=!available;input.dataset.activityScope=scope;input.onchange=()=>selectedActivitiesDirty=true;label.append(input,el('strong','',data.names[scope]));card.append(label,el('p','scope',available?data.reward_summary[scope]:'当前运行版本未安装，开关不可用'),el('small','',activityWindow(scope,data)));box.append(card)}}catch(e){$('#selectedActivitiesState').textContent='活动状态读取失败，请重新读取。';$('#selectedActivitiesFields').disabled=true;error(e)}finally{selectedLoading=false}}
$('#loadSelectedActivities').onclick=()=>{if(selectedActivitiesPending)return error(Error('请先核实保留的原活动请求'));loadSelectedActivities(true)};
async function submitSelectedActivities(){const result=await api('selected2026',selectedActivitiesPending);$('#selectedActivitiesReceipt').textContent=JSON.stringify({operation_id:result.operation_id,revision:result.revision,enabled:result.enabled,replayed:result.replayed},null,2);selectedActivitiesPending=null;selectedActivitiesDirty=false;$('#retrySelectedActivities').hidden=true;await loadSelectedActivities(true);toast('活动开关已保存')}
$('#selectedActivitiesForm').onsubmit=e=>{e.preventDefault();action($('#saveSelectedActivities'),async()=>{if(selectedActivitiesPending||!selectedActivities?.available)throw Error('请先读取活动状态或核实原请求');const enabled={...selectedActivities.enabled};for(const input of $$('[data-activity-scope]'))enabled[input.dataset.activityScope]=input.checked;const value=await confirm('保存签到、称号与助力开关','仅修改当前已安装活动开关，保留原排期、资格、奖励和累计记录。','',$('#selectedActivitiesReason').value);if(!value)return;selectedActivitiesPending={operation_id:value.operation_id,reason:value.reason,expected_revision:selectedActivities.revision,enabled};$('#selectedActivitiesReceipt').textContent='操作编号：'+value.operation_id;$('#retrySelectedActivities').hidden=false;await submitSelectedActivities()})};
$('#retrySelectedActivities').onclick=e=>action(e.currentTarget,async()=>{if(!selectedActivitiesPending)throw Error('没有保留的原请求');await submitSelectedActivities()});

let serverSettings=null,serverSettingsDirty=false;
async function loadServerSettings(force=false){if(serverSettingsDirty&&!force)return;try{const data=await api('server-settings');serverSettings=data;serverSettingsDirty=false;$('#serverSettingsState').textContent=(data.editable?'可以保存。':'当前仅可查看，请先正常关服。')+data.effect;$('#serverSettingsFields').disabled=!data.editable;const groups=new Map(),box=$('#serverSettingsCards');box.replaceChildren();for(const field of data.fields){if(!groups.has(field.group)){const card=el('article','card settings-group');card.append(el('h2','',field.group));groups.set(field.group,card);box.append(card)}const label=el('label',field.kind==='bool'?'setting-toggle':'',field.label),input=el('input');input.dataset.serverSetting=field.name;input.type=field.kind==='bool'?'checkbox':field.kind==='text'?'text':'number';if(field.kind==='bool')input.checked=field.value;else if(field.kind==='text'){input.value=field.value;input.maxLength=field.max;input.required=true}else{input.value=field.value;input.min=field.min;input.max=field.max;input.step=field.kind==='int'?'1':'any';input.required=true}input.oninput=()=>serverSettingsDirty=true;label.append(input);groups.get(field.group).append(label)}}catch(e){$('#serverSettingsState').textContent='参数读取失败，请重新载入。';$('#serverSettingsFields').disabled=true;error(e)}}
$('#loadServerSettings').onclick=()=>loadServerSettings(true);
$('#serverSettingsForm').onsubmit=e=>{e.preventDefault();action($('#saveServerSettings'),async()=>{if(!serverSettings?.editable)throw Error('请先正常关服并重新读取参数');const settings={};for(const input of $$('[data-server-setting]'))settings[input.dataset.serverSetting]=input.type==='checkbox'?input.checked:input.type==='text'?input.value:Number(input.value);const value=await confirm('保存服务运营参数','保存前自动备份双库和配置；参数在下次开服时生效。','',$('#serverSettingsReason').value);if(!value)return;const result=await api('server-settings',{operation_id:value.operation_id,reason:value.reason,expected_revision:serverSettings.revision,settings});$('#serverSettingsReceipt').textContent=JSON.stringify(result,null,2);serverSettingsDirty=false;await loadServerSettings(true);toast(result.message)})};
