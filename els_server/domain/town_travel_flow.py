"""Bind the ordinary native58C success to its225/227 destination."""
import struct,time,uuid
from els_server.protocol.protocol_codec import Event
from els_server.protocol import town_travel_messages as wire
from els_server.domain.town_travel import DestinationRequirementError

def _ordinary_actor(s):
    from els_server.domain.equipment_chip_flow import current_lease
    a=getattr(s,'account',None);app=getattr(s,'application',None)
    return bool(a is not None and a.store is not None and a.store.uid==a.uid
        and current_lease(s) and (app is None or app.registry.enabled(a.account_id)))

def _ordinary_binding(s):
    a=s.account
    return (a,a.store,a.uid,a.account_id,s.shop_session_id)

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x58c:return None
    if not (s.enter_town and s.item_test and s.client_build=='dx11_260923' and s.account.characters is not None):return []
    destination=struct.unpack_from('>i',event.payload)[0] if len(event.payload)>=4 else 0
    if destination==1012:return _handle_village1012(s,event,sequence)
    def failure(requirement=None):
        if not _ordinary_actor(s):return []
        return [wire.acknowledgement(destination,s.account.get_reward_balances()['ed'],
            result=653 if requirement is not None else -1,details=requirement.details if requirement is not None else (0,0,0,0))]
    if not _ordinary_actor(s):return failure()
    if (event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
        or type(sequence) is not int or not 0<=sequence<2**64 or s.role!='game'):return failure()
    pending=getattr(s,'town_warp_transition',None)
    if pending is not None:
        if (pending.get('actor_binding')==_ordinary_binding(s) and pending['payload']==event.payload
            and pending['sequence']==sequence and s.phase in ('map_loading','square_accepted')):
            return [Event(0x201,kind=0x58d,payload=pending['response'])]
        return failure()
    if s.phase!='town_ready' or s.dungeon_return_pending:return failure()
    source=s.account.get_location()['map']
    if s.active_map!=source:return failure()
    binding=_ordinary_binding(s)
    account,store,uid,account_id,session_id=binding
    def authorize():
        return bool(_ordinary_actor(s) and _ordinary_binding(s)==binding and s.role=='game'
            and s.phase=='town_ready' and not s.dungeon_return_pending and s.active_map==source
            and s.account.get_location()['map']==source and getattr(s,'town_warp_transition',None) is None)
    try:
        wire.request(event.payload)
        from els_server.storage.town_travel import travel
        operation=str(uuid.uuid5(uuid.UUID(s.shop_session_id),f'town-warp:{s.account.uid}:{sequence}'))
        result=travel(store.path,uid,account_id,source,event.payload,operation,now=int(time.time()),authorize=authorize)
    except DestinationRequirementError as error:return failure(error)
    except (ValueError,OverflowError):return failure()
    with s.account.lock:s.account.location=s.account.store.load()
    s.town_warp_transition=dict(destination=destination,payload=event.payload,sequence=sequence,response=result['response'],operation=operation,actor_binding=binding)
    s.phase='map_loading';s.pending_map=None;s.inventory_town_sync_sent=False
    return [Event(0x201,kind=0x58d,payload=result['response'])]

# Recover by closing only the new1012 writer, not by removing its readers.
VILLAGE1012_WRITER_ENABLED = True


def _village1012_identity(s):
    if getattr(s, 'application', None) is None:
        from els_server.domain.cartridge_exchange_flow import _local_selected
        return bool(_local_selected(s) and s.enter_town and s.item_test and s.client_build=='dx11_260923')
    from els_server.domain.equipment_engrave_flow import current_lease
    # app=None is the old helper's fixture compatibility, not an actual lease.
    account = getattr(s, 'account', None)
    return bool(getattr(s, 'application', None) is not None and current_lease(s)
        and s.role == 'game' and s.enter_town and s.item_test and s.client_build == 'dx11_260923'
        and account is not None and account.characters is not None and account.store is not None
        and account.store.uid == account.uid)


def _village1012_envelope(s, event, sequence, kind):
    return bool(_village1012_identity(s) and event.event_id == 0x202 and event.kind == kind
        and type(sequence) is int and 1 <= sequence < 2**32 and event.performers == (0,)
        and event.uid == event.target_uid == 2**64-1 and event.payload_mode == 0)


