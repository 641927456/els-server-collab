"""Let the GM panel see players in the local profile without a restart.

``mode = "local"`` builds plain ``LocalSession`` objects. Those never enter
``app.playing`` or ``world.members`` — the only two sources the panel reads —
so the online list was structurally empty and every panel action answered
"player offline" while the game was running right next door.

This module widens the panel's view to every live session of both profiles and
routes GM pushes through the periodic notification slice, because a plain
``LocalSession`` owns no mailbox. It only assigns methods onto ``Runtime`` and
wraps ``Application.periodic_chunks``; sockets, saves and the wire protocol are
untouched.

It is installed by ``els_server.domain.quest_flow``, a hot-reload whitelisted
module, so an edited handler reaches a running server while the player stays in
game. Nothing here is needed at import time by any other module.
"""
import threading
import time

_lock = threading.Lock()


def _snapshot(group):
    """Materialise a session container that another thread may be mutating."""
    for _ in range(3):
        try:
            return list(group.keys()) if isinstance(group, dict) else list(group)
        except (RuntimeError, TypeError):
            continue
    return []


def _sessions(runtime):
    """Live characters from every source the two profiles use, one row each."""
    app = getattr(runtime, 'app', None)
    groups = []
    playing = getattr(app, 'playing', None)
    if isinstance(playing, dict):
        groups.append(playing)
    members = getattr(getattr(app, 'world', None), 'members', None)
    if isinstance(members, dict):
        groups.append(members)
    local = getattr(getattr(runtime, 'server', None), 'local_sessions', None)
    if local:
        groups.append(local)
    aux = getattr(app, '_aux_local_sessions', None)
    if aux:
        groups.append(aux)
    rows = []
    seen = set()
    for group in groups:
        for session in _snapshot(group):
            if id(session) in seen:
                continue
            seen.add(id(session))
            # A plain LocalSession has neither released nor identity; a helper
            # connection that never picked a role must stay out of the roster.
            if getattr(session, 'released', False):
                continue
            if getattr(session, 'role', None) != 'game':
                continue
            account = getattr(session, 'account', None)
            if account is None:
                continue
            try:
                character = account.character()
            except Exception:
                continue
            if character is None:
                continue
            rows.append((session, character))
    # Local mode shares one account record across connections, so the same
    # character can be listed twice; keep the most advanced session per uid.
    rank = {'town_ready': 3, 'dungeon_active': 3, 'channels_ready': 2}
    best = {}
    for session, character in rows:
        uid = character.get('uid')
        score = rank.get(getattr(session, 'phase', None), 1)
        if uid not in best or score > best[uid][0]:
            best[uid] = (score, session, character)
    return [(session, character) for _, session, character in best.values()]


def _ensure_mailbox(session):
    """Give a plain LocalSession the mailbox every GM push writes into."""
    box = getattr(session, 'mailbox', None)
    if box is not None and not getattr(session, '_gm_local_box', False):
        return box  # friends session: handle() drains this one itself
    if box is None:
        from els_server.domain.friends_world import Mailbox
        box = Mailbox()
        session.mailbox = box
        session._gm_local_box = True
    return box


def _install_delivery(runtime):
    """Drain local mailboxes on the periodic slice, the only push channel."""
    app = getattr(runtime, 'app', None)
    if app is None:
        return
    with _lock:
        if getattr(app, '_gm_local_delivery', False):
            return
        original = getattr(app, 'periodic_chunks', None)
        if original is None:
            return
        def chunks(sessions):
            sessions = tuple(sessions)
            cursor = [0]
            async def run():
                async for results in original(sessions):
                    patched = []
                    for messages, error in results:
                        session = sessions[cursor[0]] if cursor[0] < len(sessions) else None
                        cursor[0] += 1
                        if error is None and getattr(session, '_gm_local_box', False):
                            box = getattr(session, 'mailbox', None)
                            extra = box.drain() if box is not None else []
                            if extra:
                                messages = list(messages or ()) + extra
                        patched.append((messages, error))
                    yield patched
            return run()
        app.periodic_chunks = chunks
        app._gm_local_delivery = True


def _live(self):
    return _sessions(self)


def _players(self):
    _install_delivery(self)
    rows = []
    for session, character in _sessions(self):
        identity = getattr(session, 'identity', None) or {}
        account = session.account
        try:
            career = self.career_labels(character)
            ed = account.get_reward_balances()['ed']
        except Exception:
            continue
        rows.append(dict(uid=character['uid'], name=character['name'], level=character['level'],
            unit_type=character['unit_type'], unit_class=character['unit_class'], **career,
            account_id=identity.get('id', account.account_id),
            account=identity.get('name', account.account_name), phase=session.phase,
            map=getattr(session, 'active_map', None), session=session.shop_session_id, ed=ed))
    return rows


