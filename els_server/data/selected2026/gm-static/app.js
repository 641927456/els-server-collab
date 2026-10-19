'use strict';
const $=id=>document.getElementById(id);
let key='',state=null,pending=null,busy=false;
const labels=['growth','attendance','online'];
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'notice';}
function lock(value){busy=value;$('save').disabled=value;$('refresh').disabled=value;$('retry').disabled=value;for(const input of document.querySelectorAll('#rows input'))input.disabled=value||!state?.available_scopes?.includes(input.dataset.scope);}
async function api(value){const response=await fetch('/api/selected2026',{method:value?'POST':'GET',headers:{'X-GM-Key':key,...(value?{'Content-Type':'application/json'}:{})},...(value?{body:JSON.stringify(value)}:{})});const data=await response.json();if(!response.ok||!data.ok){const error=Error(data.error||'操作未确认');error.definitive=[400,401,403,404,415].includes(response.status);throw error;}return data.result;}
function render(next){state=next;$('editor').hidden=false;$('login').hidden=true;$('revision').textContent=`当前版本 ${next.revision} · 设置已持久保存`;$('rows').replaceChildren();
for(const name of labels){const card=document.createElement('article');const label=document.createElement('label');label.className='switch';const title=document.createElement('span');title.textContent=next.names[name];const input=document.createElement('input');input.type='checkbox';input.id=`enabled-${name}`;input.checked=next.enabled[name];input.dataset.scope=name;input.disabled=!next.available_scopes.includes(name);input.setAttribute('aria-label',next.names[name]);label.append(title,input);const text=document.createElement('p');text.textContent=next.reward_summary[name];card.append(label,text);$('rows').append(card);}
$('calendar').textContent=JSON.stringify(next.configuration,null,2);}
async function refresh(){if(busy)return;lock(true);try{render(await api());message('已读取服务端当前状态。');}catch(error){message(error.message,true);}finally{lock(false);}}
async function submit(value){lock(true);try{const next=await api(value);render(next);pending=null;$('retry').hidden=true;message(next.clock_refresh_errors?.length?'设置已保存；部分在线计时刷新需核查服务日志。':next.replayed?'原操作已确认，当前设置和领奖记录保持。':'设置已保存，在线角色按新开关执行。');}catch(error){pending=error.definitive?null:value;$('retry').hidden=error.definitive;message(error.message+(error.definitive?'；本次未应用，请刷新后提交。':'；原操作编号已保留。'),true);}finally{lock(false);}}
$('login').addEventListener('submit',event=>{event.preventDefault();key=$('key').value.trim();refresh();});
$('refresh').addEventListener('click',refresh);
$('settings').addEventListener('submit',event=>{event.preventDefault();if(busy||!state)return;if(pending){message('尚有未确认操作，请先用原编号核对重试。',true);return;}const enabled=Object.fromEntries(labels.map(name=>[name,$(`enabled-${name}`).checked]));pending={operation_id:crypto.randomUUID(),reason:$('reason').value.trim(),expected_revision:state.revision,enabled};submit(pending);});
$('retry').addEventListener('click',()=>{if(pending&&!busy)submit(pending);});
const fragment=new URLSearchParams(location.hash.slice(1));if(fragment.has('key')){key=fragment.get('key');history.replaceState(null,'',location.pathname);refresh();}
