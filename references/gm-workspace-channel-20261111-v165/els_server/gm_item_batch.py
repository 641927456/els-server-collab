"""Server-selected, atomic item grants with a single durable batch receipt."""
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import time
import uuid

from els_server.gm_runtime import canonical, operation, prepare_mailbox, publish_mailboxes
from els_server.storage.sqlite_timing import write_transaction

MODES = ('online', 'characters', 'accounts')
FIELDS = {'mode', 'template', 'quantity'}
APPLY_FIELDS = FIELDS | {'operation_id', 'reason', 'expected_audience', 'confirm'}
ITEM_FIELDS = {'mode', 'items'}
ITEM_APPLY_FIELDS = ITEM_FIELDS | (APPLY_FIELDS - FIELDS)
MAX_LINES = 24


def _plans(value):
    from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
    from els_server.domain.reward_rules import item_plan
    from els_server.storage.gm_item_mail import plan_for_mail
    from els_server.storage.inventory_state import validate_plan

    mode = value['mode']
    legacy = 'items' not in value
    rows = [dict(template=value['template'], quantity=value['quantity'])] if legacy else value['items']
    if mode not in MODES or not isinstance(rows, list) or not 1 <= len(rows) <= MAX_LINES:
        raise ValueError('请选择发放范围并添加 1–24 种道具')
    plans = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'template', 'quantity'}:
            raise ValueError('道具清单字段无效')
        template, quantity = row['template'], row['quantity']
        if type(template) is not int or type(quantity) is not int or not 1 <= quantity <= 99 or template in seen:
            raise ValueError('请为每种道具填写 1–99 的数量，每种道具只能出现一次')
        seen.add(template)
        plans.append(item_plan(template, quantity))
    if mode == 'online':
        return validate_plan(plans)
    if legacy:
        return [plan_for_mail(plans[0])]
    attachments = []
    for plan in validate_plan(plans):
        stack = TEMPLATE_MAX_STACKS[plan['template']]
        for start in range(0, plan['quantity'], stack):
            attachments.append(dict(plan, quantity=min(stack, plan['quantity'] - start)))
    if len(attachments) > MAX_LINES:
        raise ValueError('每位接收者最多 24 封附件邮件，请减少种类或数量')
    return attachments


def _accounts(config):
    if config.mode == 'local':
        return {1}
    with closing(sqlite3.connect(config.accounts_file.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        return {row[0] for row in db.execute('SELECT id FROM accounts WHERE id>=2 AND enabled=1')}


def _audience(runtime, db, mode):
    if mode == 'online':
        targets = sorted(
            (session.account.uid, session.shop_session_id)
            for session in runtime.app.playing.values()
            if session.role == 'game' and not session.released
            and runtime.app.registry.enabled(session.identity['id'])
        )
        return targets
    enabled = _accounts(runtime.app.config)
    if mode == 'accounts':
        return [(account, None, '') for account in sorted(enabled)]
    from els_server.storage.character_lifecycle import states

    lifecycle = states(db)
    roles = db.execute('''SELECT o.account_id,c.uid,c.name FROM character_owners o
        JOIN characters c ON c.uid=o.uid ORDER BY o.account_id,c.uid''')
    return [(account, uid, name) for account, uid, name in roles
            if account in enabled and not lifecycle.get(uid, {}).get('requested_at')
            and not lifecycle.get(uid, {}).get('finalized_at')]


def _preview(value, targets, plans):
    if not targets:
        raise ValueError('当前范围没有可接收的玩家')
    contents = [value['items']] if 'items' in value else [value['template'], value['quantity']]
    fingerprint = hashlib.sha256(canonical([value['mode'], *contents, targets]).encode()).hexdigest()
    return dict(recipients=len(targets), expected_audience=fingerprint,
                mails_per_recipient=0 if value['mode'] == 'online' else len(plans))


def preview(runtime, value):
    if set(value) not in (FIELDS, ITEM_FIELDS):
        raise ValueError('全服发放预览字段无效')
    plans = _plans(value)
    with closing(sqlite3.connect(runtime.app.config.state_file.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        db.execute('BEGIN')
        return _preview(value, _audience(runtime, db, value['mode']), plans)


def _receipt(db, key):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gm_item_receipts'").fetchone():
        return None
    row = db.execute('SELECT digest,receipt FROM gm_item_receipts WHERE operation_id=?', (key,)).fetchone()
    return (row[0], json.loads(row[1])) if row else None


def inspect(runtime, value):
    key = value.get('operation_id')
    if set(value) != {'operation_id'} or not isinstance(key, str) or str(uuid.UUID(key)) != key:
        raise ValueError('操作编号无效')
    with closing(sqlite3.connect(runtime.app.config.state_file.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        old = _receipt(db, key)
    receipt = old[1] if old and old[1].get('mode') in MODES else None
    return dict(committed=receipt is not None, receipt=receipt)


def apply(runtime, value):
    from els_server.domain.dungeon_drops import pickup_inventory_notice
    from els_server.domain.local_session import SessionOrderError
    from els_server.storage.gm_item_mail import issue
    from els_server.storage.inventory_state import InventoryFull, grant_items

    if set(value) not in (APPLY_FIELDS, ITEM_APPLY_FIELDS):
        raise ValueError('全服发放字段无效')
    if value['confirm'] != '全服发放':
        raise ValueError('请输入确认文字：全服发放')
    key = operation(value)
    expected = value['expected_audience']
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('请先预览接收范围')
    digest = hashlib.sha256(canonical(value).encode()).hexdigest()
    boxes = []
    with closing(sqlite3.connect(runtime.app.config.state_file, timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            old = _receipt(db, key)
            if old:
                if old[0] != digest or 'mode' not in old[1]:
                    raise ValueError('同一操作编号不能用于不同发货内容')
                return dict(old[1], replayed=True)
            plans = _plans(value)
            mode = value['mode']
            targets = _audience(runtime, db, mode)
            checked = _preview(value, targets, plans)
            if checked['expected_audience'] != expected:
                raise ValueError('接收范围已变化，请重新预览')
            now = int(time.time())
            if mode == 'online':
                for uid, session_id in targets:
                    session = runtime.session(dict(uid=uid, session=session_id))
                    try:
                        changes = grant_items(db, plans, uid)
                    except InventoryFull as error:
                        raise ValueError(f'角色 #{uid} 背包空间不足，本批未发放') from error
                    try:
                        box = prepare_mailbox(session, [pickup_inventory_notice(changes)])
                    except SessionOrderError as error:
                        raise ValueError(f'角色 #{uid} 的连接暂时无法接收通知，本批未发放') from error
                    boxes.append((session, box))
            else:
                for index, plan in enumerate(plans, 1):
                    campaign = f'gm-items-{key}' if 'items' not in value else f'gm-items-{key}-{index}'
                    issue(db, campaign, targets, plan, now)
            receipt = dict(operation_id=key, mode=mode, recipients=len(targets),
                           mails_per_recipient=checked['mails_per_recipient'],
                           delivery='committed-and-queued' if mode == 'online' else 'game-mail',
                           time=now, replayed=False)
            if 'items' in value:
                receipt['items'] = value['items']
            else:
                receipt.update(template=value['template'], quantity=value['quantity'])
            db.execute('CREATE TABLE IF NOT EXISTS gm_item_receipts (operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, receipt TEXT NOT NULL)')
            db.execute('INSERT INTO gm_item_receipts VALUES (?,?,?)', (key, digest, canonical(receipt)))
    publish_mailboxes(boxes)
    return receipt
