'use strict';

const batchStorageKey='els-gm-batch-request';
let batchPending=JSON.parse(sessionStorage.getItem(batchStorageKey)||'null');
let batchBusy=false;
let batchModeActive=false;
const batchItems=new Map();
const batchModes={
    online:'当前在线角色 · 直接入背包',
    characters:'全服有效角色 · 角色邮件',
    accounts:'全服启用账号 · 账号共享邮件'
};
const batchModeHelp={
    online:'只发给当前在线的角色，道具直接进入背包。',
    characters:'所有有效角色分别收到邮件。一个账号有多个角色时，每个角色都有一份。',
    accounts:'每个启用账号收到一份道具。同账号任一角色可以在邮箱领取，多个附件会分成多封邮件。'
};

function setGiveMode(batch) {
    batchModeActive=batch;
    $('#singleGive').hidden=batch;
    $('#batchGive').hidden=!batch;
    $('#singleGiveTab').setAttribute('aria-pressed',String(!batch));
    $('#batchGiveTab').setAttribute('aria-pressed',String(batch));
    $('#catalogAction').textContent=batch
        ?'点击道具加入群发清单，也可以拖到清单。'
        :'点击道具选中，也可以拖到单人发放区。';
}

function catalogItemClick(item) {
    if (batchModeActive) addBatchItem(item);
    else choose(item);
}

function addBatchItem(item) {
    if (batchBusy||batchPending) return;
    if (batchItems.has(item.id)) {
        $('#batchRows').querySelector('[data-template="'+item.id+'"]')?.focus();
        return;
    }
    if (batchItems.size>=24) return error(Error('每批最多添加 24 种道具'));
    batchItems.set(item.id,{item,quantity:1});
    renderBatchDraft();
}

function renderBatchDraft() {
    const rows=[];
    for (const entry of batchItems.values()) {
        const {item}=entry;
        const line=el('div','draft-row');
        const label=el('div','draft-item-name');
        label.append(el('strong','',item.name),el('small','','#'+item.id+' · 堆叠 '+item.stack));
        const quantity=el('input');
        quantity.type='number';
        quantity.min='1';
        quantity.max='99';
        quantity.required=true;
        quantity.value=entry.quantity;
        quantity.dataset.template=item.id;
        quantity.setAttribute('aria-label',item.name+'的数量');
        quantity.oninput=()=>{entry.quantity=quantity.value};
        const remove=el('button','text-button','移除');
        remove.type='button';
        remove.setAttribute('aria-label','移除 '+item.name);
        remove.onclick=()=>{batchItems.delete(item.id);renderBatchDraft()};
        line.append(icon(item),label,quantity,remove);
        rows.push(line);
    }
    $('#batchRows').replaceChildren(...rows);
    $('#batchCount').textContent=batchItems.size+' 种道具';
    renderBatchControls();
}

function renderBatchControls(){
    const available=state?.batch_give_available===true;
    const mode=$('#batchMode').value;
    $('#batchFields').disabled=batchBusy||!!batchPending;
    $('#batchGiveButton').disabled=!batchItems.size||!available||!mode;
    $('#clearBatch').disabled=!batchItems.size;
    $('#batchRetry').disabled=batchBusy||!batchPending||!available;
    $('#batchInspect').disabled=batchBusy||!available;
    $('#batchModeHelp').textContent=batchModeHelp[mode]||'选好接收范围后，这里会说明玩家到哪里领取。';
    const message=batchPending?'这笔发放结果待核实。请先查询回执。'
        :!available?'游戏服务未就绪。可以先选道具，开服后再发。'
        :!batchItems.size?'先添加道具，再为每种道具填写数量。'
        :!mode?'道具已加入，请选择发给谁。'
        :'填写原因后预览，核对接收人数和每份道具。';
    if ($('#batchStatus').textContent!==message) $('#batchStatus').textContent=message;
}

function rememberBatch(value){
    batchPending=value;
    if(value)sessionStorage.setItem(batchStorageKey,JSON.stringify(value));
    else sessionStorage.removeItem(batchStorageKey);
    renderBatchControls();
}

