'use strict';
let eventsDirty=false,eventsRevision=0,accountOffset=0,accountTotal=0,accountGeneration=0,accountTimer,inventoryTarget=null,inventoryOffset=0,inventoryCount=0,inventoryGeneration=0,inventoryTimer;
let favorites=new Set();try{const saved=JSON.parse(localStorage.getItem('els-gm-favorites')||'[]');if(Array.isArray(saved))favorites=new Set(saved.filter(v=>Number.isSafeInteger(v)&&v>0).slice(0,500))}catch{}
const units={1:'艾索德',2:'爱莎',3:'蕾娜',4:'雷文',5:'伊芙',6:'澄',7:'艾拉',8:'艾丽希斯',9:'艾迪',10:'露／希尔',11:'萝丝',12:'艾因',13:'菈比',14:'诺亚',15:'莉缇娅'};
async function loadFacets(){if($('#categoryFilter').options.length>1)return;try{const data=await api('categories');for(const row of data.categories)$('#categoryFilter').append(new Option(row.name+' ('+row.count+')',row.id));for(const row of data.groups)$('#bagFilter').append(new Option(row.name+' · 背包 '+row.id+' ('+row.count+')',row.id));$('#iconsOnly').title='原始图标覆盖 '+data.with_icons+' / '+data.total+' 种可发道具';$('#iconCoverage').textContent='原始图标 '+data.with_icons.toLocaleString()+' / '+data.total.toLocaleString()+'；'+(data.total-data.with_icons)+' 种客户端缺失贴图的道具显示分类占位图。'}catch(e){error(e)}}
for(const id of ['categoryFilter','sortFilter','favoritesOnly'])$('#'+id).onchange=()=>{itemsOffset=0;loadItems()};
$('#clearSearch').onclick=()=>{for(const id of ['search','bagFilter','categoryFilter'])$('#'+id).value='';$('#sortFilter').value='relevance';$('#favoritesOnly').checked=false;$('#iconsOnly').checked=false;itemsOffset=0;loadItems()};
function updateFavorite(){const b=$('#favoriteItem');b.disabled=!selected;b.textContent=selected&&favorites.has(selected.id)?'★ 已收藏 · 点击取消':'☆ 收藏此道具'}
$('#favoriteItem').onclick=()=>{if(!selected)return;if(favorites.has(selected.id))favorites.delete(selected.id);else{if(favorites.size>=500)return error(Error('最多收藏 500 种道具'));favorites.add(selected.id)}localStorage.setItem('els-gm-favorites',JSON.stringify([...favorites]));updateFavorite();if($('#favoritesOnly').checked)loadItems()};
$('#experienceMultiplier').oninput=()=>ratesDirty=true;
$$('[data-xp]').forEach(b=>b.onclick=()=>{$('#experienceMultiplier').value=b.dataset.xp;ratesDirty=true;toast('已填入 '+b.dataset.xp+' 倍经验，请保存后生效')});

async function loadInventory(){if(!inventoryTarget)return;const generation=++inventoryGeneration;try{const data=await api('inventory?'+new URLSearchParams({account:inventoryTarget.account,uid:inventoryTarget.uid,offset:inventoryOffset,q:$('#inventorySearch').value}));if(generation!==inventoryGeneration)return;inventoryCount=data.total;$('#inventoryTitle').textContent=data.name+' · 只读背包';$('#inventoryTotal').textContent='角色 UID '+data.uid+' · 共 '+data.total+' 个物品实例；快照以读取时的存档为准。';const box=$('#inventoryGrid');box.replaceChildren();for(const item of data.rows){const card=el('div','item-card');card.append(icon(item),el('strong','',item.name),el('small','','#'+item.id+' × '+item.quantity),el('small','',item.bag+' · 位置 '+item.slot),el('small','','实例 '+item.instance_uid));box.append(card)}if(!data.rows.length)empty(box,'没有匹配的物品','此页只读展示当前角色实际持有的道具。');$('#inventoryPage').textContent=(Math.floor(inventoryOffset/48)+1)+' / '+Math.max(1,Math.ceil(data.total/48));$('#prevInventory').disabled=inventoryOffset===0;$('#nextInventory').disabled=inventoryOffset+48>=data.total}catch(e){error(e)}}
$('#closeInventory').onclick=()=>{$('#inventoryDialog').close();inventoryGeneration++};$('#inventorySearch').oninput=()=>{clearTimeout(inventoryTimer);inventoryTimer=setTimeout(()=>{inventoryOffset=0;loadInventory()},300)};$('#prevInventory').onclick=()=>{inventoryOffset=Math.max(0,inventoryOffset-48);loadInventory()};$('#nextInventory').onclick=()=>{inventoryOffset+=48;loadInventory()};