def _village1012_failure(s,requirement=None):
    from els_server.storage.town_travel import village1012_snapshot
    try:
        if not _village1012_identity(s):
            return []  # No owned actor is available for a currency response.
        saved = village1012_snapshot(s.account.store.path, s.account.uid, s.account.account_id,
                                    authorize=lambda: _village1012_identity(s))
        return [wire.acknowledgement(1012, saved['balance']['ed'],
            result=653 if requirement is not None else -1,details=requirement.details if requirement is not None else (0,0,0,0))]
    except (ValueError, KeyError, TypeError, AttributeError):
        return []


def _village1012_pending(s, pending, account, store, session_id):
    if (not _village1012_identity(s) or s.account is not account or account.store is not store
            or s.shop_session_id != session_id or getattr(s, 'town_warp_transition', None) is not pending
            or s.phase not in ('map_loading', 'square_accepted') or not isinstance(pending, dict)):
        return False
    context = pending.get('binding', {}).get('context', {})
    return bool(context.get('account') == account.account_id and context.get('owner') == account.uid
        and context.get('session_id') == session_id and context.get('destination') == 1012
        and s.active_map == context.get('source') and not s.dungeon_return_pending)


def _handle_village1012(s, event, sequence):
    from els_server.storage.town_travel import travel
    if not _village1012_envelope(s, event, sequence, 0x58c):
        return _village1012_failure(s)
    if not VILLAGE1012_WRITER_ENABLED:
        return _village1012_failure(s)
    try:
        wire.request(event.payload)
        account, store, session_id = s.account, s.account.store, s.shop_session_id
        pending = getattr(s, 'town_warp_transition', None)
        if pending is not None:
            if (not isinstance(pending, dict) or pending.get('payload') != event.payload
                    or pending.get('sequence') != sequence or not _village1012_pending(s, pending, account, store, session_id)):
                raise ValueError('Village1012 pending request mismatch')
            context = pending['binding']['context']
            source = context['source']
            authorize = lambda: _village1012_pending(s, pending, account, store, session_id)
        else:
            source = account.get_location()['map']
            if s.phase != 'town_ready' or s.dungeon_return_pending or s.active_map != source:
                raise ValueError('Village1012 current source phase')
            context = dict(account=account.account_id, owner=account.uid, source=source,
                           destination=1012, session_id=session_id, sequence=sequence)
            authorize = lambda: bool(_village1012_identity(s) and s.account is account and account.store is store
                and s.shop_session_id == session_id and s.phase == 'town_ready'
                and s.active_map == source and not s.dungeon_return_pending
                and getattr(s, 'town_warp_transition', None) is None and account.get_location()['map'] == source)
        operation = str(uuid.uuid5(uuid.UUID(session_id), f'town-warp:{account.uid}:{sequence}'))
        result = travel(store.path, account.uid, account.account_id, source, event.payload, operation,
                        now=int(time.time()), context=context, authorize=authorize, pending=pending)
        if result['replayed']:
            return [Event(0x201, kind=0x58d, payload=result['response'])]
        # An uncertain failure here must be observed, never automatically paid
        # again. The committed saved1012 remains valid for cold restoration.
        with account.lock:
            account.location = store.load()
        s.town_warp_transition = dict(destination=1012, payload=event.payload, sequence=sequence,
            response=result['response'], operation=operation, binding=result['binding'])
        s.phase = 'map_loading'
        s.pending_map = None
        s.inventory_town_sync_sent = False
        return [Event(0x201, kind=0x58d, payload=result['response'])]
    except DestinationRequirementError as error:
        return _village1012_failure(s,error)
    except (ValueError, OverflowError, KeyError, TypeError, AttributeError):
        return _village1012_failure(s)


