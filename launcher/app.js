'use strict';
const icons={
 home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-6v-7h-4v7H4a1 1 0 0 1-1-1Z"/>',
 gm:'<path d="m12 3 8 4v5c0 5-8 9-8 9S4 17 4 12V7Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
 backup:'<path d="M4 7h6l2 2h8v11H4Z"/><path d="M4 7V4h6l2 2h8v3"/><path d="M12 12v5m-2-2 2 2 2-2"/>',
 features:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 17h7m-3.5-3.5v7"/>',
 settings:'<path d="m9 3-.7 3-2.8 1L3 9l1.5 3L3 15l2.5 2 2.8 1L9 21h6l.7-3 2.8-1 2.5-2-1.5-3L21 9l-2.5-2-2.8-1L15 3Z"/><circle cx="12" cy="12" r="3"/>',
 logs:'<path d="M6 3h9l4 4v14H6Z"/><path d="M14 3v5h5M9 12h7m-7 4h7"/>',
 refresh:'<path d="M20 9a8 8 0 1 0-1 9M20 4v5h-5"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',
 play:'<path d="m8 4 12 8-12 8Z"/>',arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
 check:'<path d="m5 12 4 4L19 6"/>',info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
 coin:'<circle cx="12" cy="12" r="9"/><path d="M15 8h-5v8h5m-5-4h4"/>',
 level:'<path d="m5 16 7-7 7 7M5 9l7-7 7 7M12 10v11"/>',
 box:'<path d="m12 3 9 5-9 5-9-5Zm-9 5v10l9 4 9-4V8M12 13v9M7 5l10 5"/>',
 search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
 town:'<path d="M3 21V8l5-4 5 4v13m0-10h7v10M6 12h3m-3 4h3m8 0v5"/>',
 folder:'<path d="M3 7V4h7l2 3h9v13H3Z"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
 stop:'<rect x="5" y="5" width="14" height="14" rx="2"/>',
 minimize:'<path d="M5 12h14"/>',maximize:'<rect x="5" y="5" width="14" height="14" rx="1"/>',restore:'<path d="M8 8V4h12v12h-4M4 8h12v12H4Z"/>',
 crystal:'<path d="m12 2 7 8-7 12-7-12Zm0 0v12m-7-4 7 4 7-4"/>',
 user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
 warning:'<path d="M12 3 2 21h20ZM12 9v5m0 3v.1"/>',
 repo:'<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="8" r="2.5"/><path d="M6 8.5v7M8.5 6h4A3.5 3.5 0 0 1 16 9.5M18 10.5V12a4 4 0 0 1-4 4h-4"/>'
};
const icon=(name)=>`<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]||icons.info}</svg>`;
const esc=(value)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(value)=>Number(value||0).toLocaleString('zh-CN');
const $=(s)=>document.querySelector(s);
const routes={home:['冒险首页','home'],gm:['GM 工具','gm'],backups:['存档备份','backup'],features:['功能进度','features'],repo:['仓库同步','repo'],settings:['启动设置','settings'],logs:['运行日志','logs']};
let token=location.hash.slice(1);
if(token && !routes[token]){sessionStorage.setItem('els-launcher-token',token);history.replaceState(null,'','/');}
else token=sessionStorage.getItem('els-launcher-token')||'';
let page='home',tab='profile',state=null,repoData=null,characters=[],selected=Number(localStorage.getItem('els-character')||1001),chosenItem=null,epoch=0,mutating=false,closed=false,searchTimer,itemOffset=0,itemsQuery='',itemsGroup='all';
const main=$('#main');
document.body.classList.toggle('motion-off',localStorage.getItem('els-reduce-motion')==='true');
$('#refresh').innerHTML=icon('refresh');$('#close-app').innerHTML=icon('close');
$('#minimize-app').innerHTML=icon('minimize');$('#maximize-app').innerHTML=icon('maximize');
$('#navigation').innerHTML=Object.entries(routes).map(([key,[name,img]],i)=>`${i===4?'<div class="nav-separator"></div>':''}<button class="nav-item" data-nav="${key}" title="${name}" aria-label="${name}">${icon(img)}<span>${name}</span></button>`).join('');

