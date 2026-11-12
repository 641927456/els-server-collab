"""Persistent admission switches for implemented events; active runs finish normally."""
import json
import os
from pathlib import Path
import time

EVENTS={41550:'愚人节活动副本',41580:'校园祭活动副本',41620:'甜品咖啡厅活动副本',40046:'德拉巴基战场'}
ABYSS_WEAPON = 580
EVENTS[ABYSS_WEAPON] = '深渊武器成长助力'
SCOPE = {ABYSS_WEAPON: '控制新报名。已参加角色可继续完成任务和领取奖励。'}
_path=None
_state=dict(revision=0,events={str(k):dict(enabled=True,start=None,end=None) for k in EVENTS})


def validate(value):
    if not isinstance(value,dict) or set(value)!={'revision','events'} or type(value['revision']) is not int or value['revision']<0:
        raise ValueError('活动配置版本无效')
    if not isinstance(value['events'],dict) or set(value['events'])!={str(k) for k in EVENTS}:raise ValueError('只能配置已实现的活动')
    for rule in value['events'].values():
        if not isinstance(rule,dict) or set(rule)!={'enabled','start','end'} or type(rule['enabled']) is not bool:raise ValueError('活动开关无效')
        for field in ('start','end'):
            if rule[field] is not None and (type(rule[field]) is not int or not 0<=rule[field]<=4102444800):raise ValueError('活动时间无效')
        if rule['start'] is not None and rule['end'] is not None and rule['start']>=rule['end']:raise ValueError('结束时间必须晚于开始时间')
    return json.loads(json.dumps(value))


def configure(path):
    global _path,_state
    _path=Path(path)
    if _path.exists():
        value = json.loads(_path.read_text('utf8'))
        # Existing four-entry settings retain their revision and admission windows.
        if (isinstance(value, dict) and isinstance(value.get('events'), dict)
                and set(value['events']) == {str(k) for k in EVENTS if k != ABYSS_WEAPON}):
            value['events'][str(ABYSS_WEAPON)] = dict(enabled=True,start=None,end=None)
    else:
        value = dict(revision=0,events={str(k):dict(enabled=True,start=None,end=None) for k in EVENTS})
    _state = validate(value)


def is_open(identity,now=None):
    if identity not in EVENTS:return True
    rule=_state['events'][str(identity)];now=time.time() if now is None else now
    return rule['enabled'] and (rule['start'] is None or now>=rule['start']) and (rule['end'] is None or now<rule['end'])


def require_open(identity, now=None):
    if not is_open(identity, now):raise ValueError('活动当前未开放')


def snapshot():
    state=validate(_state)
    return dict(state,rows=[dict(id=k,name=v,**state['events'][str(k)],open=is_open(k),
        scope=SCOPE.get(k,'仅控制新入场，原等级、门票、任务和组队条件仍需满足')) for k,v in EVENTS.items()])


def live_calendar():
    from els_server.domain.anniversary_promotion import STARTS, ENDS, MAIL_DEADLINE
    from els_server.domain import hot_time
    from els_server.domain.resonance import experience_multiplier

    now = time.time()
    return [
        dict(name='15周年庆典', open=STARTS <= now < ENDS, start=STARTS, end=ENDS,
             scope='沿用正式排期，已发邮件领取截止时间单独计算。', mail_deadline=MAIL_DEADLINE),
        dict(name='常驻热力时刻', open=True, start=None, end=None,
             scope='普通经验 ×{} · 共鸣经验 ×{} · 掉落 ×{} · {}'.format(
                 hot_time.ordinary_multiplier(), experience_multiplier(), hot_time.drop_multiplier(),
                 '普通疲劳不限' if hot_time.unlimited_fatigue() else '普通疲劳按原规则')),
    ]


def update(events,expected):
    global _state
    if type(expected) is not int or expected!=_state['revision']:raise ValueError('活动配置已更新，请刷新后提交')
    value=validate(dict(revision=expected+1,events=events))
    if _path is None:raise ValueError('未启用 GM 活动配置')
    _path.parent.mkdir(parents=True,exist_ok=True);tmp=_path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    tmp.replace(_path);_state=value
    return snapshot()
