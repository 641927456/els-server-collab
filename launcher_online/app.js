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
 repo:'<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="8" r="2.5"/><path d="M6 8.5v7M8.5 6h4A3.5 3.5 0 0 1 16 9.5M18 10.5V12a4 4 0 0 1-4 4h-4"/>',
 send:'<path d="m3 11 18-8-8 18-2.5-7.5Z"/><path d="M21 3 10.5 13.5"/>',
 megaphone:'<path d="M3 11v3l4 1 9 5V4L7 9l-4 2Z"/><path d="M19 9a4 4 0 0 1 0 6M8 15l1 5"/>',
 sliders:'<path d="M4 6h10m4 0h2M4 12h4m4 0h8M4 18h12m4 0h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
 ticket:'<path d="M4 8a2 2 0 0 0 2-2h12a2 2 0 0 0 2 2v3a2 2 0 0 0 0 2v3a2 2 0 0 0-2 2H6a2 2 0 0 0-2-2v-3a2 2 0 0 0 0-2Z"/><path d="M13 6v12" stroke-dasharray="2 3"/>',
 gem:'<path d="m6 4 6-1 6 1 3 5-9 12L3 9Z"/><path d="M3 9h18M12 3l-3 6 3 12 3-12-3-6"/>',
 users:'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20v-1.5a6.5 6.5 0 0 1 13 0V20"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M21.5 20v-1.5a6.5 6.5 0 0 0-4-6"/>',
 image:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m4 19 5.5-5.5L14 18l3-3 3 3"/>',
 film:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16m8-16v16M3 9h5m8 0h5M3 15h5m8 0h5"/>',
 palette:'<circle cx="12" cy="12" r="9"/><circle cx="8" cy="9" r="1"/><circle cx="12" cy="7" r="1"/><circle cx="16" cy="9" r="1"/><path d="M12 21a3 3 0 0 1 0-6h2a2.5 2.5 0 0 0 0-5"/>',
 copy:'<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
 offline:'<path d="M3 3l18 18"/><path d="M8.6 8.7A8 8 0 0 0 4 14m5.2-1.6A4 4 0 0 1 12 11.5m2.9.7a4 4 0 0 1 1.9 1.8M12 20h.1"/>'
};
const icon=(name)=>`<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]||icons.info}</svg>`;
const esc=(value)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(value)=>Number(value||0).toLocaleString('zh-CN');
const $=(s)=>document.querySelector(s);
const routes={home:['冒险首页','home'],gm:['GM 工具','gm'],backups:['存档备份','backup'],features:['功能进度','features'],repo:['仓库同步','repo'],settings:['启动设置','settings'],logs:['运行日志','logs']};
let token=location.hash.slice(1);
if(token && !routes[token]){sessionStorage.setItem('els-launcher-token',token);history.replaceState(null,'','/');}
else token=sessionStorage.getItem('els-launcher-token')||'';
let page='home',tab='send',state=null,repoData=null,characters=[],selected=Number(localStorage.getItem('els-character')||1001),chosenItem=null,epoch=0,mutating=false,closed=false,searchTimer,itemOffset=0,itemsQuery='',itemsGroup='all';
let gmOnline=null,gmStatusAt=0,onlinePlayer=null,couponRewards=null,couponPicks=new Map(),couponBatches=null,cashInfo=null,ratesDirty=false,eventsDirty=false,gmTimer=0;
let bgSettings=null,bgAnim=0,bgStars=null,bgDust=null,bgSeed=Math.random()*1000;
const GM_TABS={send:['在线发放','send'],announce:['游戏公告','megaphone'],rates:['概率配置','sliders'],events:['活动开关','clock'],coupons:['优惠券','ticket'],cash:['A币充值','gem'],offline:['离线工具','offline'],bag:['背包查看','box'],history:['操作记录','clock']};
const ONLINE_TABS=['send','announce','rates','events','coupons','cash'];
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
function heading(title,sub,action=''){return `<div class="page-heading"><div><p class="eyebrow">${page==='home'?'YOUR LOCAL WORLD':page==='gm'?'GAME MASTER ONLINE':page==='backups'?'SAVE & PROTECT':page==='features'?'WORLD IN PROGRESS':page==='repo'?'REPOSITORY SYNC':page==='logs'?'SESSION LOG':'LAUNCHER PREFERENCES'}</p><h1>${title}</h1><p>${sub}</p></div>${action}</div>`;}
function empty(text,img='box'){return `<div class="empty-state">${icon(img)}${text}</div>`;}
function role(){return characters.find(c=>c.uid===selected)||characters[0];}
function roleSummary(c){if(!c)return empty('还没有本地角色。首次进入游戏后，在角色界面创建。','user');return `<div class="role-summary"><div class="role-emblem ${c.unit_type===5?'blue':''}">${esc(c.role.slice(0,1))}</div><div class="role-info"><strong>${esc(c.name)}</strong><small><span class="level-tag">Lv. ${c.level}</span>${esc(c.role)} <span class="muted">· UID ${c.uid}</span></small></div></div>`;}
function stats(c){return `<div class="role-stats"><div><span>持有 ED</span><strong>${number(c.ed)}</strong></div><div><span>背包格位</span><strong>${number(c.item_count)} <small>件</small></strong></div><div><span>角色等级</span><strong>${c.level} <small>/ 99</small></strong></div></div>`;}
function writeNotice(){return `<div class="notice ${state?.gm_locked?'warn':''}">${icon(state?.gm_locked?'warning':'gm')}<div><strong>${state?.gm_locked?'游戏或服务端正在运行 · 离线工具只读':'离线工具 · 可以修改'}</strong><br>${state?.gm_locked?'在线发放不受影响。离线修改需先正常退出游戏，之后会自动解锁。':'离线修改每次提交前自动备份，下次登录生效。游戏运行时请改用「在线发放」。'}</div></div>`;}

