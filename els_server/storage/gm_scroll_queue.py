"""GM scroll use: consume one owned +N scroll and set one equipment level.

The current client sends no use packet for these scroll templates, so the local
GM performs the same business step on the owned instances and pushes a full
inventory sync to the online character.
"""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path


def directory(state_file):
    return Path(state_file).resolve().parent/'gm-scroll-queue'


def _pending(state_file):
    return directory(state_file)/'pending'


def _receipts(state_file):
    return directory(state_file)/'receipts'


def _failed(state_file):
    return directory(state_file)/'failed'


def enqueue(state_file, job):
    required = {'operation_id', 'uid', 'item_uid', 'scroll', 'reason'}
    if not isinstance(job, dict) or set(job) != required:
        raise ValueError('卷轴任务字段不完整')
    operation = job['operation_id']
    if (not isinstance(operation, str) or len(operation) != 36
            or any(c not in '0123456789abcdef-' for c in operation)):
        raise ValueError('无效操作编号')
    if type(job['uid']) is not int or job['uid'] < 1001:
        raise ValueError('角色编号无效')
    if type(job['item_uid']) is not int or job['item_uid'] < 1:
        raise ValueError('装备实例编号无效')
    if type(job['scroll']) is not int or job['scroll'] < 1:
        raise ValueError('卷轴编号无效')
    if not isinstance(job['reason'], str) or not 2 <= len(job['reason'].strip()) <= 200:
        raise ValueError('请输入 2–200 字的操作原因')
    folder = _pending(state_file)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/(operation+'.json')
    if target.exists() or (_receipts(state_file)/(operation+'.json')).exists():
        return dict(operation_id=operation, state='queued')
    temporary = folder/(operation+'.tmp')
    with temporary.open('w', encoding='utf8') as stream:
        stream.write(json.dumps(job, ensure_ascii=False, sort_keys=True))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    return dict(operation_id=operation, state='queued')


def status(state_file):
    result = {}
    for key, folder, limit in (('queued', _pending(state_file), 50),
                               ('done', _receipts(state_file), 50),
                               ('failed', _failed(state_file), 20)):
        rows = []
        if folder.is_dir():
            for path in sorted(folder.glob('*.json'), reverse=True)[:limit]:
                try:
                    rows.append(json.loads(path.read_text('utf8')))
                except (OSError, ValueError):
                    continue
        result[key] = rows
    return result


def process(app, state_file, now=None):
    folder = _pending(state_file)
    if not folder.is_dir():
        return 0
    processed = 0
    for path in sorted(folder.glob('*.json')):
        job = {}
        try:
            job = json.loads(path.read_text('utf8'))
            receipt = deliver(app, state_file, job, now=now)
        except sqlite3.OperationalError:
            continue
        except Exception as error:
            context = {key: job.get(key) for key in ('uid', 'item_uid', 'scroll', 'reason')} \
                if isinstance(job, dict) else {}
            _record(path, _failed(state_file), dict(context, error=str(error),
                                                    operation_id=path.stem, time=int(time.time())))
            continue
        _record(path, _receipts(state_file), dict(receipt, operation_id=path.stem,
                                                  time=int(time.time())))
        processed += 1
    return processed


def deliver(app, state_file, job, now=None):
    required = {'operation_id', 'uid', 'item_uid', 'scroll', 'reason'}
    if not isinstance(job, dict) or set(job) != required:
        raise ValueError('卷轴任务字段不完整')
    from els_server.domain.enhancement_scroll import level as scroll_level, scroll
    from els_server.domain.equipment_enhancement import validate
    from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS, VERIFIED_TEMPLATES
    from els_server.storage import equipment_enhancement
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import remove
    from els_server.storage.profession_state import require_owner
    uid, item_uid, scroll_template = job['uid'], job['item_uid'], job['scroll']
    if not scroll(scroll_template):
        raise ValueError('该道具不是已注册的强化卷轴')
    target_level = scroll_level(scroll_template)
    with closing(sqlite3.connect(state_file, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        owner = db.execute('SELECT account_id FROM character_owners WHERE uid=?', (uid,)).fetchone()
        if owner is None:
            raise ValueError('角色不存在')
        require_owner(db, uid, owner[0])
        items = load_items(db, uid)
        target = next((i for i in items if i['uid'] == item_uid), None)
        if target is None or target.get('count') != 1:
            raise ValueError('目标装备不存在或数量不为 1')
        source = next((i for i in items if i['template'] == scroll_template and i.get('count', 0) >= 1), None)
        if source is None:
            raise ValueError('背包中没有对应的强化卷轴')
        if (source['group'], source['metadata']) != (TEMPLATE_BAG_GROUPS[scroll_template],
                                                     VERIFIED_TEMPLATES[scroll_template]):
            raise ValueError('强化卷轴实例格式不符')
        previous = target.get('enhancement', 0)
        if previous >= target_level:
            raise ValueError('装备强化已不低于 +'+str(target_level))
        validate(target['template'], target_level)
        equipment_enhancement.replace(db, uid, item_uid, previous, target_level)
        if source['count'] > 1:
            if db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',
                          (source['uid'], uid, source['count'])).rowcount != 1:
                raise ValueError('强化卷轴堆叠已变化')
        else:
            remove(db, uid, source)
        db.commit()
    receipt = dict(uid=uid, item_uid=item_uid, template=target['template'],
                   scroll=scroll_template, level=target_level, before=previous)
    receipt['notified'] = notify_online(app, uid)
    return receipt


def notify_online(app, uid):
    if app is None:
        return False
    session = next((s for s in app.playing.values()
                    if not getattr(s, 'released', False) and getattr(s, 'role', None) == 'game'
                    and getattr(getattr(s, 'account', None), 'uid', None) == uid), None)
    if session is None:
        return False
    from els_server.gm_runtime import prepare_mailbox
    session.mailbox = prepare_mailbox(session, [session.saved_user_sync()])
    return True


def _record(source, folder, payload):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/source.name
    temporary = folder/(source.name+'.tmp')
    with temporary.open('w', encoding='utf8') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    source.unlink()
