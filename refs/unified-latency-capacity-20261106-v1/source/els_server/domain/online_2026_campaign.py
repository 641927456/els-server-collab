"""Explicit local integration of observed30min -> selected character mail.

Rules/item/scope come from the pinned CN2026 selection and title linkage.
Internal Access identifiers, no-extra-flags, hide-after-mail and sweep cadence
are named LOCAL policies, not claims of captured retail server configuration.
No client claim request or replacement of the global Access tree is added.
"""
from contextlib import closing
from dataclasses import replace
from els_server.performance import sqlite_observed
import hashlib,math,sqlite3,logging
from els_server.domain.online_2026_clock import OnlineTitleClock
from els_server.domain.online_2026_display import OnlineTitleDisplay
from els_server.domain.online_2026_mail_notice import OnlineMailNotice,MailNoticePolicy
from els_server.protocol.access_event_2026 import ActivityRecord
from els_server.storage.online_2026_progress import OnlineTitleProgress
from els_server.storage.online_2026_delivery import OnlineTitleDelivery,TITLE_LINK_SHA256

LOCAL_POLICY='local-coexistence2026-observed-mail-and-access-v1'


def local_access_record():
    """An explicit local ID namespace, not a recovered retail key/code pair."""
    return ActivityRecord(-20261007,20261007,'2026共存的庆典-称号发放',30.,
        '累计在线30分钟','奖励通过角色邮件发放',0,((723809,1,0),),7,0.,0.,0,0,0,False,(0,0))


class OnlineTitleCampaign:
    def __init__(self,clock,*,title_link,record,enabled,mail_identity,mail_policy,local_policy):
        if not isinstance(clock,OnlineTitleClock) or not callable(enabled) or not callable(mail_identity):
            raise TypeError('Explicit trusted clock/eligibility policies required')
        if local_policy!=LOCAL_POLICY or record!=local_access_record() or type(mail_policy) is not MailNoticePolicy:
            raise ValueError('Named local Access/mail policy required')
        if type(title_link) is not bytes or hashlib.sha256(title_link).hexdigest()!=TITLE_LINK_SHA256:
            raise ValueError('Pinned selected title linkage required')
        record.encode()
        self.clock,self.link,self.record=clock,title_link,record
        self.enabled,self.mail_identity,self.mail_policy=enabled,mail_identity,mail_policy
        original=clock.eligibility
        clock.eligibility=lambda s:original(s) if self._enabled(s) else None
        self.display=OnlineTitleDisplay();self.mail=OnlineMailNotice()
        self._context=None;self._next_scan=0.;self._force=True

    def _enabled(self,s):
        value=self.enabled(s)
        if type(value) is not bool:raise ValueError('Trusted boolean availability required')
        return value

    def observe(self,s,*,stop=False):
        self.clock.observe(s,stop=stop)

    def outgoing(self,events):
        if any(e.event_id==0x201 and e.kind in (0x1ce,0x1d3,0x1d5,0x1d7) for e in events):
            self.mail.reset();self._force=True

    def notifications(self,s):
        # This method composes notices locally; none is sent before return.
        # A later read may fail after an earlier mail receipt committed. Restore
        # only connection projection caches so the next scan emits that durable
        # result again. Reward receipts and player state are never rolled back.
        display=tuple(getattr(self.display,k) for k in ('_record','_context','_shape','_anchor'))
        accepted=self.mail._accepted
        scan=(self._context,self._next_scan,self._force)
        try:return self._notifications(s)
        except sqlite3.OperationalError as error:
            code=getattr(error,'sqlite_errorcode',None)
            if type(code) is not int or code & 255 not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):raise
            for key,value in zip(('_record','_context','_shape','_anchor'),display):setattr(self.display,key,value)
            self.mail._accepted=accepted
            self._context,self._next_scan,self._force=scan
            sqlite_observed(busy=True)
            logging.getLogger(__name__).debug('Online title notification deferred: SQLite code=%s',code)
            return []

    def _notifications(self,s):
        if self.clock.closed:return []
        identity=self.mail_identity(s)
        context=(identity,self.clock.identity,self._enabled(s))
        mono,wall=self.clock.monotonic(),self.clock.epoch()
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<2**63 for v in (mono,wall)):
            raise ValueError('Invalid online notification clock')
        if context==self._context and not self._force and mono<self._next_scan:return []
        messages=[]
        if identity is None:
            self.display.clear(messages.append);self.mail.reset()
        else:
            path,account,character,level=identity;now=math.floor(wall)
            # Mail visibility is independent of the activity being enabled.
            # Existing ordinary/account mail is included in the same snapshot.
            selected=self.clock.identity if self._enabled(s) else None
            if selected is None:
                self.display.clear(messages.append)
            else:
                if selected!=identity:raise ValueError('Online display/mail role identity mismatch')
                def read_delivery(db,*,issue):
                    repo=OnlineTitleProgress(db,self.clock.selection_bytes,campaign=self.clock.campaign)
                    repo._definition();repo._owner(account,character)
                    periods=db.execute('SELECT week FROM online2026_periods WHERE campaign=? AND starts<=? AND ends>?',
                        (self.clock.campaign,now,now)).fetchall()
                    if len(periods)>1:raise ValueError('Overlapping online periods')
                    week=periods[0][0] if periods else None
                    outcome=None;view=None
                    if week is not None:
                        delivery=OnlineTitleDelivery(repo,self.link)
                        if issue:outcome=delivery.issue(account=account,character=character,week=week,now=now)
                        else:outcome,_,_,view=delivery.read_preview(account=account,character=character,week=week,now=now)
                    return repo,week,outcome,view
                def display(repo,week,outcome,view):
                    if outcome is None or outcome['status'] in ('issued','already_issued','ineligible'):
                        # Explicit local policy: once its mail commits, remove
                        # only this owned row. Never action0/global replacement.
                        self.display.clear(messages.append)
                    elif view is None:
                        # The actual writer can return not_ready after its fresh
                        # recheck. It has committed and supplies no read view.
                        self.display.synchronize(repo,account=account,character=character,week=week,now=now,
                            record=self.record,emit=messages.append)
                    else:
                        self.display.synchronize_view(repo,view,account=account,character=character,week=week,now=now,
                            record=self.record,emit=messages.append)
                # Non-ready/already-issued notifications are read projections.
                # Only a positive preview enters the original durable issuer;
                # it repeats period/policy/owner/receipt checks under its writer.
                with snapshot_connection(path,timeout=0)as db:
                    db.execute('BEGIN')
                    repo,week,outcome,view=read_delivery(db,issue=False)
                    needs_issue=week is not None and outcome is None
                    if not needs_issue:display(repo,week,outcome,view)
                    db.rollback()
                if needs_issue:
                    with closing(sqlite3.connect(path,timeout=0))as db:
                        with write_transaction(db):repo,week,outcome,view=read_delivery(db,issue=True)
                        display(repo,week,outcome,view)
            self.mail.synchronize(path,account=account,character=character,now=now,policy=self.mail_policy,emit=messages.append)
        self._context=context;self._next_scan=mono+1.;self._force=False
        return messages

from els_server.storage.read_scope import snapshot_connection
from els_server.storage.sqlite_timing import write_transaction
