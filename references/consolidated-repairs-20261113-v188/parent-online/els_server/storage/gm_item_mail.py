"""GM item grants through the existing native system mailbox and escrow."""
from els_server.storage.game_mail import MailError


def recipient(db, mail_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gm_item_mail_recipients'").fetchone():
        return None
    row = db.execute('SELECT uid FROM gm_item_mail_recipients WHERE mail_id=?', (mail_id,)).fetchone()
    return row[0] if row else None


def plan_for_mail(plan):
    from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
    from els_server.storage.inventory_state import validate_plan

    plan, = validate_plan([plan])
    if plan['quantity'] > TEMPLATE_MAX_STACKS[plan['template']]:
        raise MailError('邮件每封只能附一组，请减少每人发放数量')
    return plan


def issue(db, campaign, targets, plan, now):
    from els_server.domain.equipment_chip_rules import TEMPLATE as CHIP, generate
    from els_server.protocol.mail_attachment_messages import detail, header
    from els_server.storage.game_mail import ensure
    from els_server.storage.item_instances import next_uid
    from els_server.storage.mail_attachments import put
    from els_server.storage.player_mail import RETURN_RETENTION

    ensure(db)
    if targets[0][1] is not None:
        db.execute('''CREATE TABLE IF NOT EXISTS gm_item_mail_recipients (
            mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),
            uid INTEGER NOT NULL REFERENCES characters(uid))''')
    sender, title = 'GM', '全服道具发放'
    body = f"请领取全服发放的道具 #{plan['template']} × {plan['quantity']}。"
    expires = now + RETURN_RETENTION
    for account, uid, name in targets:
        mid = db.execute('''INSERT INTO game_mail
            (campaign,account_id,sender,title,body,ed,created_at,expires_at)
            VALUES (?,?,?,?,?,0,?,?)''',
            (f'{campaign}-{uid or 0}', account, sender, title, body, now, expires)).lastrowid
        if uid is not None:
            db.execute('INSERT INTO gm_item_mail_recipients VALUES (?,?)', (mid, uid))
        item = dict(uid=next_uid(db), template=plan['template'], metadata=plan['metadata'],
                    group=plan['group'], slot=0, count=plan['quantity'])
        if 'expires_at' in plan:
            item['expires_at'] = plan['expires_at']
        if item['template'] == CHIP:
            item['option_groups'] = {'1': generate()}
        put(db, mid, item, item)
        row = dict(id=mid, sender=sender, title=title, body=body, ed=0, item=item, mail_type=5,
                   recipient=name, created_at=now, expires_at=expires, read_at=None, claimed_at=None)
        header(row)
        detail(row)
