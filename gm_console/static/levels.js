'use strict';
let levelTarget=null,pendingLevel=null;
try{pendingLevel=JSON.parse(sessionStorage.getItem('els-gm-level-pending')||'null')}catch{}
function openLevelEditor(account,role){
    levelTarget={account,role};
    $('#levelTarget').textContent=role.name+' · '+careerName(role)+' · UID '+role.uid+' · 当前 Lv.'+role.level;
    $('#targetLevel').min=String(role.level+1);$('#targetLevel').value='99';$('#levelReason').value='';
    $('#levelReceipt').hidden=true;$('#saveLevel').disabled=false;
    $('#retryLevel').hidden=!pendingLevel;
    $('#levelDialog').showModal();
}
$('#cancelLevel').onclick=()=>$('#levelDialog').close();
async function submitLevel(value){
    pendingLevel=value;sessionStorage.setItem('els-gm-level-pending',JSON.stringify(value));
    $('#saveLevel').disabled=true;$('#retryLevel').disabled=true;
    try{
        const r=await api('set-level',value);
        pendingLevel=null;sessionStorage.removeItem('els-gm-level-pending');
        $('#levelReceipt').hidden=false;
        $('#levelReceipt').textContent=(r.replayed?'已核实原操作，未重复修改。':'等级与经验已保存。')+' '+r.name+'：Lv.'+r.before_level+' → Lv.'+r.level+'。下次进入角色生效。操作编号：'+r.operation_id+(r.backup?'。备份：'+r.backup:'');
        $('#retryLevel').hidden=true;
        await loadAccounts();await refresh();toast('角色等级已保存，下次进入角色生效');
    }catch(e){
        error(e);$('#retryLevel').hidden=false;$('#levelReceipt').hidden=false;
        $('#levelReceipt').textContent='本次请求尚未确认完成。可核实原操作，或在操作记录中查询。操作编号：'+value.operation_id;
        $('#saveLevel').disabled=false;
    }finally{$('#retryLevel').disabled=false}
}
$('#levelForm').onsubmit=async e=>{
    e.preventDefault();if(!levelTarget)return;
    const {account,role}=levelTarget,level=Number($('#targetLevel').value),reason=$('#levelReason').value.trim();
    if(!Number.isInteger(level)||level<=role.level||level>99)return error(Error('目标等级须高于当前等级，最高99级'));
    if(reason.length<2)return error(Error('请输入操作原因'));
    const value={account_id:account.id,uid:role.uid,level,expected_version:role.level_version,reason};
    const fingerprint=v=>JSON.stringify([v.account_id,v.uid,v.level,v.expected_version,v.reason]);
    value.operation_id=pendingLevel&&fingerprint(pendingLevel)===fingerprint(value)?pendingLevel.operation_id:crypto.randomUUID();
    await submitLevel(value);
};
$('#retryLevel').onclick=async()=>{if(pendingLevel)await submitLevel(pendingLevel)};
