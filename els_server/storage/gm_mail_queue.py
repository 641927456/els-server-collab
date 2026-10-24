"""Online GM item mail: queue files consumed by the running server.

A job creates one character-restricted letter with one item attachment, so the
player claims it in game without leaving the session. Jobs are idempotent by
operation id and never bypass inventory creation or option validation.
"""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path


def directory(state_file):
    return Path(state_file).resolve().parent/'gm-mail-queue'


def receipts(state_file):
    return directory(state_file)/'receipts'


def _pending(state_file):
    return directory(state_file)/'pending'


def _failed(state_file):
    return directory(state_file)/'failed'


def enqueue(state_file, job):
    required = {'operation_id', 'uid', 'template', 'quantity', 'option_groups',
                'title', 'body', 'reason', 'sender'}
    if not isinstance(job, dict) or set(job) != required:
        raise ValueError('邮件任务字段不完整')
    operation = job['operation_id']
    if (not isinstance(operation, str) or len(operation) != 36
            or any(c not in '0123456789abcdef-' for c in operation)):
        raise ValueError('无效操作编号')
    if type(job['uid']) is not int or job['uid'] < 1001:
        raise ValueError('收件角色编号无效')
    if type(job['template']) is not int or not 1 <= job['template'] < 2**31:
        raise ValueError('道具编号无效')
    if type(job['quantity']) is not int or not 1 <= job['quantity'] <= 99:
        raise ValueError('邮件数量为 1–99')
    if job['option_groups'] is not None and not isinstance(job['option_groups'], dict):
        raise ValueError('属性预设格式无效')
    for key in ('title', 'body', 'reason', 'sender'):
        if not isinstance(job[key], str) or not job[key]:
            raise ValueError('邮件文本不完整')
    folder = _pending(state_file)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/(operation+'.json')
    if target.exists():
        return dict(operation_id=operation, state='queued')
    done = receipts(state_file)/(operation+'.json')
    if done.exists():
        return dict(operation_id=operation, state='done', receipt=json.loads(done.read_text('utf8')))
    temporary = folder/(operation+'.tmp')
    with temporary.open('w', encoding='utf8') as stream:
        stream.write(json.dumps(job, ensure_ascii=False, sort_keys=True))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    return dict(operation_id=operation, state='queued')


def status(state_file):
    queued = []
    folder = _pending(state_file)
    if folder.is_dir():
        for path in sorted(folder.glob('*.json'), reverse=True)[:50]:
            try:
                queued.append(json.loads(path.read_text('utf8')))
            except (OSError, ValueError):
                continue
    done = []
    folder = receipts(state_file)
    if folder.is_dir():
        for path in sorted(folder.glob('*.json'), reverse=True)[:50]:
            try:
                done.append(json.loads(path.read_text('utf8')))
            except (OSError, ValueError):
                continue
    failed = []
    folder = _failed(state_file)
    if folder.is_dir():
        for path in sorted(folder.glob('*.json'), reverse=True)[:20]:
            try:
                failed.append(json.loads(path.read_text('utf8')))
            except (OSError, ValueError):
                continue
    return dict(queued=queued, done=done, failed=failed)


class RetryLater(Exception):
    """The running server cannot deliver this job yet; keep it queued."""


def process(state_file, now=None):
    folder = _pending(state_file)
    staged = directory(state_file)/'staged'
    if staged.is_dir():
        folder.mkdir(parents=True, exist_ok=True)
        for path in sorted(staged.glob('*.json')):
            os.replace(path, folder/path.name)
    if not folder.is_dir():
        return 0
    processed = 0
    for path in sorted(folder.glob('*.json')):
        job = {}
        try:
            job = json.loads(path.read_text('utf8'))
            receipt = deliver(state_file, job)
        except sqlite3.OperationalError:
            # A busy or locked database is transient: keep the job queued.
            continue
        except RetryLater:
            # A newer template registration may arrive with the next restart.
            continue
        except Exception as error:
            context = {key: job.get(key) for key in ('uid', 'template', 'quantity', 'title')} \
                if isinstance(job, dict) else {}
            _record(path, _failed(state_file), dict(context, error=str(error),
                                                    operation_id=path.stem, time=int(time.time())))
            continue
        payload = dict(receipt, operation_id=path.stem, time=int(time.time()))
        _record(path, receipts(state_file), payload)
        processed += 1
    return processed


def deliver(state_file, job, now=None):
    required = {'operation_id', 'uid', 'template', 'quantity', 'option_groups',
                'title', 'body', 'reason', 'sender'}
    if not isinstance(job, dict) or set(job) != required:
        raise ValueError('邮件任务字段不完整')
    from els_server.storage.game_mail import ensure, _text
    from els_server.domain.gm_item_options import apply
    from els_server.domain.gm_item_catalog import plan as gm_item_plan
    from els_server.storage import mail_attachments
    from els_server.storage.inventory_state import grant_items
    from els_server.storage.item_instances import remove
    uid, template, quantity = job['uid'], job['template'], job['quantity']
    title, body = _text(job['title'], 80), _text(job['body'], 2000)
    from els_server.domain.erp_potions_existing import TEMPLATES as erp_templates
    if template in erp_templates:
        raise ValueError('共鸣药水不能通过邮件发放，请在离线时直接发放')
    item_plan = gm_item_plan(template, quantity)
    groups = apply(template, job['option_groups'])
    now = int(time.time()) if now is None else now
    with closing(sqlite3.connect(state_file, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        ensure(db)
        owner = db.execute('SELECT account_id FROM character_owners WHERE uid=?', (uid,)).fetchone()
        if owner is None:
            raise ValueError('收件角色不存在')
        account = owner[0]
        campaign = 'gm-item-'+job['operation_id']
        old = db.execute('SELECT id FROM game_mail WHERE campaign LIKE ? AND account_id=? ORDER BY id',
                         (campaign+'%', account)).fetchall()
        if old:
            return dict(mail_ids=[row[0] for row in old], uid=uid, template=template, replayed=True)
        plan = [item_plan]
        awarded = grant_items(db, plan, uid)
        if not 1 <= len(awarded) <= 99:
            raise ValueError('单次邮件最多寄送 99 件')
        mail_ids = []
        for index, granted in enumerate(awarded):
            name = campaign+('-'+str(index) if index else '')
            cur = db.execute('''INSERT INTO game_mail
                (campaign,account_id,sender,title,body,ed,created_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?)''',
                (name, account, job['sender'], title, body, 0, now, now+30*86400))
            mail_id = cur.lastrowid
            db.execute('INSERT INTO player_mail_meta VALUES (?,?,?,?,NULL,NULL)',
                       (mail_id, uid, account, uid))
            item = dict(granted)
            if groups:
                from els_server.storage.equipment_options import replace
                replace(db, uid, item['uid'], item.get('option_groups', {}), groups)
                item['option_groups'] = groups
            remove(db, uid, item)
            mail_attachments.put(db, mail_id, item, item)
            mail_ids.append(mail_id)
        db.commit()
    return dict(mail_ids=mail_ids, uid=uid, template=template, quantity=len(awarded),
                replayed=False)


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
