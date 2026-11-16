"""Ordinary clear Force overflow, in the original reward transaction."""
import json,time


def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ordinary_force_reward_mail'").fetchone())


def recipient(db,mail_id):
    if not exists(db):return None
    row=db.execute('SELECT owner FROM ordinary_force_reward_mail WHERE mail_id=?',(mail_id,)).fetchone()
    return row[0] if row else None


def is_clear_source(source):
    return (source.kind=='ordinary' and
            json.loads(source._source).get('reward_source')=='local-full-native-clear-current-display-pool')


def defer(db,owner,source,item):
    # Called by grant_items after its exact full-plan factory binding and
    # instance construction. The attachment preserves that instance and seal.
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source)
    from els_server.domain.force_drop_balance import managed
    if source._db is not db or source.owner!=owner or not is_clear_source(source) or not managed(item['template']):
        raise ValueError('Force overflow requires the original ordinary clear writer')
    source.validate_template(item['template'])
    from els_server.storage.game_mail import ensure
    ensure(db)
    db.execute('''CREATE TABLE IF NOT EXISTS ordinary_force_reward_mail (
        mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),owner INTEGER NOT NULL,
        operation TEXT NOT NULL REFERENCES raid_reward_sources(operation_id))''')
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()[0]
    from els_server.storage.player_mail import RETURN_RETENTION
    now=int(time.time())
    cur=db.execute('''INSERT INTO game_mail
        (campaign,account_id,sender,title,body,ed,created_at,expires_at)
        VALUES(?,?,?,?,?,0,?,?)''',
        (f'ordinary-force-{source.operation}-{item["uid"]}',account,'副本奖励',
         '背包已满：原力奖励','本次通关获得的原力奖励因背包空间不足寄送，请整理背包后领取。',
         now,now+RETURN_RETENTION))
    mail=cur.lastrowid
    db.execute('INSERT INTO ordinary_force_reward_mail VALUES(?,?,?)',(mail,owner,source.operation))
    from els_server.storage.mail_attachments import put
    put(db,mail,item,item)
    from els_server.storage.player_mail import decorate
    from els_server.protocol.mail_attachment_messages import header,detail
    cur=db.execute('SELECT * FROM game_mail WHERE id=?',(mail,))
    row=dict(zip((c[0] for c in cur.description),cur.fetchone()))
    row=decorate(db,row,now=now);header(row);detail(row)


def notifications(db,owner,operation):
    if not exists(db) or not db.execute('SELECT 1 FROM ordinary_force_reward_mail WHERE owner=? AND operation=?',(owner,operation)).fetchone():
        return []
    from els_server.storage.online_2026_mail_snapshot import snapshot
    from els_server.protocol.mail_notifications_2026 import notice
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()[0]
    state=snapshot(db,account=account,character=owner,now=int(time.time()))
    return [notice(unread_counts=state['unread_counts'],rows=[],flag=False)]