async function api(path,data,timeoutMs=45000){
 const options={headers:{'X-Launcher-Token':token}};
 if(data!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(data);}
 const controller=new AbortController();options.signal=controller.signal;
 const timeout=setTimeout(()=>controller.abort(),timeoutMs);
 try{const response=await fetch('/api/'+path,options);let body;try{body=await response.json();}catch{throw Error('无法读取本地服务响应，请重新打开启动器');}if(!response.ok)throw Error(body.error||'请求未能完成');return body.data;}
 catch(e){if(e.name==='AbortError')throw Error('操作仍可能在后台处理。请先刷新数据，避免重新发起同一笔发放。');throw e;}
 finally{clearTimeout(timeout);}
}
function toast(text,error=false){const element=document.createElement('div');element.className='toast'+(error?' error':'');element.textContent=text;$('#toast-area').append(element);setTimeout(()=>element.remove(),6500);}
function heading(title,sub,action=''){return `<div class="page-heading"><div><p class="eyebrow">${page==='home'?'YOUR LOCAL WORLD':page==='gm'?'GAME MASTER':page==='backups'?'SAVE & PROTECT':page==='features'?'WORLD IN PROGRESS':page==='repo'?'REPOSITORY SYNC':page==='logs'?'SESSION LOG':'LAUNCHER PREFERENCES'}</p><h1>${title}</h1><p>${sub}</p></div>${action}</div>`;}
function empty(text,img='box'){return `<div class="empty-state">${icon(img)}${text}</div>`;}
function role(){return characters.find(c=>c.uid===selected)||characters[0];}
function roleSummary(c){if(!c)return empty('还没有本地角色。首次进入游戏后，在角色界面创建。','user');return `<div class="role-summary"><div class="role-emblem ${c.unit_type===5?'blue':''}">${esc(c.role.slice(0,1))}</div><div class="role-info"><strong>${esc(c.name)}</strong><small><span class="level-tag">Lv. ${c.level}</span>${esc(c.role)} <span class="muted">· UID ${c.uid}</span></small></div></div>`;}
function stats(c){return `<div class="role-stats"><div><span>持有 ED</span><strong>${number(c.ed)}</strong></div><div><span>背包格位</span><strong>${number(c.item_count)} <small>件</small></strong></div><div><span>角色等级</span><strong>${c.level} <small>/ 99</small></strong></div></div>`;}
function writeNotice(){return `<div class="notice ${state?.gm_locked?'warn':''}">${icon(state?.gm_locked?'warning':'gm')}<div><strong>${state?.gm_locked?'游戏或服务端正在运行 · 只读模式':'离线 GM · 可以修改'}</strong><br>${state?.gm_locked?'可查看角色和搜索道具。请先正常退出游戏，修改功能会自动解锁。':'每次提交前自动备份。修改下次登录生效，发放和等级调整均保留操作记录。'}</div></div>`;}

function renderHome(){
 const c=role();
 main.innerHTML=heading('准备好，继续冒险。','熟悉的世界，属于你的旅程。',`<button class="button outlined" data-action="check">${icon('check')}检查游戏环境</button>`)+`
 <section class="hero" aria-label="魔奇原生场景插图"><div><p class="eyebrow">THE JOURNEY CONTINUES</p><h2>再一次，<br>踏入<span>艾里奥斯。</span></h2><p class="hero-copy">从熟悉的魔奇出发，继续你的冒险。<br>角色进度与背包，都会为你保留。</p></div><div class="hero-bottom"><div class="hero-launch"><button class="button launch-button" id="launch-game" data-action="start">${icon('play')}启动游戏</button><div class="launch-caption" id="launch-caption">自动准备本地环境<br>启动后在游戏内选择你的角色</div></div><span class="scene-credit">原生场景 · 魔奇 RUBEN</span></div></section>
 <div class="home-grid"><section class="panel"><div class="panel-head"><h2>我的角色 <small>${characters.length} / 16</small></h2><button class="button text" data-nav="gm">管理角色 ${icon('arrow')}</button></div>${roleSummary(c)}${c?stats(c):''}<div class="quick-row"><button class="button subtle" data-action="backup">${icon('backup')}备份存档</button><button class="button subtle" data-nav="logs">${icon('logs')}查看日志</button></div></section>
 <section class="panel"><div class="panel-head"><h2>冒险手记</h2><span class="badge">本地世界</span></div><div class="info-line"><span class="info-icon">${icon('crystal')}</span><div><h3>从艾尔之树启程</h3><p>已接入本地副本探索、清怪开门与通关奖励。</p></div></div><div class="info-line"><span class="info-icon">${icon('box')}</span><div><h3>让角色慢慢成长</h3><p>商城、背包、转职和部分装备功能已开放。</p></div></div><div class="info-line"><span class="info-icon">${icon('gm')}</span><div><h3>为你的世界多一点自由</h3><p>退出游戏后，可在 GM 工具中发放 ED 和已验证道具。</p></div></div></section></div>
 <div class="mini-banner">${icon('info')}<span>这个世界仍在完善中。各项玩法的接入情况，可在「功能进度」中查看。</span><button class="button text" data-nav="features" style="margin-left:auto;flex-shrink:0">查看进度 ${icon('arrow')}</button></div>`;
}