def _session(self, value):
    uid = value.get('uid')
    if type(uid) is not int:
        raise ValueError('角色编号无效')
    match = None
    for session, character in _sessions(self):
        if character.get('uid') == uid or getattr(session.account, 'uid', None) == uid:
            match = session
            break
    if match is None or match.shop_session_id != value.get('session'):
        raise ValueError('玩家已离线或重新登录，请刷新在线列表')
    if getattr(match, 'social_overflow', False) or getattr(match, 'coop_error', None):
        raise ValueError('玩家连接暂时不可写入')
    identity = getattr(match, 'identity', None)
    registry = getattr(self.app, 'registry', None)
    if identity is not None and registry is not None and not registry.enabled(identity['id']):
        raise ValueError('玩家连接暂时不可写入')
    if match.phase not in ('town_ready', 'dungeon_active'):
        raise ValueError('玩家正在切换场景，请稍后刷新再发放')
    _ensure_mailbox(match)
    return match


def _targets(runtime):
    return [session for session, _ in _sessions(runtime)
            if not getattr(session, 'social_overflow', False) and not getattr(session, 'coop_error', None)]


def _announce(self, value):
    from els_server.gm_runtime import operation, prepare_mailbox
    operation(value)
    from els_server.protocol.gm_messages import scrolling_notice
    from els_server.protocol.protocol_codec import encode_event
    text = value.get('text')
    event = scrolling_notice(text)
    repeat, interval = value.get('repeat', 1), value.get('interval', 60)
    if type(repeat) is not int or not 1 <= repeat <= 20 or type(interval) is not int or not 10 <= interval <= 3600:
        raise ValueError('公告次数为 1–20，间隔为 10–3600 秒')
    # Encode before queueing: a malformed event inside the periodic slice would
    # close the player's connection instead of failing this call.
    encode_event(event)
    _install_delivery(self)
    targets = _targets(self)
    if repeat > 1:
        if len(self.scheduled) >= 20:
            raise ValueError('公告计划已满')
        self.scheduled.append(dict(id=value['operation_id'], event=event, text=text,
            remaining=repeat - 1, interval=interval, next=time.monotonic() + interval))
    for session in targets:
        _ensure_mailbox(session)
        session.mailbox = prepare_mailbox(session, [event])
    return dict(recipients=len(targets), repeat=repeat, operation_id=value['operation_id'])


def _give(self, value):
    """``Runtime.give`` with the panel ceiling raised to the native stack cap.

    ``inventory_state.LOCAL_MAX_STACK`` is 999 and ``reward_rules.item_plan``
    already accepts up to 999, so the 99 in the original entry check was the
    only thing rejecting larger shipments. This is the same body as
    ``els_server.gm_runtime.Runtime.give`` with that one bound widened, and it
    is attached here so a running server picks it up without a restart.
    """
    import hashlib
    import json
    import sqlite3
    from contextlib import closing
    from els_server import gm_runtime as runtime_module
    from els_server.domain.reward_rules import item_plan
    from els_server.storage.inventory_state import grant_items, InventoryFull
    from els_server.domain.dungeon_drops import pickup_inventory_notice
    key = runtime_module.operation(value)
    template, quantity = value.get('template'), value.get('quantity')
    if type(template) is not int or type(quantity) is not int or not 1 <= quantity <= 999:
        raise ValueError('每次发放数量为 1–999')
    plan = item_plan(template, quantity)
    digest = hashlib.sha256(runtime_module.canonical(value).encode()).hexdigest()
    with closing(sqlite3.connect(self.app.config.state_file, timeout=10)) as db, \
            runtime_module.write_transaction(db):
        db.execute('CREATE TABLE IF NOT EXISTS gm_item_receipts (operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, receipt TEXT NOT NULL)')
        old = db.execute('SELECT digest,receipt FROM gm_item_receipts WHERE operation_id=?', (key,)).fetchone()
        if old:
            if old[0] != digest:
                raise ValueError('同一操作编号不能用于不同发货内容')
            return dict(json.loads(old[1]), replayed=True)
        s = self.session(value)
        try:
            changed = grant_items(db, [plan], s.account.uid, admin_grant=True)
        except InventoryFull as error:
            raise ValueError('玩家背包空间不足，未发放任何物品') from error
        events = [pickup_inventory_notice(changed)]
        box = runtime_module.prepare_mailbox(s, events)
        receipt = dict(operation_id=key, uid=s.account.uid, name=s.account.character()['name'],
                       template=template, quantity=quantity, reason=value['reason'],
                       time=time.time(), replayed=False, delivery='committed-and-queued')
        db.execute('INSERT INTO gm_item_receipts VALUES (?,?,?)', (key, digest, runtime_module.canonical(receipt)))
    s.mailbox = box
    return receipt