function localTime(epoch){if(epoch===null)return '';const d=new Date(epoch*1000);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,19)}
function renderEvents(){if(!state?.events)return;eventsRevision=state.events.revision;$('#eventsRevision').textContent='v'+eventsRevision;const box=$('#eventCards');box.replaceChildren();for(const event of state.events.rows){const card=el('article','card event-card'),head=el('div','card-heading');head.append(el('h2','',event.name),el('span','badge'+(event.open?' online':''),event.open?'已开放':!event.enabled?'已关闭':event.start&&event.start*1000>Date.now()?'等待开始':'已结束'));card.append(head,el('p','scope','活动编号 '+event.id+' · '+event.scope));const toggle=el('label','event-toggle'),check=el('input');check.type='checkbox';check.checked=event.enabled;check.dataset.event=event.id;check.dataset.field='enabled';toggle.append(check,document.createTextNode('允许开放此活动'));card.append(toggle);const pair=el('div','form-pair');for(const field of ['start','end']){const label=el('label','',field==='start'?'开始时间（留空即刻）':'结束时间（留空长期）'),input=el('input');input.type='datetime-local';input.step='1';input.value=localTime(event[field]);input.dataset.event=event.id;input.dataset.field=field;label.append(input);pair.append(label)}card.append(pair);box.append(card)}$$('#eventCards input').forEach(input=>input.oninput=()=>eventsDirty=true)}
$('#eventsForm').onsubmit=async e=>{e.preventDefault();await action(e.submitter,async()=>{if(!state.ready)throw Error('请在游戏服务运行后保存活动配置');const expectedRevision=eventsRevision;const events={};for(const input of $$('#eventCards input')){const id=input.dataset.event;events[id]||={};events[id][input.dataset.field]=input.type==='checkbox'?input.checked:input.value?Math.floor(new Date(input.value).getTime()/1000):null}const value=await confirm('保存活动开放配置','只影响新入场；已在活动内的玩家可以继续完成本局。','',$('#eventsReason').value);if(value){await api('events',{...value,events,expected_revision:expectedRevision});eventsDirty=false;toast('活动开关和时间范围已保存')}})};

$('#reloadEvents').onclick=()=>{eventsDirty=false;refresh()};
$('#reloadRates').onclick=()=>{ratesDirty=false;formalDropsDirty=false;$('#error').hidden=true;refresh()};

function renderActivityCalendar() {
    const box=$('#activityCalendar');
    const rows=state.activity_calendar||[];
    box.replaceChildren(...rows.map(event=>{
        const card=el('div','job');
        const heading=el('div','card-heading');
        heading.append(el('strong','',event.name),el('span','badge'+(event.open?' online':''),event.open?'进行中':'未开放'));
        card.append(heading,el('p','scope',event.scope));
        if (event.start) card.append(el('small','',announcementTime(event.start)+' 至 '+announcementTime(event.end)));
        if (event.mail_deadline) card.append(el('small','','邮件领取截止 '+announcementTime(event.mail_deadline)));
        return card;
    }));
    if (!rows.length) box.append(el('p','scope','开服后读取当前版本的运营排期。'));
}
