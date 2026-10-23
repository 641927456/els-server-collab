'use strict';
(() => {
 const data={"version":"activities-status-canonical-erp-candidate-v165","updated_at":"2026-10-19T20:04:25.139437+00:00","progress_url":"https://134.175.57.52:80/els-progress/","rows":[{"name":"战斗力助力活动（2026-07-29期）","local":"两只原力内层箱选择、学习、装备、重登已验并装本地；地区前置26640窗口候选已验。受控350原生加点后重新启动已核：350级/第2页余344/攻击1/双防5，无再次加点；不等于自然成长350。","remaining":"停止本会话游戏自测，整图、自然350与签到跨日交玩家验收。新正式本地共鸣账本与旧成长候选需统一：165隔离存储适配的自然经验/活动提升同账本、回执重试、事务回滚和冷读受控已过；旧存档迁移、结算调用链与通知接合未完。神物箱固定预设仍缺。完整成长及新适配未安装，线上控制继续禁用。"},{"name":"胡巴的签到（2026-06-17期）","local":"实际累计在线60分钟、0次通关，原生显示60/60；退出重登保留可领任务，原确认只生成1份印章及710084×20奖励邮件，界面1/42。现有正式本地运行代码已验，本轮无新增安装。","remaining":"自然跨日/次日接续及全部奖励道具用途仍待。保留首次时限参数失败、领奖后600秒安全截止退出99；SDK成功边界为私有QA条件，不冒称原登录全流程。已验附件领取不重跑，游戏服未安装所选活动、控制禁用。"},{"name":"2026共存的庆典-称号发放（2026-10-07期）","local":"复用原真实30分钟、邮件附件、称号使用装备冷登及到期证据；独立包剔除成长运行依赖，GM关闭区间不计时、普通任务旧回执及外层事务保持，已独立备份同步正式本地。","remaining":"三项完整自然流程尚未验收；本地测试日期独立于官网历史期。线上仅状态页，游戏服未安装所选活动，在线控制禁用。"}]};
 const host=document.getElementById('events');if(!host||document.getElementById('onlineActivityRepair'))return;
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
 const panel=make('article','card');panel.id='onlineActivityRepair';panel.dataset.version=data.version;
 const heading=make('div','card-heading');heading.append(make('h2','','活动修复与接入进度'),make('span','badge','本地修复进行中'));panel.append(heading);
 panel.append(make('p','scope','线上游戏尚未部署本批活动协议。下列内容是本地修复状态，相关线上活动控制暂不可用。'));
 panel.append(make('p','scope','本地奖励已按官网和道具库配置；当前线上图标不代表本批活动已开启。'));
 for(const row of data.rows){const card=make('div','job');card.append(make('strong','',row.name+' · 线上暂不可用'),make('p','scope',row.local),make('p','scope','待补：'+row.remaining));panel.append(card)}
 const link=make('a','text-button','查看线上修复进度表 ↗');link.href=data.progress_url;link.target='_blank';link.rel='noopener noreferrer';panel.append(link);
 panel.append(make('p','scope','状态快照：'+data.updated_at+' · '+data.version));host.append(panel);
})();