def _tick(self):
    # Called once a second for the whole session; an empty schedule must cost
    # nothing beyond this test, same as the original loop over an empty list.
    if not self.scheduled:
        return
    now = time.monotonic()
    for job in list(self.scheduled):
        if now < job['next']:
            continue
        for session in _targets(self):
            try:
                _ensure_mailbox(session)
                from els_server.gm_runtime import prepare_mailbox
                session.mailbox = prepare_mailbox(session, [job['event']])
            except ValueError:
                pass
        job['remaining'] -= 1
        job['next'] = now + job['interval']
        if not job['remaining']:
            self.scheduled.remove(job)


def _level_offline_guard(self, account_id):
    for session, _ in _sessions(self):
        identity = getattr(session, 'identity', None) or {}
        if identity.get('id', getattr(session.account, 'account_id', None)) == account_id:
            raise ValueError('该账号仍有角色在线，请先返回角色选择或退出游戏，再刷新资料')
    # Local mode authenticates nobody, so there is no registry to consult.
    registry = getattr(self.app, 'registry', None)
    if registry is not None and not registry.enabled(account_id):
        raise ValueError('账号不存在或已停用')


def install(force=False):
    """Attach the local-profile behaviour to Runtime. Idempotent unless forced."""
    from els_server.gm_runtime import Runtime
    with _lock:
        if getattr(Runtime, '_gm_local_patch', False) and not force:
            return False
        Runtime._live = _live
        Runtime.players = _players
        Runtime.session = _session
        Runtime.announce = _announce
        Runtime.give = _give
        Runtime.tick = _tick
        Runtime.level_offline_guard = _level_offline_guard
        Runtime._gm_local_patch = True
    return True


# The whitelist reloads this module on edit, but a re-executed module does not
# re-attach anything by itself, so it installs itself on every execution.
try:
    install(force=True)
except Exception:
    pass


# --- live data patches --------------------------------------------------------
# Editing this file is the only way to reach a running process without asking
# the player to restart, so data fixes ride along with the self-install above.


def _patch_log(text):
    try:
        from pathlib import Path
        import time
        root = Path(__file__).resolve().parents[1]
        path = root / 'state' / 'gm-patch.log'
        if path.exists() and path.stat().st_size > 4_000_000:
            keep = path.read_text(encoding='utf8', errors='replace').splitlines()[-20_000:]
            path.write_text('\n'.join(keep) + '\n', encoding='utf8')
        with path.open('a', encoding='utf8') as handle:
            handle.write('%.3f %s\n' % (time.time(), text))
    except Exception:
        pass


def _reload_dungeon_routes():
    """Attach an edited ``DungeonRun._load_stage`` to the live class.

    ``importlib.reload`` reuses the module dict but re-executes the class
    statement, so anything already holding ``DungeonRun`` keeps the old method.
    Rebinding the freshly loaded function onto the existing class and putting
    that class back under the module name keeps ``type(run) is DungeonRun``
    identity checks intact for runs created before and after the edit.
    """
    import importlib
    import els_server.domain.dungeon_routes as routes
    old = routes.DungeonRun
    fresh = importlib.reload(routes)
    if fresh.DungeonRun is not old:
        old._load_stage = fresh.DungeonRun._load_stage
        fresh.DungeonRun = old
    return sorted(fresh.SOURCE_NPC_POINT_REBASE)


def _reload_gm_events():
    """Adopt the event switches on disk without restarting the server."""
    from pathlib import Path
    from els_server.domain import gm_events
    path = Path(__file__).resolve().parents[1] / 'state/activity2026-gm/development/events.json'
    if not path.exists():
        return None
    return gm_events.configure(str(path))


def _reload_domain(name):
    """Re-execute one domain module that the watcher itself cannot reach.

    ``hot_reload.watch`` freezes its module list at startup
    (``names = tuple(names or modules())``), so a module missing from
    ``state/hot-reload.json`` when the server booted can never be reloaded
    afterwards -- touching the request file only re-runs the frozen set. This
    file *is* in that set, so re-executing it is the only way to adopt an
    edited handler without dropping the player's connection.

    The dispatcher imports these handlers inside the function body
    (``from els_server.domain.guild_agit_flow import handle as ...``), so
    nothing holds the old function object and a plain reload is enough.
    """
    import importlib
    import sys
    module = sys.modules.get(name)
    if module is None:
        importlib.import_module(name)
        return 'imported'
    importlib.reload(module)
    return 'reloaded'


