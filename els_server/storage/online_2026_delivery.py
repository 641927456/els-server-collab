"""Opt-in character/week title-mail issuance within the caller's transaction.

Only the independently verified723809x1 reward exists here. No default mail
wording, deadline, activity code, scene policy or automatic trigger. A reviewed
policy must be registered explicitly; evidence labels are not self-verification.
Escrow is minted directly, so a full bag cannot consume or lose the weekly mail.
"""
import hashlib
import json
from els_server.storage.online_2026_progress import OnlineTitleProgress, _integer, _text
from els_server.storage.game_mail import MailError, _text as mail_text

TITLE_LINK_SHA256 = '34b60391c162147cb22f1aecbdff53aa96fa9b97a603fbd858aea7991fa10b32'


class OnlineTitleDelivery:
    def __init__(self, progress, title_link_bytes):
        if not isinstance(progress, OnlineTitleProgress):
            raise TypeError('Original online progress repository required')
        if hashlib.sha256(title_link_bytes).hexdigest() != TITLE_LINK_SHA256:
            raise ValueError('Verified item/title linkage changed')
        self.progress, self.db = progress, progress.db

    def initialize(self):
        with self.progress._atomic():
            self.progress._definition()
            self.db.execute('''CREATE TABLE IF NOT EXISTS online2026_mail_policy(
                campaign TEXT PRIMARY KEY,payload_json TEXT NOT NULL,payload_sha256 TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS online2026_delivery(
                campaign TEXT NOT NULL,character INTEGER NOT NULL,week INTEGER NOT NULL,
                account INTEGER NOT NULL,policy_sha256 TEXT NOT NULL,
                mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),created_at INTEGER NOT NULL,
                PRIMARY KEY(campaign,character,week))''')

    def register_policy(self, *, sender, title, body, deadline, purpose, provenance):
        """Caller must verify actual wording/deadline before a non-test activation."""
        mail_text(sender,24);mail_text(title,80);mail_text(body,2000)
        _integer(deadline,1);_text(provenance)
        from els_server.domain.item_expiration import validate as validate_expiration
        validate_expiration(deadline)
        if deadline >= 2**31 or purpose not in ('explicit_local_test','cn_2026_historical'):
            raise ValueError('Unsupported explicit mail policy')
        data=dict(sender=sender,title=title,body=body,deadline=deadline,purpose=purpose,
                  provenance=provenance,title_link_sha256=TITLE_LINK_SHA256)
        raw=json.dumps(data,ensure_ascii=True,sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(raw.encode()).hexdigest()
        with self.progress._atomic():
            self.progress._definition()
            old=self.db.execute('SELECT payload_json,payload_sha256 FROM online2026_mail_policy WHERE campaign=?',
                                (self.progress.campaign,)).fetchone()
            if old is not None:
                if tuple(old)!=(raw,digest):raise ValueError('Registered mail policy is immutable')
            else:
                self.db.execute('INSERT INTO online2026_mail_policy VALUES (?,?,?)',(self.progress.campaign,raw,digest))
        return digest

    def issue(self, *, account, character, week, now):
        """One committed letter per character/week. Never re-mint on later retry.

        No client-chosen reward fields. All issuance, escrow UID allocation,
        scope binding and receipt insertion share a savepoint and the outer tx.
        Caller must BEGIN IMMEDIATE before observing eligibility and issuing.
        """
        _integer(now,1)
        with self.progress._atomic():
            level=self.progress._owner(account,character)
            lo,hi=self.progress._period(week)
            policy=self.db.execute('SELECT payload_json,payload_sha256 FROM online2026_mail_policy WHERE campaign=?',
                                   (self.progress.campaign,)).fetchone()
            if policy is None or hashlib.sha256(policy[0].encode()).hexdigest()!=policy[1]:
                raise ValueError('Missing or changed reviewed mail policy')
            data=json.loads(policy[0])
            purpose=self.db.execute('SELECT purpose FROM online2026_periods WHERE campaign=? AND week=?',
                                    (self.progress.campaign,week)).fetchone()[0]
            if data['purpose']!=purpose or data['title_link_sha256']!=TITLE_LINK_SHA256:
                raise ValueError('Mail policy and period evidence mismatch')
            old=self.db.execute('''SELECT account,policy_sha256,mail_id FROM online2026_delivery
                WHERE campaign=? AND character=? AND week=?''',(self.progress.campaign,character,week)).fetchone()
            if old is not None:
                if tuple(old)[:2]!=(account,policy[1]):raise ValueError('Delivery receipt identity mismatch')
                from els_server.storage.online_title_mail_scope import recipient
                if recipient(self.db,old[2])!=character or not self.db.execute(
                        'SELECT 1 FROM game_mail WHERE id=? AND account_id=?',(old[2],account)).fetchone():
                    raise ValueError('Delivery receipt lost its original letter; no reissue')
                return dict(status='already_issued',mail_id=old[2],replayed=True)
            if level<10 or not lo<=now<hi or now>=data['deadline']:
                return dict(status='ineligible',mail_id=None,replayed=False)
            if not self.progress.snapshot(account=account,character=character,week=week)['condition_met']:
                return dict(status='not_ready',mail_id=None,replayed=False)
            from els_server.storage.item_instances import next_uid
            from els_server.storage.mail_attachments import put
            from els_server.storage.online_title_mail_scope import bind
            from els_server.storage.inventory_state import validate_plan
            validate_plan([dict(template=723809,metadata=0,group=4,quantity=1,expires_at=data['deadline'])])
            identity=json.dumps([self.progress.campaign,account,character,week],separators=(',',':'))
            campaign='online2026-title-'+hashlib.sha256(identity.encode()).hexdigest()
            cur=self.db.execute('''INSERT INTO game_mail
                (campaign,account_id,sender,title,body,ed,created_at,expires_at) VALUES (?,?,?,?,?,0,?,?)''',
                (campaign,account,data['sender'],data['title'],data['body'],now,data['deadline']))
            mail_id=cur.lastrowid
            item=dict(uid=next_uid(self.db),template=723809,metadata=0,group=4,slot=0,count=1,expires_at=data['deadline'])
            put(self.db,mail_id,item,item)
            bind(self.db,mail_id=mail_id,account=account,character=character,deadline=data['deadline'])
            self.db.execute('INSERT INTO online2026_delivery VALUES (?,?,?,?,?,?,?)',
                (self.progress.campaign,character,week,account,policy[1],mail_id,now))
            return dict(status='issued',mail_id=mail_id,replayed=False)
