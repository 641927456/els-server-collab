"""Reuse committed role projections only inside one serialized operation.

The read-only observer connection never writes or holds a read transaction.
SQLite data_version changes when ANY other connection commits to that file,
including the ordinary writers used by the current operation. No TTL or
process-wide role snapshot is used; ownership and enabled-account checks are
still performed by their existing consumers.
"""
from contextlib import contextmanager,closing
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import sqlite3
import os
import threading
import time
try:
    from nt import _getfinalpathname
except ImportError:
    _getfinalpathname=None
from els_server.performance import projection_loaded


_current = ContextVar('committed_role_read_scope', default=None)


_ATOMIC = frozenset((type(None), bool, int, float, complex, str, bytes, range,
                     type(Ellipsis), type(NotImplemented), type))


def _copy_projection(value, memo=None):
    """Copy ordinary projection containers without visiting atomic memo keys.

    Keep deepcopy's alias/cycle semantics and its original handling of other
    types. A cache producer and each consumer still own separate mutable data.
    """
    kind=type(value)
    if kind in _ATOMIC:return value
    if memo is None:memo={}
    identity=id(value)
    if identity in memo:return memo[identity]
    if kind is dict:
        result={};memo[identity]=result
        for key,item in value.items():result[_copy_projection(key,memo)]=_copy_projection(item,memo)
        return result
    if kind is list:
        result=[];memo[identity]=result
        result.extend(_copy_projection(item,memo)for item in value)
        return result
    return deepcopy(value,memo)


class ReadConnections:
    """Application-owned handles; each worker exclusively uses its own pair.

    Connections retain SQL statement caches, never projected player values or
    a read transaction. Application.close drains every worker before closing
    these handles. Cross-thread close is enabled solely for that final drain.
    """
    def __init__(self):
        self.lock=threading.Lock();self.workers={};self.path_workers={}

    def current(self):
        thread=threading.get_ident()
        with self.lock:return self.workers.setdefault(thread,({}, {}, {}))

    def paths(self):
        with self.lock:return self.path_workers.setdefault(threading.get_ident(),{})

    def close(self):
        with self.lock:
            for observers,files,readers in self.workers.values():
                for db in (*observers.values(),*readers.values()):db.close()
            self.workers.clear()
            self.path_workers.clear()


class _ReadScope:
    def __init__(self,connections=None):
        self.thread = threading.get_ident()
        self.persistent=connections is not None
        self.connections,self.files,self.readers=connections.current() if self.persistent else ({},{},{})
        self.values = {}
        self.item_bodies = {}
        self.snapshots = {}
        self.item_lists = {}
        # Cache the conversion of a freshly resolved Windows kernel name,
        # never a raw path's file/parent IDs or any player/authority result.
        self.paths = connections.paths()if self.persistent else {}

    def canonical(self,value):
        """Freshly resolve links, including moved directories with the same ID.

        CPython's Windows realpath resolves the final name again to confirm
        its optional prefix removal. Reuse only that confirmed conversion;
        the kernel still resolves the complete input on EVERY invocation.
        """
        raw=Path(value)
        if _getfinalpathname is None:
            resolved=raw.resolve()
        else:
            name=os.path.normpath(str(raw))
            try:final=_getfinalpathname(name)
            except (OSError,ValueError):
                # Preserve Path.resolve(strict=False) for nonexistent paths;
                # storage locate/open still requires an actual file below.
                return raw.resolve()
            key=(final,name.startswith('\\\\?\\'))
            resolved=self.paths.get(key)
            if resolved is None:
                resolved=raw.resolve()
                # Do not bind a conversion to an earlier name if the path
                # changed while the ordinary resolver was running.
                if _getfinalpathname(str(resolved))==final:self.paths[key]=resolved
        return resolved

    def locate(self,value):
        resolved=self.canonical(value)
        return resolved,resolved.stat()

    def open(self,path):
        return sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,
            isolation_level=None,timeout=10,check_same_thread=not self.persistent)

    def read(self, path, key, load, *, identity_from=None):
        path,info = self.locate(path)
        file_id = (info.st_dev, info.st_ino)
        if self.files.get(path) not in (None,file_id):
            observer=self.connections.pop(path,None)
            if observer is not None:observer.close()
            reader=self.readers.pop(path,None)
            if reader is not None:reader.close()
            self.values = {key:value for key,value in self.values.items() if key[0] != path}
        self.files[path] = file_id
        observer = self.connections.get(path)
        if observer is None:
            observer = self.open(path)
            self.connections[path] = observer
        before = observer.execute('PRAGMA data_version').fetchone()[0]
        identity = (path, key)
        saved = self.values.get(identity)
        if saved is not None and saved[0] == before:
            projection_loaded(0,hit=True)
            return _copy_projection(saved[1])
        if identity_from is not None:
            source_key,source_load=identity_from
            source=self.values.get((path,source_key))
            fields=('uid','name','unit_type','unit_class','level','transcendence','master','revision','account_id')
            if (source is not None and source[0]==before and len(source)>2
                    and source[2]==source_load and type(source[1]) is dict
                    and all(field in source[1] for field in fields)
                    and source[1]['uid']==key[1] and source[1]['account_id']==key[0]):
                value={field:_copy_projection(source[1][field]) for field in fields}
                self.values[identity]=(before,_copy_projection(value),load)
                projection_loaded(0,hit=True)
                return value
        started=time.perf_counter()
        try:
            value = load()
        finally:
            projection_loaded(time.perf_counter()-started)
        after = observer.execute('PRAGMA data_version').fetchone()[0]
        # A writer may commit between any two component reads. Return the
        # existing consumer's result, but do not reuse a mixed-version view.
        if before == after:
            self.values[identity] = (after, _copy_projection(value), load)
        else:
            self.values.pop(identity, None)
        return value

    def close(self):
        try:
            for connection in (*self.connections.values(),*self.readers.values()):
                if self.persistent:
                    if connection.in_transaction:connection.rollback()
                else:connection.close()
        finally:
            if not self.persistent:
                self.connections.clear()
                self.files.clear()
                self.readers.clear()
            self.values.clear()
            self.item_bodies.clear()
            self.snapshots.clear()
            self.item_lists.clear()
            if not self.persistent:self.paths.clear()