function renderGM(){
 const c=role();if(c){selected=c.uid;localStorage.setItem('els-character',selected);}
 main.innerHTML=heading('GM 工具','管理这台电脑上的角色。每次修改，都有迹可循。',`<button class="button outlined" data-action="reload">${icon('refresh')}刷新资料</button>`)+`<div id="gm-notice">${writeNotice()}</div><div class="gm-layout"><aside class="panel roster"><div class="roster-title">选择角色 <span class="muted">${characters.length} / 16</span></div><div class="roster-list">${characters.map(x=>`<button class="character-card ${x.uid===selected?'selected':''}" data-character="${x.uid}" aria-pressed="${x.uid===selected}"><span class="avatar">${esc(x.role.slice(0,1))}</span><span><span class="character-name">${esc(x.name)}</span><small>${esc(x.role)} · Lv. ${x.level}</small></span></button>`).join('')||empty('进入游戏后创建角色','user')}</div></aside><div class="gm-content"><section class="panel">${c?`<div class="character-overview">${roleSummary(c)}${stats(c)}</div><div class="tabbar" role="tablist" aria-label="GM 功能">${[['profile','角色调整'],['items','道具发放'],['inventory','背包查看'],['history','操作记录']].map(([id,name])=>`<button class="tab-button ${tab===id?'active':''}" role="tab" aria-selected="${tab===id}" data-tab="${id}">${name}</button>`).join('')}</div><div id="gm-tab"></div>`:empty('没有可管理的角色','user')}</section></div></div>`;
 if(c)renderGMTab();
}
function renderGMTab(){
 const c=role();const container=$('#gm-tab');if(!c||!container)return;
 if(tab==='profile')container.innerHTML=`<div class="form-grid"><form class="form-card" data-gm-form="ed"><div class="card-icon">${icon('coin')}</div><h3>发放 ED</h3><p>增加所选角色的 ED，保留当前余额。</p><label for="ed-amount">本次发放数量</label><input class="input" id="ed-amount" name="amount" type="number" step="1" min="1" max="2000000000" value="1000000" required inputmode="numeric"><div class="field-row">${[100000,1000000,10000000,1000000000].map((n,i)=>`<button type="button" class="button subtle" data-preset="${n}">${['10 万','100 万','1000 万','10 亿'][i]}</button>`).join('')}</div><p class="field-error" aria-live="polite"></p><button class="button primary submit" data-write>预览发放 ${icon('arrow')}</button></form>
 <form class="form-card" data-gm-form="level"><div class="card-icon">${icon('level')}</div><h3>提升角色等级</h3><p>按原生经验表同步经验，最高 99 级。</p><label for="target-level">目标等级 · 当前 Lv. ${c.level}</label><input class="input" id="target-level" name="amount" type="number" step="1" min="${Math.min(99,c.level+1)}" max="99" value="${Math.min(99,Math.max(15,c.level+1))}" required inputmode="numeric"><div class="field-row">${[15,70,99].map(n=>`<button type="button" class="button subtle" data-preset="${n}" ${n<=c.level?'disabled':''}>Lv. ${n}</button>`).join('')}</div><p class="field-error" aria-live="polite"></p><button class="button primary submit" data-write ${c.level===99?'disabled data-max-level':''}>${c.level===99?'已达等级上限':'预览调整 '+icon('arrow')}</button></form>
 <div class="form-card"><div class="card-icon">${icon('town')}</div><h3>回到魔奇</h3><p>重置到已验证的初始城镇位置，适合处理角色卡位。</p><button class="button outlined submit" data-action="town" data-write>预览回城 ${icon('arrow')}</button></div>${c.tutorial_recovery?`<div class="form-card"><div class="card-icon">${icon('town')}</div><h3>恢复新手起点</h3><p>将所选旧角色移回${esc(c.role)}的原新手起点，保留等级、物品和任务。</p><button class="button outlined submit" data-action="tutorial-start" data-write>预览恢复 ${icon('arrow')}</button></div>`:''}<div class="form-card"><div class="card-icon">${icon('backup')}</div><h3>先留一份进度</h3><p>使用数据库备份保存当前全部角色、物品和操作记录。</p><button class="button outlined submit" data-action="backup">立即备份 ${icon('arrow')}</button></div></div>`;
 else if(tab==='items'){
  container.innerHTML=`<div class="toolbar"><div class="search">${icon('search')}<input class="input" id="item-search" placeholder="搜索道具名称或 ID" aria-label="搜索道具" value="${esc(itemsQuery)}"></div><select id="item-group" aria-label="道具分类"><option value="all">全部分类</option>${[[1,'装备'],[2,'饰品'],[3,'材料'],[4,'特殊'],[5,'生活'],[6,'消耗品'],[27,'时装']].map(([id,name])=>`<option value="${id}" ${itemsGroup===String(id)?'selected':''}>${name}</option>`).join('')}</select></div><div class="items-layout"><div><div class="item-results" id="item-results">${empty('正在读取已验证道具…','search')}</div><div class="pagination" id="item-pagination"></div></div><form class="item-selection" data-gm-form="item" id="item-selection"></form></div><p class="subheading">仅列出当前服务端已验证的道具。发放物品不代表相关使用玩法均已开放，可在功能进度查看。</p>`;
  renderItemSelection();loadItems();
 }else if(tab==='inventory'){
  container.innerHTML=empty('正在读取背包…');loadInventory(c.uid,epoch);
 }else{container.innerHTML=empty('正在读取操作记录…','clock');loadHistory(c.uid,epoch);}
 applyState();
}
let itemRequest=0,currentItems=[];
async function loadItems(){
 const id=++itemRequest;
 try{const data=await api(`items?q=${encodeURIComponent(itemsQuery)}&group=${encodeURIComponent(itemsGroup)}&offset=${itemOffset}`);if(id!==itemRequest||page!=='gm'||tab!=='items'||!$('#item-results'))return;currentItems=data.rows;
 $('#item-results').innerHTML=data.rows.map(x=>`<button type="button" class="item-row ${chosenItem?.id===x.id?'selected':''}" data-item="${x.id}" aria-pressed="${chosenItem?.id===x.id}"><span><strong>${esc(x.name)}</strong><small>ID ${x.id} · 每格最多 ${x.stack}</small></span><span class="item-bag">${esc(x.bag)}</span></button>`).join('')||empty('没有找到匹配道具。试试名称的一部分或数字 ID。','search');
 $('#item-pagination').innerHTML=`<span>共 ${number(data.total)} 项 · ${data.total?`${itemOffset+1}–${Math.min(itemOffset+40,data.total)}`:'0'}</span><div><button class="button subtle" data-item-page="-1" ${itemOffset===0?'disabled':''}>上一页</button><button class="button subtle" data-item-page="1" ${itemOffset+40>=data.total?'disabled':''}>下一页</button></div>`;
 }catch(e){if(id===itemRequest&&$('#item-results'))$('#item-results').innerHTML=empty(esc(e.message),'warning');}
}
function renderItemSelection(){
 const form=$('#item-selection');if(!form)return;
 form.innerHTML=chosenItem?`<div><p class="eyebrow">已选道具</p><h3>${esc(chosenItem.name)}</h3><p>ID ${chosenItem.id} · ${esc(chosenItem.bag)}</p></div><div><label class="field-label" for="item-quantity">发放数量</label><input class="input" type="number" id="item-quantity" name="amount" min="1" max="99" step="1" value="1" required inputmode="numeric"></div><p class="field-error" aria-live="polite"></p><button class="button primary" data-write>预览发放 ${icon('arrow')}</button>`:`<p class="eyebrow">发放预览</p><h3>先选择一件道具</h3><p>点击左侧的搜索结果，再填写数量。</p>`;
 applyState();
}
async function loadInventory(uid,e){try{const rows=await api('inventory?uid='+uid);if(e!==epoch||page!=='gm'||tab!=='inventory')return;$('#gm-tab').innerHTML=rows.length?`<p class="subheading" style="margin:0 0 15px">${rows.length} 个格位 · 背包及穿戴信息只读查看</p><div class="table-wrap"><table><thead><tr><th>道具</th><th>道具 ID</th><th>数量</th><th>分类</th><th>格位</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.name)}</td><td>${x.template}</td><td>${x.count}</td><td>${esc(x.bag)}</td><td>${x.slot}</td></tr>`).join('')}</tbody></table></div>`:empty('背包中还没有物品。');}catch(err){if(e===epoch&&$('#gm-tab'))$('#gm-tab').innerHTML=empty(esc(err.message),'warning');}}
async function loadHistory(uid,e){try{const data=await api('history');if(e!==epoch||page!=='gm'||tab!=='history')return;const rows=data.filter(x=>x.uid===uid);$('#gm-tab').innerHTML=rows.length?`<div class="history-list">${rows.map(x=>`<div class="history-entry">${icon('check')}<div><strong>${esc(x.detail)}</strong><small>${esc(x.time.replace('T',' ').slice(0,19))} · UID ${x.uid}<br>自动备份：${esc(x.backup)}</small></div></div>`).join('')}</div>`:empty('还没有此角色的 GM 操作记录。','clock');}catch(err){if(e===epoch&&$('#gm-tab'))$('#gm-tab').innerHTML=empty(esc(err.message),'warning');}}

async function renderBackups(e){const rows=await api('backups');if(e!==epoch)return;main.innerHTML=heading('每一段进度，都值得保留。','备份包含全部角色、资产和当前存档记录。',`<button class="button primary" data-action="backup">${icon('backup')}立即备份</button>`)+`<div class="notice">${icon('info')}<div>GM 修改前会自动创建备份；也可以手动留下当前进度。备份使用 SQLite 完整备份方式，游戏运行时同样可用。</div></div><section class="panel"><div class="panel-head"><h2>备份记录 <small>${rows.length} 份</small></h2><button class="button text" data-folder="backups">打开备份目录 ${icon('folder')}</button></div>${rows.length?`<div class="table-wrap"><table><thead><tr><th>备份文件</th><th>时间</th><th>大小</th><th>类型</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.time.replace('T',' ').slice(0,19))}</td><td>${number(Math.ceil(x.size/1024))} KB</td><td><span class="badge ${x.name.includes('manual')?'':'partial'}">${x.name.includes('manual')?'手动备份':'修改前备份'}</span></td></tr>`).join('')}</tbody></table></div>`:empty('还没有备份，点击右上角留下一份进度。','backup')}</section><div class="mini-banner">${icon('gm')}恢复备份需要完全退出游戏和服务端。当前版本提供备份与目录查看，暂未开放一键覆盖恢复。</div>`;}
async function renderFeatures(e){const rows=await api('features');if(e!==epoch)return;const labels={complete:'已接入',verified:'已验证',implemented:'已接入',partial:'部分接入',in_progress:'完善中',planned:'待接入',pending:'待验证',blocked:'待完善'};main.innerHTML=heading('世界，正在一点点完善。','这里展示服务端当前的实际接入情况。')+`<div class="notice">${icon('info')}<div>资源配表已经读取，与玩法完整实现是不同的进度。展开卡片，可查看每项仍在完善的内容。</div></div><div class="feature-grid">${rows.map(f=>`<article class="panel feature-card"><div class="panel-head"><h3>${esc(f.title)}</h3><span class="badge ${['complete','verified','implemented'].includes(f.status)?'':['partial','in_progress'].includes(f.status)?'partial':'planned'}">${esc(labels[f.status]||'待完善')}</span></div><p>${esc(f.current)}</p>${f.missing?`<details><summary>仍在完善的内容</summary><p>${esc(f.missing)}</p></details>`:''}</article>`).join('')}</div>`;}
function renderSettings(){main.innerHTML=heading('按你的习惯，准备冒险。','启动器沿用本机已经验证的游戏环境。')+`<div class="settings-grid"><section class="panel"><div class="panel-head"><h2>本地路径</h2>${icon('folder')}</div><label class="field-label">游戏客户端</label><div class="path-row"><div class="path-value">${esc(state.client)}</div><button class="button subtle" data-folder="client">打开目录</button></div><label class="field-label" style="margin-top:24px">当前存档</label><div class="path-row"><div class="path-value">${esc(state.save)}</div><button class="button subtle" data-folder="save">打开目录</button></div><div class="mini-banner">${icon('info')}当前使用你选择的 DX11 客户端和分享目录内的独立存档；更换客户端请重开启动器。</div></section><section class="panel"><div class="panel-head"><h2>使用体验</h2>${icon('settings')}</div><h3>按钮与页面动效</h3><p class="subheading">悬停、点击与状态切换使用短动效，操作反馈更清晰。</p><label class="switch-row"><input id="reduce-motion" type="checkbox" ${document.body.classList.contains('motion-off')?'checked':''}>减少界面动效</label><div class="mini-banner">${icon('gm')}游戏运行中允许查看角色和备份，GM 修改会自动锁定。</div><p class="subheading" style="margin-top:20px">关闭启动器不会中断正在运行的游戏；游戏退出后，对应的本地服务自动结束。</p></section></div><section class="panel" style="margin-top:20px"><div class="panel-head"><h2>环境检查</h2><button class="button primary" data-action="check">${icon('check')}开始检查</button></div><div id="check-results">${checkHTML()}</div></section>`;}
function checkHTML(){return state?.check?state.check.rows.map(x=>`<div class="check-row ${x.ok?'':'failed'}">${icon(x.ok?'check':'warning')}<div><strong>${esc(x.name)}</strong><small>${esc(x.detail)}</small></div></div>`).join(''):`<p class="muted" style="font-size:11px;line-height:1.9">检查客户端版本、启动资源、服务端配表与存档完整性。<br>检查不会启动游戏，也不会修改角色。</p>`;}
async function renderLogs(e){const data=await api('logs');if(e!==epoch)return;main.innerHTML=heading('让每一次启动，都有回声。','查看本启动器最近一次运行的检查与启动结果。',`<button class="button outlined" data-action="reload">${icon('refresh')}刷新日志</button>`)+`<section class="panel"><div class="panel-head"><h2>运行输出</h2><button class="button text" data-folder="logs">打开日志目录 ${icon('folder')}</button></div><pre class="log-output" id="log-output"></pre></section>`;$('#log-output').textContent=data;}

