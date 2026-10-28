"""Native ERP panel inputs over the existing formal account authority.

Reuses the pinned 610/611/612/79E/79F codecs and transactional page stores.
The reviewed local one-page/no-bonus initial policy stays explicit. No
campaign enrollment, XP grant, page expansion or effect formula.
Negative611edits use published710106/163563coins; temporary points,
category613 accepts only the reviewed ordinary scroll positive refund route.
"""
from contextlib import closing
from functools import lru_cache
from pathlib import Path
import sqlite3,struct
from els_server.storage.resonance_period import bonus as period_bonus
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.resonance_2026_profiles import ResonanceProfiles,NEW_PROFILE_POLICY
from els_server.storage.resonance_2026_operations_v2 import ResonanceOperationsV2,ResonanceOpaqueFields
from els_server.protocol.resonance_2026_request import ResonanceAllocationRequest
from els_server.protocol.resonance_2026_page_switch import page_switch_request,page_switch_reply
from els_server.protocol.resonance_2026_state import ResonanceCharacterState
from els_server.protocol.resonance_2026_reply import snapshot_reply


@lru_cache(maxsize=1)
def definitions():
    from els_server.domain.resonance_2026_curve import ResonanceCurve
    from els_server.domain.resonance_2026_allocations import ResonanceAllocations
    from els_server.game_data import client_data
    raw=(Path(__file__).resolve().parents[1]/'data/resonance2026-stats.json').read_bytes()
    ResonanceAllocations.from_original(raw)
    return ResonanceCurve.from_client_data(client_data()),raw


def enabled(s):
    return (s.role=='game' and s.client_build=='dx11_260923' and s.item_test
        and s.account.store is not None and s.account.characters is not None
        and not getattr(s,'released',False))


def profiles(db):
    curve,stats=definitions()
    return ResonanceProfiles(db,curve,stats,new_profile_policy=NEW_PROFILE_POLICY)


def prepare(db,s):
    from els_server.storage.resonance_state import snapshot
    p=profiles(db);p.pages.owner(s.account.account_id,s.account.uid)
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,s.account.uid)
    if not snapshot(db,s.account.uid,s.account.account_id)['enabled']:
        raise ValueError('ERP is not opened by an authoritative source')
    p.initialize()
    p.accounts.migrate_dominated_legacy(account=s.account.account_id,character=s.account.uid)
    state=p.synchronize(account=s.account.account_id,character=s.account.uid)
    return p,state


def synchronize(s,messages,current):
    if not enabled(s) or s.account.character()['level']<99:return messages
    with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
        # Fast read of the authoritative revisions. Schema/projection writes
        # happen only for an initial profile or changed account/page state.
        tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        row=db.execute('SELECT revision FROM resonance2026_characters WHERE character=? AND account=?',
            (s.account.uid,s.account.account_id)).fetchone() if 'resonance2026_characters' in tables else None
        from els_server.storage.resonance_period import key as period_key
        period=period_key(db,s.account.account_id,s.account.uid)if 'character_resonance_period'in tables else None
        key=(s.account.account_id,s.account.uid,current['revision'],row,period)
        if getattr(s,'resonance_page_sync_key',None)==key:return messages
        try:
            db.execute('BEGIN IMMEDIATE');p,state=prepare(db,s);notice=state.notice();encode_event(notice)
            revision=p.pages.read(s.account.account_id,s.account.uid).revision
            db.commit()
        except ValueError:
            # Unknown legacy/profile metadata is kept intact. It must not
            # prevent ordinary login or be replaced with guessed zero pages.
            db.rollback();return messages
    s.resonance_page_sync_key=(s.account.account_id,s.account.uid,current['revision'],(revision,),period)
    return [*messages,notice]


def failure(s,kind):
    state=ResonanceCharacterState(0,0,0,False,(),0,0,0,0,0,0,0)
    if kind==0x79e:return page_switch_reply(result=256,state=state)
    # Complete error DTO consumed before the original result-256 gate.
    return Event(0x201,kind=0x614 if kind==0x613 else 0x612,payload=struct.pack('>iiQiBIIQBB',256,0,0,0,0,0,0,0,0,0))


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x611,0x613,0x79e) or not enabled(s):return None
    if (type(sequence) is not int or not 1<=sequence<2**32 or event.performers!=(0,)
        or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):return []
    from els_server.domain.equipment_chip_flow import current_lease
    if s.account.store.uid!=s.account.uid or not current_lease(s):return [failure(s,event.kind)]
    try:
        if s.phase!='town_ready' or s.account.character()['level']<99:
            raise ValueError('Town and full-level character required')
        if event.kind==0x611:ResonanceAllocationRequest.decode(event.payload)
        elif event.kind==0x613:
            from els_server.protocol.resonance_2026_scroll import scroll_request
            scroll_request(event.payload)
        else:page_switch_request(event.payload)
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE');p,state=prepare(db,s)
            account,character=s.account.account_id,s.account.uid
            current=p.pages.read(account,character);metadata=p._metadata(account,character)
            if not current.enabled or metadata[1]!=(0,0,0,0,0):
                raise ValueError('Temporary or disabled profile requires its own verified policy')
            operation='native-erp:'+s.shop_session_id+':'+str(character)+':'+str(sequence)
            old=db.execute('SELECT revision FROM resonance2026_page_receipts WHERE character=? AND operation=?',
                (character,operation)).fetchone()
            expected=current.revision if old is None else old[0]-1
            ops=ResonanceOperationsV2(db,*definitions())
            if event.kind==0x611:
                request=ResonanceAllocationRequest.decode(event.payload)
                if any(delta<0 for tab,values in request.groups for stat,delta in values):
                    from els_server.domain.resonance_2026_reset_items import reset_items
                    from els_server.storage.resonance_2026_resets import ResetOperations,initialize
                    initialize(db)
                    reply=ResetOperations(db,*definitions(),reset_items()).edit(account=account,character=character,
                        operation=operation,expected_revision=expected,payload=event.payload,kind=0x611)
                else:
                    reply=ops.allocate(account=account,character=character,operation=operation,
                        expected_revision=expected,payload=event.payload,bonus_points=period_bonus(state),result=0,trailing_value=0)
            elif event.kind==0x613:
                from els_server.domain.resonance_category_scroll import scroll_items
                from els_server.storage.resonance_2026_scrolls import ScrollOperations
                from els_server.storage.resonance_2026_resets import initialize
                initialize(db)
                reply=ScrollOperations(db,*definitions(),scroll_items()).edit(account=account,character=character,
                    operation=operation,expected_revision=expected,payload=event.payload,kind=0x613)
            else:
                reply=ops.select(account=account,character=character,operation=operation,
                    expected_revision=expected,payload=event.payload,opaque_fields=ResonanceOpaqueFields(*metadata[1]))
            if event.kind==0x79e:
                reply=page_switch_reply(result=0,state=p.synchronize(account=account,character=character))
            encode_event(reply)
        return [reply]
    except ValueError:return [failure(s,event.kind)]