function showBatchReceipt(receipt){
    const target=receipt.mode==='accounts'?'个账号':'个角色';
    $('#batchReceipt').textContent='操作编号 '+receipt.operation_id+' · '+receipt.recipients+' '+target
        +' · '+(receipt.items?receipt.items.length+' 种道具 · ':'')
        +(receipt.delivery==='game-mail'?'邮件已保存'+(receipt.mails_per_recipient?' · 每位 '+receipt.mails_per_recipient+' 封':''):'道具已入账并排队发送背包通知')
        +(receipt.replayed?' · 已核对原回执':'');
}

async function runBatch(work){
    if(batchBusy)return;
    batchBusy=true;renderBatchControls();
    try{await work()}catch(e){error(e)}
    finally{batchBusy=false;renderBatchControls()}
}

async function submitBatch(){
    try{
        const receipt=await api('batch-give',batchPending);
        showBatchReceipt(receipt);
        rememberBatch(null);
        batchItems.clear();
        renderBatchDraft();
    }catch(e){
        if(e.status===400){
            $('#batchReceipt').textContent='操作编号 '+batchPending.operation_id+' · '+e.message;
            rememberBatch(null);
        }else{
            $('#batchReceipt').textContent='操作编号 '+batchPending.operation_id+' · 结果待核实，请查询原回执或重提原请求。';
            $('#batchRecovery').open=true;
        }
        throw e;
    }
}

$('#batchForm').onsubmit=e=>{
    e.preventDefault();
    if(!batchItems.size||batchPending)return;
    runBatch(async()=>{
        const draft=[...batchItems.values()];
        const items=draft.map(({item,quantity})=>({template:item.id,quantity:Number(quantity)}));
        const value={mode:$('#batchMode').value,items};
        const reason=$('#batchReason').value;
        const preview=await api('batch-give-preview',value);
        const unit=value.mode==='accounts'?'个账号':'个角色';
        const list=draft.map(({item,quantity})=>item.name+' #'+item.id+' × '+quantity).join('\n');
        const mails=preview.mails_per_recipient?' · 每位 '+preview.mails_per_recipient+' 封邮件':'';
        const approval=await confirm('确认全服道具发放',
            batchModes[value.mode]+' · 共 '+preview.recipients+' '+unit+mails+'\n'+list,
            '全服发放',reason);
        if(!approval)return;
        const request={...value,operation_id:approval.operation_id,reason:approval.reason,
            confirm:approval.confirm,expected_audience:preview.expected_audience};
        $('#batchOperation').value=request.operation_id;
        $('#batchReceipt').textContent='操作编号 '+request.operation_id+' · 正在提交';
        rememberBatch(request);
        await submitBatch();
    });
};

$('#batchInspect').onclick=()=>runBatch(async()=>{
    const operation=$('#batchOperation').value.trim();
    const found=await api('batch-give-operation?'+new URLSearchParams({operation_id:operation}));
    if(found.committed){
        showBatchReceipt(found.receipt);
        if(batchPending?.operation_id===operation){
            rememberBatch(null);
            batchItems.clear();
            renderBatchDraft();
        }
    }else{
        $('#batchReceipt').textContent='操作编号 '+operation+' · 暂无已提交的发放回执。';
    }
});
$('#batchRetry').onclick=()=>runBatch(async()=>{
    if(batchPending)await submitBatch();
});
$('#singleGiveTab').onclick=()=>setGiveMode(false);
$('#batchGiveTab').onclick=()=>setGiveMode(true);
$('#batchMode').onchange=renderBatchControls;
$('#clearBatch').onclick=()=>{batchItems.clear();renderBatchDraft()};
bindCatalogDrop($('#batchDrop'),addBatchItem);
if(batchPending){
    setGiveMode(true);
    $('#batchRecovery').open=true;
    $('#batchOperation').value=batchPending.operation_id;
    $('#batchReceipt').textContent='操作编号 '+batchPending.operation_id+' · 结果待核实。';
}
renderBatchDraft();