async function renderRepo(e){
 const data=await api('repo/refresh',{},120000);if(e!==epoch)return;repoData=data;
 const label=s=>s==='??'?'未跟踪':s.includes('R')?'重命名':s.includes('A')?'新增':s.includes('D')?'删除':'修改';
 const pills=[];
 if(data.changed.length)pills.push(`<span class="badge partial">未提交 ${data.changed.length}</span>`);
 if(data.behind)pills.push(`<span class="badge partial">落后 ${data.behind}</span>`);
 if(data.ahead)pills.push(`<span class="badge planned">领先 ${data.ahead}</span>`);
 if(!pills.length)pills.push('<span class="badge">已同步</span>');
 const id=data.identity;
 main.innerHTML=heading('本地改动，随时和仓库同步。','改动推送到独立分支，经 PR 审查后合并；主干更新只允许快进。',`<button class="button outlined" data-action="reload">${icon('refresh')}获取远端状态</button>`)+`
 <section class="panel"><div class="panel-head"><h2>仓库状态</h2><div>${pills.join('')}</div></div>
  <div class="path-row"><div class="path-value">${esc(data.repo)}</div></div>
  <div class="check-row">${icon('check')}<div><strong>${esc(data.branch)} · ${esc(data.head)}</strong><small>${esc(data.when)} ${esc(data.subject)}</small></div></div>
  <div class="check-row">${icon('info')}<div><strong>${esc(data.remote||'未配置远端')}</strong><small>${data.behind?'远端有新提交':'远端与本地一致'}${data.ahead?` · 本地有 ${data.ahead} 个未推送提交`:''}</small></div></div>
  <div class="check-row">${icon('repo')}<div><strong>Git</strong><small>${esc(data.git||'未找到')}</small></div></div>
 </section>
 <div class="settings-grid">
  <section class="panel"><div class="panel-head"><h2>提交到仓库</h2>${icon('repo')}</div>
   <p class="subheading">暂存全部改动并推送修复分支。在 main 上会自动建立独立分支，不会直接推送主干。提交前请确认下面的文件列表。</p>
   ${data.review_url?`<p><a href="${esc(data.review_url)}" target="_blank" rel="noopener noreferrer">在 GitHub 提交合并请求</a></p>`:''}
   ${data.changed.length?`<div class="table-wrap" style="max-height:220px;overflow:auto"><table><thead><tr><th>状态</th><th>文件</th></tr></thead><tbody>${data.changed.map(x=>`<tr><td>${label(x.status)}</td><td>${esc(x.path)}</td></tr>`).join('')}</tbody></table></div>`:empty('工作区没有未提交的改动','check')}
   ${id.configured?`<p class="subheading">提交人：${esc(id.name)} &lt;${esc(id.email)}&gt;</p>`:`<label class="field-label" for="repo-name">提交人名称</label><input class="input" id="repo-name" value="${esc(id.suggest_name)}" placeholder="Git 用户名"><label class="field-label" for="repo-email">提交邮箱</label><input class="input" id="repo-email" value="${esc(id.suggest_email)}" placeholder="GitHub 邮箱"><p class="subheading">身份只写入本仓库的 .git/config，不会改动全局设置。</p>`}
   <label class="field-label" for="repo-message">提交说明</label><textarea class="input" id="repo-message" maxlength="200" style="min-height:84px;resize:vertical" placeholder="说明本次改动"></textarea>
   <div class="field-row" style="margin-top:12px"><button class="button primary" data-action="repo-commit" ${!data.changed.length&&!data.ahead?'disabled':''}>提交并推送 ${icon('arrow')}</button></div>
  </section>
  <section class="panel"><div class="panel-head"><h2>从仓库拉取</h2>${icon('refresh')}</div>
   <p class="subheading">main 上可快进拉取 origin/main。工作区有改动或主干历史分歧时会停止，保留文件和提交；修复分支请先完成 PR 审查。</p>
   <div class="notice">${icon('info')}<div>拉取会更新代码文件，新代码需要重新打开启动器后生效。运行资源包若有变化，请再用“更新单机版”同步。</div></div>
   <div class="field-row"><button class="button outlined" data-action="repo-pull" ${!data.can_pull?'disabled':''}>${data.branch!=='main'?'请先审查修复分支':data.behind?`拉取 ${data.behind} 个提交`:'已是最新'}</button></div>
  </section>
 </div>
 ${data.game_running?`<div class="mini-banner">${icon('warning')}游戏或服务端正在运行，提交和拉取会在退出后解锁。</div>`:''}`;
}
async function commitRepo(){
 if(mutating)return;
 const message=$('#repo-message')?.value.trim()||'';
 const name=$('#repo-name')?.value.trim(),email=$('#repo-email')?.value.trim();
 const count=repoData?.changed.length||0;
 if(count&&!message){toast('请填写提交说明',true);$('#repo-message')?.focus();return;}
 if(!count&&!message&&!(repoData?.ahead)){toast('没有可提交的改动',true);return;}
 if($('#repo-name')&&(!name||!email.includes('@'))){toast('请填写有效的提交人名称与邮箱',true);return;}
 const summary=count?`将提交 ${count} 个文件`:`没有文件改动，将补推本地 ${repoData?.ahead||0} 个提交`;
 const ok=await confirmDialog('提交并推送修复分支？',`<p>${summary}，并推送到独立修复分支。</p><div class="summary-box">${esc(message)}</div><p>主干需要通过 PR 审查后合并；已有分支会正常推送，不自动变基或强推。</p>`,'提交并推送','repo');
 if(!ok)return;mutating=true;
 try{const result=await api('repo/commit',{message,name,email},180000);toast(result.message);await navigate('repo');}catch(err){toast(err.message,true);}finally{mutating=false;}
}
async function pullRepo(){
 if(mutating)return;
 const ok=await confirmDialog('从仓库拉取更新？',`<p>快进更新 main 的代码副本。未提交文件和主干历史分歧会阻止更新。</p>`,'拉取更新','refresh');
 if(!ok)return;
 mutating=true;
 try{const result=await api('repo/pull',{},180000);toast(result.message);await navigate('repo');}catch(err){toast(err.message,true);}finally{mutating=false;}
}