@contextmanager
def committed_reads(*,connections=None):
    current = _current.get()
    if current is not None and current.thread == threading.get_ident():
        yield
        return
    scope = _ReadScope(connections)
    token = _current.set(scope)
    try:
        yield
    finally:
        try:
            scope.close()
        finally:
            _current.reset(token)


def role_projection(account, load, *, projection='full'):
    scope = _current.get()
    if (scope is None or scope.thread != threading.get_ident()
            or account.characters is None or account.store is None):
        return load()
    second=int(time.time())
    identity_from=None
    if projection=='identity':
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.characters import Characters
        if (type(account) is LocalAccount and type(account.characters) is Characters
                and getattr(load,'__self__',None) is account
                and getattr(load,'__func__',None) is LocalAccount._character_identity_projection
                and getattr(account._character_projection,'__func__',None) is LocalAccount._character_projection
                and getattr(account.characters.get,'__func__',None) is Characters.get
                and getattr(account.characters.identity,'__func__',None) is Characters.identity
                and getattr(account.characters._project,'__func__',None) is Characters._project
                and account.characters._row is Characters._row):
            identity_from=((account.account_id,account.uid,id(account.characters),'full',second),
                           account._character_projection)
    # Full roles include time-filtered bank entries and other timed views.
    # Static identity remains reusable until its database generation changes.
    key=(account.account_id,account.uid,id(account.characters),projection)
    if projection!='identity':key+=(second,)
    return scope.read(account.store.path,key,load,identity_from=identity_from)


def inventory_projection(account,inventory,load):
    """Reuse only within an operation and a committed SQL/file generation.

    The caller still performs inventory initialization and legacy circuit
    repair before each access. No authentication, owner or live lease cache.
    A second boundary prevents time-derived validation from crossing expiry.
    """
    scope=_current.get();store=getattr(account,'store',None)
    if (scope is None or scope.thread != threading.get_ident()
            or getattr(account,'characters',None) is None or store is None
            or store.uid != account.uid or inventory.uid != account.uid
            or canonical_path(store.path) != canonical_path(inventory.path)):
        return load()
    return scope.read(store.path,('inventory',account.account_id,account.uid,
        id(store),id(inventory),int(time.time())),load)



@contextmanager
def snapshot_connection(path,*,timeout=10):
    """Operation-local read-only connection; no read transaction may escape.

    Used only by explicit snapshot/identity readers. A nested reader receives
    a separate connection, preserving the original independent transaction.
    """
    scope=_current.get()
    if scope is None or scope.thread != threading.get_ident():
        path=Path(path).resolve()
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=timeout)) as db:
            try:yield db
            finally:
                if db.in_transaction:db.rollback()
        return
    # Reuse the observer's generation check without borrowing any data value.
    path,info=scope.locate(path);identity=(info.st_dev,info.st_ino)
    if scope.files.get(path)!=identity:
        for connections in (scope.connections,scope.readers):
            old=connections.pop(path,None)
            if old is not None:old.close()
        scope.values={key:value for key,value in scope.values.items() if key[0]!=path}
        scope.files[path]=identity
    db=scope.readers.get(path)
    if db is not None and db.in_transaction:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=timeout)) as nested:
            try:
                with _tracked_snapshot(scope,nested,path,identity,timeout=timeout):yield nested
            finally:
                if nested.in_transaction:nested.rollback()
        return
    if db is None:
        db=scope.open(path)
        scope.readers[path]=db
    try:
        with _reader_timeout(db,timeout),_tracked_snapshot(scope,db,path,identity,timeout=timeout):yield db
    finally:
        if db.in_transaction:db.rollback()


