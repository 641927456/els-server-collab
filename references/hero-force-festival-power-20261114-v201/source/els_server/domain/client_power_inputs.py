"""Saved combat inputs used to expire client reports, without calculating CP."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,time
from els_server.domain.item_expiration import expired
from els_server.storage.erp_support_quest_scope import _table_snapshot
from els_server.storage.inventory_state import load_equipped_items
from els_server.storage.guild_membership_state import snapshot as guild_snapshot
from els_server.storage.wardrobe import counts as wardrobe_counts
from els_server.storage.companion_state import rows as companions
from els_server.storage.ordinary_skill_pages import _current_slots
from els_server.domain.resonance_allocation_flow import profiles as resonance_profiles
from els_server.storage.resonance_period import active as resonance_blessing

def snapshot(session, *, db=None):
    if db is None:
        with closing(sqlite3.connect(Path(session.account.store.path).resolve().as_uri()+'?mode=ro',uri=True)) as saved:
            saved.execute('BEGIN')
            return snapshot(session,db=saved)
    account = session.account
    uid = account.uid
    with _table_snapshot(db):
        now = int(time.time())
        character, = account.characters._project_rows(db, uid)
        if character['pending_delete']:
            raise ValueError('Client power role is pending deletion')
        character = {key: value for key, value in character.items()
                     if key not in ('normal_fatigue', 'life_stamina', 'cleared_dungeons', 'known_resurrection_count', 'luciel_active_unit', 'luciel_active_revision')}
        if character.get('resonance') is not None:
            character['resonance'] = {key:value for key,value in character['resonance'].items()
                                      if key not in ('experience','revision','level')}
        if character.get('artifact') is not None:
            character['artifact'] = {key:value for key,value in character['artifact'].items()
                                     if key != 'experience'}
        # ERP level and invested points arrive through different native
        # messages. Keep the selected allocation, not its revision or
        # unspent budget, which can change during this kill's own EXP.
        allocation = None
        if character['resonance']['enabled'] and db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='resonance2026_characters'").fetchone():
            profile = resonance_profiles(db)
            pages = profile.pages.read(account.account_id, uid)
            if pages is not None:
                metadata = profile._metadata(account.account_id, uid) if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='resonance2026_profile_metadata'").fetchone() else None
                allocation = dict(enabled=pages.enabled, selected_page=pages.selected_page,
                                  points=pages.selected().points, opaque=None if metadata is None else metadata[1])
        character['resonance_allocation'] = allocation
        character['resonance_blessing'] = (resonance_blessing(db, account.account_id, uid, now=now)
                                           if character['resonance']['enabled'] else None)
        collection = character.get('el_search_collection')
        if collection is not None:
            # Original collection synergy includes its exact expiry second.
            character['collection_synergy_current'] = bool(collection['active'] and collection['expiry'] >= now)
        character['guild_membership'] = guild_snapshot(db, uid, account.account_id)
        character['wardrobe'] = wardrobe_counts(db, uid, account.account_id)
        # Reuse the full Unit's four worn groups, including Artifact gear.
        # Bag positions/counts do not invalidate the combat calculation.
        items = load_equipped_items(db, uid)
        skills = _current_slots(db, uid, character)
        validity = [(item['uid'], expired(item, now=now)) for item in items]
        pet = None
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone():
            row = db.execute('SELECT pet FROM companion_active WHERE owner=?', (uid,)).fetchone()
            if row and row[0]:
                pet = next(value for value in companions(db, uid, 'pet') if value['uid'] == row[0])
                pet = dict(pet, current=not pet.get('expires_at') or now < pet['expires_at'])
        inputs = character, items, skills, validity, pet
    encoded = json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()
    return inputs, hashlib.sha256(encoded).hexdigest()