async function navigate(next=page){
 if(!routes[next])return;const changed=page!==next;page=next;const e=++epoch;
 for(const b of document.querySelectorAll('[data-nav]'))if(b.classList.contains('nav-item')){b.classList.toggle('active',b.dataset.nav===page);if(b.dataset.nav===page)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
 $('#breadcrumb').textContent=routes[page][0];main.setAttribute('aria-busy','true');
 main.innerHTML='<div class="initial-loading"><div class="spinner"></div><p>正在读取本地数据…</p></div>';
 try{
  const [s,cs]=await Promise.all([api('state'),api('characters')]);if(e!==epoch)return;state=s;characters=cs;
  if(page==='home')renderHome();else if(page==='gm')renderGM();else if(page==='backups')await renderBackups(e);else if(page==='features')await renderFeatures(e);else if(page==='repo')await renderRepo(e);else if(page==='settings')renderSettings();else await renderLogs(e);
  if(e===epoch){applyState();if(changed){window.scrollTo({top:0,behavior:'instant'});main.focus({preventScroll:true});}}
 }catch(err){if(e===epoch){main.innerHTML=`<div class="error-panel"><h2>暂时无法读取本地环境</h2><p>${esc(err.message)}</p><button class="button outlined" data-action="reload">${icon('refresh')}重试</button></div>`;toast(err.message,true);}}
 finally{if(e===epoch)main.setAttribute('aria-busy','false');}
}
function applyState(){
 if(!state)return;
 $('#minimize-app').hidden=!state.native_window;$('#maximize-app').hidden=!state.native_window;
 $('#maximize-app').innerHTML=icon(state.maximized?'restore':'maximize');
 $('#maximize-app').title=state.maximized?'还原窗口':'最大化窗口';
 $('#maximize-app').setAttribute('aria-label',state.maximized?'还原窗口':'最大化窗口');
 const busy=['checking','starting','stopping'].includes(state.phase);
 const status=state.phase==='checking'?'正在检查环境':state.phase==='starting'?'正在启动游戏':state.phase==='stopping'?'正在保存并退出':state.game_running?'游戏运行中':'本地环境就绪';
 $('#header-status').textContent=status;$('#header-status').classList.toggle('warn',busy);
 $('#footer-state').textContent=state.message==='准备就绪'?(state.game_running?'已有游戏运行 · GM 只读':'本地存档已连接'):state.message;
 const launch=$('#launch-game');if(launch){launch.disabled=busy||state.game_running||state.owned;launch.innerHTML=(busy?'<span class="spinner small"></span>':icon('play'))+(state.phase==='checking'?'检查环境中':state.phase==='starting'?'正在启动':state.phase==='stopping'?'退出中':state.game_running?'游戏运行中':'启动游戏');}
 const caption=$('#launch-caption');if(caption)caption.innerHTML=state.owned?`本次游戏由启动器管理<br><button class="button text" data-action="stop" style="color:#bde7ef;min-height:18px;font-size:10px">${icon('stop')}退出本次游戏</button>`:state.game_running?'已有游戏正在运行<br>正常退出后可再次启动':'自动准备本地环境<br>启动后在游戏内选择你的角色';
 for(const b of document.querySelectorAll('[data-action="check"]'))b.disabled=busy||mutating;
 for(const b of document.querySelectorAll('[data-write]'))b.disabled=state.gm_locked||mutating||b.hasAttribute('data-max-level');
 const notice=$('#gm-notice');if(notice)notice.innerHTML=writeNotice();
 const checks=$('#check-results');if(checks)checks.innerHTML=state.phase==='checking'?'<div class="initial-loading" style="min-height:120px"><div class="spinner"></div><p>正在检查，请稍候…</p></div>':checkHTML();
}
async function poll(){if(closed)return;try{const old=state;state=await api('state');applyState();if(old&&old.gm_locked&&!state.gm_locked&&page==='gm'&&!$('#confirm-dialog').open)await navigate('gm');}catch(e){$('#header-status').textContent='连接中断';$('#header-status').classList.add('warn');for(const b of document.querySelectorAll('[data-write],#launch-game'))b.disabled=true;}}
const pollTimer=setInterval(poll,3500);

function confirmDialog(title,body,button='确认并保存',img='gm'){
 return new Promise(resolve=>{const dialog=$('#confirm-dialog');$('#dialog-title').textContent=title;$('#dialog-body').innerHTML=body;$('#dialog-icon').innerHTML=icon(img);$('#dialog-confirm').textContent=button;dialog.returnValue='cancel';dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});dialog.showModal();});
}
async function reviewGM(action,value){
 const c=role();if(!c||mutating)return;
 if(state.gm_locked){toast('请先正常退出游戏，GM 修改将在离线后解锁',true);return;}
 const labels={ed:`增加 ${number(value)} ED`,level:`提升到 Lv. ${value}`,item:`${esc(chosenItem?.name)} × ${value.quantity}`,town:'回到魔奇初始位置',tutorial_start:`移回${esc(c.role)}的原新手起点（等级、物品和任务保持不变）`};
 const snapshot={operation_id:crypto.randomUUID(),uid:c.uid,version:c.version,action,value};
 const ok=await confirmDialog('为这个角色提交修改？',`<p>目标角色：<strong>${esc(c.name)}</strong> · UID ${c.uid}</p><div class="summary-box">${labels[action]}</div><p>提交前自动备份。此次操作将写入存档，下次登录生效。</p>`);
 if(!ok)return;mutating=true;applyState();
 try{const result=await api('gm',snapshot);toast(result.message);await navigate('gm');}catch(e){toast(e.message,true);}finally{mutating=false;await poll();}
}