@contextmanager
def _reader_timeout(db,timeout):
    if timeout==10:
        yield
        return
    original=db.execute('PRAGMA busy_timeout').fetchone()[0]
    milliseconds=max(0,int(timeout*1000))
    if original!=milliseconds:db.execute('PRAGMA busy_timeout='+str(milliseconds))
    try:yield
    finally:
        if original!=milliseconds:db.execute('PRAGMA busy_timeout='+str(original))


@contextmanager
def _tracked_snapshot(scope,db,path,file_id,*,timeout=10):
    observer=scope.connections.get(path)
    if observer is None:
        observer=scope.open(path)
        scope.connections[path]=observer
    # Capture before the caller can BEGIN or establish its read snapshot.
    with _reader_timeout(observer,timeout):
        entry=(path,file_id,observer,observer.execute('PRAGMA data_version').fetchone()[0])
    previous=scope.snapshots.get(db);scope.snapshots[db]=entry
    try:yield
    finally:
        if previous is None:scope.snapshots.pop(db,None)
        else:scope.snapshots[db]=previous


def validated_item_projection(db,owner,item_uid,load):
    """Cache data only in this operation; writer connections always run load.

    A readonly snapshot may be older than the observer after another commit.
    Such a reader neither consumes nor populates the current-generation cache.
    The original full load/validation is the sole producer of cached values.
    """
    scope=_current.get()
    if scope is None or scope.thread!=threading.get_ident():return load(db,owner,item_uid=item_uid)
    entry=scope.snapshots.get(db)
    if entry is None or not db.in_transaction or item_uid is not None and type(item_uid)is not int:return load(db,owner,item_uid=item_uid)
    # BEGIN is deferred. Pin the reader before comparing its entry generation,
    # so a commit after the comparison cannot make a cache hit mix snapshots.
    db.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone()
    path,file_id,observer,generation=entry
    def stamp():
        info=path.stat()
        return ((info.st_dev,info.st_ino),observer.execute('PRAGMA data_version').fetchone()[0],int(time.time()))
    before=stamp()
    if before[:2]!=(file_id,generation):return load(db,owner,item_uid=item_uid)
    key=(path,owner,item_uid,load);saved=scope.item_lists.get(key)
    if saved is not None and saved[0]==before:
        projection_loaded(0,hit=True)
        return _copy_projection(saved[1])
    value=load(db,owner,item_uid=item_uid)
    if stamp()==before:scope.item_lists[key]=(before,_copy_projection(value))
    return value


def quest_notification_projection(state,load,*,projection='quest-notification'):
    """Reply-only active/completed quest view within one committed operation."""
    scope=_current.get()
    if scope is None or scope.thread != threading.get_ident():return load()
    return scope.read(state.path,(projection,state.account_id,state.uid,int(time.time()),getattr(load,'__func__',load)),load)


def item_body_projection(item,encode,*,wire_key=None):
    """Reuse pure wire bytes for an already validated, unchanged item.

    No ownership, qualification, SQL reads or validation result is cached.
    The original body encoder may supply its UID/slot-free key; the outer
    record still writes both fields and every caller still validates each item.
    Each worker operation/thread owns this scope; nested values are copied
    so changing a socket, expiry, count or other field cannot reuse old bytes.
    """
    scope=_current.get()
    if scope is None or scope.thread!=threading.get_ident():return encode(item)
    identity=(encode,item['uid'])if wire_key is None else(encode,item['template'],item['metadata'],item['group'],item['count'])
    value=item if wire_key is None else wire_key
    previous=scope.item_bodies.get(identity)
    if previous is not None and previous[0]==value:return previous[1]
    body=encode(item)
    scope.item_bodies[identity]=(_copy_projection(value),body)
    return body


@contextmanager
def checked_paths():
    """Deduplicate path work inside one check; recheck before accepting it.

    This carries no authorization or state across calls/operations. End checks
    include file identity so an atomic replacement cannot borrow a prior path.
    All original graph/owner/enabled/SQL guards remain at their call sites.
    """
    paths={}
    def current(raw):
        # canonical_path resolves the complete input in the kernel on every
        # call; only CPython's already-confirmed prefix conversion is reused.
        resolved=canonical_path(raw);info=resolved.stat()
        return resolved,(info.st_dev,info.st_ino)
    def resolve(value):
        raw=Path(value)
        if raw not in paths:
            try:paths[raw]=current(raw)
            except OSError as error:raise ValueError('Live database path unavailable') from error
        return paths[raw][0]
    yield resolve
    for raw,identity in paths.items():
        try:now=current(raw)
        except OSError as error:raise ValueError('Live database path changed') from error
        if now!=identity:raise ValueError('Live database path changed')


def canonical_path(value):
    scope=_current.get()
    if scope is None or scope.thread!=threading.get_ident():return Path(value).resolve()
    return scope.canonical(value)


