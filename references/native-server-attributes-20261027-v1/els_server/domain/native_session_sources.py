"""Bounded original-worker source receipts committed after actual writes.

The transport's existing operation lock serializes its worker and sender.
Other peers may still mutate world state, so selection references are checked
again at the write receipt. No attribute math, SQL, extra packet or client
attachment is performed here. A metadata failure preserves business replies.
"""
from dataclasses import dataclass
import struct
import sys
import threading
from els_server.domain import native_copy_production as copies
from els_server.domain import native_skill_production as skills
from els_server.domain import native_attribute_readiness as readiness
from els_server.domain.native_attribute_delivery import DeliveryCursor


ACTIVE_PHASES=frozenset(('player_initialized','skill_ui_ready','initialization_confirmed',
    'map_loading','square_accepted','town_ready','dungeon_loading','dungeon_active'))


def _classes():
    return tuple(value for module,name in(
        ('els_server.domain.local_session','LocalSession'),
        ('els_server.application','FriendsSession'))
        if isinstance(value:=getattr(sys.modules.get(module),name,None),type))


@dataclass(frozen=True)
class WrittenSources:
    epoch:object
    messages:tuple
    copies:tuple
    updates:tuple
    ui_receipts:tuple


class SessionSources:
    def __init__(self,session):
        if type(session)not in _classes():
            raise ValueError('Original installed session required')
        self.session=session
        self.cursor=DeliveryCursor()
        self._lock=threading.Lock()
        self._pending=None
        self._closed=False
        self._selection=None
        self.failures=0
        self.produced=0
        self.written=0

    def _invalidate(self):
        self._pending=None
        self._selection=None
        self.cursor.discard()

    def _current(self):
        epoch=self.cursor.epoch
        value=skills._selection(self.session,epoch)if epoch is not None else None
        return (value is not None and self._selection is not None
            and value[0]is self._selection[0]and value[1]is self._selection[1]
            and value[2]==self._selection[2]and value[3]in ACTIVE_PHASES)

    def capture(self,function,args,kwargs,invoke):
        """Original _worker_call entry, including its original after_reply.

        No return-type adapter reaches the business flow: callers get exactly
        its original result object. Source scopes only keep Event identities.
        Initial2A derives role type from the same written native class field;
        no second player projection or SQL read is introduced.
        """
        original={};ready=[];updates=[]
        with self._lock:
            closed=self._closed
            if not closed and self.cursor.epoch is not None and not self._current():self._invalidate()
            epoch=self.cursor.epoch
        if closed:return invoke()
        def actual():
            if original.get('called'):raise RuntimeError('Original native worker invoked twice')
            original['called']=True
            original['value']=invoke()
            original['finished']=True
            return original['value']
        def qualified_worker():
            if epoch is None:return actual()
            batch=readiness.capture_worker(epoch,self.session,function,args,kwargs,actual)
            if batch.receipt is not None:ready.append(batch.receipt)
            return batch.messages
        def skill_worker():
            if epoch is None:return qualified_worker()
            batch=skills.capture(epoch,self.session,qualified_worker)
            updates.extend(batch.updates)
            return batch.messages
        try:
            batch=copies.capture(skill_worker)
            with self._lock:
                if self._closed:return original['value']
                own=tuple(p for p in batch.copies if p.owner==getattr(self.session.account,'uid',None))
                initial=tuple(p for p in own if p.event.kind==0x2a)
                if initial:
                    if len(initial)!=1 or self.session.phase!='player_initialized':
                        raise ValueError('One original successful selection copy required')
                    event=initial[0].event
                    unit_class=struct.unpack_from('>H',event.payload,4+0x15)[0]
                    from els_server.game_data import client_data
                    unit_type=client_data().unit(unit_class)['unitType']
                    epoch=self.cursor.begin(initial[0].owner,self.session.account.account_id,unit_type)
                    self._selection=skills._selection(self.session,epoch)
                    ready=[];updates=[]
                elif not self._current():
                    self._invalidate()
                    return original['value']
                if not self._current():raise ValueError('Original selection source graph changed')
                # One operation lock allows only one unsent own worker batch.
                # Replacing an unexpected old batch loses that evidence only.
                if self._pending is not None:self.failures+=1
                self._pending=WrittenSources(epoch,batch.messages,own,
                    tuple(p for p in updates if p.epoch is epoch),
                    tuple(p for p in ready if p.epoch is epoch))
                self.produced+=1
            return original['value']
        except Exception:
            with self._lock:
                self.failures+=1;self._invalidate()
            if not original.get('called'):return invoke()
            if not original.get('finished'):raise
            return original['value']

    def sent(self,messages):
        """Only after every original batch write/drain succeeded, under its lock."""
        messages=tuple(messages)
        with self._lock:
            batch,self._pending=self._pending,None
            if self._closed:return False
            if not self._current():self._invalidate();return False
            if (batch is None or batch.epoch is not self.cursor.epoch
                or len(batch.messages)!=len(messages)
                or any(a is not b for a,b in zip(batch.messages,messages))):
                self.failures+=1
                # The original writer sent an unattributed batch. It must not
                # preserve an old rank/Force source or a prepared calculation.
                self._invalidate();return False
            try:
                if messages:self.cursor.observe_sent(batch.epoch,messages,actor_ready=False,
                    copies=batch.copies,skill_updates=batch.updates,ui_receipts=batch.ui_receipts)
            except Exception:
                self.failures+=1;self._invalidate();return False
            self.written+=1
            return True

    def close(self):
        with self._lock:
            self._closed=True;self._invalidate()


def attach(session):
    if getattr(session,'_native_sources',None)is not None:
        raise ValueError('Native source lifetime already attached')
    session._native_sources=SessionSources(session)
    return session._native_sources


def capture(function,args,kwargs,invoke):
    session=getattr(function,'__self__',None)
    state=getattr(session,'_native_sources',None)
    name=getattr(function,'__name__',None)
    if (type(state)is SessionSources and state.session is session
        and name in('handle','periodic_notifications')
        and getattr(function,'__func__',None)is getattr(type(session),name,None)):
        return state.capture(function,args,kwargs,invoke)
    return invoke()
