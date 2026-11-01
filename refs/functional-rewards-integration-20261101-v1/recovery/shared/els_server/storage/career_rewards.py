"""Advancement rewards in character-owned system mail, in the career transaction."""
import time
from els_server.domain.character_rules import CLASSES


def recipient(db,mail_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='career_reward_mail'").fetchone():return None
    row=db.execute('SELECT owner FROM career_reward_mail WHERE mail_id=?',(mail_id,)).fetchone()
    return row[0] if row else None


def issue(db,before,after):
    # Quest completion already grants these boxes from its original reward
    # vector. Only item/shop advancement calls this producer. Transcendence,
    # Master Class and same-stage route changes have no new promotion outfit.
    stage=CLASSES[after['unit_class']]['stage']
    if stage!=CLASSES[before['unit_class']]['stage']+1:return []
    raise ValueError('Functional recovery pauses new career reward mail')
    if not db.in_transaction:raise ValueError('Career reward requires career transaction')
    owner=after['uid']
    from els_server.storage.game_mail import ensure,_owner
    ensure(db)
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()[0]
    _owner(db,account,owner)
    db.execute('''CREATE TABLE IF NOT EXISTS career_reward_mail (
        mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),
        owner INTEGER NOT NULL REFERENCES characters(uid))''')
    templates=[{1:109999,2:110850,3:135867}[stage]]
    if stage==3:templates.append(135869)
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item,item_body
    from els_server.game_data import client_data
    from els_server.storage.item_instances import next_uid
    from els_server.storage.mail_attachments import put
    from els_server.storage.player_mail import RETURN_RETENTION,decorate
    from els_server.protocol.mail_attachment_messages import header,detail
    now=int(time.time());mails=[]
    for template in templates:
        name=client_data().item(template)['name']
        campaign=f'career-reward-{owner}-{after["revision"]}-{template}'
        mid=db.execute('''INSERT INTO game_mail
            (campaign,account_id,sender,title,body,ed,created_at,expires_at)
            VALUES (?,?,?,?,?,0,?,?)''',(campaign,account,'阿莉尔',name,
                f'恭喜完成{stage}转！请领取转职奖励。',now,now+RETURN_RETENTION)).lastrowid
        item=validate_item(dict(uid=next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],
            group=TEMPLATE_BAG_GROUPS[template],slot=0,count=1))
        item_body(item);put(db,mid,item,item)
        db.execute('INSERT INTO career_reward_mail VALUES (?,?)',(mid,owner))
        cur=db.execute('SELECT * FROM game_mail WHERE id=?',(mid,))
        row=dict(zip((c[0] for c in cur.description),cur.fetchone()))
        row=decorate(db,row,now=now)
        header(row);detail(row)
        mails.append(mid)
    return mails