/* ---------- dynamic background engine ---------- */
const BUILTINS={stars:'星屑夜幕',aurora:'极光波纹',particles:'浮游光尘'};
function stopBgAnim(){if(bgAnim){cancelAnimationFrame(bgAnim);bgAnim=0;}}
function bgFrame(kind,ctx,w,h,t){
 ctx.clearRect(0,0,w,h);
 if(kind==='stars'){
  const sky=ctx.createLinearGradient(0,0,0,h);sky.addColorStop(0,'#0a1e2c');sky.addColorStop(.65,'#10303f');sky.addColorStop(1,'#0c2531');
  ctx.fillStyle=sky;ctx.fillRect(0,0,w,h);
  if(!bgStars||bgStars.w!==w||bgStars.h!==h){const n=Math.round(w*h/9000);bgStars={w,h,list:Array.from({length:n},()=>({x:Math.random(),y:Math.random(),r:.6+Math.random()*1.6,s:Math.random()*Math.PI*2,sp:.4+Math.random()*1.4}))};}
  for(const s of bgStars.list){const a=.25+.75*Math.abs(Math.sin(s.s+t*.001*s.sp));ctx.globalAlpha=a;ctx.fillStyle='#cfeef5';ctx.beginPath();ctx.arc(s.x*w,s.y*h,s.r,0,7);ctx.fill();}
  ctx.globalAlpha=1;
  if(t%4200<900){const p=(t%4200)/900;ctx.globalAlpha=.5*(1-Math.abs(p*2-1));ctx.strokeStyle='#e8fbff';ctx.lineWidth=1.4;ctx.beginPath();const x=w*(.2+.6*p),y=h*.25+h*.3*p;ctx.moveTo(x,y);ctx.lineTo(x-46,y-30);ctx.stroke();}
  ctx.globalAlpha=1;
 }else if(kind==='aurora'){
  ctx.fillStyle='#0b2230';ctx.fillRect(0,0,w,h);
  for(let band=0;band<3;band++){
   const hue=168+band*22,amp=h*(.09+band*.03),base=h*(.34+band*.14),phase=t*.00045+band*1.9;
   ctx.beginPath();ctx.moveTo(0,h);
   for(let x=0;x<=w;x+=14){const y=base+Math.sin(x*.004+phase)*amp+Math.sin(x*.0016-phase*.7)*amp*.6;ctx.lineTo(x,y);}
   ctx.lineTo(w,h);ctx.closePath();
   const grad=ctx.createLinearGradient(0,base-amp,0,h);grad.addColorStop(0,`hsla(${hue},70%,62%,.34)`);grad.addColorStop(1,'hsla(190,60%,40%,0)');
   ctx.fillStyle=grad;ctx.fill();
  }
 }else{
  ctx.fillStyle='#0b2230';ctx.fillRect(0,0,w,h);
  if(!bgDust||bgDust.w!==w||bgDust.h!==h){const n=Math.round(w*h/26000);bgDust={w,h,list:Array.from({length:n},()=>({x:Math.random(),y:Math.random(),r:1.2+Math.random()*2.6,v:.00012+Math.random()*.00045,sw:Math.random()*Math.PI*2}))};}
  for(const p of bgDust.list){p.y-=p.v;if(p.y<-.02){p.y=1.02;p.x=Math.random();}
   const x=(p.x+Math.sin(p.sw+t*.0004)*.012)*w,y=p.y*h;
   const g=ctx.createRadialGradient(x,y,0,x,y,p.r*4);g.addColorStop(0,'rgba(140,232,247,.85)');g.addColorStop(1,'rgba(140,232,247,0)');
   ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,p.r*4,0,7);ctx.fill();}
 }
}
function startBgAnim(kind){
 const canvas=$('#bg-canvas'),ctx=canvas.getContext('2d');
 const resize=()=>{const rect=canvas.getBoundingClientRect();canvas.width=Math.max(2,Math.round(rect.width));canvas.height=Math.max(2,Math.round(rect.height));};
 if(document.body.classList.contains('motion-off')){resize();bgFrame(kind,ctx,canvas.width,canvas.height,bgSeed);return;}
 let t=bgSeed;
 const loop=()=>{const w=canvas.clientWidth,h=canvas.clientHeight;if(canvas.width!==w||canvas.height!==h)resize();bgFrame(kind,ctx,canvas.width,canvas.height,t);t+=16;bgAnim=requestAnimationFrame(loop);};
 resize();bgAnim=requestAnimationFrame(loop);
}
function applyBackground(settings){
 if(!settings)return;
 const bg=settings.background||{};
 const layer=$('#bg-layer'),canvas=$('#bg-canvas'),image=$('#bg-image'),video=$('#bg-video');
 stopBgAnim();canvas.hidden=true;image.hidden=true;video.hidden=true;
 layer.style.display='none';document.body.classList.remove('bg-on');
 if(bg.mode==='builtin'&&BUILTINS[bg.builtin]){
  layer.style.display='block';document.body.classList.add('bg-on');
  canvas.hidden=false;startBgAnim(bg.builtin);
 }else if(bg.mode==='image'&&bg.file){
  layer.style.display='block';document.body.classList.add('bg-on');
  image.src='/background/'+encodeURIComponent(bg.file);image.hidden=false;
 }else if(bg.mode==='video'&&bg.file){
  layer.style.display='block';document.body.classList.add('bg-on');
  video.src='/background/'+encodeURIComponent(bg.file);video.hidden=false;video.play?.().catch(()=>{});
 }
 $('#bg-dim').style.opacity=String(Math.min(70,Math.max(0,bg.dim??30))/100);
}
async function setBackground(patch){
 const current=bgSettings||{background:{mode:'off',builtin:'stars',file:null,dim:30},reduce_motion:false};
 const next={...current,background:{...current.background,...patch}};
 bgSettings=next;applyBackground(next);
 try{const saved=await api('settings',next);bgSettings=saved;}catch(e){toast(e.message,true);}
}
function bgButtons(){const bg=bgSettings?.background||{};const options=[['off','palette','关闭背景','回到干净的浅色界面'],['builtin:stars','crystal','星屑夜幕','内置动态星空'],['builtin:aurora','crystal','极光波纹','内置流动极光'],['builtin:particles','crystal','浮游光尘','内置上升光点'],['image','image','自定义图片','选择本地图片文件'],['video','film','自定义视频','选择本地视频文件']];
 return options.map(([key,name,label,sub])=>{const active=bg.mode==='off'?key==='off':key==='builtin:'+bg.builtin||key===bg.mode;
  return `<button type="button" class="bg-option ${active?'selected':''}" data-bg-mode="${key}">${icon(name)}<span>${label}</span><small>${sub}</small></button>`;}).join('');}

/* ---------- home ---------- */
function renderHome(){
 const c=role();
 main.innerHTML=heading('准备好，继续冒险。','熟悉的世界，属于你的旅程。',`<button class="button outlined" data-action="check">${icon('check')}检查游戏环境</button>`)+`
 <section class="hero" aria-label="魔奇原生场景插图"><div><p class="eyebrow">THE JOURNEY CONTINUES</p><h2>再一次，<br>踏入<span>艾里奥斯。</span></h2><p class="hero-copy">从熟悉的魔奇出发，继续你的冒险。<br>游戏运行时，GM 发放与公告即时到达。</p></div><div class="hero-bottom"><div class="hero-launch"><button class="button launch-button" id="launch-game" data-action="start">${icon('play')}启动游戏</button><div class="launch-caption" id="launch-caption">自动准备本地环境<br>启动后在游戏内选择你的角色</div></div><span class="scene-credit">原生场景 · 魔奇 RUBEN</span></div></section>
 <div class="home-grid"><section class="panel"><div class="panel-head"><h2>我的角色 <small>${characters.length} / 16</small></h2><button class="button text" data-nav="gm">GM 工具 ${icon('arrow')}</button></div>${roleSummary(c)}${c?stats(c):''}<div class="quick-row"><button class="button subtle" data-action="backup">${icon('backup')}备份存档</button><button class="button subtle" data-nav="logs">${icon('logs')}查看日志</button></div></section>
 <section class="panel"><div class="panel-head"><h2>冒险手记</h2><span class="badge">在线 GM</span></div><div class="info-line"><span class="info-icon">${icon('send')}</span><div><h3>在线发放，即时到账</h3><p>游戏运行时发放道具，直接进入在线角色的背包并推送通知。</p></div></div><div class="info-line"><span class="info-icon">${icon('megaphone')}</span><div><h3>公告与概率随调随用</h3><p>滚动公告、经验与掉落倍率、活动开关，都在 GM 工具里。</p></div></div><div class="info-line"><span class="info-icon">${icon('palette')}</span><div><h3>按你的喜好布置启动器</h3><p>在「启动设置」中选择动态背景：内置星屑、极光或你自己的图片和视频。</p></div></div></section></div>
 <div class="mini-banner">${icon('info')}<span>这个世界仍在完善中。各项玩法的接入情况，可在「功能进度」中查看。</span><button class="button text" data-nav="features" style="margin-left:auto;flex-shrink:0">查看进度 ${icon('arrow')}</button></div>`;
}

