"""Offline level raises; caller must hold the GM gate and serialized worker."""
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import time

from els_server.gm_runtime import canonical, operation


def validate(value):
    operation(value)
    if set(value) != {'operation_id','reason','account_id','uid','level','expected_version'}:
        raise ValueError('调级请求字段无效')
    for key, low, high in (('account_id',2,2**53-1),('uid',1001,2**53-1),('level',1,99)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError('账号、角色或目标等级无效（等级为 1–99）')
    if not isinstance(value['expected_version'],str) or not re.fullmatch('[0-9a-f]{64}',value['expected_version']):
        raise ValueError('请刷新角色资料后再调整等级')


def version(character, balance):
    return hashlib.sha256(canonical([list(character),list(balance)]).encode()).hexdigest()


def state(db, uid):
    c = db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
    b = db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone()
    if c is None or b is None:
        raise ValueError('角色或经验存档不存在')
    return c, b


def inspect(db, value, offline_guard):
    offline_guard(value['account_id'])
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(value['uid'],)).fetchone() != (value['account_id'],):
        raise ValueError('角色不属于所选账号')
    c, b = state(db,value['uid'])
    if version(c,b) != value['expected_version']:
        raise ValueError('角色数据已变化，请刷新后重新提交')
    target = value['level']
    if target <= c[4]:
        raise ValueError('仅支持提升等级，目标必须高于当前等级；降级会影响现有职业和技能')
    from els_server.game_data import client_data
    xp = client_data().thresholds[target-1]
    if xp <= b[1]:
        raise ValueError('当前经验与等级不一致，请先核查存档')
    return c, b, xp


def preview(path, value, offline_guard):
    validate(value)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('BEGIN')
        # Committed operations may be retried after the expected version changes.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gm_level_receipts'").fetchone():
            old = db.execute('SELECT digest,receipt FROM gm_level_receipts WHERE operation_id=?',(value['operation_id'],)).fetchone()
            if old:
                if old[0] != hashlib.sha256(canonical(value).encode()).hexdigest():
                    raise ValueError('同一操作编号不能用于不同调级内容')
                return dict(json.loads(old[1]),replayed=True)
        c, b, xp = inspect(db,value,offline_guard)
        return dict(uid=c[0],name=c[1],before_level=c[4],level=value['level'],experience=xp)


def set_level(path, value, offline_guard):
    validate(value)
    from els_server.game_data import client_data
    from els_server.domain.career_labels import labels
    digest = hashlib.sha256(canonical(value).encode()).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        # Check a receipt before the guard/version so retries remain read-only,
        # including retries after the player logs in again.
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gm_level_receipts'").fetchone()
        if exists:
            old = db.execute('SELECT digest,receipt FROM gm_level_receipts WHERE operation_id=?',(value['operation_id'],)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('同一操作编号不能用于不同调级内容')
                return dict(json.loads(old[1]),replayed=True)
        c, b, xp = inspect(db,value,offline_guard)
        target = value['level']
        receipt = dict(operation_id=value['operation_id'],account_id=value['account_id'],uid=c[0],name=c[1],
                       before_level=c[4],level=target,before_experience=b[1],experience=xp,
                       reason=value['reason'],time=time.time(),replayed=False,delivery='next-login',
                       **labels(c[2],c[3]))
        db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=?',(target,c[0]))
        db.execute('UPDATE reward_balances SET experience=?,revision=revision+1 WHERE uid=?',(xp,c[0]))
        offline_guard(value['account_id'])
        db.execute('CREATE TABLE IF NOT EXISTS gm_level_receipts (operation_id TEXT PRIMARY KEY,digest TEXT NOT NULL,receipt TEXT NOT NULL)')
        db.execute('INSERT INTO gm_level_receipts VALUES (?,?,?)',(value['operation_id'],digest,canonical(receipt)))
        return receipt
