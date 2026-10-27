"""One owned SQL snapshot for authoritative native attribute production.

No data value is borrowed from session projection caches or a second database
connection. The read transaction ends before expensive arithmetic or encoding.
This is source acquisition; it does not assign a combat total or send packets.
"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sqlite3
import time


def attach_character_sources(db, owner, character, *, at=None):
    """Complete the narrow quest-role reader using same-connection helpers."""
    from els_server.storage.titles import snapshot as titles,completed_for_equipment
    from els_server.storage.boosting_2026_force_inventory import saved as owned_forces
    from els_server.storage.boosting_2026_force_equipment import saved as equipped_forces
    from els_server.storage.skill_traits import saved as saved_traits
    from els_server.storage.ordinary_skill_pages import view as page_view
    title_source=titles(db,owner,now=at)
    character['title']=title_source['title']
    character['title_source']=title_source
    character['title_completed_quests']=completed_for_equipment(db,owner)
    character['force_inventory']=owned_forces(db,owner)
    character['force_slots']=equipped_forces(db,owner)
    traits=saved_traits(db,owner)
    if traits:
        from els_server.domain.skill_traits import visible
        character['skill_traits']=visible(character,traits)
    pages=page_view(db,owner)
    if pages['count']>1:character['ordinary_skill_pages']=pages
    if character.get('unit_type')==10:
        from els_server.storage.luciel_state import state,active_state
        character['luciel_style']=state(db,owner)['style']
        character['luciel_active_unit']=active_state(db,owner)['active_unit']


def read_companion_sources(db, owner, *, at=None):
    """Read pets without invoking mount settlement or login/schema writers."""
    tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present={'companions','companion_active'}&tables
    if not present:return dict(pets=(),mounts=(),active_pet=0,active_mount=0,mounted=False)
    if len(present)!=2:raise ValueError('Incomplete companion source schema')
    from els_server.storage.companion_state import rows
    # rows(...,'pet') uses the established read-only attachments. Asking for
    # all companions would invoke mount_state.attach/settle and write a clock.
    pets=tuple(rows(db,owner,'pet'))
    mounts=[]
    for row in db.execute('SELECT uid,owner,kind,unit,name,source_item FROM companions WHERE owner=? AND kind=? ORDER BY uid',(owner,'mount')):
        value=dict(zip(('uid','owner','kind','unit','name','source_item'),row))
        runtime=db.execute('SELECT owner,stamina,accounted_at,ridden FROM mount_runtime WHERE uid=?',(row[0],)).fetchone()if 'mount_runtime'in tables else None
        if runtime is not None and runtime[0]!=owner:raise ValueError('Companion runtime owner differs')
        value['saved_runtime']=runtime
        mounts.append(value)
    active=db.execute('SELECT pet,mount,mounted FROM companion_active WHERE owner=?',(owner,)).fetchone()or(0,0,0)
    if (any(type(v)is not int for v in active)or min(active[:2])<0 or active[2]not in(0,1)):
        raise ValueError('Invalid saved active companion source')
    pet,mount,mounted=active
    if pet:
        selected=next((p for p in pets if p['uid']==pet),None)
        if selected is None:raise ValueError('Active pet source ownership differs')
        from els_server.storage.boosting_2026_limited_pet import require_current
        require_current(selected,at=at)
    selected_mount=next((p for p in mounts if p['uid']==mount),None)
    if mount and selected_mount is None:raise ValueError('Active mount source ownership differs')
    if mounted and (selected_mount is None or selected_mount['saved_runtime']is None):
        raise ValueError('Mounted source requires committed runtime')
    return dict(pets=pets,mounts=tuple(mounts),active_pet=pet,active_mount=mount,mounted=bool(mounted))


def read_world_effect_sources(db, owner, at):
    """Retain the installed ordinary/economic reader and source receipts.

    The currently installed helper owns retained consumers and LOCAL reader
    differences. Do not reproduce an older three-item catalog here, settle
    anything or use a new connection. Its encoder moment is not a modifier
    input: retaining it in the source digest would invalidate caches each
    second even when every actual effect and deadline stayed unchanged.
    """
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name GLOB 'world_elixir_*' LIMIT 1").fetchone():
        return dict(owner=owner,revision=0,rows=[])
    from els_server.storage.world_elixirs import _state,_clock
    state=_state(db,owner,_clock(at))
    if (not {'owner','revision','rows'}<=set(state)or set(state)-{'owner','revision','rows','_moment'}
            or state['owner']!=owner):raise ValueError('Installed world effect source shape differs')
    return {key:state[key]for key in('owner','revision','rows')}


def read_resonance_profile(db, owner, account_id):
    """Read the selected page after the ordinary allocation synchronizer.

    This reader never provisions missing pages or credits earned levels. The
    canonical writer must finish first, otherwise an enabled account would
    incorrectly look like a complete zero-allocation character.
    """
    if not db.in_transaction:
        raise ValueError('Native resonance source requires caller snapshot')
    from dataclasses import asdict
    from els_server.storage.resonance_state import snapshot
    current=snapshot(db,owner,account_id)
    if not current['enabled']:
        return dict(account=current,profile=None)
    tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'resonance2026_characters','resonance2026_profile_metadata'}<=tables:
        raise ValueError('Native resonance source requires synchronized character pages')
    from els_server.domain.resonance_allocation_flow import profiles
    source=profiles(db)
    progress=source.accounts._read(account_id)
    pages=source.pages.read(account_id,owner)
    metadata=source._metadata(account_id,owner)
    if progress is None or pages is None or metadata is None:
        raise ValueError('Native resonance source requires complete existing profile')
    if (progress.revision,progress.level,progress.cumulative_experience)!=(
            current['revision'],current['level'],current['experience']):
        raise ValueError('Native resonance account authority differs')
    earned,opaque=metadata
    if earned!=progress.level:
        raise ValueError('Native resonance level credit requires canonical synchronization')
    state=source._state(progress,pages,opaque)
    return dict(account=current,profile=dict(revision=pages.revision,
        earned_level=earned,pages=asdict(pages),state=asdict(state)))


def read_in_transaction(db, owner, account_id, *, at=None):
    from els_server.storage.character_schema import character_uid
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.seal_quests import load_character, current_slots
    from els_server.storage.inventory_state import load_items
    from els_server.domain.character_rules import validate_career_state
    owner=character_uid(owner)
    at=int(time.time())if at is None else at
    if type(at)is not int or not 0<at<2**31-7200:raise ValueError('Native source validity time')
    if type(account_id) is not int or not 0<account_id<2**63:
        raise ValueError('Native attribute account identity')
    if not db.in_transaction:
        raise ValueError('Native attribute source requires caller snapshot')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account_id,):
        raise ValueError('Native attribute source ownership changed')
    require_active_character(db,owner)
    character=load_character(db,owner,account_id)
    attach_character_sources(db,owner,character,at=at)
    validate_career_state(character)
    items=tuple(load_items(db,owner))
    slots=tuple(current_slots(db,character))
    resonance=read_resonance_profile(db,owner,account_id)
    companions=read_companion_sources(db,owner,at=at)
    world_effects=read_world_effect_sources(db,owner,at)
    if character['uid']!=owner:
        raise ValueError('Native attribute source identity changed')
    # The narrow quest-role reader supplies artifact/seals/collection/guild
    # and basic account resonance. The same-connection attachments above add
    # title qualification, force ownership/loadout, traits and page metadata;
    # selected ERP allocations are separate. ordinary_slots are skill-bar
    # slots, not worn equipment slots.
    # All attached item instances come from the very same db.
    value=dict(owner=owner,account_id=account_id,character=character,
               items=items,ordinary_slots=slots,resonance=resonance,companions=companions,
               world_effects=world_effects)
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
    return dict(deepcopy(value),source_sha256=hashlib.sha256(raw).hexdigest())


def capture(path, owner, account_id, *, at=None):
    path=Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,
                               isolation_level=None,timeout=10)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        try:
            return read_in_transaction(db,owner,account_id,at=at)
        finally:
            db.rollback()