document.addEventListener('submit',async event=>{
 const form=event.target.closest('[data-gm-form]');if(!form)return;event.preventDefault();
 const error=form.querySelector('.field-error');if(error)error.textContent='';
 if(!form.reportValidity())return;
 const value=Number(new FormData(form).get('amount'));const action=form.dataset.gmForm;
 if(!Number.isSafeInteger(value)||value<1){if(error)error.textContent='请输入有效的正整数';return;}
 if(action==='level'&&value<=role().level){if(error)error.textContent='目标等级需要高于当前等级';return;}
 if(action==='ed'&&value>2000000000){if(error)error.textContent='单次最多发放 20 亿 ED';return;}
 if(action==='level'&&value>99){if(error)error.textContent='普通等级上限为 99';return;}
 if(action==='item'&&!chosenItem)return;
 await reviewGM(action,action==='item'?{template:chosenItem.id,quantity:value}:value);
});
document.addEventListener('click',async event=>{
 const b=event.target.closest('button,[data-nav]');if(!b||b.disabled)return;
 if(b.dataset.nav){event.preventDefault();await navigate(b.dataset.nav);return;}
 if(b.dataset.character){selected=Number(b.dataset.character);chosenItem=null;localStorage.setItem('els-character',selected);await navigate('gm');return;}
 if(b.dataset.tab){tab=b.dataset.tab;epoch++;renderGM();return;}
 if(b.dataset.preset){const form=b.closest('form');form.querySelector('[name="amount"]').value=b.dataset.preset;form.querySelector('.field-error').textContent='';return;}
 if(b.dataset.item){chosenItem=currentItems.find(x=>x.id===Number(b.dataset.item));for(const row of document.querySelectorAll('[data-item]')){row.classList.toggle('selected',row===b);row.setAttribute('aria-pressed',String(row===b));}renderItemSelection();return;}
 if(b.dataset.itemPage){itemOffset=Math.max(0,itemOffset+40*Number(b.dataset.itemPage));await loadItems();$('#item-results')?.scrollTo(0,0);return;}
 if(b.dataset.folder){try{await api('open',{which:b.dataset.folder});}catch(e){toast(e.message,true);}return;}
 const action=b.dataset.action;
 if(!action)return;
 try{
  if(action==='reload'){await navigate();return;}
  if(action==='repo-commit'){await commitRepo();return;}
  if(action==='repo-pull'){await pullRepo();return;}
  if(action==='town'){await reviewGM('town',20000);return;}
  if(action==='tutorial-start'&&role()?.tutorial_recovery){await reviewGM('tutorial_start',{version:role().tutorial_recovery.version});return;}
  if(action==='backup'){b.disabled=true;const old=b.innerHTML;b.innerHTML='<span class="spinner small"></span>备份中';try{const result=await api('backup',{});toast(result.message);if(page==='backups')await navigate();}finally{if(b.isConnected){b.disabled=false;b.innerHTML=old;}}return;}
  if(action==='stop'){if(!await confirmDialog('退出本次游戏？','<p>请先结束当前副本并保存进度。启动器将结束自己启动的游戏实例，再等待服务端完成保存。</p>','退出游戏','stop'))return;}
  b.disabled=true;
  const result=await api(action,{});toast(result.message);await poll();
  if(action==='check')await navigate('settings');
 }catch(e){toast(e.message,true);applyState();}
});
document.addEventListener('input',event=>{if(event.target.id==='item-search'){itemsQuery=event.target.value;itemOffset=0;clearTimeout(searchTimer);searchTimer=setTimeout(loadItems,220);}});
document.addEventListener('change',event=>{if(event.target.id==='item-group'){itemsGroup=event.target.value;itemOffset=0;loadItems();}if(event.target.id==='reduce-motion'){document.body.classList.toggle('motion-off',event.target.checked);localStorage.setItem('els-reduce-motion',event.target.checked);}});
$('#refresh').addEventListener('click',()=>navigate());
async function windowAction(action){try{await api('window',{action});await poll();}catch(e){toast(e.message,true);}}
$('#minimize-app').addEventListener('click',()=>windowAction('minimize'));
$('#maximize-app').addEventListener('click',()=>windowAction('toggle_maximize'));
$('#titlebar').addEventListener('dblclick',e=>{if(state?.native_window&&!e.target.closest('button,.top-actions'))windowAction('toggle_maximize');});
$('#close-app').addEventListener('click',async()=>{try{await api('close',{});closed=true;clearInterval(pollTimer);window.close();main.innerHTML='<div class="initial-loading"><h2>启动器已关闭</h2><p>可以关闭此窗口。运行中的游戏会继续运行。</p></div>';}catch(e){toast(e.message,true);}});
$('#confirm-dialog').addEventListener('click',event=>{const d=event.currentTarget;if(event.target===d){const r=d.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)d.close('cancel');}});
navigate('home');
