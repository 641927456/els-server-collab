"""Character-scoped, source-bound guild rewards through the existing mailbox."""
import hashlib,json
from els_server.storage.guild_system_state import exists

def recipient(db,mail_id):
    if not exists(db,'native_guild_reward_mail_v2'):return None
    row=db.execute('SELECT owner FROM native_guild_reward_mail_v2 WHERE mail_id=?',(mail_id,)).fetchone()
    return None if row is None else row[0]

def farm_share(db,saved,harvester,plot,plant,operation,now):
    owner=plot['waterer']
    if owner not in saved['members']or plot['plant']!=plant['GUILD_PLANT_ID']or plot['matures']>now:
        raise ValueError('Guild farm mail reward source')
    from els_server.storage.game_mail import ensure
    ensure(db)
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_reward_mail_v2(
        operation TEXT PRIMARY KEY,mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),owner INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,source_json TEXT NOT NULL)''')
    key=operation+':water-share';source=dict(harvester=harvester,plot=plot,plant=plant['GUILD_PLANT_ID'],owner=owner)
    if db.execute('SELECT 1 FROM native_guild_reward_mail_v2 WHERE operation=?',(key,)).fetchone():raise ValueError('Farm reward already committed')
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
    if account is None:raise ValueError('Guild reward character owner')
    from els_server.storage.player_mail import ORDINARY_RETENTION
    mid=db.execute('INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at) VALUES(?,?,?,?,?,0,?,?)',
        ('guild-'+hashlib.sha256(key.encode()).hexdigest(),account[0],'美优','公会农场浇水奖励','你照料的作物已经收获，感谢你的帮助。',now,now+ORDINARY_RETENTION)).lastrowid
    db.execute('INSERT INTO native_guild_reward_mail_v2 VALUES(?,?,?,?,?)',(key,mid,owner,saved['id'],json.dumps(source,sort_keys=True)))
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item,item_body
    from els_server.storage.item_instances import next_uid
    from els_server.storage.mail_attachments import put
    template=plant['RESULT_ITEM_ID']
    item=validate_item(dict(uid=next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],slot=0,count=plant['DEFAULT_RESULT_AMOUNT']//10))
    item_body(item);put(db,mid,item,item)
    from els_server.storage.player_mail import decorate
    from els_server.protocol.mail_attachment_messages import header,detail
    result=db.execute('SELECT * FROM game_mail WHERE id=?',(mid,));row=dict(zip([c[0]for c in result.description],result.fetchone()))
    row=decorate(db,row,now=now);header(row);detail(row)
    return mid

def expedition(db,saved,week,stage,participant,now,reason):
    """Already-earned stage entitlement, exact character and seven-day mail."""
    from els_server.storage.game_mail import ensure
    from els_server.storage import guild_system_state as system
    ensure(db)
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_reward_mail_v2(
        operation TEXT PRIMARY KEY,mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),owner INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,source_json TEXT NOT NULL)''')
    clear=f"guild-expedition:{saved['id']}:{week}:{stage}:clear"
    row=db.execute('SELECT guild_id,kind,result FROM native_guild_operations_v2 WHERE operation=?',(clear,)).fetchone()
    if row is None or row[:2]!=(saved['id'],0xac1):raise ValueError('Guild expedition mail lost clear source')
    proof=json.loads(row[2]);owner=participant['uid'];original=proof['participants'].get(str(owner))
    if original is None or any(original[k]!=participant[k]for k in('uid','account','source','damage')):raise ValueError('Guild expedition mail participant differs from completed source')
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
    if account!=(participant['account'],):raise ValueError('Guild expedition mail owner')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item,item_body
    from els_server.storage.item_instances import next_uid
    from els_server.storage.mail_attachments import put
    from els_server.storage.player_mail import decorate
    from els_server.protocol.mail_attachment_messages import header,detail
    for raw_template,quantity in participant['rewards'].items():
        template=int(raw_template);key=clear+':'+str(owner)+':'+str(template)+':mail'
        if db.execute('SELECT 1 FROM native_guild_reward_mail_v2 WHERE operation=?',(key,)).fetchone():raise ValueError('Guild expedition mail already issued')
        source=dict(clear_operation=clear,week=week,stage=stage,owner=owner,template=template,quantity=quantity,reason=reason)
        mid=db.execute('INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at) VALUES(?,?,?,?,?,0,?,?)',
            ('guild-'+hashlib.sha256(key.encode()).hexdigest(),account[0],'美优','公会讨伐队奖励','这是你参加公会讨伐队获得的奖励，请及时领取。',now,now+7*86400)).lastrowid
        db.execute('INSERT INTO native_guild_reward_mail_v2 VALUES(?,?,?,?,?)',(key,mid,owner,saved['id'],json.dumps(source,sort_keys=True)))
        item=validate_item(dict(uid=next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],slot=0,count=quantity))
        item_body(item);put(db,mid,item,item)
        cursor=db.execute('SELECT * FROM game_mail WHERE id=?',(mid,));mail=dict(zip([c[0]for c in cursor.description],cursor.fetchone()))
        mail=decorate(db,mail,now=now);header(mail);detail(mail)