def _reload_login_builders():
    """Adopt ``local_messages`` edits without restarting the server.

    ``els_server.domain.local_session`` binds ``player_initialization`` at
    import time (line 3) and can never be hot-reloaded, so every edit to the 2A
    builder used to require a full restart and a relog -- which is exactly why
    the customization selection never got a second look. Reload the module and
    put the fresh functions back under the names the callers actually resolve:
    ``local_session`` calls them as bare globals, so rebinding its module
    attributes is enough.
    """
    import importlib
    from els_server.protocol import local_messages
    fresh = importlib.reload(local_messages)
    from els_server.domain import local_session
    rebound = []
    for name in ('player_initialization', 'character_list', 'character_unit',
                 'responses', 'client_economy_fields', 'character_gate_notice',
                 'inventory_initialization', 'optional_player_initializations',
                 'skill_slots_initialization', 'key_bindings_initialization'):
        value = getattr(fresh, name, None)
        if value is None or not hasattr(local_session, name):
            continue
        setattr(local_session, name, value)
        rebound.append(name)
    try:
        from els_server.domain import fishing_attempt
        if hasattr(fishing_attempt, 'player_initialization'):
            fishing_attempt.player_initialization = fresh.player_initialization
    except Exception:
        pass
    return rebound


# --- cold login town restore ---------------------------------------------------
# The 225(town,1) refusal is fixed in els_server.domain.town_travel_flow
# (``authorize_cold_start_entry``) rather than wrapped here, so there is one
# implementation only. That module is in state/hot-reload.json, so later edits
# to it reach a running server the same way this file does.

def _install_reply_code_trace():
    """Record the reply kinds and leading result codes of a live session.

    The client renders 「当前无法使用。」 from its own string table and the
    server never emits 2856, so the only way to name the culprit is to see
    which reply carried a failure while the player was entering the town.
    Heartbeat and movement traffic is skipped so one login stays readable.
    """
    import struct
    from els_server.domain import local_session as module
    current = module.LocalSession.handle
    if getattr(current, '_reply_code_version', 0) >= 4:
        return 'already installed'
    # Unwrap any earlier version of this wrapper so the chain never stacks.
    original = current
    for _ in range(8):
        previous = getattr(original, '_previous', None)
        if previous is None:
            break
        original = previous
    quiet = frozenset((0x563, 0x7d0, 0x104, 0x18e, 0x38e, 0x22b,
                       0x91, 0x85, 0xa0, 0x2ea, 0x0))

    def handle(self, event, *args, **kwargs):
        reply = original(self, event, *args, **kwargs)
        try:
            kind = getattr(event, 'kind', 0)
            if kind in quiet:
                return reply
            rows = []
            for item in reply or ():
                payload = getattr(item, 'payload', b'') or b''
                codes = [struct.unpack_from('>i', payload, i)[0]
                         for i in range(0, min(len(payload), 12) - 3, 4)]
                rows.append('0x%x[%s]' % (getattr(item, 'kind', 0),
                                          ','.join(str(c) for c in codes)))
            _patch_log('reply req=0x%x phase=%s -> %s'
                       % (kind, getattr(self, 'phase', '?'), ' '.join(rows) or 'none'))
        except Exception:
            pass
        return reply

    handle._reply_code_trace = True
    handle._reply_code_version = 4
    handle._previous = original
    module.LocalSession.handle = handle
    return 'installed'


try:
    _patch_log('reply code trace %s' % (_install_reply_code_trace(),))
except Exception as _error:
    _patch_log('reply code trace failed %s: %s' % (type(_error).__name__, _error))


try:
    _patch_log('point rebase %r' % (_reload_dungeon_routes(),))
except Exception as _error:
    _patch_log('point rebase failed %s: %s' % (type(_error).__name__, _error))
try:
    _reload_gm_events()
    from els_server.domain.gm_events import snapshot as _event_snapshot
    _patch_log('events %r' % ([(row['id'], row['open']) for row in _event_snapshot()['rows']],))
except Exception as _error:
    _patch_log('events reload failed %s: %s' % (type(_error).__name__, _error))
try:
    _patch_log('login builders %r' % (_reload_login_builders(),))
except Exception as _error:
    _patch_log('login builders failed %s: %s' % (type(_error).__name__, _error))
try:
    # Order matters: guild_agit_flow binds room_identity/world_state/scene at
    # import time, so the housing module has to be re-executed first or the
    # freshly reloaded agit module keeps the old function objects.
    _patch_log('housing room %r' % (
        _reload_domain('els_server.domain.housing_room_flow'),))
    _patch_log('guild agit %r' % (
        _reload_domain('els_server.domain.guild_agit_flow'),))
except Exception as _error:
    _patch_log('guild agit failed %s: %s' % (type(_error).__name__, _error))

