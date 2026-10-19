"""Account-owned GM mail and exactly-once ED attachment claims.

Administration is a local server operation, never a client-selected privilege.
All writes, including response encoding, are inside one SQLite transaction.
"""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import time


class MailError(ValueError):
    def __init__(self,message,code=1):
        super().__init__(message)
        self.code=code


def ensure(db):
    from els_server.storage.mailbox_extras import ensure as ensure_extras
    ensure_extras(db)
    db.execute('''CREATE TABLE IF NOT EXISTS gm_mail_campaigns (
        campaign TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL,
        recipients_json TEXT NOT NULL, created_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS game_mail (
        id INTEGER PRIMARY KEY AUTOINCREMENT, campaign TEXT NOT NULL,
        account_id INTEGER NOT NULL CHECK(account_id>=1),
        sender TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
        ed INTEGER NOT NULL CHECK(ed BETWEEN 0 AND 70000000000),
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        read_at INTEGER, claimed_at INTEGER, claimed_uid INTEGER,
        deleted_at INTEGER, UNIQUE(campaign,account_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS game_mail_claims (
        mail_id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL,
        uid INTEGER NOT NULL, ed INTEGER NOT NULL, claimed_at INTEGER NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS game_mail_owner ON game_mail(account_id,deleted_at,id)')
    from els_server.storage.player_mail import ensure as ensure_player_mail
    ensure_player_mail(db)


def initialize(path):
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        ensure(db)


def _text(value,limit):
    if (not isinstance(value,str) or not value or len(value.encode('utf-16le'))>limit*2
            or any(ord(c)<32 and c not in '\n\t' for c in value)):
        raise MailError('Invalid mail text')
    return value


def gm_campaign(path,campaign,recipients,*,ed,title,body,sender='GM',now=None):
    """Local management API. No network handler calls this method.

    Freeze the reviewed account IDs before calling; never discover or create
    players here. Accounts without characters keep the same pending mail.
    """
    if not isinstance(campaign,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,95}',campaign):
        raise MailError('Invalid campaign')
    if (not isinstance(recipients,list) or not recipients or len(recipients)>10000
            or any(type(a) is not int or not 2<=a<2**31 for a in recipients)
            or len(set(recipients))!=len(recipients)):
        raise MailError('Invalid reviewed recipients')
    if type(ed) is not int or not 1<=ed<=70_000_000_000:
        raise MailError('Invalid ED grant')
    title=_text(title,80);body=_text(body,2000);sender=_text(sender,24)
    recipients=sorted(recipients)
    now=int(time.time()) if now is None else now
    if type(now) is not int or not 1<=now<2**31:
        raise MailError('Invalid mail timestamp')
    plan=json.dumps(dict(ed=ed,title=title,body=body,sender=sender),ensure_ascii=True,sort_keys=True)
    digest=hashlib.sha256(plan.encode()).hexdigest()
    ids=json.dumps(recipients,separators=(',',':'))
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');ensure(db)
        old=db.execute('SELECT payload_sha256,recipients_json FROM gm_mail_campaigns WHERE campaign=?',(campaign,)).fetchone()
        if old is not None:
            if old!=(digest,ids):raise MailError('Campaign retry conflicts with original grant')
            replay=True
        else:
            db.execute('INSERT INTO gm_mail_campaigns VALUES (?,?,?,?)',(campaign,digest,ids,now))
            for account in recipients:
                db.execute('''INSERT INTO game_mail
                    (campaign,account_id,sender,title,body,ed,created_at,expires_at)
                    VALUES (?,?,?,?,?,?,?,?)''',(campaign,account,sender,title,body,ed,now,now+365*86400))
            replay=False
        rows=db.execute('SELECT id,account_id FROM game_mail WHERE campaign=? ORDER BY account_id',(campaign,)).fetchall()
        if len(rows)!=len(recipients):raise MailError('Campaign receipt is incomplete')
        return dict(campaign=campaign,replayed=replay,ed_per_account=ed,
                    mails=[dict(id=i,account_id=a) for i,a in rows])


def _owner(db,account,uid):
    if type(account) is not int or type(uid) is not int or account<1 or uid<1001:
        raise MailError('Invalid authenticated owner')
    row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
    if row is None or row[0]!=account:
        raise MailError('Mail character ownership mismatch')


def _row(db,account,mail_id,uid,*,now=None):
    if type(mail_id) is not int or not 1<=mail_id<2**63:
        raise MailError('Invalid mail ID')
    row=db.execute('SELECT * FROM game_mail WHERE id=? AND account_id=? AND deleted_at IS NULL',
                   (mail_id,account)).fetchone()
    if row is None:raise MailError('Mail not found')
    from els_server.storage.player_mail import require_recipient,decorate
    require_recipient(db,mail_id,uid)
    return decorate(db,dict(row),now=now)


def inbox(path,account,uid,*,page=1,now=None):
    if type(page) is not int or not 1<=page<=100000:raise MailError('Invalid mail page')
    now=int(time.time()) if now is None else now
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN');_owner(db,account,uid)
        from els_server.storage.player_mail import visible_sql,decorate
        count=db.execute('SELECT count(*) FROM game_mail WHERE account_id=? AND deleted_at IS NULL AND expires_at>? AND '+visible_sql(),(account,now,uid)).fetchone()[0]
        rows=db.execute('''SELECT * FROM game_mail WHERE account_id=? AND deleted_at IS NULL
            AND expires_at>? AND '''+visible_sql()+''' ORDER BY id DESC LIMIT 10 OFFSET ?''',(account,now,uid,(page-1)*10)).fetchall()
        return count,[decorate(db,dict(r),now=now) for r in rows]


def read(path,account,uid,mail_id,encode,*,now=None):
    now=int(time.time()) if now is None else now
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE');_owner(db,account,uid)
        row=_row(db,account,mail_id,uid,now=now)
        if row['expires_at']<=now:raise MailError('Mail expired',2985)
        if row['read_at'] is None:
            db.execute('UPDATE game_mail SET read_at=? WHERE id=?',(now,mail_id));row['read_at']=now
        return encode(row)


def _ids(ids):
    if (not isinstance(ids,list) or not 1<=len(ids)<=10 or len(set(ids))!=len(ids)
            or any(type(i) is not int or not 1<=i<2**63 for i in ids)):
        raise MailError('Invalid mail selection')


def claim(path,account,uid,ids,encode,*,now=None,include_items=False,include_claim_counts=False):
    """Any owned character can claim; one campaign/account grant across all roles.

    A retry always returns the current absolute ED, never the old balance.
    Client attachment inventory/maps are ignored; the DB is authoritative.
    """
    _ids(ids);now=int(time.time()) if now is None else now
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');_owner(db,account,uid)
        rows=[_row(db,account,i,uid,now=now) for i in ids]
        if any(r['expires_at']<=now for r in rows):raise MailError('Mail expired',2985)
        balance=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone()
        if balance is None:raise MailError('Missing character ED balance')
        pending=[r for r in rows if r['claimed_at'] is None]
        amount=sum(r['ed'] for r in pending)
        after=balance['ed']+amount
        from els_server.storage import mail_attachments as attachments
        if not include_items and any(r.get('item') for r in rows):
            raise MailError('Attachment-aware response encoder required')
        changes={r['id']:attachments.claim(db,uid,r['id'],now=now) for r in rows}
        if amount:
            from els_server.domain.bank_rules import player_ed_limit
            level=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()[0]
            if after>player_ed_limit(level) or balance['revision']>=2**63-1:
                raise MailError('Character ED carrying limit',2970)
            db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=?',(after,uid))
        for row in pending:
            db.execute('INSERT INTO game_mail_claims VALUES (?,?,?,?,?)',(row['id'],account,uid,row['ed'],now))
            db.execute('UPDATE game_mail SET claimed_at=?,claimed_uid=?,read_at=COALESCE(read_at,?) WHERE id=?',
                       (now,uid,now,row['id']))
        if include_claim_counts:
            if not include_items:raise MailError('Item-aware claim counts require item-aware encoder')
            awarded={r['id']:{r['item']['template']:r['item']['count']}
                     for r in pending if r.get('item') is not None}
            return encode(ids,after,changes,awarded)
        return encode(ids,after,changes) if include_items else encode(ids,after)


def delete(path,account,uid,ids,encode,*,now=None):
    _ids(ids);now=int(time.time()) if now is None else now
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE');_owner(db,account,uid)
        rows=[]
        for mail_id in ids:
            # Deletion retries are successful only for the same authenticated owner.
            row=db.execute('SELECT * FROM game_mail WHERE id=? AND account_id=?',(mail_id,account)).fetchone()
            if row is None:raise MailError('Mail not found')
            from els_server.storage.player_mail import require_recipient
            require_recipient(db,mail_id,uid)
            rows.append(row)
        # Expired player attachments must enter the return escrow before a
        # delete can hide the source. Target these IDs, independently of the
        # bounded background maintenance backlog. A pending return itself is
        # retained even after its display deadline.
        from els_server.storage.mail_attachments import pending
        has_assets=lambda r:r['ed'] or pending(db,r['id'],now=now)
        if any(has_assets(r) and r['claimed_at'] is None and db.execute(
                'SELECT 1 FROM player_mail_meta WHERE mail_id=? AND return_of IS NOT NULL',
                (r['id'],)).fetchone() for r in rows):
            raise MailError('Claim ED attachment before deleting returned mail',2969)
        from els_server.storage.player_mail import expire_due
        expire_due(db,now,mail_ids=ids)
        rows=[db.execute('SELECT * FROM game_mail WHERE id=?',(i,)).fetchone() for i in ids]
        if any(has_assets(r) and r['claimed_at'] is None and r['expires_at']>now for r in rows):
            raise MailError('Claim ED attachment before deleting mail',2969)
        for row in rows:
            db.execute('UPDATE game_mail SET deleted_at=COALESCE(deleted_at,?) WHERE id=?',(now,row['id']))
        return encode(ids)