/* ---------- GM page ---------- */
function gmBanner(){
 if(!gmOnline)return '';
 if(gmOnline.online)return `<div class="gm-banner">${icon('check')}<div><strong>在线 GM 已连接</strong><br>在线角色 ${gmOnline.players.length} 位 · 概率配置 v${gmOnline.rates?.revision??0} · 活动配置 v${gmOnline.events?.revision??0}。发放即时到账，无需重启游戏。</div><button class="button subtle refresh-inline" data-action="gm-refresh">${icon('refresh')}刷新状态</button></div>`;
 return `<div class="gm-banner off">${icon('offline')}<div><strong>在线 GM 未连接</strong><br>${esc(gmOnline.error||'启动游戏后，本机服务端会开启在线 GM 通道。')}</div><button class="button subtle refresh-inline" data-action="gm-refresh">${icon('refresh')}重新检测</button></div>`;
}
function gmStrip(){
 if(!gmOnline?.online)return '';
 const phases={town_ready:'城镇中',dungeon_active:'副本中',dungeon_ready:'准备副本',character_ready:'角色选择',closing:'断开中'};
 return `<div class="online-strip"><div class="online-stat"><span>在线角色</span><strong>${gmOnline.players.length}</strong> <small>位</small></div><div class="online-stat"><span>重复公告</span><strong>${gmOnline.announcements?.length??0}</strong> <small>个计划</small></div><div class="online-stat"><span>经验倍率</span><strong>${((gmOnline.rates?.experience_bp??10000)/10000).toLocaleString('zh-CN')}</strong> <small>倍</small></div><div class="online-stat"><span>配置版本</span><strong>v${gmOnline.rates?.revision??0}</strong> <small>概率 · 活动 v${gmOnline.events?.revision??0}</small></div></div>`;
}
function renderGM(){
 main.innerHTML=heading('GM 工具','在线发送即时生效；离线修改照旧有备份和记录。',`<button class="button outlined" data-action="reload">${icon('refresh')}刷新资料</button>`)+`<div id="gm-banner">${gmBanner()}</div><div id="gm-strip">${gmStrip()}</div><section class="panel"><div class="tabbar" role="tablist" aria-label="GM 功能">${Object.entries(GM_TABS).map(([id,[name,img]])=>`<button class="tab-button ${tab===id?'active':''}" role="tab" aria-selected="${tab===id}" data-tab="${id}">${name}</button>`).join('')}</div><div id="gm-tab"></div></section>`;
 renderGMTab();
}
function onlineLock(msg){
 return `<div class="gm-online-lock">${icon('offline')}<strong>${esc(msg||'等待本地服务端上线')}</strong><br>启动游戏后，在线 GM 会自动连接；<br>在此之前可以使用「离线工具」与「操作记录」。</div>`;
}
async function renderGMTab(){
 const container=$('#gm-tab');if(!container)return;
 if(ONLINE_TABS.includes(tab)){
  if(!gmOnline?.online){container.innerHTML=onlineLock(gmOnline?.error);return;}
  if(tab==='send')renderSendTab();
  else if(tab==='announce')renderAnnounceTab();
  else if(tab==='rates')renderRatesTab();
  else if(tab==='events')renderEventsTab();
  else if(tab==='coupons')renderCouponsTab();
  else if(tab==='cash')renderCashTab();
  return;
 }
 if(tab==='offline'){renderOfflineTab();return;}
 if(tab==='bag'){container.innerHTML=empty('正在读取背包…');loadInventory(epoch);return;}
 container.innerHTML=empty('正在读取操作记录…','clock');loadHistory(epoch);
}
function renderSendTab(){
 const players=gmOnline.players;
 container_players:{
  const target=onlinePlayer&&players.some(p=>p.session===onlinePlayer)?onlinePlayer:(players[0]?.session||'');
  onlinePlayer=target;
 }
 const current=players.find(p=>p.session===onlinePlayer);
 const phases={town_ready:'城镇中',dungeon_active:'副本中',dungeon_ready:'准备副本',character_ready:'角色选择',closing:'断开中'};
 $('#gm-tab').innerHTML=`<div class="give-layout"><div><p class="subheading" style="margin:0 0 12px">选择在线角色，搜索并发放道具；道具直接进入背包并推送拾取通知。</p><div class="player-list" id="gm-players">${players.map(p=>`<button type="button" class="player-row ${p.session===onlinePlayer?'selected':''}" data-player="${esc(p.session)}"><span class="avatar">${esc((p.name||'?').slice(0,1))}</span><span><strong>${esc(p.name)} <span class="phase-tag ${p.phase==='dungeon_active'?'dungeon':''}">${phases[p.phase]||p.phase}</span></strong><small>${esc(p.unit_name||'')} · Lv. ${p.level} · UID ${p.uid} · 账号 ${esc(p.account)}</small></span><span class="pick">${p.session===onlinePlayer?'已选中':'选择'}</span></button>`).join('')||empty('当前没有在线角色。进入游戏后再来发放。','users')}</div><div class="toolbar" style="margin-top:18px"><div class="search">${icon('search')}<input class="input" id="item-search" placeholder="搜索道具名称或 ID" aria-label="搜索道具" value="${esc(itemsQuery)}"></div><select id="item-group" aria-label="道具分类"><option value="all">全部分类</option>${[[1,'装备'],[2,'饰品'],[3,'材料'],[4,'特殊'],[5,'生活'],[6,'消耗品'],[27,'时装']].map(([id,name])=>`<option value="${id}" ${itemsGroup===String(id)?'selected':''}>${name}</option>`).join('')}</select></div><div class="item-results" id="item-results">${empty('正在读取道具目录…','search')}</div><div class="pagination" id="item-pagination"></div></div><aside class="item-selection" id="online-give"></aside></div>`;
 loadItems();renderOnlineGive();
}
function renderOnlineGive(){
 const form=$('#online-give');if(!form)return;
 const players=gmOnline?.players||[];const current=players.find(p=>p.session===onlinePlayer);
 form.innerHTML=current?`<p class="eyebrow">在线发放预览</p><h3>${esc(current.name)}</h3><p>UID ${current.uid} · ${esc(current.unit_name||'')} · Lv. ${current.level}<br>发放后立即进入背包并推送通知。</p>${chosenItem?`<p class="eyebrow" style="margin-top:14px">已选道具</p><h3>${esc(chosenItem.name)}</h3><p>ID ${chosenItem.id} · ${esc(chosenItem.bag)} · 每格最多 ${chosenItem.stack}</p><label class="field-label" for="give-quantity">发放数量</label><input class="input" type="number" id="give-quantity" min="1" max="99" step="1" value="1" inputmode="numeric"><button class="button primary" data-action="gm-give" style="width:100%;margin-top:16px">发送给 ${esc(current.name)} ${icon('send')}</button>`:`<p class="eyebrow" style="margin-top:14px">发放预览</p><h3>先选择一件道具</h3><p>点击左侧搜索结果后再发送。</p>`}`:`<p class="eyebrow">在线发放预览</p><h3>等待在线角色</h3><p>游戏内进入角色后，这里会出现可选择的收件人。</p>`;
 applyState();
}
function renderAnnounceTab(){
 const jobs=gmOnline.announcements||[];
 $('#gm-tab').innerHTML=`<p class="subheading" style="margin:0 0 14px">全服滚动公告（游戏顶部横幅）。支持定时重复，可随时取消后续发送。</p><form id="announce-form" style="max-width:640px"><label class="field-label" for="announce-text">公告内容 · 1–200 字，不允许 &lt; &gt;</label><textarea class="input" id="announce-text" maxlength="200" style="min-height:90px;resize:vertical" required placeholder="例如：今晚 8 点开启双倍经验活动！"></textarea><div class="form-grid" style="grid-template-columns:1fr 1fr;margin-top:12px"><div><label class="field-label" for="announce-repeat">重复次数 · 1–20</label><input class="input" id="announce-repeat" type="number" min="1" max="20" step="1" value="1" inputmode="numeric"></div><div><label class="field-label" for="announce-interval">重复间隔 · 10–3600 秒</label><input class="input" id="announce-interval" type="number" min="10" max="3600" step="1" value="60" inputmode="numeric"></div></div><button class="button primary" data-action="gm-announce" style="margin-top:16px">${icon('megaphone')}发送公告</button></form><div class="announcement-list">${jobs.length?jobs.map(j=>`<div class="announcement-job"><div><strong>${esc(j.text)}</strong><small>剩余 ${j.remaining} 次 · 间隔 ${j.interval} 秒</small></div><button class="button subtle" data-action="gm-cancel-announce" data-job="${esc(j.id)}">取消后续</button></div>`).join(''):'<p class="muted" style="font-size:10px">暂无重复公告计划。单次公告发送后即结束。</p>'}</div>`;
}
function rateInput(kind,index,label,value,ph){
 return `<div class="rate-cell"><label>${label}</label><input class="input" type="number" min="0" max="100" step="0.01" data-rate-kind="${kind}" data-rate-index="${index}" value="${value===null||value===undefined?'':esc(value)}" placeholder="${esc(ph||'默认规则')}" oninput="ratesDirty=true"><small>单位 % · 留空沿用默认</small></div>`;
}
function renderRatesTab(){
 const rates=gmOnline.rates||{};
 $('#gm-tab').innerHTML=`<p class="subheading" style="margin:0 0 14px">对后续掉落、强化与副本经验判定生效；已发出的掉落不会重新判定。100 基点 = 1%。</p><form id="rates-form" style="max-width:760px"><label class="field-label">副本经验倍率 · 当前 ${( (rates.experience_bp??10000)/10000).toLocaleString('zh-CN')} 倍（0–100）</label><input class="input" id="rate-exp" type="number" min="0" max="100" step="0.01" value="${((rates.experience_bp??10000)/10000).toLocaleString('zh-CN',{maximumFractionDigits:4})}" style="max-width:220px" oninput="ratesDirty=true"><p class="subheading" style="margin-top:18px">掉落概率覆盖</p><div class="rate-grid" style="margin-top:10px">${rateInput('drops','ordinary','普通怪物物品',rates.drops?.ordinary!=null?String(rates.drops.ordinary/100):null,'默认掉落表')}${rateInput('drops','boss','BOSS 物品',rates.drops?.boss!=null?String(rates.drops.boss/100):null,'默认掉落表')}${rateInput('drops','chest','宝箱物品',rates.drops?.chest!=null?String(rates.drops.chest/100):null,'默认掉落表')}${rateInput('drops','ed','ED 掉落概率',rates.drops?.ed!=null?String(rates.drops.ed/100):null,'默认 100%')}</div><p class="subheading" style="margin-top:18px">强化成功率（+0 → +12）</p><div class="enh-grid">${rates.enhancement?.map((v,i)=>rateInput('enhancement',String(i),'+'+i+' → +'+(i+1),v!=null?String(v/100):null,'默认')).join('')||''}</div><div class="field-row" style="margin-top:18px"><button type="button" class="button subtle" data-action="rates-reset">恢复默认（表单）</button><button class="button primary" data-action="gm-rates">${icon('check')}保存概率配置</button><span class="muted" style="font-size:10px;align-self:center">当前版本 v${rates.revision??0}${ratesDirty?' · 有未保存修改':''}</span></div></form>`;
}
function epochToLocal(v){if(!v)return '';const d=new Date(v*1000),p=n=>String(n).padStart(2,'0');return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes());}
function localToEpoch(v){if(!v)return null;const t=new Date(v).getTime();return Number.isFinite(t)&&t>0?Math.floor(t/1000):null;}
function renderEventsTab(){
 const rows=gmOnline.events?.rows||[];eventsDirty=false;
 $('#gm-tab').innerHTML=`<p class="subheading" style="margin:0 0 14px">仅控制新入场；原等级、门票、任务和组队条件仍需满足。留空时间表示不限制。</p>${rows.map(r=>`<div class="event-row"><div><strong>${esc(r.name)}</strong> <span class="muted">#${r.id}</span><br><small class="muted">${esc(r.scope||'')}</small></div><div class="event-fields"><label class="switch-row compact"><input type="checkbox" data-event-enabled="${r.id}" ${r.enabled?'checked':''}> 开放</label><input class="input" type="datetime-local" data-event-start="${r.id}" value="${epochToLocal(r.start)}" title="开始时间（可选）"><input class="input" type="datetime-local" data-event-end="${r.id}" value="${epochToLocal(r.end)}" title="结束时间（可选）"></div></div>`).join('')||empty('没有可配置的活动','clock')}<div class="field-row" style="margin-top:18px"><button class="button primary" data-action="gm-events">${icon('check')}保存活动配置</button><span class="muted" style="font-size:10px;align-self:center">当前版本 v${gmOnline.events?.revision??0}</span></div>`;
}
function renderCouponsTab(){
 if(couponRewards===null){api('gm-online',{action:'coupon-rewards',value:{}}).then(data=>{couponRewards=data.rows||[];if(page==='gm'&&tab==='coupons')renderCouponsTab();}).catch(e=>{$('#gm-tab').innerHTML=empty(esc(e.message),'warning');});$('#gm-tab').innerHTML=empty('正在读取可发放的奖励目录…','ticket');return;}
 const picks=[...couponPicks.entries()];
 $('#gm-tab').innerHTML=`<div class="coupon-layout"><div><p class="subheading" style="margin:0 0 12px">生成兑换券：玩家在游戏内输入 20 位兑换码后，到邮箱领取奖励。仅限已验证的永久时装单件。</p><div class="form-card"><h3>选择奖励（最多 8 种，合计 ≤ 99 件）</h3><div style="display:grid;gap:7px;max-height:300px;overflow:auto;margin-top:12px">${couponRewards.map(r=>`<label class="coupon-pick ${couponPicks.has(r.template)?'selected':''}"><input type="checkbox" data-coupon-template="${r.template}" ${couponPicks.has(r.template)?'checked':''} style="accent-color:#0ba9ce;width:15px;height:15px"> ${esc(r.name)} <small>#${r.template}</small>${couponPicks.has(r.template)?`<input type="number" data-coupon-qty="${r.template}" min="1" max="99" value="${couponPicks.get(r.template)}" style="width:64px;min-height:30px;padding:4px 7px;margin-left:8px" onclick="event.stopPropagation()">`:''}</label>`).join('')}</div><div class="form-grid" style="grid-template-columns:1fr 1fr;margin-top:16px"><div><label class="field-label">生成张数 · 1–100</label><input class="input" id="coupon-count" type="number" min="1" max="100" value="1"></div><div><label class="field-label">每张可兑换次数 · 1–100</label><input class="input" id="coupon-redemptions" type="number" min="1" max="100" value="1"></div><div><label class="field-label">生效时间（可选，默认立即）</label><input class="input" id="coupon-start" type="datetime-local" value="${epochToLocal(Math.floor(Date.now()/1000))}"></div><div><label class="field-label">失效时间（默认 7 天后）</label><input class="input" id="coupon-expires" type="datetime-local" value="${epochToLocal(Math.floor(Date.now()/1000)+7*86400)}"></div></div><label class="field-label" style="margin-top:12px">限定账号（可选；填写后每张只能被该账号兑换 1 次）</label><input class="input" id="coupon-account" type="number" min="2" step="1" placeholder="留空 = 任意账号可兑换"><button class="button primary" data-action="gm-coupon-issue" style="margin-top:16px">${icon('ticket')}生成兑换券</button></div><div id="coupon-codes"></div></div><div><div class="panel-head"><h2>历史批次</h2><button class="button text" data-action="coupon-reload">${icon('refresh')}刷新</button></div><div id="coupon-batches">${couponBatches===null?'<p class="muted" style="font-size:10px">正在加载…</p>':''}</div></div></div>`;
 renderCouponBatches();
}
function renderCouponBatches(){
 const box=$('#coupon-batches');if(!box)return;
 if(couponBatches===null){api('gm-online',{action:'coupon-list',value:{offset:0}}).then(data=>{couponBatches=data;if(page==='gm'&&tab==='coupons')renderCouponBatches();}).catch(e=>{box.innerHTML=empty(esc(e.message),'warning');});return;}
 box.innerHTML=couponBatches.rows.length?couponBatches.rows.map(b=>`<div class="coupon-batch"><strong>${esc(b.reason||'兑换券批次')}</strong> <span class="badge ${b.revoked_at?'planned':''}">${b.revoked_at?'已作废':'有效'}</span><small>${b.codes.length} 张 · 生成于 ${new Date(b.created_at*1000).toLocaleString('zh-CN',{hour12:false})}<br>${b.codes.filter(c=>c.used).length} 张已兑换${b.revoke_reason?' · 作废原因：'+esc(b.revoke_reason):''}</small></div>`).join(''):empty('还没有生成过兑换券。','ticket');
}
async function renderCashTab(){
 $('#gm-tab').innerHTML=empty('正在读取 A币余额…','gem');
 try{cashInfo=await api('gm-online',{action:'cash-balance',value:{account_id:1}});}catch(e){$('#gm-tab').innerHTML=empty(esc(e.message),'warning');return;}
 if(page!=='gm'||tab!=='cash')return;
 $('#gm-tab').innerHTML=`<div style="max-width:560px"><p class="subheading" style="margin:0 0 14px">A币（Ariel Cash）是本机商城使用的账户余额，发放后立即生效。</p><div class="online-stat" style="margin-bottom:16px"><span>账号 1 当前 A币余额</span><strong>${number(cashInfo.balance)}</strong></div><label class="field-label" for="cash-amount">本次充值数量 · 1 – 2,147,483,647</label><input class="input" id="cash-amount" type="number" min="1" max="2147483647" step="1" value="1000" inputmode="numeric"><div class="field-row">${[100,1000,10000].map(n=>`<button type="button" class="button subtle" data-cash-preset="${n}">${number(n)}</button>`).join('')}</div><button class="button primary" data-action="gm-cash" style="margin-top:16px">${icon('gem')}确认充值</button></div>`;
}
function renderOfflineTab(){
 const c=role();
 const options=characters.map(x=>`<option value="${x.uid}" ${x.uid===selected?'selected':''}>${esc(x.name)} · ${esc(x.role)} · Lv. ${x.level} · UID ${x.uid}</option>`).join('');
 $('#gm-tab').innerHTML=writeNotice()+`<label class="field-label" for="offline-character">选择角色</label><select id="offline-character" style="max-width:420px">${options||'<option value="">尚无角色</option>'}</select>`+(c?`<div class="offline-tools" style="margin-top:18px"><form class="form-card" data-gm-form="ed"><div class="card-icon">${icon('coin')}</div><h3>发放 ED</h3><p>增加所选角色的 ED，保留当前余额。需游戏完全退出。</p><label for="ed-amount">本次发放数量</label><input class="input" id="ed-amount" name="amount" type="number" step="1" min="1" max="2000000000" value="1000000" required inputmode="numeric"><div class="field-row">${[100000,1000000,10000000,1000000000].map((n,i)=>`<button type="button" class="button subtle" data-preset="${n}">${['10 万','100 万','1000 万','10 亿'][i]}</button>`).join('')}</div><p class="field-error" aria-live="polite"></p><button class="button primary submit" data-write>预览发放 ${icon('arrow')}</button></form>
 <form class="form-card" data-gm-form="level"><div class="card-icon">${icon('level')}</div><h3>提升角色等级</h3><p>按原生经验表同步经验，最高 99 级。需游戏完全退出。</p><label for="target-level">目标等级 · 当前 Lv. ${c.level}</label><input class="input" id="target-level" name="amount" type="number" step="1" min="${Math.min(99,c.level+1)}" max="99" value="${Math.min(99,Math.max(15,c.level+1))}" required inputmode="numeric"><div class="field-row">${[15,70,99].map(n=>`<button type="button" class="button subtle" data-preset="${n}" ${n<=c.level?'disabled':''}>Lv. ${n}</button>`).join('')}</div><p class="field-error" aria-live="polite"></p><button class="button primary submit" data-write ${c.level===99?'disabled data-max-level':''}>${c.level===99?'已达等级上限':'预览调整 '+icon('arrow')}</button></form>
 <div class="form-card"><div class="card-icon">${icon('town')}</div><h3>回到魔奇</h3><p>重置到已验证的初始城镇位置，适合处理角色卡位。</p><button class="button outlined submit" data-action="town" data-write>预览回城 ${icon('arrow')}</button></div>
 ${c.tutorial_recovery?`<div class="form-card"><div class="card-icon">${icon('town')}</div><h3>恢复新手起点</h3><p>将所选旧角色移回${esc(c.role)}的原新手起点，保留等级、物品和任务。</p><button class="button outlined submit" data-action="tutorial-start" data-write>预览恢复 ${icon('arrow')}</button></div>`:''}
 <div class="form-card"><div class="card-icon">${icon('backup')}</div><h3>先留一份进度</h3><p>使用数据库备份保存当前全部角色、物品和操作记录。</p><button class="button outlined submit" data-action="backup">立即备份 ${icon('arrow')}</button></div></div>
 <p class="subheading" style="margin-top:20px">离线发放道具：退出游戏后，可直接把道具写进所选角色的背包。</p><div class="toolbar"><div class="search">${icon('search')}<input class="input" id="offline-item-search" placeholder="搜索道具名称或 ID" aria-label="离线搜索道具" value="${esc(itemsQuery)}"></div><select id="offline-item-group" aria-label="道具分类"><option value="all">全部分类</option>${[[1,'装备'],[2,'饰品'],[3,'材料'],[4,'特殊'],[5,'生活'],[6,'消耗品'],[27,'时装']].map(([id,name])=>`<option value="${id}" ${itemsGroup===String(id)?'selected':''}>${name}</option>`).join('')}</select></div><div class="items-layout"><div><div class="item-results" id="offline-item-results">${empty('正在读取道具目录…','search')}</div><div class="pagination" id="offline-item-pagination"></div></div><form class="item-selection" data-gm-form="item" id="offline-item-selection"></form></div>`:empty('进入游戏后创建角色，才能使用离线工具。','user'));
 if(c){chosenItem=null;renderOfflineItemSelection();loadOfflineItems();}
 applyState();
}
function renderOfflineItemSelection(){
 const form=$('#offline-item-selection');if(!form)return;
 form.innerHTML=chosenItem?`<div><p class="eyebrow">已选道具</p><h3>${esc(chosenItem.name)}</h3><p>ID ${chosenItem.id} · ${esc(chosenItem.bag)}</p></div><div><label class="field-label" for="item-quantity">发放数量</label><input class="input" type="number" id="item-quantity" name="amount" min="1" max="99" step="1" value="1" required inputmode="numeric"></div><p class="field-error" aria-live="polite"></p><button class="button primary" data-write>预览发放 ${icon('arrow')}</button>`:`<p class="eyebrow">发放预览</p><h3>先选择一件道具</h3><p>点击左侧的搜索结果，再填写数量。</p>`;
 applyState();
}
let itemRequest=0,currentItems=[];
function itemRowsHtml(data){return data.rows.map(x=>`<button type="button" class="item-row ${chosenItem?.id===x.id?'selected':''}" data-item="${x.id}" aria-pressed="${chosenItem?.id===x.id}"><span><strong>${esc(x.name)}</strong><small>ID ${x.id} · 每格最多 ${x.stack}</small></span><span class="item-bag">${esc(x.bag)}</span></button>`).join('')||empty('没有找到匹配道具。试试名称的一部分或数字 ID。','search');}
async function loadItems(){
 const id=++itemRequest;
 try{const data=await api(`items?q=${encodeURIComponent(itemsQuery)}&group=${encodeURIComponent(itemsGroup)}&offset=${itemOffset}`);if(id!==itemRequest||page!=='gm'||tab!=='send'||!$('#item-results'))return;currentItems=data.rows;
 $('#item-results').innerHTML=itemRowsHtml(data);
 $('#item-pagination').innerHTML=`<span>共 ${number(data.total)} 项 · ${data.total?`${itemOffset+1}–${Math.min(itemOffset+40,data.total)}`:'0'}</span><div><button class="button subtle" data-item-page="-1" ${itemOffset===0?'disabled':''}>上一页</button><button class="button subtle" data-item-page="1" ${itemOffset+40>=data.total?'disabled':''}>下一页</button></div>`;
 }catch(e){if(id===itemRequest&&$('#item-results'))$('#item-results').innerHTML=empty(esc(e.message),'warning');}
}
async function loadOfflineItems(){
 const id=++itemRequest;
 try{const data=await api(`items?q=${encodeURIComponent(itemsQuery)}&group=${encodeURIComponent(itemsGroup)}&offset=${itemOffset}`);if(id!==itemRequest||page!=='gm'||tab!=='offline'||!$('#offline-item-results'))return;currentItems=data.rows;
 $('#offline-item-results').innerHTML=itemRowsHtml(data);
 $('#offline-item-pagination').innerHTML=`<span>共 ${number(data.total)} 项 · ${data.total?`${itemOffset+1}–${Math.min(itemOffset+40,data.total)}`:'0'}</span><div><button class="button subtle" data-item-page="-1" data-offline="1" ${itemOffset===0?'disabled':''}>上一页</button><button class="button subtle" data-item-page="1" data-offline="1" ${itemOffset+40>=data.total?'disabled':''}>下一页</button></div>`;
 }catch(e){if(id===itemRequest&&$('#offline-item-results'))$('#offline-item-results').innerHTML=empty(esc(e.message),'warning');}
}
async function loadInventory(e){try{const rows=await api('inventory?uid='+selected);if(e!==epoch||page!=='gm'||tab!=='bag')return;$('#gm-tab').innerHTML=rows.length?`<p class="subheading" style="margin:0 0 15px">${esc(role()?.name||'')} · ${rows.length} 个格位 · 背包及穿戴信息只读查看</p><div class="table-wrap"><table><thead><tr><th>道具</th><th>道具 ID</th><th>数量</th><th>分类</th><th>格位</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.name)}</td><td>${x.template}</td><td>${x.count}</td><td>${esc(x.bag)}</td><td>${x.slot}</td></tr>`).join('')}</tbody></table></div>`:empty('背包中还没有物品。');}catch(err){if(e===epoch&&$('#gm-tab'))$('#gm-tab').innerHTML=empty(esc(err.message),'warning');}}
async function loadHistory(e){try{const data=await api('history');if(e!==epoch||page!=='gm'||tab!=='history')return;const rows=data.filter(x=>x.uid===selected);$('#gm-tab').innerHTML=rows.length?`<p class="subheading" style="margin:0 0 12px">离线工具的操作记录（在线发放的回执在服务端审计中）。</p><div class="history-list">${rows.map(x=>`<div class="history-row">${icon('check')}<div><strong>${esc(x.detail)}</strong><small>${esc(x.time.replace('T',' ').slice(0,19))} · UID ${x.uid}<br>自动备份：${esc(x.backup)}</small></div></div>`).join('')}</div>`:empty('还没有此角色的离线 GM 操作记录。','clock');}catch(err){if(e===epoch&&$('#gm-tab'))$('#gm-tab').innerHTML=empty(esc(err.message),'warning');}}

/* ---------- online GM helpers ---------- */
function confirmGM(title,body,button='发送',reason='在线启动器 GM 操作'){
 return new Promise(resolve=>{
  const dialog=$('#confirm-dialog');
  $('#dialog-title').textContent=title;
  $('#dialog-body').innerHTML=body+`<label class="field-label" for="dialog-reason" style="margin-top:16px">操作原因（写入服务端审计，2–200 字）</label><input class="input" id="dialog-reason" maxlength="200" value="${esc(reason)}">`;
  $('#dialog-icon').innerHTML=icon('gm');
  $('#dialog-confirm').textContent=button;
  dialog.returnValue='cancel';
  dialog.addEventListener('close',()=>{if(dialog.returnValue==='confirm')resolve(($('#dialog-reason')?.value||'').trim());else resolve(null);},{once:true});
  dialog.showModal();
  const input=$('#dialog-reason');input?.focus();input?.select();
  input?.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('#dialog-confirm').click();}},{once:true});
 });
}
function describeOnline(action,r){
 if(!r||typeof r!=='object')return '操作已完成';
 if(action==='give')return (r.replayed?'该操作编号已发放过，未重复发货。':'已落账并推送背包通知。')+' 收件 UID '+r.uid;
 if(action==='announce')return '已排队发送给 '+r.recipients+' 位在线角色，共 '+r.repeat+' 次';
 if(action==='cancel-announcement')return '已取消重复公告计划';
 if(action==='rates')return '概率配置已更新至 v'+r.revision;
 if(action==='events')return '活动配置已更新至 v'+r.revision;
 if(action==='coupon-issue')return r.replayed?'该操作编号已存在，已取回原回执。':'已生成 '+((r.codes||[]).length)+' 张兑换券';
 if(action==='coupon-revoke')return r.already_revoked?'该批次此前已作废':'批次已作废';
 if(action==='cash-credit')return '已充值 '+number(r.credited)+' A币，余额 '+number(r.after?.balance??0);
 return '操作已完成';
}
async function sendOnline(action,value,label,button='发送'){
 if(mutating)return;
 if(!gmOnline?.online){toast('在线 GM 未连接：'+(gmOnline?.error||'请先启动游戏'),true);return;}
 const reason=await confirmGM('发送在线 GM 操作？',label,button);
 if(reason===null)return;
 if(reason.length<2){toast('请输入 2–200 字的操作原因',true);return;}
 mutating=true;applyState();
 try{const result=await api('gm-online',{action,value:{...value,reason,operation_id:crypto.randomUUID()}},60000);
  toast(describeOnline(action,result));
  if(action==='coupon-issue')showCouponCodes(result);
  ratesDirty=false;eventsDirty=false;
  await refreshGmStatus();
  await renderGMTabSafe();
 }catch(e){toast(e.message,true);}
 finally{mutating=false;await poll();}
}
async function renderGMTabSafe(){if(page==='gm'&&$('#gm-tab'))renderGMTab();}
function showCouponCodes(result){
 const box=$('#coupon-codes');if(!box)return;
 const codes=result?.codes||[];
 box.innerHTML=codes.length?`<div class="form-card" style="margin-top:16px"><h3>兑换码（仅本次显示，请立即复制保存）</h3><div class="code-box" id="coupon-code-box">${esc(codes.join('\n'))}</div><button class="button subtle" data-action="copy-codes" style="margin-top:12px">${icon('copy')}复制全部兑换码</button></div>`:'';
}
async function refreshGmStatus(){
 try{const data=await api('gm-status',undefined,12000);gmOnline=data;gmStatusAt=Date.now();
  const banner=$('#gm-banner'),strip=$('#gm-strip');
  if(banner)banner.innerHTML=gmBanner();
  if(strip)strip.innerHTML=gmStrip();
  applyState();
 }catch(e){/* state poll surfaces connection issues */}
}
setInterval(()=>{if(closed||document.hidden)return;if(page==='gm'&&ONLINE_TABS.includes(tab))refreshGmStatus();},6000);

/* ---------- other pages ---------- */
async function renderBackups(e){const rows=await api('backups');if(e!==epoch)return;main.innerHTML=heading('每一段进度，都值得保留。','备份包含全部角色、资产和当前存档记录。',`<button class="button primary" data-action="backup">${icon('backup')}立即备份</button>`)+`<div class="notice">${icon('info')}<div>离线修改前会自动创建备份；也可以手动留下当前进度。备份使用 SQLite 完整备份方式，游戏运行时同样可用。</div></div><section class="panel"><div class="panel-head"><h2>备份记录 <small>${rows.length} 份</small></h2><button class="button text" data-folder="backups">打开备份目录 ${icon('folder')}</button></div>${rows.length?`<div class="table-wrap"><table><thead><tr><th>备份文件</th><th>时间</th><th>大小</th><th>类型</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.name)}</td><td>${esc(x.time.replace('T',' ').slice(0,19))}</td><td>${number(Math.ceil(x.size/1024))} KB</td><td><span class="badge ${x.name.includes('manual')?'':'partial'}">${x.name.includes('manual')?'手动备份':'修改前备份'}</span></td></tr>`).join('')}</tbody></table></div>`:empty('还没有备份，点击右上角留下一份进度。','backup')}</section><div class="mini-banner">${icon('gm')}恢复备份需要完全退出游戏和服务端。当前版本提供备份与目录查看，暂未开放一键覆盖恢复。</div>`;}
async function renderFeatures(e){const rows=await api('features');if(e!==epoch)return;const labels={complete:'已接入',verified:'已验证',implemented:'已接入',partial:'部分接入',in_progress:'完善中',planned:'待接入',pending:'待验证',blocked:'待完善'};main.innerHTML=heading('世界，正在一点点完善。','这里展示服务端当前的实际接入情况。')+`<div class="notice">${icon('info')}<div>资源配表已经读取，与玩法完整实现是不同的进度。展开卡片，可查看每项仍在完善的内容。</div></div><div class="feature-grid">${rows.map(f=>`<article class="panel feature-card"><div class="panel-head"><h3>${esc(f.title)}</h3><span class="badge ${['complete','verified','implemented'].includes(f.status)?'':['partial','in_progress'].includes(f.status)?'partial':'planned'}">${esc(labels[f.status]||'待完善')}</span></div><p>${esc(f.current)}</p>${f.missing?`<details><summary>仍在完善的内容</summary><p>${esc(f.missing)}</p></details>`:''}</article>`).join('')}</div>`;}
function renderSettings(){
 const bg=bgSettings?.background||{};
 const reduce=document.body.classList.contains('motion-off');
 main.innerHTML=heading('按你的习惯，准备冒险。','无边框窗口 · 动态背景 · 启动器沿用本机已验证的游戏环境。')+
 `<div class="settings-grid"><section class="panel"><div class="panel-head"><h2>动态背景</h2>${icon('palette')}</div><p class="subheading">选择内置动画，或导入你自己的图片 / 视频。背景只在启动器内显示，不影响游戏。</p><div class="bg-options" id="bg-options">${bgButtons()}</div><div id="bg-file-row" style="margin-top:14px">${bg.mode==='image'||bg.mode==='video'?`<label class="field-label" for="bg-file">选择${bg.mode==='image'?'图片':'视频'}文件（≤ 24 MB）</label><input class="input" id="bg-file" type="file" accept="${bg.mode==='image'?'.png,.jpg,.jpeg,.webp,.gif':'.mp4,.webm'}">`:''}</div><div class="dim-row"><span style="text-align:left;min-width:0">背景明暗</span><input id="bg-dim-range" type="range" min="0" max="70" step="5" value="${bg.dim??30}"><span id="bg-dim-value">${bg.dim??30}%</span></div>${bg.file?`<p class="bg-current">当前自定义背景：${esc(bg.file)}</p>`:''}<div class="mini-banner">${icon('info')}内置背景为启动器自绘动画，不读取任何外部文件；自定义文件保存在本机启动器目录。</div></section>
 <section class="panel"><div class="panel-head"><h2>使用体验</h2>${icon('settings')}</div><h3>按钮与页面动效</h3><p class="subheading">关闭动效后，动态背景会显示为静止画面。</p><label class="switch-row"><input id="reduce-motion" type="checkbox" ${reduce?'checked':''}>减少界面动效</label><h3 style="margin-top:24px">本地路径</h3><label class="field-label">游戏客户端</label><div class="path-row"><div class="path-value">${esc(state.client)}</div><button class="button subtle" data-folder="client">打开目录</button></div><label class="field-label" style="margin-top:18px">当前存档</label><div class="path-row"><div class="path-value">${esc(state.save)}</div><button class="button subtle" data-folder="save">打开目录</button></div><label class="field-label" style="margin-top:18px">自定义背景目录</label><div class="path-row"><div class="path-value">${esc(state.save.replace(/\\[^\\]+$/,'')+'\\launcher-online\\backgrounds')}</div><button class="button subtle" data-folder="backgrounds">打开目录</button></div><div class="mini-banner">${icon('gm')}游戏运行中允许使用在线 GM；离线修改会自动锁定，退出后解锁。</div><p class="subheading" style="margin-top:18px">关闭启动器不会中断正在运行的游戏；游戏退出后，对应的本地服务自动结束。</p></section></div>
 <section class="panel" style="margin-top:20px"><div class="panel-head"><h2>环境检查</h2><button class="button primary" data-action="check">${icon('check')}开始检查</button></div><div id="check-results">${checkHTML()}</div></section>`;
}
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
   <div class="notice">${icon('info')}<div>拉取会更新代码文件，新代码需要重新打开启动器后生效。运行资源包若有变化，请再用「更新单机版」同步。</div></div>
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
  if(page==='gm'){await refreshGmStatus();if(e!==epoch)return;renderGM();}
  else if(page==='home')renderHome();
  else if(page==='backups')await renderBackups(e);
  else if(page==='features')await renderFeatures(e);
  else if(page==='repo')await renderRepo(e);
  else if(page==='settings')renderSettings();
  else await renderLogs(e);
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
 $('#footer-state').textContent=state.message==='准备就绪'?(state.game_running?'已有游戏运行 · 在线 GM 可用':'本地存档已连接'):state.message;
 const launch=$('#launch-game');if(launch){launch.disabled=busy||state.game_running||state.owned;launch.innerHTML=(busy?'<span class="spinner small"></span>':icon('play'))+(state.phase==='checking'?'检查环境中':state.phase==='starting'?'正在启动':state.phase==='stopping'?'退出中':state.game_running?'游戏运行中':'启动游戏');}
 const caption=$('#launch-caption');if(caption)caption.innerHTML=state.owned?`本次游戏由启动器管理<br><button class="button text" data-action="stop" style="color:#bde7ef;min-height:18px;font-size:10px">${icon('stop')}退出本次游戏</button>`:state.game_running?'已有游戏正在运行<br>在线 GM 已就绪，去发放吧':'自动准备本地环境<br>启动后在游戏内选择你的角色';
 for(const b of document.querySelectorAll('[data-action="check"]'))b.disabled=busy||mutating;
 for(const b of document.querySelectorAll('[data-write]'))b.disabled=state.gm_locked||mutating||b.hasAttribute('data-max-level');
 for(const b of document.querySelectorAll('[data-online-action]'))b.disabled=mutating||!gmOnline?.online;
 const checks=$('#check-results');if(checks)checks.innerHTML=state.phase==='checking'?'<div class="initial-loading" style="min-height:120px"><div class="spinner"></div><p>正在检查，请稍候…</p></div>':checkHTML();
}
async function poll(){if(closed)return;try{const old=state;state=await api('state');applyState();if(old&&old.gm_locked&&!state.gm_locked&&page==='gm'&&!$('#confirm-dialog').open&&tab==='offline')await navigate('gm');}catch(e){$('#header-status').textContent='连接中断';$('#header-status').classList.add('warn');for(const b of document.querySelectorAll('[data-write],#launch-game'))b.disabled=true;}}
const pollTimer=setInterval(poll,3500);