def authorize_village1012_entry(s, event, sequence):
    """Strict225 context, with stored cold/return compatibility kept separate."""
    from els_server.storage.town_travel import village1012_committed, village1012_snapshot
    if (not _village1012_envelope(s, event, sequence, 0x225) or event.payload != struct.pack('>iB', 1012, 0)
            or s.phase not in ('map_loading', 'square_accepted', 'town_ready')):
        return False
    account, store, session_id = s.account, s.account.store, s.shop_session_id
    pending = getattr(s, 'town_warp_transition', None)
    try:
        if pending is not None:
            if not _village1012_pending(s, pending, account, store, session_id):
                return False
            context = pending['binding']['context']
            village1012_committed(store.path, account.uid, account.account_id, context['source'], pending['payload'],
                pending['operation'], context, pending,
                authorize=lambda: _village1012_pending(s, pending, account, store, session_id))
            return True
        # Restoring an already saved map is not a cross-scene paid warp. No new
        # receipt, debit, location update or historical-response replay occurs.
        saved = village1012_snapshot(store.path, account.uid, account.account_id,
            authorize=lambda: bool(_village1012_identity(s) and s.account is account and account.store is store
                and s.shop_session_id == session_id and getattr(s, 'town_warp_transition', None) is None
                and s.phase in ('map_loading', 'square_accepted', 'town_ready')))
        # Current Village1011 Start1710 links to1012 Start1712. This is the
        # original walking225/227 path, not a paid58C transition. Keep the
        # source-bound reader here; the caller still applies1012's current
        # level99/completed27600 gates before acknowledging225. Only227 saves
        # the arrived position; no fee, receipt, quest or reward is created.
        if saved['location']['town'] == 1011 and account.get_location()['map'] == 1011:
            from els_server.domain.town_travel import catalog
            towns = catalog()['towns']
            return bool(_village1012_identity(s) and s.account is account and account.store is store
                and s.shop_session_id == session_id and s.active_map == 1011
                and s.phase in ('town_ready', 'square_accepted') and not s.dungeon_return_pending
                and getattr(s, 'pending_map', None) in (None, 1011, 1012)
                and towns['1011']['requirement']['AFTER'] == 1012
                and towns['1012']['requirement']['BEFORE'] == 1011)
        if saved['location']['town'] != 1012 or account.get_location()['map'] != 1012:
            return False
        if s.dungeon_return_pending:
            origin = getattr(s, 'village1012_return_origin', None)
            return bool(isinstance(origin, dict) and origin.get('owner') == account.uid
                and origin.get('account') == account.account_id and origin.get('store') is store
                and origin.get('session_id') == session_id and origin.get('source') == 1012
                and origin.get('run_id') == s.reward_run_id and origin.get('dungeon') == s.dungeon_id
                and getattr(s, 'dungeon_participants', None) == frozenset((account.uid,))
                and isinstance(s.dungeon_end_payload, bytes) and 100 <= len(s.dungeon_end_payload) <= 8192
                and s.dungeon_end_payload[:4] == struct.pack('>i', 0x72) and s.phase == 'map_loading')
        # A dungeon-origin transition cannot masquerade as a cold restore just
        # by clearing the pending-return boolean while a live run remains.
        return bool(s.phase in ('map_loading', 'square_accepted', 'town_ready')
                    and (getattr(s, 'dungeon_end_payload', None) is None or s.active_map == 1012))
    except (ValueError, OverflowError, KeyError, TypeError, AttributeError):
        return False


def capture_village1012_origin(s, event):
    """Read-only source capture around existing successful solo admission."""
    if (event.event_id != 0x202 or event.kind not in (0x37f, 0x382)
            or s.phase != 'town_ready' or s.active_map != 1012 or not _village1012_identity(s)):
        return None
    from els_server.storage.town_travel import village1012_snapshot
    try:
        saved = village1012_snapshot(s.account.store.path, s.account.uid, s.account.account_id,
                                    authorize=lambda: _village1012_identity(s) and s.phase == 'town_ready' and s.active_map == 1012)
        if saved['location']['town'] != 1012:
            return None
        return dict(owner=s.account.uid, account=s.account.account_id, store=s.account.store,
                    session_id=s.shop_session_id, source=1012, prior_run=getattr(s,'reward_run_id',None))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def finish_village1012_origin(s, origin):
    if origin is None:
        return
    # No admission or dungeon behavior is added here: only capture an existing
    # successful solo run's exact actor/source/run. Unproved other paths close.
    s.village1012_return_origin = None
    try:
        run = uuid.UUID(s.reward_run_id)
        if (not _village1012_identity(s) or s.phase != 'dungeon_loading'
                or s.account.uid != origin['owner'] or s.account.account_id != origin['account']
                or s.account.store is not origin['store'] or s.shop_session_id != origin['session_id']
                or s.reward_run_id == origin['prior_run'] or str(run) != s.reward_run_id or run.version != 4
                or getattr(s, 'dungeon_participants', None) != frozenset((s.account.uid,))):
            return
        s.village1012_return_origin = dict(origin, run_id=s.reward_run_id, dungeon=s.dungeon_id)
    except (ValueError, AttributeError, TypeError, KeyError):
        return
