"""Ordinary character mail, exact-once debit/escrow and durable ED returns.

Current runtime scope: text/ED and qualified ordinary item attachments.
Unverified sealed transfers remain rejected before charging or moving assets.
Ordinary retention (30 days), inbox bound (100) and retained returned ED are
explicit server policies, not claims about retail server configuration.
"""
from contextlib import closing
import hashlib,json,sqlite3,time
from els_server.storage.game_mail import MailError,_active_owner,_text
from els_server.storage.characters import validate_name
from els_server.domain.player_mail_rules import fee

ORDINARY_RETENTION=30*86400
RETURN_RETENTION=365*86400
INBOX_LIMIT=100


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS player_mail_meta (
        mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),
        recipient_uid INTEGER NOT NULL, sender_account INTEGER NOT NULL,
        sender_uid INTEGER NOT NULL CHECK(sender_uid>=1001),
        return_of INTEGER UNIQUE, returned_to INTEGER,
        CHECK(recipient_uid>=1001 OR (recipient_uid=0 AND return_of IS NOT NULL)))''')
    db.execute('''CREATE TABLE IF NOT EXISTS player_mail_receipts (
        operation TEXT PRIMARY KEY, account_id INTEGER NOT NULL,
        sender_uid INTEGER NOT NULL, digest TEXT NOT NULL,
        mail_id INTEGER NOT NULL, recipient TEXT NOT NULL,
        fee INTEGER NOT NULL, created_at INTEGER NOT NULL)''')
    from els_server.storage.mail_attachments import ensure as ensure_items
    ensure_items(db)


def visible_sql(db=None):
    from els_server.storage.black_market_mail import exists as market_exists
    if db is not None and market_exists(db):
        from els_server.storage.online_title_mail_scope import exists as title_exists
        extra=' UNION ALL SELECT recipient_uid FROM online2026_mail_scope WHERE mail_id=game_mail.id'if title_exists(db)else''
        return "NOT EXISTS (SELECT 1 FROM (SELECT recipient_uid FROM player_mail_meta WHERE mail_id=game_mail.id UNION ALL SELECT recipient_uid FROM black_market_mail WHERE mail_id=game_mail.id"+extra+") p WHERE p.recipient_uid NOT IN (0,?))"
    # One bound UID argument; administrative account mail has no meta row.
    from els_server.storage.online_title_mail_scope import exists
    if db is not None and exists(db):
        return '''NOT EXISTS (SELECT 1 FROM (
            SELECT recipient_uid FROM player_mail_meta WHERE mail_id=game_mail.id
            UNION ALL SELECT recipient_uid FROM online2026_mail_scope WHERE mail_id=game_mail.id
            ) p WHERE p.recipient_uid NOT IN (0,?))'''
    return '''NOT EXISTS (SELECT 1 FROM player_mail_meta p WHERE p.mail_id=game_mail.id
              AND p.recipient_uid NOT IN (0,?))'''


def require_recipient(db,mail_id,uid):
    row=db.execute('SELECT recipient_uid FROM player_mail_meta WHERE mail_id=?',(mail_id,)).fetchone()
    if row is not None and row[0] not in (0,uid):raise MailError('Letter belongs to another character')
    from els_server.storage.online_title_mail_scope import recipient
    target=recipient(db,mail_id)
    if target is not None and target!=uid:raise MailError('Event letter belongs to another character')
    from els_server.storage.black_market_mail import meta as market_meta
    market=market_meta(db,mail_id)
    if market is not None and market[0]!=uid:raise MailError('Market letter belongs to another character')


def decorate(db,row,*,now=None):
    meta=db.execute('SELECT recipient_uid FROM player_mail_meta WHERE mail_id=?',(row['id'],)).fetchone()
    from els_server.storage.online_title_mail_scope import recipient
    target=recipient(db,row['id'])
    if target is not None:
        # Retail LT_EVENT_CHARACTER (71) requires its original RewardID table.
        # The selected local event uses native LT_MESSAGE (5) direct-item mail;
        # retain the existing folder0 route and original server recipient guard.
        # This is explicit local compatibility, not the retail mail type.
        row['mail_type']=5  # LT_MESSAGE: native direct item, local delivery compatibility
        if meta is None:meta=(target,)
    if row.get('campaign','').startswith('attendance2026-'):
        row['mail_type']=5  # Account ownership remains enforced by game_mail.
    if meta and meta[0]:
        name=db.execute('SELECT name FROM characters WHERE uid=?',(meta[0],)).fetchone()
        if name:row['recipient']=name[0]
    from els_server.storage.black_market_mail import meta as market_meta
    market=market_meta(db,row['id'])
    if market is not None:
        row['mail_type']=market[1]
        name=db.execute('SELECT name FROM characters WHERE uid=?',(market[0],)).fetchone()
        if name:row['recipient']=name[0]
    from els_server.storage.mail_attachments import pending
    item=pending(db,row['id'],now=int(time.time()) if now is None else now)
    if item is not None:row['item']=item
    return row


def _short(text,units):
    return text.encode('utf-16le')[:units*2].decode('utf-16le',errors='ignore')


def expire_due(db,now,*,mail_ids=None):
    """One transaction moves unclaimed ED to at most one return letter.

    Returned ED remains in escrow until claimed; an overdue return renews its
    display deadline instead of being destroyed or bounced indefinitely.
    """
    if not db.in_transaction:raise MailError('Mail expiry requires transaction')
    from els_server.storage import mail_attachments as attachments
    attachments.retire_expired(db,now)
    restriction='';args=[now]
    if mail_ids is not None:
        from els_server.storage.game_mail import _ids
        _ids(mail_ids)
        restriction=' AND g.id IN ('+','.join('?' for _ in mail_ids)+')'
        args.extend(mail_ids)
    rows=db.execute('''SELECT g.id,g.account_id,g.sender,g.title,g.body,g.ed,g.claimed_at,
        p.recipient_uid,p.sender_account,p.sender_uid,p.return_of
        FROM game_mail g JOIN player_mail_meta p ON p.mail_id=g.id
        WHERE g.deleted_at IS NULL AND g.expires_at<=? AND p.returned_to IS NULL'''
        +restriction+' ORDER BY g.id LIMIT 100',args).fetchall()
    from els_server.storage.online_title_mail_scope import retire_due
    changed=retire_due(db,now,mail_ids=mail_ids)
    for row in rows:
        mid,recipient_account,sender,title,body,ed,claimed,recipient_uid,sender_account,sender_uid,return_of=row
        item=attachments.pending(db,mid,now=now)
        if return_of is not None and claimed is None and (ed or item):
            db.execute('UPDATE game_mail SET expires_at=? WHERE id=?',(now+RETURN_RETENTION,mid));changed+=1;continue
        if return_of is None and claimed is None and (ed or item):
            owner=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(sender_uid,)).fetchone()
            target_uid=sender_uid if owner and owner[0]==sender_account else 0
            cur=db.execute('''INSERT INTO game_mail
                (campaign,account_id,sender,title,body,ed,created_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?)''',('player-return-'+str(mid),sender_account,'\u90ae\u653f\u7cfb\u7edf',
                _short('\u9000\u56de\uff1a'+title,80),_short('\u539f\u90ae\u4ef6\u5230\u671f\uff0c\u9644\u4ef6\u5df2\u9000\u56de\u3002\n'+body,2000),ed,now,now+RETURN_RETENTION))
            returned=cur.lastrowid
            db.execute('INSERT INTO player_mail_meta VALUES (?,?,?,?,?,NULL)',
                       (returned,target_uid,recipient_account,recipient_uid or sender_uid,mid))
            db.execute('UPDATE player_mail_meta SET returned_to=? WHERE mail_id=?',(returned,mid))
            attachments.move_return(db,mid,returned,now=now)
        db.execute('UPDATE game_mail SET deleted_at=? WHERE id=?',(now,mid));changed+=1
    return changed


def maintenance(path,*,now=None):
    now=int(time.time()) if now is None else now
    with closing(sqlite3.connect(path,timeout=.1)) as db,db:
        due=db.execute('''SELECT 1 FROM game_mail g JOIN player_mail_meta p ON p.mail_id=g.id
            WHERE g.deleted_at IS NULL AND g.expires_at<=? AND p.returned_to IS NULL LIMIT 1''',(now,)).fetchone()
        item_due=db.execute('''SELECT 1 FROM player_mail_items WHERE claimed_at IS NULL AND moved_to IS NULL
            AND expired_at IS NULL AND expires_at<? LIMIT 1''',(now,)).fetchone()
        from els_server.storage.online_title_mail_scope import has_due
        if not due and not item_due and not has_due(db,now):return 0
        db.execute('BEGIN IMMEDIATE');return expire_due(db,now)


def send(path,account,uid,request,operation,encode,*,now=None):
    expected={'recipient','title','body','ed','item','count','flag','extra'}
    if not isinstance(request,dict) or set(request)!=expected:raise MailError('Invalid send fields')
    if (type(request['ed']) is not int or not 0<=request['ed']<=70_000_000_000
            or any(type(request[k]) is not int or request[k]!=0 for k in ['flag','extra'])):
        raise MailError('Ordinary client cannot select privileged or guild mail')
    if (type(request['item']) is not int or not 0<=request['item']<2**63
            or type(request['count']) is not int or not 0<=request['count']<=99
            or bool(request['item'])!=bool(request['count']) or request['item'] and request['ed']):
        raise MailError('Invalid attachment or mixed item/ED mail')
    name=validate_name(request['recipient']);title=_text(request['title'],80)
    body='' if request['body']=='' else _text(request['body'],2000)
    if not isinstance(operation,str) or not 1<=len(operation)<=160:raise MailError('Invalid send operation')
    canonical=json.dumps(dict(recipient=name,title=title,body=body,ed=request['ed'],item=request['item'],count=request['count']),ensure_ascii=True,sort_keys=True)
    digest=hashlib.sha256(canonical.encode()).hexdigest();now=int(time.time()) if now is None else now
    if type(now) is not int or not 1<=now<2**31:raise MailError('Invalid send timestamp')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');_active_owner(db,account,uid)
        from els_server.storage import mail_attachments as attachments
        old=db.execute('''SELECT account_id,sender_uid,digest,mail_id,recipient,fee
            FROM player_mail_receipts WHERE operation=?''',(operation,)).fetchone()
        balance=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone()
        if balance is None:raise MailError('Missing sender ED balance')
        if old:
            if old[:3]!=(account,uid,digest):raise MailError('Send retry conflicts with original request')
            return encode(dict(ed=balance[0],recipient=old[4],mail_id=old[3],fee=old[5],replayed=True,
                               changes=attachments.sent_changes(db,uid,operation)))
        expire_due(db,now)
        target=db.execute('''SELECT c.uid,c.name,o.account_id FROM characters c
            JOIN character_owners o ON o.uid=c.uid WHERE c.name_key=?''',(name.casefold(),)).fetchone()
        if target is None or target[0]==uid:raise MailError('Unknown recipient or self mail')
        if db.execute('SELECT 1 FROM mail_blacklist WHERE owner=? AND target=?',(target[0],uid)).fetchone():
            raise MailError('Recipient blocks this sender')
        count=db.execute('''SELECT count(*) FROM game_mail WHERE account_id=? AND deleted_at IS NULL
            AND expires_at>? AND '''+visible_sql(db),(target[2],now,target[0])).fetchone()[0]
        if count>=INBOX_LIMIT:raise MailError('Recipient inbox is full')
        sender=db.execute('SELECT name FROM characters WHERE uid=?',(uid,)).fetchone()[0]
        source=item=None;positions=[];price=0
        if request['item']:
            source,item,price,positions=attachments.take(db,uid,request['item'],request['count'],now=now)
        cost=fee(request['ed'],price=price,quantity=request['count']);debit=request['ed']+cost
        if balance[0]<debit or balance[1]>=2**63-1:raise MailError('Insufficient ED for attachment and postage')
        after=balance[0]-debit
        if db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=? AND revision=?',
                      (after,uid,balance[1])).rowcount!=1:raise MailError('Sender balance changed')
        campaign='player-'+hashlib.sha256(operation.encode()).hexdigest()
        cur=db.execute('''INSERT INTO game_mail
            (campaign,account_id,sender,title,body,ed,created_at,expires_at)
            VALUES (?,?,?,?,?,?,?,?)''',(campaign,target[2],sender,title,body,request['ed'],now,now+ORDINARY_RETENTION))
        mid=cur.lastrowid
        db.execute('INSERT INTO player_mail_meta VALUES (?,?,?,?,NULL,NULL)',(mid,target[0],account,uid))
        if item is not None:
            attachments.put(db,mid,source,item)
            db.execute('INSERT INTO player_mail_send_items VALUES (?,?)',(operation,json.dumps(positions)))
        db.execute('INSERT INTO player_mail_receipts VALUES (?,?,?,?,?,?,?,?)',
                   (operation,account,uid,digest,mid,target[1],cost,now))
        return encode(dict(ed=after,recipient=target[1],mail_id=mid,fee=cost,replayed=False,
                           changes=attachments.changes(db,uid,positions)))