function confirmDialog(title,body,button='确认并保存',img='gm'){
 return new Promise(resolve=>{const dialog=$('#confirm-dialog');$('#dialog-title').textContent=title;$('#dialog-body').innerHTML=body;$('#dialog-icon').innerHTML=icon(img);$('#dialog-confirm').textContent=button;dialog.returnValue='cancel';dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});dialog.showModal();});
}
async function reviewGM(action,value){
 const c=role();if(!c||mutating)return;
 if(state.gm_locked){toast('请先正常退出游戏，离线修改将在退出后解锁（在线发放不受影响）',true);return;}
 const labels={ed:`增加 ${number(value)} ED`,level:`提升到 Lv. ${value}`,item:`${esc(chosenItem?.name)} × ${value.quantity}`,town:'回到魔奇初始位置',tutorial_start:`移回${esc(c.role)}的原新手起点（等级、物品和任务保持不变）`};
 const snapshot={operation_id:crypto.randomUUID(),uid:c.uid,version:c.version,action,value};
 const ok=await confirmDialog('为这个角色提交离线修改？',`<p>目标角色：<strong>${esc(c.name)}</strong> · UID ${c.uid}</p><div class="summary-box">${labels[action]}</div><p>提交前自动备份。此次操作将写入存档，下次登录生效。</p>`);
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
 if(b.dataset.tab){tab=b.dataset.tab;epoch++;renderGM();return;}
 if(b.dataset.character){selected=Number(b.dataset.character);chosenItem=null;localStorage.setItem('els-character',selected);await navigate('gm');return;}
 if(b.dataset.preset){const form=b.closest('form');form.querySelector('[name="amount"]').value=b.dataset.preset;form.querySelector('.field-error').textContent='';return;}
 if(b.dataset.cashPreset){const input=$('#cash-amount');if(input)input.value=b.dataset.cashPreset;return;}
 if(b.dataset.bgMode!==undefined&&b.dataset.bgMode!==null&&b.dataset.bgMode!==''){
  const key=b.dataset.bgMode;
  if(key.startsWith('builtin:'))await setBackground({mode:'builtin',builtin:key.slice(8)});
  else if(key==='image'||key==='video')await setBackground({mode:key});
  else await setBackground({mode:'off'});
  const options=$('#bg-options');if(options)options.innerHTML=bgButtons();
  const row=$('#bg-file-row');if(row)row.innerHTML=(bgSettings?.background.mode==='image'||bgSettings?.background.mode==='video')?`<label class="field-label" for="bg-file">选择${bgSettings.background.mode==='image'?'图片':'视频'}文件（≤ 24 MB）</label><input class="input" id="bg-file" type="file" accept="${bgSettings.background.mode==='image'?'.png,.jpg,.jpeg,.webp,.gif':'.mp4,.webm'}">`:'';
  return;
 }
 if(b.dataset.item){chosenItem=currentItems.find(x=>x.id===Number(b.dataset.item));for(const row of document.querySelectorAll('[data-item]')){row.classList.toggle('selected',row===b);row.setAttribute('aria-pressed',String(row===b));}if(tab==='send')renderOnlineGive();else renderOfflineItemSelection();return;}
 if(b.dataset.itemPage){itemOffset=Math.max(0,itemOffset+40*Number(b.dataset.itemPage));if(b.dataset.offline)await loadOfflineItems();else await loadItems();$('#item-results')?.scrollTo(0,0);$('#offline-item-results')?.scrollTo(0,0);return;}
 if(b.dataset.player){onlinePlayer=b.dataset.player;for(const row of document.querySelectorAll('[data-player]'))row.classList.toggle('selected',row===b);renderOnlineGive();return;}
 if(b.dataset.couponTemplate!==undefined&&b.dataset.couponTemplate!==''){
  const id=Number(b.dataset.couponTemplate);
  if(b.type==='checkbox'){/* handled in change */}
  return;
 }
 if(b.dataset.folder){try{await api('open',{which:b.dataset.folder});}catch(e){toast(e.message,true);}return;}
 if(b.dataset.job){await sendOnline('cancel-announcement',{id:b.dataset.job},'取消这条重复公告的后续发送？','取消计划');return;}
 if(b.dataset.couponBatch){await sendOnline('coupon-revoke',{batch_id:b.dataset.couponBatch},'作废这批兑换券？作废后不能再兑换。','作废批次');return;}
 const action=b.dataset.action;
 if(!action)return;
 try{
  if(action==='reload'){await navigate();return;}
  if(action==='gm-refresh'){await refreshGmStatus();toast(gmOnline?.online?'在线 GM 已连接':'在线 GM 未连接：'+(gmOnline?.error||''));return;}
  if(action==='repo-commit'){await commitRepo();return;}
  if(action==='repo-pull'){await pullRepo();return;}
  if(action==='town'){await reviewGM('town',20000);return;}
  if(action==='tutorial-start'&&role()?.tutorial_recovery){await reviewGM('tutorial_start',{version:role().tutorial_recovery.version});return;}
  if(action==='gm-give'){
   const current=gmOnline?.players?.find(p=>p.session===onlinePlayer);
   if(!current){toast('请先选择在线角色',true);return;}
   const qty=Number($('#give-quantity')?.value);
   if(!Number.isSafeInteger(qty)||qty<1||qty>99){toast('发放数量需要是 1–99 的整数',true);return;}
   if(!chosenItem){toast('请先选择一件道具',true);return;}
   await sendOnline('give',{uid:current.uid,session:current.session,template:chosenItem.id,quantity:qty},
    `<p>收件角色：<strong>${esc(current.name)}</strong> · UID ${current.uid}</p><div class="summary-box">${esc(chosenItem.name)} × ${qty}（ID ${chosenItem.id}）</div><p>道具直接进入在线背包并推送拾取通知，立即生效。</p>`,'在线发放');
   return;
  }
  if(action==='gm-announce'){
   const text=($('#announce-text')?.value||'').trim();
   const repeat=Number($('#announce-repeat')?.value),interval=Number($('#announce-interval')?.value);
   if(!text){toast('请输入公告内容',true);return;}
   if(text.includes('<')||text.includes('>')){toast('公告不允许 < > 字符',true);return;}
   if(!Number.isSafeInteger(repeat)||repeat<1||repeat>20){toast('重复次数需要是 1–20 的整数',true);return;}
   if(!Number.isSafeInteger(interval)||interval<10||interval>3600){toast('重复间隔需要是 10–3600 秒',true);return;}
   await sendOnline('announce',{text,repeat,interval},`<p>全服滚动公告：</p><div class="summary-box">${esc(text)}</div><p>重复 ${repeat} 次，间隔 ${interval} 秒。发送后立即显示在游戏内。</p>`,'发送公告');
   return;
  }
  if(action==='rates-reset'){
   for(const input of document.querySelectorAll('[data-rate-kind]'))input.value='';
   const exp=$('#rate-exp');if(exp)exp.value='1';
   ratesDirty=true;toast('已在表单中恢复默认，请保存后生效');return;
  }
  if(action==='gm-rates'){
   const settings={drops:{},enhancement:[],experience_bp:Math.round(Number($('#rate-exp')?.value)*10000)};
   if(!Number.isSafeInteger(settings.experience_bp)||settings.experience_bp<0||settings.experience_bp>1000000){toast('经验倍率需要在 0–100 倍内',true);return;}
   for(const input of document.querySelectorAll('[data-rate-kind]')){
    const n=input.value.trim()===''?null:Math.round(Number(input.value)*100);
    if(n!==null&&(!Number.isSafeInteger(n)||n<0||n>10000)){toast('概率需要是 0–100 之间的百分比',true);return;}
    if(input.dataset.rateKind==='enhancement')settings.enhancement[Number(input.dataset.rateIndex)]=n;
    else settings.drops[input.dataset.rateIndex]=n;
   }
   if(settings.enhancement.length!==13){toast('强化配置不完整，请刷新后重试',true);return;}
   const expected=gmOnline?.rates?.revision;
   await sendOnline('rates',{settings,expected_revision:expected},'<p>保存概率与经验配置？对后续判定生效，已发出的掉落不重新判定。</p>','保存配置');
   return;
  }
  if(action==='gm-events'){
   const events={};
   for(const row of gmOnline.events.rows||[]){
    const enabled=document.querySelector(`[data-event-enabled="${row.id}"]`)?.checked;
    const start=localToEpoch(document.querySelector(`[data-event-start="${row.id}"]`)?.value);
    const end=localToEpoch(document.querySelector(`[data-event-end="${row.id}"]`)?.value);
    if(start&&end&&start>=end){toast('结束时间必须晚于开始时间',true);return;}
    events[String(row.id)]={enabled:!!enabled,start,end};
   }
   const expected=gmOnline?.events?.revision;
   await sendOnline('events',{events,expected_revision:expected},'<p>保存活动开关与时间窗？仅控制新入场。</p>','保存配置');
   return;
  }
  if(action==='gm-coupon-issue'){
   const rewards=[...couponPicks.entries()].map(([template,quantity])=>({template,quantity}));
   if(!rewards.length){toast('请至少选择一种奖励',true);return;}
   if(rewards.length>8){toast('奖励种类最多 8 种',true);return;}
   if(rewards.reduce((sum,r)=>sum+r.quantity,0)>99){toast('奖励合计不能超过 99 件',true);return;}
   const count=Number($('#coupon-count')?.value),redemptions=Number($('#coupon-redemptions')?.value);
   const accountRaw=($('#coupon-account')?.value||'').trim();
   const account=accountRaw?Number(accountRaw):null;
   if(!Number.isSafeInteger(count)||count<1||count>100){toast('生成张数需要是 1–100 的整数',true);return;}
   if(!Number.isSafeInteger(redemptions)||redemptions<1||redemptions>100){toast('可兑换次数需要是 1–100 的整数',true);return;}
   if(account!==null&&(!Number.isSafeInteger(account)||account<2)){toast('限定账号需要是 ≥2 的账号编号',true);return;}
   if(account!==null&&redemptions!==1){toast('限定账号的兑换券每张只能兑换 1 次，请把可兑换次数改为 1',true);return;}
   const starts_at=localToEpoch($('#coupon-start')?.value),expires_at=localToEpoch($('#coupon-expires')?.value);
   if(!starts_at||!expires_at||starts_at>=expires_at){toast('失效时间必须晚于生效时间',true);return;}
   await sendOnline('coupon-issue',{count,max_redemptions:redemptions,starts_at,expires_at,account_id:account,rewards},
    `<p>生成 <strong>${count}</strong> 张兑换券，每张可兑换 ${redemptions} 次。</p><div class="summary-box">${rewards.map(r=>esc((couponRewards.find(x=>x.template===r.template)||{}).name||('#'+r.template))+' × '+r.quantity).join('、')}</div><p>兑换码只在本次结果显示，请及时复制保存。</p>`,'生成兑换券');
   return;
  }
  if(action==='coupon-reload'){couponBatches=null;renderCouponBatches();return;}
  if(action==='copy-codes'){
   const text=$('#coupon-code-box')?.textContent||'';
   try{await navigator.clipboard.writeText(text);toast('兑换码已复制到剪贴板');}catch{toast('复制失败，请手动选择复制',true);}
   return;
  }
  if(action==='gm-cash'){
   const amount=Number($('#cash-amount')?.value);
   if(!Number.isSafeInteger(amount)||amount<1||amount>2147483647){toast('充值数量需要是 1 – 2,147,483,647 的整数',true);return;}
   try{cashInfo=await api('gm-online',{action:'cash-balance',value:{account_id:1}});}catch(e){toast(e.message,true);return;}
   await sendOnline('cash-credit',{account_id:1,amount,expected_balance:cashInfo.balance},
    `<p>向账号 1 充值 <strong>${number(amount)}</strong> A币。</p><div class="summary-box">当前余额 ${number(cashInfo.balance)} → 预计 ${number(cashInfo.balance+amount)}</div><p>立即生效，用于本机商城余额。</p>`,'确认充值');
   return;
  }
  if(action==='backup'){b.disabled=true;const old=b.innerHTML;b.innerHTML='<span class="spinner small"></span>备份中';try{const result=await api('backup',{});toast(result.message);if(page==='backups')await navigate();}finally{if(b.isConnected){b.disabled=false;b.innerHTML=old;}}return;}
  if(action==='stop'){if(!await confirmDialog('退出本次游戏？','<p>请先结束当前副本并保存进度。启动器将结束自己启动的游戏实例，再等待服务端完成保存。</p>','退出游戏','stop'))return;}
  b.disabled=true;
  const result=await api(action,{});toast(result.message);await poll();
  if(action==='check')await navigate('settings');
 }catch(e){toast(e.message,true);applyState();}
});
document.addEventListener('input',event=>{
 if(event.target.id==='item-search'||event.target.id==='offline-item-search'){itemsQuery=event.target.value;itemOffset=0;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{if(tab==='send')loadItems();else if(tab==='offline')loadOfflineItems();},220);}
 else if(event.target.id==='bg-dim-range'){const value=Number(event.target.value);$('#bg-dim-value').textContent=value+'%';$('#bg-dim').style.opacity=String(value/100);clearTimeout(searchTimer);searchTimer=setTimeout(()=>setBackground({dim:value}),400);}
});
document.addEventListener('change',async event=>{
 if(event.target.id==='item-group'||event.target.id==='offline-item-group'){itemsGroup=event.target.value;itemOffset=0;if(tab==='send')loadItems();else if(tab==='offline')loadOfflineItems();}
 else if(event.target.id==='reduce-motion'){document.body.classList.toggle('motion-off',event.target.checked);localStorage.setItem('els-reduce-motion',event.target.checked);applyBackground(bgSettings);}
 else if(event.target.dataset.couponTemplate){
  const id=Number(event.target.dataset.couponTemplate);
  if(event.target.checked)couponPicks.set(id,Number(document.querySelector(`[data-coupon-qty="${id}"]`)?.value)||1);
  else couponPicks.delete(id);
  renderCouponsTab();
 }
 else if(event.target.dataset.couponQty){couponPicks.set(Number(event.target.dataset.couponQty),Number(event.target.value)||1);}
 else if(event.target.id==='bg-file'){
  const file=event.target.files?.[0];
  if(!file)return;
  if(file.size>24*1024*1024){toast('背景文件需要小于 24 MB',true);return;}
  if(file.size===0){toast('文件为空',true);return;}
  toast('正在导入背景…');
  const reader=new FileReader();
  reader.onload=async()=>{
   try{
    const result=await api('background/import',{filename:file.name,data:String(reader.result)},120000);
    await setBackground({mode:result.mode,file:result.file});
    const options=$('#bg-options');if(options)options.innerHTML=bgButtons();
    toast(result.message||'动态背景已更新');
    const settings=$('#main');if(page==='settings')renderSettings();
   }catch(e){toast(e.message,true);}
  };
  reader.readAsDataURL(file);
 }
 else if(event.target.id==='offline-character'){selected=Number(event.target.value);chosenItem=null;localStorage.setItem('els-character',selected);renderOfflineTab();}
});
$('#refresh').addEventListener('click',()=>navigate());
async function windowAction(action){try{await api('window',{action});await poll();}catch(e){toast(e.message,true);}}
$('#minimize-app').addEventListener('click',()=>windowAction('minimize'));
$('#maximize-app').addEventListener('click',()=>windowAction('toggle_maximize'));
$('#titlebar').addEventListener('dblclick',e=>{if(state?.native_window&&!e.target.closest('button,.top-actions'))windowAction('toggle_maximize');});
$('#close-app').addEventListener('click',async()=>{try{await api('close',{});closed=true;clearInterval(pollTimer);window.close();main.innerHTML='<div class="initial-loading"><h2>启动器已关闭</h2><p>可以关闭此窗口。运行中的游戏会继续运行。</p></div>';}catch(e){toast(e.message,true);}});
$('#confirm-dialog').addEventListener('click',event=>{const d=event.currentTarget;if(event.target===d){const r=d.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)d.close('cancel');}});

/* ---------- boot ---------- */
(async()=>{
 try{
  bgSettings=await api('settings');
  localStorage.setItem('els-background',JSON.stringify(bgSettings));
 }catch(e){
  try{bgSettings=JSON.parse(localStorage.getItem('els-background')||'null');}catch{bgSettings=null;}
 }
 applyBackground(bgSettings);
 navigate('home');
})();
