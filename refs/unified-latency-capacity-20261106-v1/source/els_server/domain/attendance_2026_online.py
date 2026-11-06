"""Connection-observed monotonic time, never dungeon time or client durations.

Eligibility is a required trusted server policy. The campaign's complete scene
policy still needs confirmation; construction is explicit and defaults off.
"""
from els_server.performance import sqlite_observed,clock_stage
import math
import sqlite3
import logging
import time
import uuid
from contextlib import closing
from els_server.storage.attendance_2026_progress import AttendanceProgress


class AttendanceOnlineClock:
    def __init__(self, definition, *, campaign, definition_sha256, schedule,
                 eligibility, monotonic=time.monotonic, epoch=time.time):
        self.definition,self.campaign,self.digest=definition,campaign,definition_sha256
        self.schedule,self.eligibility=schedule,eligibility
        self.monotonic,self.epoch=monotonic,epoch
        self.identity=None;self.base=None;self.anchor=None;self.committed=0
        self.last_monotonic=None;self.token=uuid.uuid4().hex;self.closed=False
        self._deferred=None;self._attempt=None

    def observe(self, session, *, stop=False):
        if self.closed:return
        self._attempt=None
        try:return self._observe(session,stop=stop)
        except sqlite3.OperationalError as error:
            code=getattr(error,'sqlite_errorcode',None)
            if stop or type(code) is not int or code & 255 not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):raise
            # Keep the original anchor/cursor. The next observation retries
            # committed interval unions, never inventing or duplicating time.
            sqlite_observed(busy=True)
            if self._attempt is not None:self._deferred=self._attempt
            logging.getLogger(__name__).debug('Attendance online persistence deferred: SQLite code=%s',code)
        finally:
            if stop:
                self.closed=True;self.identity=None

    def _observe(self, session, *, stop):
        mono,wall=self.monotonic(),self.epoch()
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (mono,wall)):
            raise ValueError('Invalid server clock')
        if self.last_monotonic is not None and mono<self.last_monotonic:
            raise ValueError('Monotonic clock moved backwards')
        self.last_monotonic=mono
        # Finish the interval belonging to the previously observed role before
        # switching identities. No process-persistent anchor can count downtime.
        with clock_stage('attendance_eligibility'):
            current=self.eligibility(session)
        if self.identity is not None:
            elapsed=mono-self.base
            if current==self.identity and abs(wall-(self.anchor+elapsed))<=2:
                end=self.anchor+int(elapsed)
                start=self.anchor+self.committed
                path,account,character,level=self.identity
                if start<end and(stop or self._deferred!=(self.identity,end)):
                    # A busy observation of this exact whole-second span is
                    # retried when its end advances, not again after the same
                    # packet. The next span still includes the pending gap.
                    self._attempt=(self.identity,end)
                    from els_server.domain.online_clock_transaction import current_commit
                    shared=current_commit()
                    if shared is not None:
                        from functools import partial
                        with clock_stage('attendance_persist'):
                            shared.persist(self,path,partial(self._write_spans,account=account,character=character,level=level,start=start,end=end,atomic=True))
                    else:
                        with clock_stage('attendance_connect'):
                            connection=sqlite3.connect(path,timeout=10 if stop else 0)
                        with clock_stage('attendance_persist'),closing(connection)as db:
                            self._write_spans(db,account,character,level,start,end,atomic=False)
                    self.committed=int(elapsed)
                    self._deferred=None
            else:
                # Wall-clock jumps may change campaign/day attribution. Preserve
                # committed observations, drop the uncertain gap and re-anchor.
                self.identity=None
        current=None if stop else current
        if current!=self.identity or self.identity is None:
            self.identity=current
            self.base=mono;self.anchor=int(wall);self.committed=0
            self._deferred=None

    def _write_spans(self,db,account,character,level,start,end,*,atomic):
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(character,)).fetchone()!=(account,):
            raise ValueError('Online role ownership changed')
        if db.execute('SELECT definition_sha256 FROM activity518_campaigns WHERE campaign=?',(self.campaign,)).fetchone()!=(self.digest,):
            raise ValueError('Online campaign definition changed')
        p=AttendanceProgress(db,self.definition,campaign_id=self.campaign,definition_sha256=self.digest)
        record=p.record_online_atomic if atomic else p.record_online
        for period,a,b in self.schedule.split(start,end):
            record(account=str(account),character=str(character),level=level,
                operation=f'online:{self.token}:{start}:{end}:{period}',period=period,starts=a,ends=b)


def selected_local_test_character(session):
    """Explicit test policy for implemented world phases, not full CN scene proof."""
    if (session.role!='game' or session.client_build!='dx11_260923'
            or session.phase not in ('map_loading','square_accepted','town_ready','dungeon_loading','dungeon_active')
            or getattr(session,'released',False) or session.account.characters is None):
        return None
    account=session.account
    if hasattr(session,'application'):
        app=session.application
        if (not app.registry.enabled(session.identity['id'])
                or session.identity['id']!=account.account_id
                or app.playing.get(account.account_id) is not session):
            return None
    # Read current owned eligibility fields without unrelated wire projections.
    identity=getattr(account,'character_identity',account.character)
    character=identity()
    if character is None or character['uid']!=account.uid or character['level']<10:return None
    return (str(account.store.path),account.account_id,account.uid,character['level'])
