"""Persistent admission switches for implemented events; active runs finish normally."""
import json
import os
from pathlib import Path
import time

EVENTS={41550:'愚人节活动副本',41580:'校园祭活动副本',41620:'甜品咖啡厅活动副本',40046:'德拉巴基战场'}
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
    _state=validate(json.loads(_path.read_text('utf8'))) if _path.exists() else validate(dict(revision=0,events={str(k):dict(enabled=True,start=None,end=None) for k in EVENTS}))


def is_open(identity,now=None):
    if identity not in EVENTS:return True
    rule=_state['events'][str(identity)];now=time.time() if now is None else now
    return rule['enabled'] and (rule['start'] is None or now>=rule['start']) and (rule['end'] is None or now<rule['end'])


def require_open(identity):
    if not is_open(identity):raise ValueError('活动当前未开放')


def snapshot():
    state=validate(_state)
    return dict(state,rows=[dict(id=k,name=v,**state['events'][str(k)],open=is_open(k),
        scope='仅控制新入场；原等级、门票、任务和组队条件仍需满足') for k,v in EVENTS.items()])


def update(events,expected):
    global _state
    if type(expected) is not int or expected!=_state['revision']:raise ValueError('活动配置已更新，请刷新后提交')
    value=validate(dict(revision=expected+1,events=events))
    if _path is None:raise ValueError('未启用 GM 活动配置')
    _path.parent.mkdir(parents=True,exist_ok=True);tmp=_path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    tmp.replace(_path);_state=value
    return snapshot()
