"""Explicit GM overrides for implemented local drops and ordinary enhancement.

No change to official source tables. One immutable snapshot is used per call;
the single Application worker owns edits. Defaults preserve existing behavior.
"""
import hashlib
import json
import os
from pathlib import Path

_path = None
_state = dict(revision=0, drops=dict(ordinary=None, boss=None, chest=None,ed=None), enhancement=[None]*13,experience_bp=10000)


def validate(value):
    if isinstance(value,dict) and set(value)=={'revision','drops','enhancement'} and isinstance(value['drops'],dict) and set(value['drops'])=={'ordinary','boss','chest'}:
        value=dict(value,drops=dict(value['drops'],ed=None),experience_bp=10000)
    if not isinstance(value, dict) or set(value) != {'revision', 'drops', 'enhancement','experience_bp'}:
        raise ValueError('概率配置字段不完整')
    if type(value['revision']) is not int or value['revision'] < 0:
        raise ValueError('概率版本无效')
    if not isinstance(value['drops'], dict) or set(value['drops']) != {'ordinary', 'boss', 'chest','ed'}:
        raise ValueError('掉落分类无效')
    if not isinstance(value['enhancement'], list) or len(value['enhancement']) != 13:
        raise ValueError('需要 +0 至 +12 的十三档成功率')
    if type(value['experience_bp']) is not int or not 0<=value['experience_bp']<=1000000:
        raise ValueError('经验倍率需要在 0–100 倍内')
    for n in [*value['drops'].values(), *value['enhancement']]:
        if n is not None and (type(n) is not int or not 0 <= n <= 10000):
            raise ValueError('概率需要在 0–10000 基点内；100 基点 = 1%')
    return json.loads(json.dumps(value))


def configure(path):
    global _path, _state
    _path = Path(path)
    _state = validate(json.loads(_path.read_text(encoding='utf8'))) if _path.exists() else validate(
        dict(revision=0, drops=dict(ordinary=None, boss=None, chest=None,ed=None), enhancement=[None]*13,experience_bp=10000))


def snapshot():
    return validate(_state)


def update(value, expected):
    global _state
    if type(expected) is not int or expected != _state['revision']:
        raise ValueError('概率配置已更新，请刷新后重新提交')
    candidate = validate(dict(value, revision=expected+1))
    if _path is None:
        raise ValueError('未启用 GM 概率配置')
    _path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf8') as stream:
        json.dump(candidate, stream, ensure_ascii=False, indent=2)
        stream.flush();os.fsync(stream.fileno())
    temporary.replace(_path)
    _state = candidate
    return snapshot()


def chance(category, numerator, denominator):
    override = _state['drops'][category]
    return (numerator, denominator) if override is None else (override, 10000)


def allow_drop(run, dungeon, stage, key, boss=False):
    numerator, denominator = chance('ed', 1, 1)
    draw = int.from_bytes(hashlib.sha256(f'{run}:{dungeon}:{stage}:{key}:gm-drop'.encode()).digest(), 'big')
    return draw % denominator < numerator


def clear_experience(session,base):
    """Pin at first settlement attempt, so a retry cannot reroll its grant."""
    if type(base) is not int or not 0<=base<=2**31-1:raise ValueError('经验基础值无效')
    run=session.reward_run_id
    old=getattr(session,'_gm_experience',None)
    if old is not None and old[0]==run:
        if old[1]!=base:raise ValueError('同一副本经验基础值发生变化')
        return old[2]
    amount=min(2**31-1,base*_state['experience_bp']//10000)
    session._gm_experience=(run,base,amount)
    return amount


def enhancement_rates(level, original):
    success = _state['enhancement'][level]
    if success is None:
        return list(original)
    remaining = 10000-success
    old = sum(original[1:])
    if not old:
        return [success, remaining, *([0]*(len(original)-2))]
    failures = [n*remaining//old for n in original[1:]]
    failures[0] += remaining-sum(failures)
    return [success, *failures]
