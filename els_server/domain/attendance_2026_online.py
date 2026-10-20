"""Connection-observed monotonic time, never dungeon time or client durations.

Eligibility is a required trusted server policy. The campaign's complete scene
policy still needs confirmation; construction is explicit and defaults off.
"""
import math
import sqlite3
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

    def observe(self, session, *, stop=False):
        if self.closed:return
        try:return self._observe(session,stop=stop)
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
        current=self.eligibility(session)
        if self.identity is not None:
            elapsed=mono-self.base
            if current==self.identity and abs(wall-(self.anchor+elapsed))<=2:
                end=self.anchor+int(elapsed)
                start=self.anchor+self.committed
                path,account,character,level=self.identity
                if start<end:
                    with closing(sqlite3.connect(path,timeout=10)) as db:
                        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(character,)).fetchone()!=(account,):
                            raise ValueError('Online role ownership changed')
                        if db.execute('SELECT definition_sha256 FROM activity518_campaigns WHERE campaign=?',(self.campaign,)).fetchone()!=(self.digest,):
                            raise ValueError('Online campaign definition changed')
                        p=AttendanceProgress(db,self.definition,campaign_id=self.campaign,definition_sha256=self.digest)
                        for period,a,b in self.schedule.split(start,end):
                            # A failed later daily slice can be retried exactly;
                            # already committed slices are immutable idempotent facts.
                            p.record_online(account=str(account),character=str(character),level=level,
                                operation=f'online:{self.token}:{start}:{end}:{period}',period=period,starts=a,ends=b)
                    self.committed=int(elapsed)
            else:
                # Wall-clock jumps may change campaign/day attribution. Preserve
                # committed observations, drop the uncertain gap and re-anchor.
                self.identity=None
        current=None if stop else current
        if current!=self.identity or self.identity is None:
            self.identity=current
            self.base=mono;self.anchor=int(wall);self.committed=0


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
