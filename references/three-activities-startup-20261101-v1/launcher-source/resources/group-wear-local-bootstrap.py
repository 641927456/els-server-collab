"""Install a signed, accepted LOCAL runtime beside a clean Git checkout, without executing it."""
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid

FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
OVERRIDES = {'els_server/storage/wear_moves.py', 'tools/native_cache_sync.js', 'els_server/storage/life_stamina.py', 'els_server/data/dungeon_source_loot.json', 'els_server/storage/blacksmith_enhancement.py', 'els_server/domain/drop_pickup.py', 'els_server/friends_relay.py', 'els_server/domain/field_boss.py', 'els_server/domain/silver_mirror_flow.py', 'els_server/storage/boosting_2026_accessories.py', 'els_server/data/formal_pve_economy.manifest.json', 'els_server/application.py', 'els_server/domain/fishing_bait_loot.py', 'els_server/domain/formal_pve_economy.py', 'els_server/domain/cartridge_selection_box.py', 'els_server/domain/retained_native_consumables.py', 'els_server/storage/promotion_reward_boxes.py', 'els_server/data/town_travel.json', 'els_server/domain/market_conversion_rules.py', 'analysis/shop-listing-20261015/fashion-bundles.json', 'els_server/storage/account_fishing_tasks_scope.py', 'tools/native_cache_sync.py', 'els_server/friends_bridge.py', 'els_server/domain/dungeon_settlement_commands.py', 'tools/trace_dx11_login.js', 'els_server/protocol/field_boss_messages.py', 'els_server/storage/skill_unlocks.py', 'els_server/data/character_custom_permanent.json', 'els_server/storage/furniture_boxes.py', 'els_server/storage/boosting_2026_participation_gear.py', 'els_server/domain/title_economy.py', 'tools/launch_friends_client.py', 'els_server/data/story_quests.json', 'els_server/domain/owned_growth_items.py', 'els_server/storage/published_2026_bundles.py', 'els_server/domain/dungeon_loot_catalog.py', 'els_server/domain/fashion_singles.py', 'analysis/client-6c6b5180/extended-shop-body-proof.json', 'els_server/storage/boosting_2026_fashion_rewards.py', 'els_server/storage/white_armor_boxes.py', 'els_server/domain/skill_expansion.py', 'els_server/domain/region_quests.py', 'els_server/storage/shop_state.py', 'els_server/domain/elixir_economy.py', 'els_server/domain/pve_economy_flow.py', 'els_server/enchant_data.py', 'els_server/domain/boosting_2026_force_inventory.py', 'els_server/storage/wardrobe_ticket_box.py', 'els_server/domain/accessory_identification.py', 'els_server/storage/bag_capacity.py', 'els_server/domain/cubes.py', 'els_server/domain/dungeon_flow.py', 'tools/launch_client.py', 'els_server/domain/skill_state.py', 'els_server/domain/story_controller_retirements.py', 'els_server/domain/tutorial_accessory.py', 'els_server/storage/companion_state.py', 'els_server/storage/local_clear_rules.py', 'els_server/storage/boosting_2026_nested_capacity.py', 'els_server/domain/friends_world.py', 'els_server/storage/town_travel.py', 'els_server/storage/character_custom.py', 'els_server/data/fashion_singles.json', 'els_server/storage/player_mail.py', 'els_server/storage/boosting_2026_limited_pet.py', 'els_server/domain/town_travel.py', 'els_server/storage/town_dialogue.py', 'els_server/domain/boosting_2026_force_equipment.py', 'els_server/storage/boosting_2026_force_rewards.py', 'els_server/domain/equipment_ui_flow.py', 'els_server/data/story_quests.manifest.json', 'els_server/domain/dungeon_source_loot.py', 'els_server/domain/fishing_village1500.py', 'els_server/storage/raid_reward_actions.py', 'els_server/data/client/dungeon_routes.json', 'els_server/domain/acquisition_policy.py', 'els_server/domain/character_custom.py', 'els_server/storage/reward_state.py', 'els_server/data/dungeon_material_loot_catalog.json', 'els_server/domain/boosting_2026_participation_gear.py', 'els_server/data/market_conversion.json', 'els_server/domain/pet_support_flow.py', 'els_server/storage/wisdom_potions.py', 'els_server/domain/town_travel_flow.py', 'els_server/storage/teacher_elixir_boxes.py', 'tools/probe_updated_client.py', 'els_server/domain/quest_flow.py', 'els_server/storage/boosting_2026_force_inventory.py', 'els_server/storage/artifact_progression.py', 'els_server/storage/enhancement_scroll.py', 'analysis/shop-listing-20261015/bundle-order.json', 'els_server/storage/epic_followups.py', 'els_server/domain/raid_reward_items.py', 'els_server/storage/elixir_economy.py', 'els_server/domain/el_search_collection.py', 'els_server/storage/titles.py', 'config/dungeon_local_rules.json', 'els_server/domain/friends_dungeon.py', 'els_server/storage/expansion_items.py', 'els_server/data/accessory_identification_groups.json', 'els_server/domain/raid_economy_flow.py', 'els_server/storage/fixed_cubes.py', 'els_server/domain/wisdom_potions.py', 'els_server/domain/identification_ui.py', 'els_server/storage/potion_choice_box.py', 'els_server/domain/black_market_box_rules.py', 'els_server/domain/dungeon_material_loot_catalog.py', 'els_server/storage/wardrobe.py', 'els_server/data/town_travel.manifest.json', 'els_server/data/dungeon_loot_catalog.json', 'els_server/protocol/quest_messages.py', 'els_server/transport.py', 'els_server/storage/el_search_collection.py', 'tools/local_fresh_state.py', 'els_server/storage/seal_quests.py', 'els_server/domain/dungeon_equipment_loot_flow.py', 'els_server/domain/dungeon_routes.py', 'els_server/domain/sage_sockets.py', 'analysis/shop-standalone-20261015/ice-shop-exclusions.json', 'els_server/domain/housing_room_flow.py', 'els_server/domain/shop_listing.py', 'els_server/domain/inventory_items.py', 'els_server/data/formal_pve_economy.json', 'els_server/storage/dungeon_equipment_loot.py', 'els_server/data/client/dungeon_routes.manifest.json', 'els_server/domain/local_session.py', 'els_server/storage/pet_support.py', 'els_server/storage/local_state.py', 'els_server/data/retained_native_consumables.json', 'analysis/client-6c6b5180/extended-shop-catalog.json', 'els_server/storage/resonance_state.py', 'els_server/domain/role_progression.py', 'els_server/domain/seal_quests.py', 'analysis/shop-listing-20261015/fashion-bundles-body-proof.json', 'els_server/domain/session_dispatch.py', 'els_server/protocol/character_custom_messages.py', 'tools/client_compatibility_profiles.json', 'els_server/storage/boosting_2026_title_rewards.py', 'els_server/storage/job_reward_boxes.py', 'els_server/storage/inventory_state.py', 'els_server/domain/dungeon_drops.py', 'els_server/data/identification_ui.json', 'els_server/storage/force_rank4_schema.py', 'els_server/storage/paid_enhancement.py', 'els_server/data/fashion_singles.manifest.json'}
ADDITIONS = {'els_server/domain/group_wear.py', 'tools/native_group_wear_sync.py', 'tools/group_wear_sync.js', 'els_server/domain/el_search_effects.py', 'els_server/protocol/guidebook_messages.py', 'els_server/data/enhancement_unlock.json', 'els_server/data/pvp_seven.json', 'els_server/domain/pet_expedition.py', 'els_server/data/mentor45000.json', 'els_server/domain/friends_pvp.py', 'els_server/domain/weapon_growth.py', 'els_server/domain/clear_ed_display.py', 'els_server/data/owned_reward_boxes.json', 'els_server/domain/weapon_growth_flow.py', 'els_server/domain/pvp_official_1v1_policy.py', 'els_server/protocol/pvp_room_messages.py', 'els_server/domain/special_quest_rewards.py', 'els_server/domain/owned_reward_boxes.py', 'els_server/domain/guidebook_flow.py', 'els_server/data/cooking_clear_materials.json', 'els_server/protocol/pvp_death_messages.py', 'els_server/domain/pvp_registration.py', 'els_server/domain/native_force_exchange_flow.py', 'els_server/protocol/weapon_growth_messages.py', 'els_server/data/weapon_growth.json', 'els_server/protocol/pvp_match_messages.py', 'els_server/storage/henir_force_rewards.py', 'els_server/data/el_search_collection_tickets.json', 'analysis/shop-missing-20261031-v1/CharCustomData.tables.json', 'els_server/domain/pvp_round.py', 'tools/dungeon_map_markers.py', 'els_server/storage/collection_synergy.py', 'els_server/data/field_travel.manifest.json', 'els_server/domain/el_search_collection_flow.py', 'els_server/data/secret_fragment_box.json', 'els_server/domain/public_controller_rules.py', 'els_server/protocol/pvp_loading_messages.py', 'els_server/storage/mentor45000_scope.py', 'els_server/domain/native_force_catalog.py', 'els_server/storage/pvp_settlement.py', 'els_server/domain/pvp_support.py', 'els_server/domain/pvp_quests.py', 'analysis/shop-onepiece-20261031-v1/fashion-exclusions.json', 'els_server/domain/secret_fragment_box.py', 'els_server/protocol/pvp_result_messages.py', 'analysis/shop-missing-20261031-v1/package-membership-supplement.json', 'tools/local_fresh_state.py', 'els_server/data/secret_clear_rewards.manifest.json', 'els_server/domain/mentor45000.py', 'els_server/storage/native_force_exchange.py', 'els_server/data/secret_clear_rewards.json', 'els_server/protocol/pet_expedition_messages.py', 'tools/world_event_iteration.py', 'els_server/domain/el_search_collection_tickets.py', 'els_server/data/el_search_effects.json', 'els_server/domain/pet_expedition_flow.py', 'els_server/protocol/bag_expansion_messages.py', 'els_server/data/native_line_triggers.json', 'els_server/domain/secret_clear_rewards.py', 'tools/world_event_iteration.js', 'els_server/domain/el_search_collection_quest.py', 'els_server/storage/pet_expedition.py', 'els_server/domain/field_travel.py', 'tools/native_wear_sync.py', 'els_server/domain/native_line_triggers.py', 'els_server/domain/pvp_loading.py', 'els_server/data/native_force_catalog.json', 'els_server/domain/native_script_loot.py', 'els_server/storage/el_search_collection_tickets.py', 'tools/native_wear_sync.js', 'els_server/storage/weapon_growth.py', 'tools/pvp_hp_source.js', 'els_server/data/special_task_readers.json', 'els_server/domain/bag_expansion_flow.py', 'els_server/protocol/pvp_play_messages.py', 'els_server/domain/enhancement_unlock.py', 'els_server/domain/cooking_clear_materials.py', 'els_server/storage/guidebook.py', 'tools/dungeon_map_markers.js', 'els_server/data/field_travel.json', 'els_server/domain/session_auxiliary.py', 'els_server/storage/pvp_official_profiles.py', 'els_server/domain/pvp_actor.py', 'tools/pvp_hp_source.py', 'analysis/shop-onepiece-20261031-v1/native-body-proof.json'}
RESERVED = {'con', 'prn', 'aux', 'nul'} | {f'{p}{i}' for p in ('com', 'lpt') for i in range(1, 10)}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def hash_text(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def relative(value):
    need(isinstance(value, str) and 0 < len(value) <= 220, 'Invalid relative runtime path')
    need(not any(c in value for c in '\\:\x00\r\n*?"<>|'), 'Unsafe relative runtime path')
    path = PurePosixPath(value)
    need(not path.is_absolute() and str(path) == value, 'Noncanonical relative runtime path')
    need(all(p not in ('', '.', '..') and p == p.rstrip(' .') and
             p.split('.')[0].casefold() not in RESERVED for p in path.parts), 'Unsafe runtime leaf')
    return path


def no_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        need(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()),
             'Linked installation or source paths are refused')
    return path


def under(root, name):
    relative(name)
    root = no_links(root)
    path = root.joinpath(*PurePosixPath(name).parts)
    no_links(path)
    need(path.resolve().is_relative_to(root.resolve()), 'Runtime path escaped its root')
    return path


def read(path, maximum=4 * 1024 * 1024):
    path = no_links(path)
    need(path.is_file() and path.stat().st_size <= maximum, 'Missing or oversized JSON document')
    return json.loads(path.read_bytes())


def encoded(document):
    return (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def write_new(path, data):
    no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def atomic_new(path, data):
    """Publish a complete file atomically, refusing replacement on every platform."""
    no_links(path)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        write_new(temporary, data)
        # Same-directory NTFS/POSIX link creation is atomic and fails if path exists.
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def progress(percent, message):
    print('ELS_BOOTSTRAP_PROGRESS:' + json.dumps({'percent': percent, 'message': message}, ensure_ascii=True), flush=True)


def rows(document):
    need(isinstance(document, dict) and isinstance(document.get('files'), list), 'Invalid verified runtime manifest')
    need(0 < len(document['files']) <= 4096, 'Runtime manifest file count exceeded')
    result, names, total = {}, set(), 0
    for row in document['files']:
        need(isinstance(row, dict), 'Invalid runtime entry')
        path = str(relative(row.get('path')))
        need(path.casefold() not in names and hash_text(row.get('sha256')) and
             type(row.get('size')) is int and 0 <= row['size'] <= 268435456, 'Invalid or duplicate runtime entry')
        names.add(path.casefold())
        total += row['size']
        need(total <= 2147483648, 'Runtime size budget exceeded')
        result[path] = {'path': path, 'size': row['size'], 'sha256': row['sha256']}
    return result


def source_rows_hash(file_rows):
    canonical = json.dumps([file_rows[path] for path in sorted(file_rows)], sort_keys=True,
                           separators=(',', ':'), ensure_ascii=False).encode('utf8')
    return hashlib.sha256(canonical).hexdigest()


def verify(root, row):
    path = under(root, row['path'])
    need(path.is_file() and path.stat().st_size == row['size'] and digest(path) == row['sha256'],
         'Runtime file failed SHA verification: ' + row['path'])


def git(repo, *arguments):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('GIT_'):
            del env[key]
    # Preserve the user's established text/eol normalization. Disabling their
    # Git configuration would falsely mark a clean CRLF checkout as modified.
    # No hooks or fsmonitor commands are allowed in these read-only operations.
    env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    process = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
                              *arguments], cwd=repo, env=env, capture_output=True, timeout=120, creationflags=FLAGS)
    need(process.returncode == 0, 'Git repository verification failed')
    return process.stdout


def git_json(repo, commit, path):
    relative(path)
    raw = git(repo, 'cat-file', '-p', commit + ':' + path)
    need(len(raw) <= 8 * 1024 * 1024, 'Git metadata size exceeded')
    return json.loads(raw)


def git_unchanged(repo, commit):
    need(git(repo, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip() == commit,
         'Git HEAD changed during initialization')
    need(not git(repo, 'status', '--porcelain', '--untracked-files=all', '--ignore-submodules=all').strip(),
         'Git checkout has uncommitted or untracked changes')


def source_binding(repo, commit, runtime, manifest_rows, metadata):
    need(metadata.get('schema') == 1 and re.fullmatch('[a-z0-9][a-z0-9-]{0,95}', metadata.get('release', '')),
         'Invalid signed local source metadata')
    need(hash_text(metadata.get('source_formal_manifest_sha256')), 'Invalid source acceptance hash')
    selection = git_json(repo, commit, 'channels/current-engine.json')
    local = selection.get('accepted', {}).get('local', {})
    need(local.get('release') == metadata.get('source_release') and
         local.get('formal_manifest_sha256') == metadata['source_formal_manifest_sha256'] and
         selection.get('profile') == metadata.get('profile'), 'Git LOCAL acceptance differs from signed package')
    profile = git_json(repo, commit, selection['profile'])
    entries = profile.get('channels', {}).get('local', {}).get('files')
    need(isinstance(entries, list) and entries, 'Git LOCAL profile is incomplete')
    formal = rows({'files': entries})
    need(type(metadata.get('source_file_count')) is int and metadata['source_file_count'] == len(formal) and
         hash_text(metadata.get('source_files_sha256')) and
         source_rows_hash(formal) == metadata['source_files_sha256'],
         'Git LOCAL complete business index differs from the signed package')
    need('config/server.toml' in formal and
         hash_text(metadata.get('generated_config_source_sha256')) and
         metadata['generated_config_source_sha256'] == formal['config/server.toml']['sha256'] and
         'config/server.toml' not in manifest_rows,
         'Signed generated local configuration binding differs')
    original_entries = {entry['path']: entry for entry in entries}
    locked = rows(git_json(repo, commit, 'runtime-assets.lock.json'))
    overrides = {}
    for row in metadata.get('support_overrides', []):
        path = str(relative(row.get('path')))
        need(path in OVERRIDES and path not in overrides and path in formal and
             hash_text(row.get('source_sha256')) and hash_text(row.get('runtime_sha256')) and
             formal[path]['sha256'] == row['source_sha256'] and path in manifest_rows and
             manifest_rows[path]['sha256'] == row['runtime_sha256'], 'Invalid signed support override')
        overrides[path] = row
    additions = set()
    for row in metadata.get('support_additions', []):
        path = str(relative(row.get('path')))
        need(path in ADDITIONS and path not in additions and path not in formal and
             hash_text(row.get('runtime_sha256')) and path in manifest_rows and
             manifest_rows[path]['sha256'] == row['runtime_sha256'], 'Invalid signed support addition')
        additions.add(path)
    for index, (path, row) in enumerate(formal.items(), 1):
        entry = original_entries[path]
        need(('source' in entry) != ('asset' in entry), 'Ambiguous Git LOCAL source')
        if 'source' in entry:
            source = str(relative(entry['source']))
            raw = git(repo, 'cat-file', '-p', commit + ':' + source)
            need(len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                 'Git LOCAL source differs: ' + path)
        else:
            need(entry['asset'] == path and path in locked and locked[path] == row,
                 'Git LOCAL asset is not locked: ' + path)
        if path != 'config/server.toml':
            need(path in manifest_rows, 'Signed LOCAL package omits accepted business file: ' + path)
            if path not in overrides:
                need(manifest_rows[path] == row, 'Signed LOCAL package differs from accepted business file: ' + path)
        if index % 64 == 0:
            progress(15 + 18 * index // len(formal), '正在逐项核对 Git 本地来源…')
    # A required helper must be signed and explicitly declared, never supplied by checkout.
    need('tools/local_fresh_state.py' in formal or 'tools/local_fresh_state.py' in additions,
         'Signed fresh-state helper was not declared')
    return formal, overrides, additions


def check_existing(workspace, metadata, signed_rows, generated):
    current = workspace / 'releases/local/current.json'
    pointer_bytes = no_links(current).read_bytes()
    pointer = read(current)
    need(pointer.get('channel') == 'local' and hash_text(pointer.get('manifest_sha256')),
         'Existing local pointer is invalid; no files were replaced')
    need(pointer.get('source_release') == metadata['source_release'] and
         pointer.get('source_formal_manifest_sha256') == metadata['source_formal_manifest_sha256'],
         'Existing local accepted source differs; update the unified launcher before upgrading')
    root = under(workspace, pointer.get('path'))
    need(root.parent == workspace / 'releases/local', 'Existing local pointer escapes releases')
    need(root.name == metadata['release'] and pointer.get('release') == metadata['release'],
         'Existing local runtime version differs; no files were replaced')
    need(digest(root / 'local-business-manifest.json') == pointer['manifest_sha256'],
         'Existing local business manifest differs; no files were replaced')
    business = rows(read(root / 'local-business-manifest.json'))
    bundle = rows(read(root / 'client-bundle-manifest.json'))
    need(set(bundle) == set(signed_rows) | {'config/server.toml', 'local-first-run.json'} and
         all(path in bundle and bundle[path] == row for path, row in signed_rows.items()),
         'Existing runtime differs from the signed local package')
    for name in ('config/server.toml', 'local-first-run.json'):
        need(no_links(root / name).read_bytes() == generated[name],
             'Existing local configuration or fresh marker differs; no files were replaced')
    need('els_server/application.py' in business and 'tools/launch_client.py' in bundle and
         'config/server.toml' in bundle and 'local-first-run.json' in bundle,
         'Existing first-install runtime is incomplete; no files were replaced')
    for row in bundle.values():
        verify(root, row)
    need(all(path in bundle and bundle[path] == row for path, row in business.items()),
         'Existing local business and runtime manifests differ')
    need(current.read_bytes() == pointer_bytes, 'Existing local pointer changed during verification')
    return {'ok': True, 'workspace': str(workspace), 'root': str(root),
            'release': pointer.get('release', root.name), 'reused': True}


@contextmanager
def installation_lock(workspace):
    path = workspace / '.first-local-install.lock'
    no_links(path)
    stream = path.open('a+b')
    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('Local initialization is already running; retry after it finishes') from error
        yield
    finally:
        # OS-held lock releases on close or process exit. Persistent zero-state lock
        # file avoids deleting another process's mutex between open and lock.
        stream.close()


def configuration(workspace):
    values = {'host': '127.0.0.1', 'port': 19400, 'profile': 'integrated_dx11', 'mode': 'local',
              'state_file': str(workspace / 'state/integrated.sqlite3'),
              'log_dir': str(workspace / 'logs/server'), 'attribute_enchant_enabled': True,
              'normal_equipment_moves_enabled': True, 'equipment_repair_enabled': True,
              'selected2026_pair_file': '../els_server/data/selected2026/local-pair.json'}
    return ('[server]\n' + ''.join(key + ' = ' + json.dumps(value, ensure_ascii=False) + '\n'
                                   for key, value in values.items())).encode('utf8')


def generated_documents(workspace, metadata, commit, manifest_rows, formal, additions):
    config = configuration(workspace)
    marker = encoded({'schema': 1, 'kind': 'els-local-fresh-state', 'workspace': str(workspace),
                      'release': metadata['release'], 'state_file': str(workspace / 'state/integrated.sqlite3'),
                      'config_sha256': hashlib.sha256(config).hexdigest()})
    documents = {'config/server.toml': config, 'local-first-run.json': marker}
    installed_rows = dict(manifest_rows)
    for name, data in documents.items():
        installed_rows[name] = {'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    business = encoded({'release': metadata['release'], 'channel': 'local',
                        'source_release': metadata['source_release'],
                        'source_formal_manifest_sha256': metadata['source_formal_manifest_sha256'],
                        'repository_commit': commit,
                        'files': [installed_rows[path] for path in sorted(set(formal) | additions)]})
    business_hash = hashlib.sha256(business).hexdigest()
    documents['local-business-manifest.json'] = business
    documents['client-bundle-manifest.json'] = encoded({'release': metadata['release'], 'channel': 'local',
                      'files': [installed_rows[path] for path in sorted(installed_rows)]})
    documents['release-snapshot.json'] = encoded({'release': metadata['release'], 'channel': 'local',
                      'status': 'initialized-from-signed-local-runtime', 'repository_commit': commit,
                      'local_business_manifest_sha256': business_hash, 'fresh_save_imported': False})
    pointer = {'ok': True, 'verified': True, 'release': metadata['release'], 'channel': 'local',
               'path': 'releases/local/' + metadata['release'], 'manifest_sha256': business_hash,
               'source_release': metadata['source_release'],
               'source_formal_manifest_sha256': metadata['source_formal_manifest_sha256'],
               'repository_commit': commit, 'first_initialization': True, 'player_database_imported': False}
    return documents, installed_rows, pointer


"""Bounded additions compiled into the bootstrap resource; not a separate component."""

MANAGED_KIND = 'unique-v42-managed-to-identity-v1'
MANAGED_OLD_ENVELOPE = 'c0fe16c35b05440258ed372ba2eb67da1419c2de62263e3b8c90aae4b7065371'
MANAGED_OLD_METADATA = '4688c349a9fb73a592c115ee610261cd9b2ba69cd5e9ccfafdd2b6050be575c1'
MANAGED_UPDATER = 'c976b8c28c85d54b128ac0943e1abf20969859c5139b7e3b5ece98bead049fc2'
MANAGED_OLD_FORMAL = 'd621337b400fc4dfe3a61bd32be2180bd98c55e4c8ab2beba3eae2e3e2b91b11'
MANAGED_NEW_FORMAL = '7c72970e3e5781c43a32d3f748d32c14fcedfe0b4f3f3fd660086a2cfcbf9f5e'
MANAGED_FIVE = {'els_server/storage/characters.py', 'els_server/storage/seal_quests.py',
                'els_server/storage/career_shop.py', 'els_server/protocol/local_messages.py',
                'els_server/protocol/dungeon_messages.py'}


# Exact third-cohort SOURCE descriptor; package identity excludes only metadata self-row.
STRUCTURE_SOURCE_RELEASE = 'local-native-server-structure-20261029-v1'
STRUCTURE_RUNTIME_RELEASE = 'local-git-first-run-server-structure-20261029-v1'
STRUCTURE_FORMAL = 'b014a2cfaab3968fb16055f85cbe35803b5cb5d1369382ee7ba5b6193dda43f2'
STRUCTURE_PROFILE = 'channels/server-structure-accepted-20261029-v1.json'
STRUCTURE_PROFILE_HASH = '05e234b9d1b055c1f991bea500d9d0f8ec15203a44cad33ccd6627de2f6b6a42'
STRUCTURE_SOURCE_ROWS = '6dc7ebde683c9ebea3d0327be7c7e46c3a1fd3843783869d05ddec4dc295f461'
STRUCTURE_RUNTIME_WITHOUT_METADATA = '850db3b453824c42f5dde271285783141a3b4dfaf2017d01aa3ee5bcb5cd3b38'
STRUCTURE_POLICY_KIND = 'exact-v42-or-identity-to-server-structure-v1'
STRUCTURE_PREDECESSORS = [{'name': 'v42', 'key': ('local-git-first-run-20261029-v1', 'local-native-shop-flow-20261029-v1', 'd621337b400fc4dfe3a61bd32be2180bd98c55e4c8ab2beba3eae2e3e2b91b11'), 'envelope': 'c0fe16c35b05440258ed372ba2eb67da1419c2de62263e3b8c90aae4b7065371', 'metadata': '4688c349a9fb73a592c115ee610261cd9b2ba69cd5e9ccfafdd2b6050be575c1', 'archive': '70e06dca0f929d0f2bc053a5cb226b960bf7026c13ae10dda503f96f485aeec4', 'runtime_rows': '1d8c54487337d12b72bd2f8ae58b8d2e211cae83ab939a61c4f1e9f9c453afbe', 'formal_rows': '7900ad4eef4985b6b953b00e880f8b303224e0bb97debd59e178057301de3cdb'}, {'name': 'identity', 'key': ('local-git-first-run-identity-20261029-v1', 'local-native-unit-account-identity-20261029-v1', '7c72970e3e5781c43a32d3f748d32c14fcedfe0b4f3f3fd660086a2cfcbf9f5e'), 'envelope': 'ed47a5df4fd5d47bacf297226cce4783866ded16d88074b14d277e9bebeffa04', 'metadata': '0a2e4071eb897b8e0b6b210152d305b28bbe571366b95b86f8ed0b5dec54432c', 'archive': 'c2479938972ae6f9c6f3747d2348f28473dbaa2635ee93e16c1b9239e309f86e', 'runtime_rows': '6d87d9dcac786bc9644b686fe6cf1d41f0c55ea2c8d1c0bd2d98f354340c7d35', 'formal_rows': 'b36e18da6a4a3729d8a3b8dd20f4a486906cbd88e62158c2a97d893b2cbe49b8'}]
STRUCTURE_OVERRIDES = [{'path': 'tools/launch_client.py', 'source_sha256': '74f5c5406c93b526e1bb34cac36c5eb4ef8eeca4fbc3292d05c5de8f18f08142', 'runtime_sha256': '9cb6fd2b579b11c90ec2ccc31babd3c383e9b8bbd43ccfed330cdf4aa689e6f8'}, {'path': 'tools/client_compatibility_profiles.json', 'source_sha256': '9f6a0cc4ee8c3f2f293cc2b19c94610f31bc029e0aeb9ddb7c278dc6f478aff0', 'runtime_sha256': '04166e975104b9d25e7bf224eeb1a2f34501689cc33cb76ee457c0b4797906e1'}]
STRUCTURE_ADDITIONS = [{'path': 'tools/local_fresh_state.py', 'runtime_sha256': '9bed6a12b3adeeb63f49d60f81bc8f89a64c1e676726ee09a7d627382efe9d56'}]
STRUCTURE_CONFIG = '4e14201a91e69df87af8bf5aac226f303f027fde76b98e2967b85c442c2e8124'


def structure_target(metadata):
    return (metadata.get('release'), metadata.get('source_release'), metadata.get('source_formal_manifest_sha256')) == (STRUCTURE_RUNTIME_RELEASE, STRUCTURE_SOURCE_RELEASE, STRUCTURE_FORMAL)


def structure_policy(metadata, new_rows):
    import base64
    need(structure_target(metadata), 'Unknown STRUCTURE managed target')
    need(metadata.get('profile') == STRUCTURE_PROFILE and type(metadata.get('source_file_count')) is int and
         metadata['source_file_count'] == 1332 and metadata.get('source_files_sha256') == STRUCTURE_SOURCE_ROWS,
         'STRUCTURE complete accepted business identity differs')
    need(metadata.get('support_overrides') == STRUCTURE_OVERRIDES and metadata.get('support_additions') == STRUCTURE_ADDITIONS and
         metadata.get('generated_config_source_sha256') == STRUCTURE_CONFIG, 'STRUCTURE signed support/config differs')
    need(len(new_rows) == 1786 and 'local-bootstrap-source.json' in new_rows and
         source_rows_hash({k:v for k,v in new_rows.items() if k != 'local-bootstrap-source.json'}) == STRUCTURE_RUNTIME_WITHOUT_METADATA,
         'STRUCTURE exact complete runtime membership differs')
    p = metadata.get('upgrade_from')
    need(isinstance(p, dict) and type(p.get('schema')) is int and p['schema'] == 1 and
         p.get('kind') == STRUCTURE_POLICY_KIND and
         (p.get('to_runtime_release'), p.get('to_source_release'), p.get('to_source_formal_manifest_sha256')) ==
         (STRUCTURE_RUNTIME_RELEASE, STRUCTURE_SOURCE_RELEASE, STRUCTURE_FORMAL), 'STRUCTURE signed predecessor policy differs')
    entries = p.get('predecessors')
    need(isinstance(entries, list) and len(entries) == 2, 'STRUCTURE requires exactly two pinned predecessor definitions')
    contracts = {}
    for entry, fixed in zip(entries, STRUCTURE_PREDECESSORS):
        key = tuple(entry.get(k) for k in ('from_runtime_release','from_source_release','from_source_formal_manifest_sha256'))
        need(entry.get('name') == fixed['name'] and key == tuple(fixed['key']) and key not in contracts,
             'Unknown or duplicate STRUCTURE predecessor')
        eb = base64.b64decode(entry['old_signed_envelope_base64'], validate=True)
        need(len(eb) < 1048576 and hashlib.sha256(eb).hexdigest() == entry.get('old_signed_envelope_sha256') == fixed['envelope'],
             'STRUCTURE original signed envelope identity differs')
        signed = json.loads(base64.b64decode(json.loads(eb)['payload'], validate=True))
        old_rows = rows(signed)
        need(len(old_rows) == 1779 and source_rows_hash(old_rows) == fixed['runtime_rows'] and
             signed['archive']['sha256'] == fixed['archive'], 'STRUCTURE original full signed membership differs')
        mb = base64.b64decode(entry['old_metadata_base64'], validate=True)
        need(len(mb) < 1048576 and hashlib.sha256(mb).hexdigest() == entry.get('old_metadata_sha256') ==
             fixed['metadata'] == old_rows['local-bootstrap-source.json']['sha256'], 'STRUCTURE original metadata differs')
        old_meta = json.loads(mb)
        need((old_meta['release'], old_meta['source_release'], old_meta['source_formal_manifest_sha256']) == key,
             'STRUCTURE original accepted metadata target differs')
        old_formal = rows({'files':entry['old_formal_rows']})
        need(len(old_formal) == old_meta['source_file_count'] == 1325 and source_rows_hash(old_formal) ==
             entry.get('old_formal_rows_sha256') == fixed['formal_rows'] == old_meta['source_files_sha256'],
             'STRUCTURE original complete business source differs')
        need(entry.get('updater_sha256') == MANAGED_UPDATER, 'STRUCTURE exact updater differs')
        contracts[key] = dict(policy=entry, old_rows=old_rows, old_meta=old_meta, old_formal=old_formal,
                             policy_sha256=hashlib.sha256(encoded(dict(target=p, selected=entry['name']))).hexdigest())
    return dict(structure_contracts=contracts)


def structure_select(contract, pointer):
    if 'structure_contracts' not in contract:
        return contract
    key = tuple(pointer.get(k) for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key in contract['structure_contracts'], 'Existing source is not an exact STRUCTURE predecessor')
    return contract['structure_contracts'][key]


def structure_journal_contract(workspace, u, contract, path):
    if 'structure_contracts' not in contract:
        return contract
    path = no_links(Path(path))
    need(path.is_absolute() and path == path.resolve() and path.is_relative_to(workspace / 'state/local-updater') and
         path.name == 'journal.json', 'STRUCTURE recovery journal escaped its canonical root')
    journal = u.read(path)
    return structure_select(contract, journal['parent'])



# SOURCE ONLY: every new descriptor value is pending final reviewed C3.
REPAIR_SOURCE_RELEASE = 'local-accessory-identification-groups-20261030-v1'
REPAIR_RUNTIME_RELEASE = 'local-git-first-run-group-wear-20261101-v1'
REPAIR_FORMAL = '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'
REPAIR_PROFILE = 'channels/accessory-identification-accepted-20261031-v1.json'
REPAIR_PROFILE_HASH = '3f7002d2e2b5601d9ec2225bda47fc80b75646bea2cd22d29e8fcdcb3e9aab32'
REPAIR_SOURCE_ROWS = 'd7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999'
REPAIR_SOURCE_COUNT = 1342
REPAIR_RUNTIME_COUNT = 1880
REPAIR_RUNTIME_WITHOUT_METADATA = 'c945edaf36a5175128147bebb7e16846a3b0478b5f8d9b167abc3b6f0d89019c'
REPAIR_SOURCE_SET = '250a0581df1ca0cb945786c4cfb699b419997b66d24141fa9d02eb444d2ee2f8'
REPAIR_OVERRIDES = [{'path': 'analysis/client-6c6b5180/extended-shop-body-proof.json', 'source_sha256': 'dbbe93ed8779924da36e8452348479e253c45930fabe8493a2f62dbc591033a3', 'runtime_sha256': 'd941e266728d86c3b376314d0e20b5cff95a013a8a03f1c816b6d27941f1fdfb'}, {'path': 'analysis/client-6c6b5180/extended-shop-catalog.json', 'source_sha256': '3743b01d68e1e70224b920f96d233cad1fd5e3875b0e772f24722ee5f2b990e9', 'runtime_sha256': '2dcf6bce3ba3805d0f06b0b85a54d63158a0d67d2d24297bb38ac0fd79ac9df7'}, {'path': 'analysis/shop-listing-20261015/bundle-order.json', 'source_sha256': '68399225492583167b09eb4d8278c4e740a8089fe3f385f7b0bcd29e5d64bb85', 'runtime_sha256': '35608d6c38694d96dcbdbd5fb445d88e491129258d3ac6afa06c59df87806a63'}, {'path': 'analysis/shop-listing-20261015/fashion-bundles-body-proof.json', 'source_sha256': '5f8588d669c40cde40831fa86025b3eb3ddd6bcd9f2c4e628e867d48053f2743', 'runtime_sha256': 'a570b5b18a7553bc0d2956f40b5d3e2ffdfec8907d03f6650b8b635658bee890'}, {'path': 'analysis/shop-listing-20261015/fashion-bundles.json', 'source_sha256': 'ea683d7e7dfb57bd8d177dfd3d427367b64a58c7fcb6e2e3ae0f113790a81371', 'runtime_sha256': 'e90637ffff40b09b0ed13ab4fea1199d5713db0dc737937c70428a328eb8419f'}, {'path': 'analysis/shop-standalone-20261015/ice-shop-exclusions.json', 'source_sha256': 'c2b322e0e8c99987ae3971a6c718fb8319294c335b952f5521945d904d138ee6', 'runtime_sha256': '95624aa30c722ce2bafe2287fcbc337f40b2a5c75ebbe15b9f194daf12c1d63f'}, {'path': 'config/dungeon_local_rules.json', 'source_sha256': 'ebf664ddce3ce04a54db038cb86d31ffcc05651748c5dc8a1113e24e255c6156', 'runtime_sha256': 'ae2e35d443476b9d265dbaa51d9db0dee6f18f0de0dd92a59ea607d61007ba9a'}, {'path': 'els_server/application.py', 'source_sha256': '11bd2c4dfdae15acaa66e898a8f24022cdaaf54c4ecd7cfd986ad880d5e80c1d', 'runtime_sha256': 'bff02c99ba68ccf076c982a626b03f5e684faa18c805148313640dd0657e332b'}, {'path': 'els_server/data/accessory_identification_groups.json', 'source_sha256': '7770dc4d7d6de9bac6ad97a22d72fa7fe12774447af8f9fe4decf080cc0db2bc', 'runtime_sha256': 'ab5683c81700d9542cf662665d5477bc4fe31f87b2311198145c2b94505d5e31'}, {'path': 'els_server/data/character_custom_permanent.json', 'source_sha256': '9b6d90046480266d881b1e960bd28aebd99d353746f805a418389aacef06c668', 'runtime_sha256': '219b614469738b9b1a51931b7bf1ca6426eb7d782002a889a85ffea2a0e13871'}, {'path': 'els_server/data/client/dungeon_routes.json', 'source_sha256': 'fbafa1cb884371bc173b74e216b09f9f0f71523c69cae02b00bc7e2c7cf092a5', 'runtime_sha256': '302feba495e69870d16254ed97ff3991badd1f90f1aab95fbd86e0055b4cf0de'}, {'path': 'els_server/data/client/dungeon_routes.manifest.json', 'source_sha256': '1dc5293cac8ffb7ce0e551b3a2d9facfb06beeedb7fa8bbe34d3ede1d3859931', 'runtime_sha256': '63db97722c6afc42f87a68158e5074981fe9e079572f6cb0a9b420c9e9436e4a'}, {'path': 'els_server/data/dungeon_loot_catalog.json', 'source_sha256': 'b835c7dc350dc80f5cf198f1c28b4a231daef35544aad4131ab48ace2ad5575f', 'runtime_sha256': 'e38d43683ce04dc947b1a4c794ce79bb8fb723a6ba976438e6e872d8b1f583d6'}, {'path': 'els_server/data/dungeon_material_loot_catalog.json', 'source_sha256': 'b936d1bb6c786475ac190a073902a823610dcc9847106dd52a8c46b988a7a2ef', 'runtime_sha256': '7d0c804cdc7666f92152581a5f6acdcc79481e852a9ed627e4353f756fccee8c'}, {'path': 'els_server/data/dungeon_source_loot.json', 'source_sha256': '26ed0aa4982d74aaca54ee58b2d244523150f18dcd58d72cb5bb50e9864828a6', 'runtime_sha256': 'a74cfe1036d0e48dad91a7302cd4cd9fd082956a9b3da029efb7f7052c5b41a4'}, {'path': 'els_server/data/fashion_singles.json', 'source_sha256': '3871dbe69fbb874db98208ee3d3678ec4c39dc7cd6fff135741d6e6956487779', 'runtime_sha256': '0b387c3a0aac84f043503a5ac152f954a68743feb4e4bf2f7a4c27da515221e2'}, {'path': 'els_server/data/fashion_singles.manifest.json', 'source_sha256': 'bfd58af96d8f553f8843329e89e2982d1ff8e01f30cfdf0fc804355b9f4ffee1', 'runtime_sha256': '4a46b118d976bdab155e95e9b41e0dc94dd3e0745f11e88135551a0780325d64'}, {'path': 'els_server/data/formal_pve_economy.json', 'source_sha256': '01d100c92f9cb81624b5bd73b6e087e74ffb9d739bca6bf5e1f04c45f1951416', 'runtime_sha256': 'b915757156899436ba3dde5c9ac3bc3ce67f4408830394b932fea02dae64cc2a'}, {'path': 'els_server/data/formal_pve_economy.manifest.json', 'source_sha256': 'ec3c257a9ee129b58bf4bfc5077d1e3ce8a9e5ecedb8e27164418c4e1dfd2496', 'runtime_sha256': '8f381d10dd7aced0895c11e6ec1e863eac91df25f5703873cd3ea52d622c0582'}, {'path': 'els_server/data/identification_ui.json', 'source_sha256': 'c3e9be1f22a012b32826fd6ddeaa05bec8688fc6a7cd5b19a9259d860e9a0629', 'runtime_sha256': '4101062fe320b4accf5b03f7081474216396e74a9f67f3ed9f73c82927b4aba6'}, {'path': 'els_server/data/market_conversion.json', 'source_sha256': '4b14a2220bfe1d14c7575c1c15a75fe4d1e726ac44b50f21089af45d1c390db2', 'runtime_sha256': '9b032388be34116eb0ec57a016002e053784c536adb71a432e3d66699558a036'}, {'path': 'els_server/data/retained_native_consumables.json', 'source_sha256': 'e01be8d6a7ed023f5fef062c0f68050c6292a34406669fe425e4323e006864fb', 'runtime_sha256': 'a0d28e566c439c655d426d33988df14cf3fe845f969edaa37e9a06c6ed5122dc'}, {'path': 'els_server/data/story_quests.json', 'source_sha256': '0cb47c1197bed148c6d650b35d6ebe16a8417adb68e087b01dee40266d8459cd', 'runtime_sha256': 'ddf4fbd498fd051c7f2c2f883e1695bc116e473f0377a695d901f38e56436a6f'}, {'path': 'els_server/data/story_quests.manifest.json', 'source_sha256': '6f21356488ae68b96986c368fb981f4a68c7a411b69087983d281ad06e1495db', 'runtime_sha256': '152e70367182ff88271f725935cd4181c5189bfd5cff3682fd27faa16ea275f1'}, {'path': 'els_server/data/town_travel.json', 'source_sha256': 'b3b40954b6e9767b4af88ae4ef58e7d3898e38699419ec1ff5f1939bc9e6b406', 'runtime_sha256': '7c38b41ebc09d0994fb859dda21dc5e63d50ee827c496110ce32f4c4357d24a4'}, {'path': 'els_server/data/town_travel.manifest.json', 'source_sha256': '96fd9e640bfcd11021401b57d8b1dda661f49b6bb803b573d2ac8a968484253a', 'runtime_sha256': '4b802f9babad41b44bdc5405cedcb082be3cbe617acc708aff7494eaec47660a'}, {'path': 'els_server/domain/accessory_identification.py', 'source_sha256': '2e2fc159879ca6810136521cc5519004645c67335f97198ff1b27fc3d151d0ca', 'runtime_sha256': '836933b7151fb44517835d09d0781c923dc78fb4464b7b81ecfd8a28d041fb7c'}, {'path': 'els_server/domain/acquisition_policy.py', 'source_sha256': '0e132031cc7c27fe437e6457bd6fe67dfd00f40044cc1db4d6298e4143ce4301', 'runtime_sha256': '923fd8ebb4621768931ecfc985dfcc319cbd727bd9efe112c42a607e00393b9e'}, {'path': 'els_server/domain/black_market_box_rules.py', 'source_sha256': 'd0ad49f336701543ae860f78e3327c2d78c7c0ff8ae95ad8a744725a5b522756', 'runtime_sha256': 'a32d90e5a14def129aa444bcb7bdf4908bd28afb1d822632063970bf1a53c37b'}, {'path': 'els_server/domain/boosting_2026_force_equipment.py', 'source_sha256': '976df525ed60c6b8552f4c85879fe3e0f68669c1c0718bd91994cf66e9c30d55', 'runtime_sha256': 'dbfaa4f74dac2805b75abb21ae5e062457f6a966d4d4f3b37d595d25d8686ef0'}, {'path': 'els_server/domain/boosting_2026_force_inventory.py', 'source_sha256': '620f53d3dba19c73315d73c76eacb82aab308f12fe4029716dd998ba8cb84f72', 'runtime_sha256': 'b03b22d7bee4a624ea0150e4c56055cf91100a4540d810a6030040d71f222812'}, {'path': 'els_server/domain/boosting_2026_participation_gear.py', 'source_sha256': '3167092fa2af7b053194178125c1013f4256a854897abe5dc75f75d0fe9c471d', 'runtime_sha256': 'c959034646cfd28bb372b1230f508a666034c523fd9ba2abd1a2017c3af5bef4'}, {'path': 'els_server/domain/cartridge_selection_box.py', 'source_sha256': 'fbe0ca416a574f9b981a3747a378ca02d755c6cba9f6217619bb1e1df1d260a5', 'runtime_sha256': 'fa31e288b077fe7b1f0c5bb375fcb1d90113f5ffdbb6d93acbb16595028b40a2'}, {'path': 'els_server/domain/character_custom.py', 'source_sha256': 'f6424155e2e9904d7aaa18b93c87ef205a922e5c264d9969f48ae4a8bcdc4968', 'runtime_sha256': '250d8fd27f6d6da45c1ba96ea8da3e58be2a261f73550a7231037ab9f4d71b0a'}, {'path': 'els_server/domain/cubes.py', 'source_sha256': '1db0706806ad63057baf50bb2aced0a8b37e932c40ac47be4f3664e88f3e175f', 'runtime_sha256': '6c6476e0903041885d56ed449cf3c94fd8d9049e5c910493f983cef0d4851d6a'}, {'path': 'els_server/domain/drop_pickup.py', 'source_sha256': 'cbcccf87bc2c4fbee7e45694d436e7410e9b8fc49cfa7bf0fcc10b7f57278cc9', 'runtime_sha256': '2ca8351440bd68cb314408ac6b5170eff1e6d9a32783ba38a512f48d929fa6c6'}, {'path': 'els_server/domain/dungeon_drops.py', 'source_sha256': 'fea9c916cad993678c2b4aa90b72ac8d6cfba479ddc34af92345e5138d2f5f3d', 'runtime_sha256': 'baaf2d04513a72720ff095add3d6e7bae4db901c8c3568d74fddceb3714ad688'}, {'path': 'els_server/domain/dungeon_equipment_loot_flow.py', 'source_sha256': '22d12e24b8854c6bbd62357bfdebdbcc2373c8b241540a661c3a28fb1a3f2e31', 'runtime_sha256': '779913882c0863ae235b6e4108ca6f28cd07b69fdb16de152d143d63faa349e8'}, {'path': 'els_server/domain/dungeon_flow.py', 'source_sha256': '1d8cebddb32dfe6f79df16bcacb565858dd1d8ff9879ac073491fe9f655304e9', 'runtime_sha256': '6bf6024e768d9c410ac79316ef4fd467aa0d420712852dbe029be86a98de5a82'}, {'path': 'els_server/domain/dungeon_loot_catalog.py', 'source_sha256': 'ae03c1e1905e23987e6dc12aef6bd59a33369e24025e8f2ac879797cabd5a58e', 'runtime_sha256': '09a6e3f4f28ae817b0a73ef3c16f89f8724a35d5f6da3717c8cd7b18a81364ad'}, {'path': 'els_server/domain/dungeon_material_loot_catalog.py', 'source_sha256': '51ba09fd9cf0aa67febd54387efd3bde1fb658044bb4aa3cf74f5b1cb0e6dacf', 'runtime_sha256': '37eb525e0c9deb5610f645895f93cf983c3acb5d8e38c2cc62f8175b8404a4e1'}, {'path': 'els_server/domain/dungeon_routes.py', 'source_sha256': '80167d8f82e6520399b11f75234711121570fbbd0ac1ef83ac2baa06a1101e66', 'runtime_sha256': 'ecc69528631a970421a2f6c27d16f0ca93be373d805d4c3a6c8f24eb273f0f3c'}, {'path': 'els_server/domain/dungeon_settlement_commands.py', 'source_sha256': '5249624af540a43267f5ada8cfc06105b517e9b4b4bba2ed5b9e1890af74ae48', 'runtime_sha256': '6aad4336f4f0a42a4658fbbfc58261673d55ad72c954800c29a9528348f1fa7b'}, {'path': 'els_server/domain/dungeon_source_loot.py', 'source_sha256': '84d6498b563fbc0fe15d6460195465772ab12baeb282205d5cb40a712041613d', 'runtime_sha256': '4c859b251e9387f910214f167330e323c64228ff3418e8100608310ee2559fea'}, {'path': 'els_server/domain/el_search_collection.py', 'source_sha256': 'f4a0421a69ba1d4be23813d11da9c3a6d90fb3ddc5f19882caba89b913abef28', 'runtime_sha256': 'bf849337bc98fa0d6240fe97d444c31a7df68d7579587f72b211ffa066618ca1'}, {'path': 'els_server/domain/elixir_economy.py', 'source_sha256': '3437fec4e7b091035bee207a0a099266e39052e478f44cfa2b2951645bbc7dd4', 'runtime_sha256': '780cd7364a3af150b0047310744c29dd686d66a607ac78cb547ca39e0848f371'}, {'path': 'els_server/domain/equipment_ui_flow.py', 'source_sha256': 'f887e5760305ad3a166a7fbe6ac5dc67dea1515d5e20fcef16d744e3003bc640', 'runtime_sha256': '4988ba6ed1035aee8c4e9f932499fde60b56dd6575d5bcc09de3d47a9c461933'}, {'path': 'els_server/domain/fashion_singles.py', 'source_sha256': '3b60e0ed3890e0314fcb22361d3abb808d4542091382fab8921bcb73f114ae0c', 'runtime_sha256': '62ed00c32cf217c021ed74c958f0232a0a1c7a93b59d602c775355a35a3a53b2'}, {'path': 'els_server/domain/field_boss.py', 'source_sha256': '0e4323e121691427ddf44798acfbdeb4a70041ecffb3d4cb24443360c4572af8', 'runtime_sha256': '41ecc34db9424ef43cb6f638a6fd338211bb5fb9116ce2755f7bb57ce1d0819b'}, {'path': 'els_server/domain/fishing_bait_loot.py', 'source_sha256': '87444c514783f0bb8798cd91fd5a3b8cf2b62e015b3296a5f680f42897467982', 'runtime_sha256': 'eafc3217edc2d4fe6bbdb8673a3967a8d7a419873e593ef22a6e453745a2929e'}, {'path': 'els_server/domain/fishing_village1500.py', 'source_sha256': 'a88414cfeb0f3bfdc47b633d960e9ce4815fa791e97f042d583b2688aa3496c0', 'runtime_sha256': 'dc216dd2eb90f268fb1a1a90b331dcd1beaaf2ebf2f44b5041fb77443a9b70b5'}, {'path': 'els_server/domain/formal_pve_economy.py', 'source_sha256': 'd3f1ce62b59b61ab2fef348b510f1592509a41e706aa9868001f1deca95b5f5a', 'runtime_sha256': 'e33f13f51a33be7d3c96d13b0522bf567fb1acb9c909f47dc8e0c9dade12573e'}, {'path': 'els_server/domain/friends_dungeon.py', 'source_sha256': '903a40432b921a56ab4b788bdcf35e0b4bf8543c5a22bbe63dd8fba268aa9452', 'runtime_sha256': '6cffddb9375fabb282e0654c6a49da32822ecd537afac661c26ed07ddc4f0ceb'}, {'path': 'els_server/domain/friends_world.py', 'source_sha256': '6076303fde43097f68aae873721b43f8e50778d9287c6ab33e5aa3aa665968a0', 'runtime_sha256': 'af7c4209f379ab80cd7436bcdec704b59bbf3ad94f5069d2326da89f6fdcc4ba'}, {'path': 'els_server/domain/housing_room_flow.py', 'source_sha256': '5d7e364afe11f931654cfcba159bcf656a2139fdf022cd75bcded9b731c7715e', 'runtime_sha256': '77b6eb562f2c75dd1ed7656f62aac8f777acdad53c6c6f23002a0235d5b330d4'}, {'path': 'els_server/domain/identification_ui.py', 'source_sha256': '38f6fa5c6f92fa87b388092dfc64917c71616dba464c94f8e73f3a5ea6390f15', 'runtime_sha256': '773883f44905f8b125243da5d638996c36414a0e7ea1eb3bb154f037ba46f551'}, {'path': 'els_server/domain/inventory_items.py', 'source_sha256': 'bb94e23b06684b9343951aee38b2709d3ef5a5cc7bcb92623b4f9e6528be0f9d', 'runtime_sha256': '071bf7dd5ccbd3f00f4ea72a2e5f38f953f487af64df2c20c6d4e7d6186a0ece'}, {'path': 'els_server/domain/local_session.py', 'source_sha256': '0edccc57a8c8f971a81066aea560b141f78ebe0223f7f14c41ada4bcac77f7a8', 'runtime_sha256': 'ea4a75627840e7e22f3e19ae104bb0cf25331743101ba32a99b6e8ab360de8c3'}, {'path': 'els_server/domain/market_conversion_rules.py', 'source_sha256': 'ea6e9241c736d1dcc507599bf4499571df155c3348d7a8cb2f67fd096c07525b', 'runtime_sha256': '814d3db6f2eca793619d5b745d009c1c59cdbbf6ba0edff970d9f7d547d8260d'}, {'path': 'els_server/domain/owned_growth_items.py', 'source_sha256': '49535f7bb763c19c0e26819c3d4ac1a216b6172c9587a941c0681626b2f3bf76', 'runtime_sha256': 'e2b1298b12d313831247184f19548a6d21198b2dc35777b2d846708cf296effc'}, {'path': 'els_server/domain/pet_support_flow.py', 'source_sha256': '8f743fd4c636be9c97bcf1f1c05067a199f0f9d44be205fac3b361fe916e7050', 'runtime_sha256': '27b63dc8a56837c70fca0407448deb77137e1e17a8cbb785633e2e882091b591'}, {'path': 'els_server/domain/pve_economy_flow.py', 'source_sha256': 'f603818e58c0cb766afc0d0e5da15e53321f4fd4c42f71dd82d9d50deca201c0', 'runtime_sha256': '3547e27691f84c55f13f8ec27e5e55e250dac793a48ca696c22be1b7026088da'}, {'path': 'els_server/domain/quest_flow.py', 'source_sha256': '0c09c564c48c758d0c47c6b7ec103a7fe4a1c3640d9fe3d6bdd404f530b97c28', 'runtime_sha256': '67b78e7312764678e465c874d8d6e5c126354091a1110d055dc6dae17de56e20'}, {'path': 'els_server/domain/raid_economy_flow.py', 'source_sha256': 'dc27ade1a5b309e7c0df368627249f0c0a067ce70cbebe1cf48cd9e53f3a5835', 'runtime_sha256': 'ba0420908a4082471338128993863ba4df567b83d0b1d52074fba56e00e5a845'}, {'path': 'els_server/domain/raid_reward_items.py', 'source_sha256': '847a7687d8ddc5a7405536eaa327d4e9bc66f337b9814975284f572e63eee7c0', 'runtime_sha256': '880f7b62fdca6d986db4d3a58969f5dd8c77a1d5ea14c5bd31260f7618e76085'}, {'path': 'els_server/domain/region_quests.py', 'source_sha256': '6cecc7a8361e1da1364e38e68c5e6b75ca660f9d2cea98dd1757e64a29850aec', 'runtime_sha256': 'd6d4aecbf0043f9e953fbc02022775600b3c14a028716523bec6973446b1e24c'}, {'path': 'els_server/domain/retained_native_consumables.py', 'source_sha256': '6b6bfbdeabf15fd26fad9765b51787b2e32299b3c8fe4513da4d66e87f67434e', 'runtime_sha256': '8216029b788f93b33fdd2a1577923088cec7deead2141dbe2e49864afc959799'}, {'path': 'els_server/domain/role_progression.py', 'source_sha256': '9379f185f237302c783625cde693fabd006866cd7a44af7880a5404738619efd', 'runtime_sha256': 'cc17085d713bb1f20afb7965ce6813c072801056895d41787f64e9cc8da1a855'}, {'path': 'els_server/domain/sage_sockets.py', 'source_sha256': '280bae10f5c855c4128b6c977e381b2a6c1264dbfed437fdc8152e86068ea86e', 'runtime_sha256': '3e0792136ae16ae5d9a78eddf2336f668b36fedcf6555890d97d2c3800c6c294'}, {'path': 'els_server/domain/seal_quests.py', 'source_sha256': '58394a360d12259ede9cbc93125bb11e20981ddfecf231611e162f0e2f34dc15', 'runtime_sha256': '11e8768f107fd6bcb3ea90040ed588ed70b71bb1b8296346794e6db775d2ed18'}, {'path': 'els_server/domain/session_dispatch.py', 'source_sha256': 'fdc74f164c2274c7f9b73dbea15641f69a2ca9728bc8e517d734be5f5867e2c2', 'runtime_sha256': 'ea4bcf585f4e7a198851a1342f5d38c231823ec3edd166a333e6ca322eb7e380'}, {'path': 'els_server/domain/shop_listing.py', 'source_sha256': '011f1cd3091de74dc659cedeafcd131ff883f423e62c4c0606e56885c1056253', 'runtime_sha256': '3dc4d2aea0ca5bd07e6639c22fdb45c12b170146f8d87043758fb66e899e5d0a'}, {'path': 'els_server/domain/silver_mirror_flow.py', 'source_sha256': 'b9dbf3b780c8a4d6ef47b4acb43b5d1ae60249ec7fb425ea4fee6a3eb5f4c96e', 'runtime_sha256': '5b7f900f4c6b3a1c442e797c791ef0cd2b2189c9de0045627c62509c52be31d1'}, {'path': 'els_server/domain/skill_expansion.py', 'source_sha256': '1021443de8f8dcffe6e8f63109ce367d911e6b1dd9d3c6dad01530bb3be1ddf8', 'runtime_sha256': 'ffa45347d9796d9a729f3630d7ad89466935a7cfe7a05ccab5544ad8b2f5ce02'}, {'path': 'els_server/domain/skill_state.py', 'source_sha256': '1eae1fdd48f1e2d5c1db087cd145e9f537ef9a27ca72f1a78e773f5a6b67f435', 'runtime_sha256': '0efbebdef5bdc73be7b0d3d24b8ec98dcf8d1b35212443ecdc1721467a11ad24'}, {'path': 'els_server/domain/story_controller_retirements.py', 'source_sha256': 'd9f8fd0460092a0227af5c760e21b065c709003a7f45701b041ce78921c685ad', 'runtime_sha256': 'f47346ddbda48b6b45ad7cfe59ccdfe2494fb4ddf797cc00d3d84ca75bb08dee'}, {'path': 'els_server/domain/title_economy.py', 'source_sha256': 'd84b6c392f8831be180281220ca2db79fcce51b0ebe3c1cf69ae0e598ec58912', 'runtime_sha256': '7bbc90a9b1e5509cb476ba5cec9d557864bebac5bd666e076c4a1a3cf5251278'}, {'path': 'els_server/domain/town_travel.py', 'source_sha256': '419b6db963c581c0ced4062d031ffa498ec490616ccf95edd5bf7458169acf7d', 'runtime_sha256': '427f478eb7372bc410de5aae2328de8f885804518ff64f1c00b8dd88841711fe'}, {'path': 'els_server/domain/town_travel_flow.py', 'source_sha256': 'f5bab88ebb9ed95e03e8d5691b0ccf2cacd75010f1691491dd2c84f6d3ff7c4b', 'runtime_sha256': '1613329defaa01ec97b3a1506cac401daab83537ce7f4210639ff6e0391c4e5f'}, {'path': 'els_server/domain/tutorial_accessory.py', 'source_sha256': '6d856e3c6f0625ae25f6de4694b6088fa2890b9792b313ddde934578b519a680', 'runtime_sha256': 'e02084170e095302da347c4644d95e3453d310d19938bbc533b64250184eb3fd'}, {'path': 'els_server/domain/wisdom_potions.py', 'source_sha256': '5901f04419721cf77065a6c891ebb7b70ab51658765116c2d40721b4477d7c5a', 'runtime_sha256': '64f673b3140a3f6bd8ff83adf0a34289ec91a687182eeaa07d13ea1157da1d18'}, {'path': 'els_server/enchant_data.py', 'source_sha256': '4daac973b74d4acd21bf9aea72260558ec6b61b95e2f37422d0d147451d119ec', 'runtime_sha256': 'f62cbfebc7c44e38a52718a88148927e71dbde9f147d1bd389a7a7dd751a9395'}, {'path': 'els_server/friends_bridge.py', 'source_sha256': 'c591b100c84bc2b62f9e2d4d0c88b8c303d50234bc702c3811498d6a841ba1b3', 'runtime_sha256': 'f6817002efecc3cd01c0e522bcd7ff12294f0ef2e8d71fb1c04c85adc10a239d'}, {'path': 'els_server/friends_relay.py', 'source_sha256': '338a9dd3fc46251e6f36a70a5d2095a2068276b0960a9b75de7b670b8f47e539', 'runtime_sha256': 'ea3cd935d99725bc5df163da6827f14f81e96ca77973c5d9591b2c49e4fd196f'}, {'path': 'els_server/protocol/character_custom_messages.py', 'source_sha256': '9ce1784e2f1d8bcf2a1767c63400963cdd726a73d223e3bbc61630d81b5aec83', 'runtime_sha256': '5b7cedfbfa01f3a0c3da38bc998228759002b441003c31e0d2ac9fc4552f3c41'}, {'path': 'els_server/protocol/field_boss_messages.py', 'source_sha256': '2ba40e043ec633c4eaa9a406f48265375e4fc533c6e6d16470977185d379834f', 'runtime_sha256': '1c32a18ee5846f8ef6c714ebd9e1e14d634a5af3c0ea8e84d9ce070f586c13f5'}, {'path': 'els_server/protocol/quest_messages.py', 'source_sha256': 'deab46e729df0a774c3f4f23bb15d481630c9d7832aeec1d614054e3228cbfba', 'runtime_sha256': 'e69e0559820c9cbbfad2cb045c699af47073f0f0b5671b6acad92990bf5de7e6'}, {'path': 'els_server/storage/account_fishing_tasks_scope.py', 'source_sha256': '7f1607768222a237449d6f5a2f1b8957fdd59f97109ac9998cba7ca62046d792', 'runtime_sha256': 'bad86270367772633a6088cf5ebcb973016f2d478c503f276c2686166e8e679f'}, {'path': 'els_server/storage/artifact_progression.py', 'source_sha256': '5b80a174443dca10ee61d01742111a5f589818304d48afd289b05fb6cbf53d89', 'runtime_sha256': '3d5fcd9d2379a281e4db4e51997af16f1225452299da148a625b19a47e73975d'}, {'path': 'els_server/storage/bag_capacity.py', 'source_sha256': '60d8948a8bd976d9e473266ec8b611a242332186906bbd23e8df0097e46f24f9', 'runtime_sha256': 'e4b98c54eb805f8b62949a168d4c20ca5c68f4225dab4329fba2712b2f0eb9df'}, {'path': 'els_server/storage/blacksmith_enhancement.py', 'source_sha256': 'e3d78a881fc6976e82e832fa43f2215a3a73931e33508690cb1090196d4f58fd', 'runtime_sha256': 'a1c80104443e47399d583d2dc8dd54a421374244c03a9273d762bd521560af43'}, {'path': 'els_server/storage/boosting_2026_accessories.py', 'source_sha256': 'ecdf805ae48574861ad5904b752d002754aa05b0fa047ddcc13fba9dca63f86c', 'runtime_sha256': '637fe48261fdbc0c0d5f6cd7b2331ec3feafd903055471f323ed44b3b6fe2e8a'}, {'path': 'els_server/storage/boosting_2026_fashion_rewards.py', 'source_sha256': 'ce5dc5af6e23613a7feda1f730ca94330b11c6fcc9b5324e2a0384fbe99e5417', 'runtime_sha256': '68849447e60ebe51bc70e06ae438cd5b06169bd4c280c03091affebce7710f0a'}, {'path': 'els_server/storage/boosting_2026_force_inventory.py', 'source_sha256': '2bdaf7ad435059b0ebb864f1432ec7c38c6c7145cf3c2ac640d84e93bff71c71', 'runtime_sha256': '1a974c2dc10a4325e15012f72c32404375c2943796d9fca9447fde660230fc53'}, {'path': 'els_server/storage/boosting_2026_force_rewards.py', 'source_sha256': 'ddba30d94f334d7d2f8cfb6ab6a7155846e4bda12f18eb07c1563f76babee765', 'runtime_sha256': '49be34b40e50de789c735784d8be38aceae19266ff048b41d3c65afb33af5bed'}, {'path': 'els_server/storage/boosting_2026_limited_pet.py', 'source_sha256': '8c569090015eb87f354bf205d6a539054cc29393e42a70dceadf7a59dfa318ac', 'runtime_sha256': '03e5ece2d5bcd49f6f940a1f6cae1323710228cde294bd4cad68da33dfde05a4'}, {'path': 'els_server/storage/boosting_2026_nested_capacity.py', 'source_sha256': 'ba74e696ac3f1868b813f7a45f5998fb4e207a40623d86e38964c47da16a144a', 'runtime_sha256': '1d0817f075e7f08ce3f96f2dc870356599953ffd25bf3e710477a147e055d664'}, {'path': 'els_server/storage/boosting_2026_participation_gear.py', 'source_sha256': '3419da287b26fab137f210e5fe70da0dd1e385d7d4f3a73e219bc2fe812b6d15', 'runtime_sha256': 'bb67f1a4c17369a181a776201658679236c2022f420e788372d02251e09290fb'}, {'path': 'els_server/storage/boosting_2026_title_rewards.py', 'source_sha256': '4b9524554fe0c84c64389c58e33bbf0a8a06963e1201ce0ab6ef6db71d983ef9', 'runtime_sha256': '51305065e7241dd8b37dad6ab4b3c704bfb836080c2d6e7534431442d6488047'}, {'path': 'els_server/storage/character_custom.py', 'source_sha256': 'aa3241688e45319ee45d6c60f3b6be3ed7c584635f5a94ddf033f8c85727c668', 'runtime_sha256': '413dddca29432bb5d1edde9a00016fd402dcff26190338d8bfe1549ac554a70a'}, {'path': 'els_server/storage/companion_state.py', 'source_sha256': 'df12b8a065d61f2db82956f3d787d6fe342435cc155ace8bffa1f270698910bc', 'runtime_sha256': '94e9185cfa79ef4c9d4cb477cf1f6cf6ec2024c60eaefb6663d8850b7a19e0b8'}, {'path': 'els_server/storage/dungeon_equipment_loot.py', 'source_sha256': '01f08fc8d0904b04fa83a6ee36398cc27dc17ec041774b09d3856de2a243f9ab', 'runtime_sha256': 'c05a9abb8ed4fa513d0642170f35b4404669839cf9d12d2e17a120c5152e42e0'}, {'path': 'els_server/storage/el_search_collection.py', 'source_sha256': 'b185c92e9ba9a27556b8ee63dd0304a44539eaebf1eaccd65c7b3afec9990889', 'runtime_sha256': '9e08bc8645faa2673182809fa0da90ee2d92414dc12aac78600487cf61509589'}, {'path': 'els_server/storage/elixir_economy.py', 'source_sha256': 'a814e05aff6ac99dc890ab10f14bbe475c1847756d48f62111b0e27690453065', 'runtime_sha256': '561cd65815ad940baa2afc7c446228eaa66896ee21f97cf67523eb5a80a9ca58'}, {'path': 'els_server/storage/enhancement_scroll.py', 'source_sha256': 'e098770ca9e772717d4104fff32a40df4a1cca11eca15d6ef33b3da50c895612', 'runtime_sha256': 'b62f1669e0ce4bb03f8a25afee96a08374540892f7e9f543bc43a9cfa1460c6b'}, {'path': 'els_server/storage/epic_followups.py', 'source_sha256': '00c5e1ce407943648754daefb2af6abbb9521c77c957a9d166f82c482479c775', 'runtime_sha256': '7b2d8d9ca2861c5d36b337e7ab87b3b51bc33f5bd9601565d31d57fa0d089f6d'}, {'path': 'els_server/storage/expansion_items.py', 'source_sha256': 'c2416708be5dccad0dd18296a4a5f6698e83823522bc95cb43b180b64ec25c2f', 'runtime_sha256': '17634457df539054806f3352f19cbf82f702b5da3e014132f0cb9f51fdb6b104'}, {'path': 'els_server/storage/fixed_cubes.py', 'source_sha256': '9d291013c158354df4189ced34097f3531827667b4f56cf4ac86ab852df60a14', 'runtime_sha256': '1c87ed9f49081dd3619bf6eaf0e653ef6732a6848cff4c3a636c90b78fe556e5'}, {'path': 'els_server/storage/force_rank4_schema.py', 'source_sha256': '67585448ff2278e95b0539b55cf902a072380224c95a0bbac18094742c74a348', 'runtime_sha256': 'bb209b9938ebc8506baebf4fbc422faa3fc5cc7fe91e4a85dae324d7e46b47ae'}, {'path': 'els_server/storage/furniture_boxes.py', 'source_sha256': '44b96ddff5111f6fd06d074ab219877bf641370429dd485582a5d881774f57de', 'runtime_sha256': '13808cd061742f06f8a4dbe5fafda67f58648e786ec00f6ae9e59240a642b2f7'}, {'path': 'els_server/storage/inventory_state.py', 'source_sha256': '642cbdc5af905f1452abbf038ffc3569aa47205c1a70e6036063a59129b6d000', 'runtime_sha256': 'a31f771ad333dc1e7c0406d6da9972752d05b8b17b64b2d2dc93892c7d1e98d9'}, {'path': 'els_server/storage/job_reward_boxes.py', 'source_sha256': '47bbc0bfd9ef0622d79aa02e0229cf77116152d2951d1312769354de85749ef8', 'runtime_sha256': '78ce660516fa6e0c4fde70c13040fab452c870de68afe52adb2b93b2f6b224f0'}, {'path': 'els_server/storage/life_stamina.py', 'source_sha256': '62f70688b6f7ad6b9f39b3dc5f4ce933754e1b8e8920e61bcaa66561f7b4b949', 'runtime_sha256': '9e75253fe22e7d5b800387a1450738a9b1e55eee14cd80d0ee51fca983b756c2'}, {'path': 'els_server/storage/local_clear_rules.py', 'source_sha256': '9430cf57a82d27cb47ee2e9454b7614f77c5633b4976070150f81accdc0233ae', 'runtime_sha256': 'bbec4b2ec3528ef2a18da39a3809abd16847daa4df22f15a87a111b596bb3505'}, {'path': 'els_server/storage/local_state.py', 'source_sha256': 'e5bdd9c7c9b053d06198a6732f6a7e8bcf4cac301f919f1faf92fd20f099e879', 'runtime_sha256': 'f532e2346fdd4270993c1c34ef7e9d8fce771fdd04b34869e3d59a116bdb5c3b'}, {'path': 'els_server/storage/paid_enhancement.py', 'source_sha256': '111228f7d81f6c117dc5c8b7c8ba0f53df997515936f1833830f567ef3149f21', 'runtime_sha256': 'b90e345c69915a78183be33457a598514b0e2bb2a97576159fca2936ccf916dc'}, {'path': 'els_server/storage/pet_support.py', 'source_sha256': 'a422ae02318878c3be6d108ef289cd31a28f80cebd137bb309ae62261efef900', 'runtime_sha256': 'e718f9824928242a98a900087cc55d712932d6ae2f94109f9ac474a91085280b'}, {'path': 'els_server/storage/player_mail.py', 'source_sha256': '049614027c4fe5e03ac38f15c492c9b3eab10678dd62623696bc70503ba60401', 'runtime_sha256': '7443226f96b8527a4f1b2e735461664065c9d800ed14c6509f7c2d43ba8aa690'}, {'path': 'els_server/storage/potion_choice_box.py', 'source_sha256': '458509687eb9c5f218c1692e79620bef5907fbf08e34f5900ecb734ef3e6a50f', 'runtime_sha256': '8197e26b0b5cc5b7130caa5fa452cdaad4b2f0ee92a59c74af49f746bf9c985c'}, {'path': 'els_server/storage/promotion_reward_boxes.py', 'source_sha256': '1c1f4a94722c0b9584263eaf82bf87a4b5857bf67b34b73f81e4d0c3e9c2887f', 'runtime_sha256': 'c3b18d161b9ba37b2f6944d60ada310fba5ffb3ee6dd833b13dc34c817140f7a'}, {'path': 'els_server/storage/published_2026_bundles.py', 'source_sha256': 'f1a89e42baaab6db74af4eb094b61b23b1f864607c9b8e51384d9565a48c3a1f', 'runtime_sha256': '4b589053e008b19480eb64bbc760b996778da5669103b3ebd2ef03cc185bffa5'}, {'path': 'els_server/storage/raid_reward_actions.py', 'source_sha256': 'd600a06e37b4973747c1260339a121f2d58c94cf1ccf635b0dfc379373675132', 'runtime_sha256': '432881373fefbda36ab5d948021f02005227499ac92040dc414ee844383c1e26'}, {'path': 'els_server/storage/resonance_state.py', 'source_sha256': '910bdcc0cf06b500bfd598b20fa411e14240dfab16654c303efd238af7f810ea', 'runtime_sha256': 'ff2a51fd64817e3449e7fde3783e285ea7456423baace92bfeeb76a4b274d983'}, {'path': 'els_server/storage/reward_state.py', 'source_sha256': '36aed4611833bb6e94853b2f49ace88a79cb2c52640e121f5585a58939a33965', 'runtime_sha256': '2a22b4d464ddbc26d61a6bb96e689b45fafc088a2c1c6a14273cf90957617bef'}, {'path': 'els_server/storage/seal_quests.py', 'source_sha256': '210b2e7aaae4ff7a0eb4bd9135b2ecf86ab584a83b7735a35da0b23dff40fbe1', 'runtime_sha256': 'e82d0ce4f3b5606cb432979756f96c8fb1389aced8fc57bb4d67698a5ce1072e'}, {'path': 'els_server/storage/shop_state.py', 'source_sha256': 'f337f348fa0a6b354b02c704ece5ade6d3f26204b0c849ecba42959c95553863', 'runtime_sha256': 'c1d7d9233d815ed00dca9ba6e0c55e631dd3b0c4c45b122e030b6362e5622638'}, {'path': 'els_server/storage/skill_unlocks.py', 'source_sha256': '5cb3f0c5772738f0b31561b00f3764a4fb2f912f0fd0585313f3aafb8aba4411', 'runtime_sha256': '5a5a9c59bd856772aac68ff557d1d5d4032845804a7dfd416f7a93a2561ff9c7'}, {'path': 'els_server/storage/teacher_elixir_boxes.py', 'source_sha256': '5916da306d579eb68c3f3bdc5ad5fe96225662358edc5a9540c32798f3d16536', 'runtime_sha256': '075dd019fe42a9fee026757c9b19d9a6a6a4789c1ba312bc7ab13ab7ab6dca91'}, {'path': 'els_server/storage/titles.py', 'source_sha256': 'a4a57a2ab6b304f4f60739a47e4863200151dd4fe74defb5cb8fafe2e670f734', 'runtime_sha256': '542adeb7c3b585b5ed291a5f510b0b166f491ef3394c25b4a968cfb24c8f4e65'}, {'path': 'els_server/storage/town_dialogue.py', 'source_sha256': 'afc54c0dc7266b7180c8ec64554f85a56ed44f4cf361210bec7df064028d1978', 'runtime_sha256': 'db95f0257c0cf0031362da94364426d9ef5258da4bad6bb7e42e44335d264492'}, {'path': 'els_server/storage/town_travel.py', 'source_sha256': '16af21bcda11d9349bda96260e7961c5e12a1dd40d238918525f1ba6aaeeee58', 'runtime_sha256': 'd32163605f847cd6e6de08fb0da91c9dfa643032c6a87f62bbcb1b1d99647c5d'}, {'path': 'els_server/storage/wardrobe.py', 'source_sha256': '611bdc6eb8fab01531e67b306308e252565f7add229a17165cf0024e52b6136e', 'runtime_sha256': '6feacc41e858be77460a65ccd0889945d7dbed8df4870cfe58390150c9d2a3c9'}, {'path': 'els_server/storage/wardrobe_ticket_box.py', 'source_sha256': '6a92fce60ecca7ee0eb8f105a76657f947bef97dd0effc3d1adb07729f700509', 'runtime_sha256': '848294d9376d5dae6ca45bd11dcb82e3c6ba766c99e0ffead46660f97dbcc824'}, {'path': 'els_server/storage/white_armor_boxes.py', 'source_sha256': 'f4781ccea7c333143c9ac48763aed75535764f0af49a05aa4ff3bc5e4f51405c', 'runtime_sha256': 'beca95c8bc801545033567a5cb832e1ee1337883523d3a411933a0f25c8b087a'}, {'path': 'els_server/storage/wisdom_potions.py', 'source_sha256': '2149512ca863f0521a136afc1d4da1a6cba37465235ea69dc450f7922cb7d05e', 'runtime_sha256': '36a97d11d5afd0944b4a6d21c3df6ce13f2239b97d93a6027362e49cdbb9ea9d'}, {'path': 'els_server/transport.py', 'source_sha256': '0786d872d918ef6fe3b42e31f844c3555dc1fc0095b5419c6626a3f30fe31d7c', 'runtime_sha256': 'e243b7f4f0364db55dfe0e7bb035b180702a900fb3251e011af8235d4a9de19e'}, {'path': 'tools/client_compatibility_profiles.json', 'source_sha256': 'f1661177edd96176b2bd0b7e869215ab27e0337e186f77c1bd026248b2ae4a9e', 'runtime_sha256': '335eeae744be0616431285b21a914ea886518fb33503615407c2517f7676dd62'}, {'path': 'tools/launch_client.py', 'source_sha256': '74f5c5406c93b526e1bb34cac36c5eb4ef8eeca4fbc3292d05c5de8f18f08142', 'runtime_sha256': '9cb6fd2b579b11c90ec2ccc31babd3c383e9b8bbd43ccfed330cdf4aa689e6f8'}, {'path': 'tools/native_cache_sync.py', 'source_sha256': '225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856', 'runtime_sha256': '77461731de1c7b512c334078907d6224f84c97b61f0fb8aa0d7d2b0b3a802236'}, {'path': 'tools/probe_updated_client.py', 'source_sha256': '82b3339b0f0a780bd118bfcc7fa63b5fbf610281a054b95ea0be4d40d3c3f649', 'runtime_sha256': 'cf30949333122e39485a7a33fc1e0a103b89e44ad3caf7243f46108f98752835'}, {'path': 'tools/trace_dx11_login.js', 'source_sha256': 'c837f547abf0e34a2768256f503af5dc04f3caccc01e5f88dc7675bf009c30ed', 'runtime_sha256': '640a6daeffd8e43382a1e0e5de9b3aa4a8a75716f265d7d372f2344179f75bb3'}, {'path': 'els_server/storage/wear_moves.py', 'source_sha256': '5fc0b3d4f6f69a94204e48dd8aed4ef0435458e8971919cc24a9131df936688e', 'runtime_sha256': '47cce25509307d0fc11beb33f3cb7ec60da9c57fb6f4a059f257c1fc64e3a2b7'}, {'path': 'tools/native_cache_sync.js', 'source_sha256': 'e2f86915262ba1ea1e919eb1b33c5f022e1a311bd267569bb02f3aee7368083a', 'runtime_sha256': '96b4466e1eaaf46f1c81b69a028078df43e298baec33cf9b9b8adbaaa66ea6cf'}]
REPAIR_ADDITIONS = [{'path': 'analysis/shop-missing-20261031-v1/CharCustomData.tables.json', 'runtime_sha256': '22246d5f5baa677b0fe22dc6f809727dfa9eea5d6d44a5cb33e2255de737b864'}, {'path': 'analysis/shop-missing-20261031-v1/package-membership-supplement.json', 'runtime_sha256': 'e0947d0a0fc7c36b39d10b990dd53842f3a395d41e97cc0936b24fba4689a2bc'}, {'path': 'analysis/shop-onepiece-20261031-v1/fashion-exclusions.json', 'runtime_sha256': '329860050bd8dd428981159364d91a606b30a1b3278af9355957b8e295900dd3'}, {'path': 'analysis/shop-onepiece-20261031-v1/native-body-proof.json', 'runtime_sha256': '286ce66a5b5a310e5285ff52d787074aeb8bf8d917924182c74cf20829544dd3'}, {'path': 'els_server/data/cooking_clear_materials.json', 'runtime_sha256': 'f6773c9d5ba53845307f38c880088420d665914b581f24a12138a89fc6ab8efb'}, {'path': 'els_server/data/el_search_collection_tickets.json', 'runtime_sha256': '216aca07fdd12ddf4ba9bfeab3a58d16eca56b89aa4f557804ee8f9654347ccb'}, {'path': 'els_server/data/el_search_effects.json', 'runtime_sha256': '00e11bb7fceb4818d2c64b06aa9d2b47fbe6d2f4150107c2ca1cd565b1784d9a'}, {'path': 'els_server/data/enhancement_unlock.json', 'runtime_sha256': '79121bc46abedc28f723442064bc2baa165da031146bff5f96a016354457874e'}, {'path': 'els_server/data/field_travel.json', 'runtime_sha256': '9e11381d603e305779b9cbb9972ad0651d252a0f717e19e70f718957161710b9'}, {'path': 'els_server/data/field_travel.manifest.json', 'runtime_sha256': '86ecac411fec64184149e7359e345174a517edcf62c73429d7e9bab6d346306b'}, {'path': 'els_server/data/mentor45000.json', 'runtime_sha256': '4240cb07e9a8e96480b1992d560c5748cec16c1ffbbe85ff84bfc659d7c4c64d'}, {'path': 'els_server/data/native_force_catalog.json', 'runtime_sha256': '6dab774cc2efcfaf94aa4aee12f308482d072268f709b0bf90f1e67a5e96adb6'}, {'path': 'els_server/data/native_line_triggers.json', 'runtime_sha256': '7de0f2f9697ebc7481c7443c2e51f5fb236ce82a6f6d4504d6aeb5427de702b1'}, {'path': 'els_server/data/owned_reward_boxes.json', 'runtime_sha256': '3ed67020222f3106c97dea75c4224937c1094aef71ba7c247b95d518a2ca7321'}, {'path': 'els_server/data/pvp_seven.json', 'runtime_sha256': 'bb1d8ff4108dda77347351aff8a57421fb4cd277bc15d6f9296a1e639ddaffeb'}, {'path': 'els_server/data/secret_clear_rewards.json', 'runtime_sha256': 'e45e11e244f6a592f2bd00a2d2754f09ba8380ee0d2fe2f761eeda9f8206504a'}, {'path': 'els_server/data/secret_clear_rewards.manifest.json', 'runtime_sha256': '9d3314e14883fdbff768270cdced86a742b236e197a88160955e731856a9ef12'}, {'path': 'els_server/data/secret_fragment_box.json', 'runtime_sha256': 'f77ff364da9987330ada36eb1c5da920e06e431a68300ac1d56f010f357b3322'}, {'path': 'els_server/data/special_task_readers.json', 'runtime_sha256': 'bd2f99a8cf340276b93963336e07d20c24e381a92e0cbed95baac317ad52f95f'}, {'path': 'els_server/data/weapon_growth.json', 'runtime_sha256': 'b1df15efdbe2f0130157cd960caf9c248852c6fca74a7dcc80775984509085cd'}, {'path': 'els_server/domain/bag_expansion_flow.py', 'runtime_sha256': 'e88ccc255174141e2c0b79e0b4116637d355a418d394ec76086d10f1e7716b4d'}, {'path': 'els_server/domain/clear_ed_display.py', 'runtime_sha256': 'c0ed6c6540861b72b71e8cec2adf459c1bf3577b9ca1744a36d3d08a214a64c1'}, {'path': 'els_server/domain/cooking_clear_materials.py', 'runtime_sha256': '3d9f445f9c1eb815733e53a3634c8643bb37e22ed3c8a0eb7a0f0fc6f8dc5e53'}, {'path': 'els_server/domain/el_search_collection_flow.py', 'runtime_sha256': 'ac57dd1ec93dc181f7a890a0c548db419e1439ce6f38d1db178583dfbad47790'}, {'path': 'els_server/domain/el_search_collection_quest.py', 'runtime_sha256': '693bd9e8dda78f46d9258370ed6d7ce1ac9e4c360a2cad6826871cb0577aa1fc'}, {'path': 'els_server/domain/el_search_collection_tickets.py', 'runtime_sha256': '3df0a731f5d21efebfa0839037f1354df0d7e7c473abf45c92a4b1546789c86a'}, {'path': 'els_server/domain/el_search_effects.py', 'runtime_sha256': '51370209df91161d29bea3bc70bf07935c23190433f65e321b2a26a2997e6cfb'}, {'path': 'els_server/domain/enhancement_unlock.py', 'runtime_sha256': '43a85b698fc0884c1333289bf1c17e337c0581593030e755e1e5ceab3f37ca03'}, {'path': 'els_server/domain/field_travel.py', 'runtime_sha256': 'cbf3445912b5efaf67e791c883cb39f0441562bea17695c242031dc46dc005a0'}, {'path': 'els_server/domain/friends_pvp.py', 'runtime_sha256': '73d2116be714cdeebf4600fe4ec475459557e84b2cde685f8a0ff984fc056e12'}, {'path': 'els_server/domain/guidebook_flow.py', 'runtime_sha256': '0aff506e990c5e1c223b3c0b3c477799bd2205c549de42a0437fe3ac1a504c1d'}, {'path': 'els_server/domain/mentor45000.py', 'runtime_sha256': '9075f107421653fe17db2db782392e1d7707560db09569bd6493ae740b30e774'}, {'path': 'els_server/domain/native_force_catalog.py', 'runtime_sha256': '32bd3df4b8ca1cfb404a84b1ab8fc6e7331b70bcce62ad7354beb958a284db3b'}, {'path': 'els_server/domain/native_force_exchange_flow.py', 'runtime_sha256': 'd8fdb7c1e8cb2358fa748bce90ad57c03367f8bc7cea87572a8d2cc0a1599689'}, {'path': 'els_server/domain/native_line_triggers.py', 'runtime_sha256': 'bb50d3362e815e78e6455080f0372a717f4da6c6145e0243d114557e187533f7'}, {'path': 'els_server/domain/native_script_loot.py', 'runtime_sha256': '3f4bcf249ea328adfe440b19f01bb17c43a614847ebbcde9505c66949b634b78'}, {'path': 'els_server/domain/owned_reward_boxes.py', 'runtime_sha256': 'c198f7946c53f451b1e1b9d6fc32f485a98663d0ff91617cab8bbe794ce0ecdd'}, {'path': 'els_server/domain/pet_expedition.py', 'runtime_sha256': '29e569107b8e895095c06c49ac5d88ff947b7877d398ef010956ba0fbcf65cad'}, {'path': 'els_server/domain/pet_expedition_flow.py', 'runtime_sha256': 'afdf002161a1e8ad2edd9aacb9c0dff5ab6038f8cfa222e2f326d5486e3ded32'}, {'path': 'els_server/domain/public_controller_rules.py', 'runtime_sha256': '8ffb98a023f9186d418b870c1e70b3bc92dc9aac55d61693eb9e33af1f7e6e20'}, {'path': 'els_server/domain/pvp_actor.py', 'runtime_sha256': 'c5a196b66bc43bb7efe967c6c187e9c84149f4a5761ffe5830978ae0ae370947'}, {'path': 'els_server/domain/pvp_loading.py', 'runtime_sha256': '8f28b6872ebaf36998fb83935c89d81f2a87ae3b4d83fc8516315c428a107abb'}, {'path': 'els_server/domain/pvp_official_1v1_policy.py', 'runtime_sha256': '6be3aec50428bcbf8016a6bbd9ce1ff5ba6ad236f1de83f3638f702a91c5b765'}, {'path': 'els_server/domain/pvp_quests.py', 'runtime_sha256': '3467de3eb9c2f4d81a5d8614638bc58ac95bb428bc5786c1f3b426aeee913165'}, {'path': 'els_server/domain/pvp_registration.py', 'runtime_sha256': 'edadb95a8535171be86821916967e2bb55ccbd3454c92c5ac55f7d6978e5df99'}, {'path': 'els_server/domain/pvp_round.py', 'runtime_sha256': 'c730b5e7b49ad319044d955e7215dc4229a09f070fdb5a9cbcb376b748f10777'}, {'path': 'els_server/domain/pvp_support.py', 'runtime_sha256': 'f43b933dfd69930d62c8bc5453c14a6e19f748b99f27d51e67a5a921e91419e1'}, {'path': 'els_server/domain/secret_clear_rewards.py', 'runtime_sha256': '8ec3aff99ff814eec1d67b2a64a099871d5bb4617187fed1ba1fd58474e1cb2d'}, {'path': 'els_server/domain/secret_fragment_box.py', 'runtime_sha256': '0b50cd18f1712fe9bc65d0f6a24cb78a311ad12d099ac974592a21e86f24c572'}, {'path': 'els_server/domain/session_auxiliary.py', 'runtime_sha256': 'be7c151859b4efbdc235e82a6a5c5bddfd42af3915fe3e75ed01c8fdd48ef72e'}, {'path': 'els_server/domain/special_quest_rewards.py', 'runtime_sha256': '14444dafbf13118fc7af901f64e664f4ebed2af5560592e349b44bc3261f1957'}, {'path': 'els_server/domain/weapon_growth.py', 'runtime_sha256': '0044c8240a34ba566dbba5c55cdc205c7d5726340b7721678a14e9cbc9bd07d9'}, {'path': 'els_server/domain/weapon_growth_flow.py', 'runtime_sha256': '8076293f9fa7257ae6aac32c028b25809e41d9ad7f83dacd1edc251b32512258'}, {'path': 'els_server/protocol/bag_expansion_messages.py', 'runtime_sha256': '93e293d5f1495906cef05d1d41bbb33c1d3ce4752870bd97b64360dd5021908b'}, {'path': 'els_server/protocol/guidebook_messages.py', 'runtime_sha256': 'c44ab37ef9bd477eecb7e9bf78ad5adce4f77ecbd917f430624845c0897734da'}, {'path': 'els_server/protocol/pet_expedition_messages.py', 'runtime_sha256': '381bdc069db97449ee89abb552588ab5c03567c8c8ec52e8250253c134a0c421'}, {'path': 'els_server/protocol/pvp_death_messages.py', 'runtime_sha256': 'c7a3f908348d4b2555c1db67e48aad22b7c951510529f9906f3fccd1d96ef8f6'}, {'path': 'els_server/protocol/pvp_loading_messages.py', 'runtime_sha256': '3b71793291770cd2425d7d95f6d01c637202e8af9a9852c6b8ef0b79acc73732'}, {'path': 'els_server/protocol/pvp_match_messages.py', 'runtime_sha256': '324eb6127083ed30331e2393e6ee1fc4aad1651b4a9e071f869222eef71aa727'}, {'path': 'els_server/protocol/pvp_play_messages.py', 'runtime_sha256': '6fbfa6993031598d9285b21b8d6cf28a9bab6f10858f13ec0c1a2ba22f7277fe'}, {'path': 'els_server/protocol/pvp_result_messages.py', 'runtime_sha256': '16784985abeec7c05920a2e793c35f7570c4b022c27d15b6108e2a00cb5ee707'}, {'path': 'els_server/protocol/pvp_room_messages.py', 'runtime_sha256': 'f2ce022482e22ea6706f17aaf780ccb49004ba8302da6885b73019c9e24d98c6'}, {'path': 'els_server/protocol/weapon_growth_messages.py', 'runtime_sha256': '8a84a4533647b74183f19e65fd8ef7114cce313dbfcaeaeee952e4852b46c408'}, {'path': 'els_server/storage/collection_synergy.py', 'runtime_sha256': '8a13005bb70db18500075247ec8b9820288e0fcca1b7238685f6e0cc27f51ea2'}, {'path': 'els_server/storage/el_search_collection_tickets.py', 'runtime_sha256': '540190882d5115a9ee61d4c0dbfdbb36312525cf0924c8b2cc4f65e8eb7a90fe'}, {'path': 'els_server/storage/guidebook.py', 'runtime_sha256': '43186511749f55d1af69f813a4427cd4472a26ef036bc43708042535623850de'}, {'path': 'els_server/storage/henir_force_rewards.py', 'runtime_sha256': '2279578c9f088024aea083132105c81e27d03e4efceddd75a302dfceb3e1cf13'}, {'path': 'els_server/storage/mentor45000_scope.py', 'runtime_sha256': '71510006a1350b6235ce31ff4d20a28ad1a4fa37feba4942afcdf3eab698c7c8'}, {'path': 'els_server/storage/native_force_exchange.py', 'runtime_sha256': '2d7585d4229aa76cdad8739cb0237a9c438a44e28365477345987deb2fd16615'}, {'path': 'els_server/storage/pet_expedition.py', 'runtime_sha256': '32cfba41c42f876de7bcf36853e110e65f4889d138e9da315c9fd70eaf7a3c47'}, {'path': 'els_server/storage/pvp_official_profiles.py', 'runtime_sha256': 'f0e6220c149951f233bf509c39671c7b57897b69a11ec90c67528bc883bd397e'}, {'path': 'els_server/storage/pvp_settlement.py', 'runtime_sha256': 'de1dd5810c5f85745204fa4399c0bfd9af8e00907954f8fd25c4cd076d4148cd'}, {'path': 'els_server/storage/weapon_growth.py', 'runtime_sha256': '5b0ab5e2fe506400405b76c028b99d76ead02f82737770350da94caf8e21098c'}, {'path': 'tools/dungeon_map_markers.js', 'runtime_sha256': '19d77e3b820702a638be0c5cf5282955f721407e8c786d90bf291348a5a6bd59'}, {'path': 'tools/dungeon_map_markers.py', 'runtime_sha256': 'c232f0da4dce6cb5255121a52f9170fc8cfde34af73e2dfbddb31760c0f000f6'}, {'path': 'tools/local_fresh_state.py', 'runtime_sha256': '9bed6a12b3adeeb63f49d60f81bc8f89a64c1e676726ee09a7d627382efe9d56'}, {'path': 'tools/native_wear_sync.js', 'runtime_sha256': '8655b2d8ced704417319c535ed08b4be6c3b56ebe55eedec7fe6cedf3100e604'}, {'path': 'tools/native_wear_sync.py', 'runtime_sha256': '0c448f6b5aa891e633b90ef5d221c56af5d422721dece5a7c8209819aca937f7'}, {'path': 'tools/pvp_hp_source.js', 'runtime_sha256': 'ac2c528f4f1a4bd881fa62b741404d8e6b24846b4540aae11c5986d96e92e6ec'}, {'path': 'tools/pvp_hp_source.py', 'runtime_sha256': '8b57ee9a758ea8094d7d7154188fe90731b0af26ab9556b2f4d009acd223a3a8'}, {'path': 'tools/world_event_iteration.js', 'runtime_sha256': '06fbd593215c6a03774d9fbcc594754b7edee5f083c015331e39bb867db69ed0'}, {'path': 'tools/world_event_iteration.py', 'runtime_sha256': '01d80c31b6ac048a9c0383ca82a4ed2661bbc1ee1afb59932861707409f26d6b'}, {'path': 'els_server/domain/group_wear.py', 'runtime_sha256': 'c491315c2b70ba3209da77eb9b75ab2ff6cbcd670da002a00c847ec40a19b109'}, {'path': 'tools/native_group_wear_sync.py', 'runtime_sha256': 'fc17e0d241fe52ea3ec41f78c63eca13d9bd773190ad86bb4705d85a1756cd96'}, {'path': 'tools/group_wear_sync.js', 'runtime_sha256': '1e3813f736fb40dbdfd7092f7d0e8ef022b888c2db9cb0f4c25abef2255c5766'}]
REPAIR_CONFIG = '4e14201a91e69df87af8bf5aac226f303f027fde76b98e2967b85c442c2e8124'
REPAIR_POLICY_KIND = 'exact-v55-transitive-to-group-wear-v1'
REPAIR_STRUCTURE_ENVELOPE = 'e11a4123f68270db611b7b5fda991c8630b9650a6de2a842d3c447b8d762cfc0'
REPAIR_STRUCTURE_METADATA = '8acdfd6bbfcdc02af18ee29e3e8b1fbffcc9b48370de5d83806fb7424a6e0c27'
REPAIR_STRUCTURE_METADATA_LENGTH = 2306378

def repair_require_bindings():
    need(all(isinstance(v,str) and v for v in (REPAIR_SOURCE_RELEASE,REPAIR_RUNTIME_RELEASE,REPAIR_PROFILE)) and
         all(hash_text(v) for v in (REPAIR_FORMAL,REPAIR_PROFILE_HASH,REPAIR_SOURCE_ROWS,REPAIR_RUNTIME_WITHOUT_METADATA,REPAIR_SOURCE_SET,REPAIR_CONFIG)) and
         type(REPAIR_SOURCE_COUNT)is int and type(REPAIR_RUNTIME_COUNT)is int and
         type(REPAIR_OVERRIDES)is list and type(REPAIR_ADDITIONS)is list,
         'Final C3 repair source/descriptor bindings pending; stop before Prepare/initialize')

def repair_target(metadata):
    return hash_text(REPAIR_FORMAL) and (metadata.get('release'),metadata.get('source_release'),metadata.get('source_formal_manifest_sha256')) == (REPAIR_RUNTIME_RELEASE,REPAIR_SOURCE_RELEASE,REPAIR_FORMAL)

def repair_v44_predecessors(entry):
    # One public V44 object contains the original two fixed predecessors. Never
    # duplicate their megabytes or broaden the old structure policy limit.
    import base64
    need(type(entry)is dict and set(entry)=={'name','old_signed_envelope_base64','old_signed_envelope_sha256','old_metadata_base64','old_metadata_sha256','old_formal_rows'}, 'Exact V44 predecessor fields required')
    need(entry['name']=='structure', 'Exact V44 predecessor name required')
    eb=base64.b64decode(entry['old_signed_envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()==entry['old_signed_envelope_sha256']==REPAIR_STRUCTURE_ENVELOPE, 'Exact old V44 signed envelope differs')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1786 and signed['archive']['sha256']=='d4481559a4c0ffff4bc4b94855d7ae5dcbfc67f5295a1f7428da69de9cce02d7', 'Exact old V44 complete runtime differs')
    mb=base64.b64decode(entry['old_metadata_base64'],validate=True)
    need(len(mb)==REPAIR_STRUCTURE_METADATA_LENGTH and hashlib.sha256(mb).hexdigest()==entry['old_metadata_sha256']==REPAIR_STRUCTURE_METADATA==old_rows['local-bootstrap-source.json']['sha256'] and old_rows['local-bootstrap-source.json']['size']==len(mb), 'Exact old V44 metadata bytes differ')
    old_meta=json.loads(mb);old_formal=rows({'files':entry['old_formal_rows']})
    need(len(old_formal)==old_meta['source_file_count']==1332 and source_rows_hash(old_formal)==old_meta['source_files_sha256']==STRUCTURE_SOURCE_ROWS, 'Exact old V44 formal rows differ')
    inherited=structure_policy(old_meta,old_rows)['structure_contracts']
    need(len(inherited)==2, 'Exact two validated V44 predecessors required')
    result=dict(inherited);key=(STRUCTURE_RUNTIME_RELEASE,STRUCTURE_SOURCE_RELEASE,STRUCTURE_FORMAL)
    need(key not in result and (old_meta['release'],old_meta['source_release'],old_meta['source_formal_manifest_sha256'])==key, 'Exact old V44 source tuple differs')
    result[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    need(len(result)==3, 'Repair requires three distinct exact predecessors')
    return result


def cache_v45_predecessors(entry):
    import base64,zlib
    need(type(entry)is dict and set(entry)=={'encoding','data'} and entry['encoding']=='zlib-base64-v45-public-v1', 'Exact V45 predecessor container required')
    need(type(entry['data'])is str and len(entry['data'])<=4*1024*1024, 'Encoded V45 predecessor too large')
    compressed=base64.b64decode(entry['data'],validate=True)
    need(len(compressed)<=3*1024*1024, 'Compressed predecessor too large')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail, 'Truncated, trailing or oversized predecessor')
    d=json.loads(raw)
    need(type(d)is dict and set(d)=={'envelope_base64','metadata_base64','formal_rows'}, 'Unexpected predecessor document fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()=='5004c9eccdbe717c41581c42c0b56658bb23009fdeebda21b7e5050380a81af8','V45 signed envelope changed')
    env=json.loads(eb);signed=json.loads(base64.b64decode(env['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1794 and signed['archive']['sha256']=='0e3efdb292016dee1904d86c463ac35165496ec9524cc5d7ea89a3c7325fb9b5','V45 archive identity changed')
    mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(len(mb)==3789766 and hashlib.sha256(mb).hexdigest()=='2adb90a9bd462e004fa7b8861fa3f9af91161ba383f778f85843f915a2010daa','V45 original metadata changed')
    need(old_rows['local-bootstrap-source.json']['sha256']==hashlib.sha256(mb).hexdigest() and old_rows['local-bootstrap-source.json']['size']==len(mb),'V45 signed metadata membership differs')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    key=('local-git-first-run-shared-repair-20261030-v1','local-native-shared-repair-20261030-v1','2291d8c2e24f72209e802de082fda701f623fc87609e201206136f5862ff9fd5')
    need(tuple(old_meta[k] for k in ('release','source_release','source_formal_manifest_sha256'))==key,'V45 source tuple changed')
    need(len(old_formal)==1340 and source_rows_hash(old_formal)==old_meta['source_files_sha256']=='3e8430e117e2cc370801c06a7d62f54c10ee3fa4d4357ebccfc4f40231701947','V45 formal rows changed')
    contracts=repair_v44_predecessors(old_meta['upgrade_from']['structure_predecessor'])
    need(len(contracts)==3 and key not in contracts,'V45 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def owned_v46_predecessors(entry):
    import base64,zlib
    need(type(entry)is dict and set(entry)=={'encoding','data'} and entry['encoding']=='zlib-base64-v46-public-v1', 'Exact V46 predecessor container required')
    need(type(entry['data'])is str and len(entry['data'])<=4*1024*1024, 'Encoded V46 predecessor too large')
    compressed=base64.b64decode(entry['data'],validate=True)
    need(len(compressed)<=3*1024*1024, 'Compressed predecessor too large')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail, 'Truncated, trailing or oversized predecessor')
    d=json.loads(raw)
    need(type(d)is dict and set(d)=={'envelope_base64','metadata_base64','formal_rows'}, 'Unexpected predecessor document fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()=='bd6ad8dd2301b4c4d8ec24209889c0c32d0a7ebb23bc0385824e7f4ce575defa','V46 signed envelope changed')
    env=json.loads(eb);signed=json.loads(base64.b64decode(env['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1794 and signed['archive']['sha256']=='ee68800402e6dc7ef6e8317d07595ffd4b220034c1477a0f122faf311e9d9d78','V46 archive identity changed')
    mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(len(mb)==2868747 and hashlib.sha256(mb).hexdigest()=='8df4c6fe66868123516414a9351026c1d5dbec84a42fd26421ea735cd81a349c','V46 original metadata changed')
    need(old_rows['local-bootstrap-source.json']['sha256']==hashlib.sha256(mb).hexdigest() and old_rows['local-bootstrap-source.json']['size']==len(mb),'V46 signed metadata membership differs')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    key=('local-git-first-run-cache-exact41400-20261030-v1','local-cache-exact41400-20261030-v1','7dd7cab0d08b85c9803e0c96d92109d4d5c2d22d729e47c0104d7f8e40d93b35')
    need(tuple(old_meta[k] for k in ('release','source_release','source_formal_manifest_sha256'))==key,'V46 source tuple changed')
    need(len(old_formal)==1340 and source_rows_hash(old_formal)==old_meta['source_files_sha256']=='bd405d403efec936c3a78a8a1a6eefb1a48debdbcd2f3c6b6e44b7c804430f6e','V46 formal rows changed')
    contracts=cache_v45_predecessors(old_meta['upgrade_from']['v45_predecessor'])
    need(len(contracts)==4 and key not in contracts,'V46 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

ACCESSORY_V47_PARTS = [('accessory-predecessor-a.txt', '1bb578d4f823db385caa49f7657feb9893c12153ec5dc557eba1ecc8c2f9fa62'), ('accessory-predecessor-b.txt', 'a178e771ba22bac3a2757cae88e65a8f580f9955f5f3d2ea76161a11260ec679')]

def accessory_v47_predecessors(entry):
    import base64,zlib
    need(type(entry)is dict and set(entry)=={'encoding','sha256'} and entry['encoding']=='embedded-zlib-base64-v47-public-v1', 'Exact V47 predecessor container required')
    need(entry['sha256']=='023f6ee8f9375eee96e5e975d3197c028cc6e47b6d3cfafdf4e297b7afbaf4c1', 'Embedded predecessor identity')
    pieces=[]
    for leaf,expected in ACCESSORY_V47_PARTS:
        raw=no_links(Path(__file__).resolve().with_name(leaf)).read_bytes()
        need(len(raw)<=3*1024*1024 and hashlib.sha256(raw).hexdigest()==expected,'Embedded predecessor part changed')
        pieces.append(raw.decode('ascii'))
    compressed=base64.b64decode(''.join(pieces),validate=True)
    need(hashlib.sha256(compressed).hexdigest()==entry['sha256'],'Embedded predecessor digest')
    need(len(compressed)<=4*1024*1024, 'Compressed predecessor too large')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail, 'Truncated, trailing or oversized predecessor')
    d=json.loads(raw)
    need(type(d)is dict and set(d)=={'envelope_base64','metadata_base64','formal_rows'}, 'Unexpected predecessor document fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()=='cedeb7b01f9f1d3da10e968d827897aba412f6146b95e7250c5bfbb028cbc933','V47 signed envelope changed')
    env=json.loads(eb);signed=json.loads(base64.b64decode(env['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1795 and signed['archive']['sha256']=='fdfec5119af224754a2155c739a0d0e4163a1706e31903f2e9e65b6fb678d27c','V47 archive identity changed')
    mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(len(mb)==3834763 and hashlib.sha256(mb).hexdigest()=='1088d1049ade31b3d3fd1a515718a6d9875a3e26951b14bff05b96dad6531edf','V47 original metadata changed')
    need(old_rows['local-bootstrap-source.json']['sha256']==hashlib.sha256(mb).hexdigest() and old_rows['local-bootstrap-source.json']['size']==len(mb),'V47 signed metadata membership differs')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    key=('local-git-first-run-owned-stones-nine-leaf-20261030-v1', 'local-owned-stones-nine-leaf-20261030-v1', '965f336f1f5f940746eedf51c1c94f57c60abbdffc50e78c025e1da3d4ff3558')
    need(tuple(old_meta[k] for k in ('release','source_release','source_formal_manifest_sha256'))==key,'V47 source tuple changed')
    need(len(old_formal)==1341 and source_rows_hash(old_formal)==old_meta['source_files_sha256']=='dbfc5f586a692e6acb240a1dd27ff29995893210550f5ecd8e7d3750a6dd0a41','V47 formal rows changed')
    contracts=owned_v46_predecessors(old_meta['upgrade_from']['v46_predecessor'])
    need(len(contracts)==5 and key not in contracts,'V47 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def wear_v48_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v48-public-v1', 'sha256': 'c76bbbef58618ce7b4aff307843b1906b5e7ce8e32a100bad2fc83894fc01917'},'Exact V48 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('wear-predecessor.txt')).read_bytes()
    need(len(raw)==309824 and hashlib.sha256(raw).hexdigest()=='68b74b889731569534bf952510dd61402669aa605bc878e9fa4e2aa80184fe7c','V48 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='c76bbbef58618ce7b4aff307843b1906b5e7ce8e32a100bad2fc83894fc01917','V48 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V48 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V48 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='1719deff1d845338fc8160eaad1f01805552144d4779977e29099c9cca4c3cf7' and hashlib.sha256(mb).hexdigest()=='836dd3b532e63cf22f95771ec234f5de3696e004655b9cdf8ceb5a080698e4da','V48 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1796 and signed['archive']['sha256']=='201c28a1efb7a5c64a6f9f5998a5af770aced95ffebfefc12614c1eaef92c444','V48 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V48 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-accessory-identification-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V48 source identity changed')
    contracts=accessory_v47_predecessors(old_meta['upgrade_from']['v47_predecessor'])
    need(len(contracts)==6 and key not in contracts,'V48 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def world_v50_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v50-public-v1', 'sha256': 'fa12cde321783cacd6b22bec2ddd556ce498f223399c50a53c63c138ecc52c16'},'Exact V50 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('world-predecessor.txt')).read_bytes()
    need(len(raw)==310316 and hashlib.sha256(raw).hexdigest()=='fac2c5f0afdf3cee8593a03af0ce919a754bbef27d0d3b2807720d785faad4fd','V50 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='fa12cde321783cacd6b22bec2ddd556ce498f223399c50a53c63c138ecc52c16','V50 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V50 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V50 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='a447d5f623f75850deeee35642bccbd0223eac3c43fad0cc66c50f55d539a323' and hashlib.sha256(mb).hexdigest()=='c1629eaf234f82a5c1b308b5277054a6b9530e55ceb54e4f6a3a9a666fa6e3f7','V50 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1798 and signed['archive']['sha256']=='458145b1f399cb10095c15769a6057f81a3570dc4f29e9878d7582f29b34a656','V50 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V50 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-wear-wait-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V50 source identity changed')
    contracts=wear_v48_predecessors(old_meta['upgrade_from']['v48_predecessor'])
    need(len(contracts)==7 and key not in contracts,'V50 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def login_v51_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v51-public-v1', 'sha256': 'caf5756786c924dffe4bba1f7adc2bc69644ab1d11c864e3d1d5829be076f428'},'Exact V51 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('login-predecessor.txt')).read_bytes()
    need(len(raw)==310896 and hashlib.sha256(raw).hexdigest()=='354920a6e9bd854d654ba93bb1ff61032bc828979ef0f256b6c5e510dd5c8e20','V51 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='caf5756786c924dffe4bba1f7adc2bc69644ab1d11c864e3d1d5829be076f428','V51 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V51 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V51 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='cd9c20dd6736c5efc50aa4a2090fb15c21db2a5484b02d68b3a8ff402a515be7' and hashlib.sha256(mb).hexdigest()=='e4d97944fd696c01534c4c656821d13ed7061c860807d9949aa03c4b2321591d','V51 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1800 and signed['archive']['sha256']=='767a908a9ca8e18a74d3153056b283226d3dbab24edd5e113a715fb724e06c2d','V51 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V51 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-world-event-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V51 source identity changed')
    contracts=world_v50_predecessors(old_meta['upgrade_from']['v50_predecessor'])
    need(len(contracts)==8 and key not in contracts,'V51 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def map_trigger_v53_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v53-public-v1', 'sha256': '20abfe69708bea671a455dda53afbe33037a9d75ca26a407544982dea2ce3336'},'Exact V53 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('map-trigger-predecessor.txt')).read_bytes()
    need(len(raw)==311084 and hashlib.sha256(raw).hexdigest()=='02d6907bc4e461dbcf3653901fc5dc1585b496af0cbcdff66d75b5b7bef186e6','V53 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='20abfe69708bea671a455dda53afbe33037a9d75ca26a407544982dea2ce3336','V53 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V53 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V53 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='f1ac107e3e4d92f6e15439a8bd3c7c7f52733e33be81719c39c5485695001a1b' and hashlib.sha256(mb).hexdigest()=='09735636edab7529c5f745b890a801956357dc72d4932ba9d3a8bf306610d792','V53 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1800 and signed['archive']['sha256']=='620de182193d3dfaf2bd8856c07d293a68fb72b6c250a7e2db098830251f72ab','V53 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V53 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-login-reconnect-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V53 source identity changed')
    contracts=login_v51_predecessors(old_meta['upgrade_from']['v51_predecessor'])
    need(len(contracts)==9 and key not in contracts,'V53 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def quest_v54_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v54-public-v1', 'sha256': '059940e145dc454fb4ec480c28bc21d32d2b099903e6edb7daddb6a97c4c67d4'},'Exact V54 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('quest-predecessor.txt')).read_bytes()
    need(len(raw)==312408 and hashlib.sha256(raw).hexdigest()=='5cc5bc4d8d855fc1460209504614080490cc5134cdc72fd979e83888a3cfeee5','V54 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='059940e145dc454fb4ec480c28bc21d32d2b099903e6edb7daddb6a97c4c67d4','V54 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V54 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V54 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='39724880909ada4c4feb86d0b3d10a6e8a65ab19a4c4f07472c333ae49e4fcfe' and hashlib.sha256(mb).hexdigest()=='c8d168e606528dbc35aa8a232bba46a7c17e363ec5bea35a2a73d430fd4bbea5','V54 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1804 and signed['archive']['sha256']=='074114c170660fe78ca1c47009c0d501e7df43594078937065d162175f6248af','V54 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V54 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-map-trigger-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V54 source identity changed')
    contracts=map_trigger_v53_predecessors(old_meta['upgrade_from']['v53_predecessor'])
    need(len(contracts)==10 and key not in contracts,'V54 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def group_wear_v55_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v55-public-v1', 'sha256': 'f16c3914081cf081e2fd39af502f37398c8455b970c9d8c14f231fa475fbdaa4'},'Exact V55 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('group-wear-predecessor.txt')).read_bytes()
    need(len(raw)==348780 and hashlib.sha256(raw).hexdigest()=='8057f9ff10baf637c3ca4ad1f63afbd8a7a0a52119d4e89bccbc53b5009e9eff','V55 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True);need(hashlib.sha256(compressed).hexdigest()=='f16c3914081cf081e2fd39af502f37398c8455b970c9d8c14f231fa475fbdaa4','V55 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V55 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V55 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='e5edd51629a893d7ffd0e7029a7dd7c9c8245a1b7f04f00b877580120be8a35b' and hashlib.sha256(mb).hexdigest()=='36478a45c0c6b4e0b20982de5035a1addc960ad93848d022eeb568d6c2d9b8c3','V55 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1877 and signed['archive']['sha256']=='7a43717786c5313e76ce854b5cb0f559d172d6e1acfc569c0942df0661ee2d7e','V55 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V55 source rows changed')
    key=tuple(old_meta[k]for k in('release','source_release','source_formal_manifest_sha256'));need(key==('local-git-first-run-quest-exp-native-20261101-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V55 source identity changed')
    contracts=quest_v54_predecessors(old_meta['upgrade_from']['v54_predecessor'])
    need(len(contracts)==11 and key not in contracts,'V55 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def repair_policy(metadata,new_rows):
    repair_require_bindings()
    need(repair_target(metadata) and metadata.get('profile')==REPAIR_PROFILE and metadata.get('source_files_sha256')==REPAIR_SOURCE_ROWS and type(metadata.get('source_file_count'))is int and metadata['source_file_count']==REPAIR_SOURCE_COUNT, 'Exact repair source descriptor differs')
    need(metadata.get('support_overrides')==REPAIR_OVERRIDES and metadata.get('support_additions')==REPAIR_ADDITIONS and metadata.get('generated_config_source_sha256')==REPAIR_CONFIG, 'Exact repair support/config differs')
    need(len(new_rows)==REPAIR_RUNTIME_COUNT and 'local-bootstrap-source.json'in new_rows and source_rows_hash({k:v for k,v in new_rows.items()if k!='local-bootstrap-source.json'})==REPAIR_RUNTIME_WITHOUT_METADATA, 'Exact repair complete runtime differs')
    need(len(encoded(metadata))<=4*1024*1024, 'Repair metadata exceeds original total4MiB limit')
    p=metadata.get('upgrade_from')
    need(type(p)is dict and set(p)=={'schema','kind','to_runtime_release','to_source_release','to_source_formal_manifest_sha256','v55_predecessor'} and type(p['schema'])is int and p['schema']==1 and p['kind']==REPAIR_POLICY_KIND, 'Exact transitive repair policy required')
    need((p['to_runtime_release'],p['to_source_release'],p['to_source_formal_manifest_sha256'])==(REPAIR_RUNTIME_RELEASE,REPAIR_SOURCE_RELEASE,REPAIR_FORMAL), 'Repair policy target differs')
    contracts=group_wear_v55_predecessors(p['v55_predecessor'])
    for key,contract in contracts.items():contract['policy_sha256']=hashlib.sha256(encoded(dict(target=p,selected=list(key)))).hexdigest()
    return dict(structure_contracts=contracts)

def managed_policy(metadata, new_rows):
    if repair_target(metadata):
        return repair_policy(metadata,new_rows)
    if structure_target(metadata):
        return structure_policy(metadata, new_rows)
    import base64
    p = metadata.get('upgrade_from')
    if p is None:
        return None
    need(isinstance(p, dict) and type(p.get('schema')) is int and p['schema'] == 1 and p.get('kind') == MANAGED_KIND,
         'Unrecognized managed predecessor policy')
    need((p.get('from_runtime_release'), p.get('from_source_release'), p.get('from_source_formal_manifest_sha256')) ==
         ('local-git-first-run-20261029-v1', 'local-native-shop-flow-20261029-v1', MANAGED_OLD_FORMAL),
         'Only the exact accepted V42 predecessor is eligible')
    need((metadata.get('release'), metadata.get('source_release'), metadata.get('source_formal_manifest_sha256')) ==
         ('local-git-first-run-identity-20261029-v1', 'local-native-unit-account-identity-20261029-v1', MANAGED_NEW_FORMAL),
         'Managed upgrade target is not the accepted identity source')
    need((p.get('to_runtime_release'), p.get('to_source_release'), p.get('to_source_formal_manifest_sha256')) ==
         (metadata['release'], metadata['source_release'], metadata['source_formal_manifest_sha256']),
         'Managed predecessor policy target differs')
    raw = base64.b64decode(p['old_signed_envelope_base64'], validate=True)
    need(len(raw) < 1048576 and hashlib.sha256(raw).hexdigest() == p['old_signed_envelope_sha256'] == MANAGED_OLD_ENVELOPE,
         'Original V42 signed envelope identity differs')
    old_signed = json.loads(base64.b64decode(json.loads(raw)['payload'], validate=True))
    old_rows = rows(old_signed)
    need(len(old_rows) == 1779 and old_signed['archive']['sha256'] == '70e06dca0f929d0f2bc053a5cb226b960bf7026c13ae10dda503f96f485aeec4',
         'Original signed V42 full membership differs')
    raw = base64.b64decode(p['old_metadata_base64'], validate=True)
    need(hashlib.sha256(raw).hexdigest() == p['old_metadata_sha256'] == MANAGED_OLD_METADATA == old_rows['local-bootstrap-source.json']['sha256'],
         'Original V42 metadata identity differs')
    old_meta = json.loads(raw)
    need((old_meta['release'], old_meta['source_release'], old_meta['source_formal_manifest_sha256']) ==
         (p['from_runtime_release'], p['from_source_release'], p['from_source_formal_manifest_sha256']),
         'Original V42 metadata source differs')
    old_formal = rows({'files': p['old_formal_rows']})
    need(len(old_formal) == old_meta['source_file_count'] == 1325 and
         source_rows_hash(old_formal) == p['old_formal_rows_sha256'] == old_meta['source_files_sha256'],
         'Original V42 complete business index differs')
    need(set(new_rows) == set(old_rows) and len(new_rows) == 1779 and
         {n for n in old_rows if old_rows[n] != new_rows[n]} == MANAGED_FIVE | {'local-bootstrap-source.json'},
         'Managed signed package is not the exact six-row identity delta')
    need(metadata.get('support_overrides') == old_meta['support_overrides'] and
         metadata.get('support_additions') == old_meta['support_additions'] and
         metadata.get('generated_config_source_sha256') == old_meta['generated_config_source_sha256'],
         'V42 support/config source rules changed')
    need(p.get('updater_sha256') == MANAGED_UPDATER, 'Installed updater dependency differs')
    return dict(policy=p, old_rows=old_rows, old_meta=old_meta, old_formal=old_formal,
                policy_sha256=hashlib.sha256(encoded(p)).hexdigest())


def managed_updater():
    import importlib.util
    path = no_links(Path(__file__).resolve().with_name('local_updater.py'))
    need(path.is_file() and digest(path) == MANAGED_UPDATER, 'Exact embedded LOCAL updater was not extracted')
    spec = importlib.util.spec_from_file_location('accepted_managed_updater', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def managed_verify_tree(root, installed, documents):
    no_links(root)
    for name, raw in documents.items():
        path = under(root, name)
        need(path.is_file() and path.stat().st_nlink == 1 and path.read_bytes() == raw,
             'Managed generated document differs: ' + name)
    for row in installed.values():
        verify(root, row)
        need(under(root, row['path']).stat().st_nlink == 1, 'Managed runtime contains a hard link')


def managed_old_state(workspace, contract, pointer=None):
    if pointer is None:
        pointer = read(workspace / 'releases/local/current.json')
    commit = pointer.get('repository_commit')
    need(isinstance(commit, str) and re.fullmatch('[a-f0-9]{40}|[a-f0-9]{64}', commit), 'Original managed Git identity missing')
    old_meta = contract['old_meta']
    additions = {r['path'] for r in old_meta['support_additions']}
    docs, installed, expected = generated_documents(workspace, old_meta, commit, contract['old_rows'], contract['old_formal'], additions)
    need(pointer == expected, 'Existing managed pointer is not the exact original V42 shape')
    root = under(workspace, expected['path'])
    need(root.parent == workspace / 'releases/local' and root.name == old_meta['release'], 'Original managed release root differs')
    managed_verify_tree(root, installed, docs)
    return dict(pointer=pointer, root=root, documents=docs, installed=installed)


def managed_database_snapshot(path):
    import sqlite3
    from contextlib import closing
    no_links(path)
    need(path.is_file() and path.stat().st_nlink == 1, 'Managed player database path differs')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        need(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'Managed player database integrity differs')
        need(not db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger'").fetchone(),
             'Unreviewed writer trigger; database preserved')
        objects = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        tables = {}
        for name, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            values = [json.dumps([(type(v).__name__, v.hex() if isinstance(v, bytes) else v) for v in row],
                                 ensure_ascii=True, separators=(',', ':')) for row in db.execute('SELECT * FROM ' + quoted)]
            tables[name] = dict(sql=sql, rows=sorted(values))
        return hashlib.sha256(json.dumps(dict(objects=objects, tables=tables), ensure_ascii=True, sort_keys=True,
                                         separators=(',', ':')).encode()).hexdigest()


def managed_journal(workspace, u, contract, path):
    path = no_links(Path(path))
    need(path.is_absolute() and path == path.resolve(), 'Managed recovery journal is not canonical')
    need(path.is_relative_to(workspace / 'state/local-updater') and path.name == 'journal.json', 'Managed recovery journal escaped its root')
    j = u.read(path)
    need(j.get('schema') == u.SCHEMA and j.get('kind') == MANAGED_KIND and
         j.get('policy_sha256') == contract['policy_sha256'] and j.get('journal') == str(path),
         'Unrecognized managed recovery journal')
    managed_old_state(workspace, contract, j['parent'])
    return path, j


def managed_recover(workspace, metadata, new_rows, formal, additions):
    contract = managed_policy(metadata, new_rows)
    if contract is None:
        return
    paths = [workspace / 'analysis/coordination-20261015' / n for n in ('active-publication.lock', 'publication-record.lock')]
    present = [p for p in paths if p.exists()]
    if not present:
        return
    u = managed_updater()
    identity = u.read(no_links(present[0]))
    need(identity.get('schema') == u.SCHEMA and identity.get('operation') == 'local-oneclick-updater' and
         all(u.read(no_links(p)) == identity for p in present), 'Foreign managed publication lock; runtime preserved')
    contract = structure_journal_contract(workspace, u, contract, identity['journal'])
    path, j = managed_journal(workspace, u, contract, identity['journal'])
    need(j['token'] == identity['token'] and j['created'] == identity['created'], 'Managed recovery lock/journal differs')
    if j.get('candidate') is not None:
        recorded = j['candidate'].get('repository_commit')
        need(isinstance(recorded, str) and re.fullmatch('[a-f0-9]{40}|[a-f0-9]{64}', recorded), 'Managed candidate Git identity differs')
        _, _, expected = generated_documents(workspace, metadata, recorded, new_rows, formal, additions)
        need(j['candidate'] == expected, 'Foreign candidate pointer prevents managed recovery')
    # The original c976 consumer checks live PID+creation time, exact parent /
    # candidate pointer, normal stop/restart and owns-only lock cleanup.
    u.recover(workspace, u.psutil_for(under(workspace, j['parent']['path'])))


def managed_is_old(workspace, metadata):
    if repair_target(metadata):
        repair_require_bindings()
        current=read(workspace/'releases/local/current.json')
        key=tuple(current.get(k)for k in('release','source_release','source_formal_manifest_sha256'))
        return key in [tuple(r['key'])for r in STRUCTURE_PREDECESSORS]+[(STRUCTURE_RUNTIME_RELEASE,STRUCTURE_SOURCE_RELEASE,STRUCTURE_FORMAL)]+[('local-git-first-run-shared-repair-20261030-v1','local-native-shared-repair-20261030-v1','2291d8c2e24f72209e802de082fda701f623fc87609e201206136f5862ff9fd5')]+[('local-git-first-run-cache-exact41400-20261030-v1', 'local-cache-exact41400-20261030-v1', '7dd7cab0d08b85c9803e0c96d92109d4d5c2d22d729e47c0104d7f8e40d93b35')]+[('local-git-first-run-owned-stones-nine-leaf-20261030-v1', 'local-owned-stones-nine-leaf-20261030-v1', '965f336f1f5f940746eedf51c1c94f57c60abbdffc50e78c025e1da3d4ff3558')]+[('local-git-first-run-accessory-identification-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]+[('local-git-first-run-wear-wait-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]+[('local-git-first-run-world-event-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]+[('local-git-first-run-login-reconnect-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]+[('local-git-first-run-map-trigger-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]+[('local-git-first-run-quest-exp-native-20261101-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]
    if structure_target(metadata):
        current = read(workspace / 'releases/local/current.json')
        key = tuple(current.get(k) for k in ('release','source_release','source_formal_manifest_sha256'))
        return any(key == tuple(row['key']) for row in STRUCTURE_PREDECESSORS)
    p = metadata.get('upgrade_from')
    if not isinstance(p, dict):
        return False
    current = read(workspace / 'releases/local/current.json')
    return ((current.get('release'), current.get('source_release'), current.get('source_formal_manifest_sha256')) ==
            ('local-git-first-run-20261029-v1', 'local-native-shop-flow-20261029-v1', MANAGED_OLD_FORMAL))


# Inserted only into the new Repair bootstrap resource. Historical resources and
# the c976 updater remain unchanged. Guard byte payloads are generator-bound.
REPAIR_RECOVERY_GUARD_PAYLOADS = {'els_server/storage/relationships.py': {'base64': 'IiIiQXRvbWljIG9yaWdpbmFsIGNvdXBsZSBwcm9wb3NhbC9hbnN3ZXIsIGltbXV0YWJsZSBkZWJpdCBzb3VyY2UgYW5kIGNvbGQgdmlldy4iIiINCmltcG9ydCBoYXNobGliLGpzb24sc3FsaXRlMyx0aW1lDQpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJlbGF0aW9uc2hpcF9ydWxlcyBpbXBvcnQgUklORyxlbGlnaWJsZQ0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcyBpbXBvcnQgcHJvcG9zZV9yZXF1ZXN0LGFuc3dlcl9yZXF1ZXN0DQpmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wucHJvdG9jb2xfY29kZWMgaW1wb3J0IGVuY29kZV9ldmVudA0KZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaXRlbV9hY3RvciBpbXBvcnQgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyDQpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5wcm9mZXNzaW9uX3N0YXRlIGltcG9ydCByZXF1aXJlX293bmVyDQpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfc3RhdGUgaW1wb3J0IGxvYWRfaXRlbXMNCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1faW5zdGFuY2VzIGltcG9ydCByZW1vdmUNClRBQkxFUz0oJ25hdGl2ZV9jb3VwbGVfcGFpcnNfdjEnLCduYXRpdmVfY291cGxlX21lbWJlcnNfdjEnLCduYXRpdmVfY291cGxlX3BlbmRpbmdfdjEnLCduYXRpdmVfY291cGxlX2FjdGlvbnNfdjEnKQ0KU0NIRU1BUz17J25hdGl2ZV9jb3VwbGVfcGFpcnNfdjEnOiAnQ1JFQVRFIFRBQkxFIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEoaWQgVEVYVCBQUklNQVJZIEtFWSxhIElOVEVHRVIgTk9UIE5VTEwsYiBJTlRFR0VSIE5PVCBOVUxMLGFfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLGJfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLGNyZWF0ZWRfYXQgSU5URUdFUiBOT1QgTlVMTCxwcm9wb3NhbCBURVhUIE5PVCBOVUxMLGFjY2VwdGFuY2UgVEVYVCBOT1QgTlVMTCxpdGVtX3VpZCBJTlRFR0VSIE5PVCBOVUxMLHZlcnNpb24gSU5URUdFUiBOT1QgTlVMTCBDSEVDSyh2ZXJzaW9uPTEpKScsICduYXRpdmVfY291cGxlX21lbWJlcnNfdjEnOiAnQ1JFQVRFIFRBQkxFIG5hdGl2ZV9jb3VwbGVfbWVtYmVyc192MShvd25lciBJTlRFR0VSIFBSSU1BUlkgS0VZIFJFRkVSRU5DRVMgY2hhcmFjdGVycyh1aWQpLGFjY291bnRfaWQgSU5URUdFUiBOT1QgTlVMTCxwYWlyX2lkIFRFWFQgTk9UIE5VTEwgUkVGRVJFTkNFUyBuYXRpdmVfY291cGxlX3BhaXJzX3YxKGlkKSknLCAnbmF0aXZlX2NvdXBsZV9wZW5kaW5nX3YxJzogJ0NSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEob3BlcmF0aW9uIFRFWFQgUFJJTUFSWSBLRVkscHJvcG9zZXIgSU5URUdFUiBOT1QgTlVMTCBVTklRVUUscmVjaXBpZW50IElOVEVHRVIgTk9UIE5VTEwgVU5JUVVFLHByb3Bvc2VyX2FjY291bnQgSU5URUdFUiBOT1QgTlVMTCxyZWNpcGllbnRfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLHByb3Bvc2VyX3Nlc3Npb24gVEVYVCBOT1QgTlVMTCxyZWNpcGllbnRfc2Vzc2lvbiBURVhUIE5PVCBOVUxMLGl0ZW1fdWlkIElOVEVHRVIgTk9UIE5VTEwsaXRlbV9qc29uIFRFWFQgTk9UIE5VTEwsY3JlYXRlZF9hdCBJTlRFR0VSIE5PVCBOVUxMLGRlc2NyaXB0b3IgQkxPQiBOT1QgTlVMTCknLCAnbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxJzogJ0NSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX2FjdGlvbnNfdjEob3BlcmF0aW9uIFRFWFQgUFJJTUFSWSBLRVkscmVxdWVzdF9oYXNoIFRFWFQgTk9UIE5VTEwsa2luZCBJTlRFR0VSIE5PVCBOVUxMLG93bmVyIElOVEVHRVIgTk9UIE5VTEwscGVlciBJTlRFR0VSIE5PVCBOVUxMLHBheWxvYWQgQkxPQiBOT1QgTlVMTCxwcm9wb3NhbCBURVhUIE5PVCBOVUxMLHN0YXR1cyBURVhUIE5PVCBOVUxMLGNyZWF0ZWRfYXQgSU5URUdFUiBOT1QgTlVMTCxiZWZvcmVfanNvbiBURVhUIE5PVCBOVUxMLGFmdGVyX2pzb24gVEVYVCBOT1QgTlVMTCknfQ0KZGVmIF9wcmVzZW50KGRiKToNCiBmb3VuZD1kaWN0KGRiLmV4ZWN1dGUoIlNFTEVDVCBuYW1lLHNxbCBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIobmFtZSkgSU4gKD8sPyw/LD8pIixUQUJMRVMpKQ0KIGlmIGZvdW5kIGFuZCBmb3VuZCE9U0NIRU1BUzpyYWlzZSBWYWx1ZUVycm9yKCdVbmtub3duIG9yIHBhcnRpYWwgY3VycmVudCBjb3VwbGUgc2NoZW1hJykNCiBpZiBkYi5leGVjdXRlKCJTRUxFQ1QgMSBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIodGJsX25hbWUpIElOICg/LD8sPyw/KSBBTkQodHlwZT0ndHJpZ2dlcidPUih0eXBlPSdpbmRleCdBTkQgc3FsIElTIE5PVCBOVUxMKSkgTElNSVQgMSIsVEFCTEVTKS5mZXRjaG9uZSgpOnJhaXNlIFZhbHVlRXJyb3IoJ1VucmV2aWV3ZWQgY291cGxlIHNjaGVtYSBleHRlbnNpb24nKQ0KIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmNvdXBsZV9jbG9zdXJlcyBpbXBvcnQgcHJlc2VudA0KIHByZXNlbnQoZGIsYmFzZT1ib29sKGZvdW5kKSkNCiByZXR1cm4gYm9vbChmb3VuZCkNCmRlZiBfc2NoZW1hKGRiKToNCiBpZiBfcHJlc2VudChkYik6cmV0dXJuDQogaWYgbm90IGRiLmluX3RyYW5zYWN0aW9uOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBzY2hlbWEgb3V0c2lkZSB3cml0ZXIgdHJhbnNhY3Rpb24nKQ0KIGZvciBzcWwgaW4gU0NIRU1BUy52YWx1ZXMoKTpkYi5leGVjdXRlKHNxbCkNCiBfcHJlc2VudChkYikNCmRlZiBfd3JpdGVfZ3VhcmQoZGIpOg0KICMgRXhhY3RseSB0aGUgaW52ZW50b3J5IGFuZCBtZXRhZGF0YSB0YWJsZXMgdG91Y2hlZCBieSBvcmlnaW5hbCByZW1vdmUoKS4NCiAjIEN1cnJlbnQgbmF0aXZlIHN0b3JhZ2UgZGVmaW5lcyBubyB0cmlnZ2VycyBvbiB0aGVzZSB3cml0ZXIgZGVwZW5kZW5jaWVzLg0KIHRhYmxlcz0oJ2ludmVudG9yeV9pdGVtcycsJ2VxdWlwbWVudF9hdHRyaWJ1dGVzJywnZXF1aXBtZW50X2R1cmFiaWxpdHknLCdlcXVpcG1lbnRfZW5oYW5jZW1lbnQnLCdpdGVtX2V4cGlyYXRpb24nLCdpdGVtX2xvY2tzJywnZXF1aXBtZW50X29wdGlvbnMnLCdlcXVpcG1lbnRfaWRlbnRpZmljYXRpb24nLCdlcXVpcG1lbnRfZW5oYW5jZW1lbnRfcHJvZ3Jlc3MnLCdpdGVtX3NlYWxzJywnYXJ0aWZhY3RfZXF1aXBtZW50X3N0YXRlJywnZXF1aXBtZW50X2NoaXBfdHVuaW5nJywnZXF1aXBtZW50X3JlZm9yZ2Vfc3RhdGVzJywnZXF1aXBtZW50X2VuZ3JhdmVfcHJldmlld3MnLCd3YXJkcm9iZV9pdGVtX3N0YXRlJywnd2FyZHJvYmVfZHllcycpDQogaWYgZGIuZXhlY3V0ZSgiU0VMRUNUIDEgRlJPTSBzcWxpdGVfbWFzdGVyIFdIRVJFIHR5cGU9J3RyaWdnZXInQU5EIGxvd2VyKHRibF9uYW1lKSBJTigiKycsJy5qb2luKCc/J2ZvciBfIGluIHRhYmxlcykrJykgTElNSVQgMScsdGFibGVzKS5mZXRjaG9uZSgpOnJhaXNlIFZhbHVlRXJyb3IoJ1VucmV2aWV3ZWQgY291cGxlIGludmVudG9yeSB3cml0ZXIgdHJpZ2dlcicpDQogX3ByZXNlbnQoZGIpDQpkZWYgX2FjdG9yKGRiLHVpZCxhY2NvdW50KToNCiByZXF1aXJlX2FjdGl2ZV9jaGFyYWN0ZXIoZGIsdWlkKTtyZXF1aXJlX293bmVyKGRiLHVpZCxhY2NvdW50KQ0KIHJvdz1kYi5leGVjdXRlKCdTRUxFQ1QgdWlkLG5hbWUsdW5pdF90eXBlIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKHVpZCwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG1pc3Npbmcgc2F2ZWQgY2hhcmFjdGVyJykNCiByZXR1cm4gZGljdCh6aXAoKCd1aWQnLCduYW1lJywndW5pdF90eXBlJykscm93KSkNCmRlZiBfZGlnZXN0KHVpZCxraW5kLHBheWxvYWQpOnJldHVybiBoYXNobGliLnNoYTI1NihzdHIodWlkKS5lbmNvZGUoKStiJzonK3N0cihraW5kKS5lbmNvZGUoKStiJzonK3BheWxvYWQpLmhleGRpZ2VzdCgpDQpkZWYgX2RlYml0KGJlZm9yZSxhZnRlcixpdGVtX3VpZCk6DQogaWYgbm90IGlzaW5zdGFuY2UoYmVmb3JlLGxpc3Qpb3Igbm90IGlzaW5zdGFuY2UoYWZ0ZXIsbGlzdClvciBhbnkobm90IGlzaW5zdGFuY2UoaSxkaWN0KWZvciBpIGluIGJlZm9yZSthZnRlcik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHNhdmVkIGludmVudG9yeSByZWNlaXB0IGFycmF5cycpDQogc291cmNlPW5leHQoKGkgZm9yIGkgaW4gYmVmb3JlIGlmIGlbJ3VpZCddPT1pdGVtX3VpZCksTm9uZSkNCiBpZiBzb3VyY2UgaXMgTm9uZSBvcihzb3VyY2VbJ3RlbXBsYXRlJ10sc291cmNlWydtZXRhZGF0YSddLHNvdXJjZVsnZ3JvdXAnXSkhPShSSU5HLDAsNClvciBzb3VyY2VbJ2NvdW50J108MTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb3JpZ2luYWwgcmluZyBzb3VyY2UgcmVjZWlwdCcpDQogZXhwZWN0ZWQ9W2RpY3QoaSlmb3IgaSBpbiBiZWZvcmVdDQogZm9yIGkgaW4gZXhwZWN0ZWQ6DQogIGlmIGlbJ3VpZCddPT1pdGVtX3VpZDppWydjb3VudCddLT0xDQogZXhwZWN0ZWQ9W2kgZm9yIGkgaW4gZXhwZWN0ZWQgaWYgaVsnY291bnQnXV0NCiBpZiBleHBlY3RlZCE9YWZ0ZXI6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11c3QgZGViaXQgZXhhY3RseSBvbmUgYm91bmQgcmluZycpDQogcmV0dXJuIHNvdXJjZQ0KZGVmIHNuYXBzaG90KGRiLG93bmVyLGFjY291bnQpOg0KIGlmIGRiLmV4ZWN1dGUoJ1NFTEVDVCBhY2NvdW50X2lkIEZST00gY2hhcmFjdGVyX293bmVycyBXSEVSRSB1aWQ9PycsKG93bmVyLCkpLmZldGNob25lKCkhPShhY2NvdW50LCk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNvbGQgb3duZXInKQ0KIGlmIG5vdCBfcHJlc2VudChkYik6cmV0dXJuIE5vbmUNCiBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5jb3VwbGVfY2xvc3VyZXMgaW1wb3J0IGNsb3NlZF9wYWlycw0KIGNsb3NlZD1jbG9zZWRfcGFpcnMoZGIsb3duZXIsYWNjb3VudCkNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIHBhaXJfaWQsYWNjb3VudF9pZCBGUk9NIG5hdGl2ZV9jb3VwbGVfbWVtYmVyc192MSBXSEVSRSBvd25lcj0/Jywob3duZXIsKSkuZmV0Y2hvbmUoKQ0KICMgRXZlcnkgZ2VuZXJhdGlvbiBpbnZvbHZpbmcgdGhpcyBvd25lciBtdXN0IHJldGFpbiBpdHMgdmFsaWRhdGVkIGltbXV0YWJsZQ0KICMgc291cmNlLCBpbmNsdWRpbmcgb2xkIGNsb3N1cmVzIHdoaWxlIGEgbGF0ZXIgcGFpciBpcyBhY3RpdmUuDQogcGFpcnM9e3ZbMF1mb3IgdiBpbiBkYi5leGVjdXRlKCdTRUxFQ1QgaWQgRlJPTSBuYXRpdmVfY291cGxlX3BhaXJzX3YxIFdIRVJFIGE9P09SIGI9PycsKG93bmVyLG93bmVyKSl9DQogaWYgcGFpcnMhPWNsb3NlZHwoe3Jvd1swXX1pZiByb3cgaXMgbm90IE5vbmUgZWxzZSBzZXQoKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHBhaXIgbGFja3MgbWVtYmVyIG9yIGV4YWN0IGNsb3N1cmUnKQ0KIGlmIHJvdyBpcyBOb25lOnJldHVybiBOb25lDQogaWYgcm93WzFdIT1hY2NvdW50IG9yIHJvd1swXWluIGNsb3NlZDpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbWVtYmVyIGFjY291bnQgb3IgY2xvc2VkIGdlbmVyYXRpb24nKQ0KIHJldHVybiBfcGFpcl9zbmFwc2hvdChkYixyb3dbMF0sb3duZXIsYWNjb3VudCkNCg0KZGVmIF9wYWlyX3NuYXBzaG90KGRiLHBhaXJfaWQsb3duZXIsYWNjb3VudCwqLGNsb3NlZD1GYWxzZSk6DQogcGFpcj1kYi5leGVjdXRlKCdTRUxFQ1QgYSxiLGFfYWNjb3VudCxiX2FjY291bnQsY3JlYXRlZF9hdCxwcm9wb3NhbCxhY2NlcHRhbmNlLGl0ZW1fdWlkLHZlcnNpb24gRlJPTSBuYXRpdmVfY291cGxlX3BhaXJzX3YxIFdIRVJFIGlkPT8nLChwYWlyX2lkLCkpLmZldGNob25lKCkNCiBpZiBwYWlyIGlzIE5vbmUgb3IgcGFpclstMV0hPTE6cmFpc2UgVmFsdWVFcnJvcignVW5rbm93biBjb3VwbGUgbWVtYmVyL3BhaXInKQ0KIGEsYixhYSxiYSxzdGFtcCxwcm9wb3NhbCxhY2NlcHRhbmNlLGl0ZW1fdWlkLHZlcnNpb249cGFpcg0KIGlmKG93bmVyLGFjY291bnQpbm90IGluKChhLGFhKSwoYixiYSkpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleGFjdCBwYWlyIG93bmVyL2FjY291bnQnKQ0KIG1lbWJlcnM9ZGIuZXhlY3V0ZSgnU0VMRUNUIG93bmVyLGFjY291bnRfaWQgRlJPTSBuYXRpdmVfY291cGxlX21lbWJlcnNfdjEgV0hFUkUgcGFpcl9pZD0/IE9SREVSIEJZIG93bmVyJywocGFpcl9pZCwpKS5mZXRjaGFsbCgpDQogaWYgbWVtYmVycyE9KFtdaWYgY2xvc2VkIGVsc2Ugc29ydGVkKFsoYSxhYSksKGIsYmEpXSkpb3IgYT09YiBvciBvd25lciBub3QgaW4oYSxiKW9yIHN0YW1wPD0wOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleGFjdGx5IHR3byByZWNpcHJvY2FsIG93bmVkIG1lbWJlcnMnKQ0KIGZvciB1aWQsYWlkIGluIHNvcnRlZChbKGEsYWEpLChiLGJhKV0pOg0KICBpZiBkYi5leGVjdXRlKCdTRUxFQ1QgYWNjb3VudF9pZCBGUk9NIGNoYXJhY3Rlcl9vd25lcnMgV0hFUkUgdWlkPT8nLCh1aWQsKSkuZmV0Y2hvbmUoKSE9KGFpZCwpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtZW1iZXIgYWNjb3VudCBjaGFuZ2VkJykNCiBhY3Rpb249ZGIuZXhlY3V0ZSgnU0VMRUNUIHJlcXVlc3RfaGFzaCxraW5kLG93bmVyLHBlZXIscGF5bG9hZCxwcm9wb3NhbCxzdGF0dXMsY3JlYXRlZF9hdCxiZWZvcmVfanNvbixhZnRlcl9qc29uIEZST00gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIFdIRVJFIG9wZXJhdGlvbj0/JywoYWNjZXB0YW5jZSwpKS5mZXRjaG9uZSgpDQogaWYgYWN0aW9uIGlzIE5vbmUgb3IgYWN0aW9uWzE6NF0hPSgweDNmZSxiLGEpb3IgYWN0aW9uWzU6OF0hPShwcm9wb3NhbCwnYWNjZXB0ZWQnLHN0YW1wKW9yIGFjdGlvblswXSE9X2RpZ2VzdChiLDB4M2ZlLGFjdGlvbls0XSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGxhY2tzIGltbXV0YWJsZSBleGFjdCBhY2NlcHRhbmNlIHByb2R1Y2VyJykNCiBwYXJzZWQ9YW5zd2VyX3JlcXVlc3QoYWN0aW9uWzRdKQ0KIGlmKHBhcnNlZFsnYW5zd2VyJ10scGFyc2VkWydwcm9wb3NlciddLHBhcnNlZFsncmVjaXBpZW50J10pIT0oMCxhLGIpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtdXR1YWwgYWNjZXB0YW5jZSBzb3VyY2UgaWRlbnRpdGllcycpDQogc291cmNlPV9kZWJpdChqc29uLmxvYWRzKGFjdGlvbls4XSksanNvbi5sb2FkcyhhY3Rpb25bOV0pLGl0ZW1fdWlkKQ0KIHByb3Bvc2VkPWRiLmV4ZWN1dGUoJ1NFTEVDVCBraW5kLG93bmVyLHBlZXIscGF5bG9hZCxzdGF0dXMscmVxdWVzdF9oYXNoLGJlZm9yZV9qc29uLGFmdGVyX2pzb24gRlJPTSBuYXRpdmVfY291cGxlX2FjdGlvbnNfdjEgV0hFUkUgb3BlcmF0aW9uPT8nLChwcm9wb3NhbCwpKS5mZXRjaG9uZSgpDQogaWYgcHJvcG9zZWQgaXMgTm9uZSBvciBwcm9wb3NlZFs6M10hPSgweDNmYixhLGIpb3IgcHJvcG9zZWRbNF0hPSdwcm9wb3NlZCdvciBwcm9wb3NlZFs1XSE9X2RpZ2VzdChhLDB4M2ZiLHByb3Bvc2VkWzNdKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbGFja3Mgb3JpZ2luYWwgcHJvcG9zYWwnKQ0KIGlmIHByb3Bvc2VfcmVxdWVzdChwcm9wb3NlZFszXSkhPXBhcnNlZFsnb3duX25hbWUnXW9yIGpzb24ubG9hZHMocHJvcG9zZWRbNl0pIT1bc291cmNlXW9yIHByb3Bvc2VkWzZdIT1wcm9wb3NlZFs3XTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3QgcHJvcG9zYWwgcmluZyBzb3VyY2UgY2hhbmdlZCcpDQogcGVlcj1iIGlmIG93bmVyPT1hIGVsc2UgYTtuYW1lPWRiLmV4ZWN1dGUoJ1NFTEVDVCBuYW1lIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKHBlZXIsKSkuZmV0Y2hvbmUoKQ0KIGlmIG5hbWUgaXMgTm9uZTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcGFydG5lciBjaGFyYWN0ZXIgdW5hdmFpbGFibGUnKQ0KIHJldHVybiBkaWN0KHBhaXJfaWQ9cGFpcl9pZCxraW5kPTEscGVlcl91aWQ9cGVlcixwZWVyX25hbWU9bmFtZVswXSxjcmVhdGVkX2F0PXN0YW1wKQ0KZGVmIF9yaW5nKGRiLG93bmVyLCosbm93LHVpZD1Ob25lKToNCiBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50DQogZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5pdGVtX2xvY2tzIGltcG9ydCByZXF1aXJlX3VubG9ja2VkDQogY2FuZGlkYXRlcz1baSBmb3IgaSBpbiBsb2FkX2l0ZW1zKGRiLG93bmVyKWlmKGlbJ3RlbXBsYXRlJ10saVsnbWV0YWRhdGEnXSxpWydncm91cCddKT09KFJJTkcsMCw0KWFuZCh1aWQgaXMgTm9uZSBvciBpWyd1aWQnXT09dWlkKV0NCiBmb3IgaXRlbSBpbiBzb3J0ZWQoY2FuZGlkYXRlcyxrZXk9bGFtYmRhIGk6KGlbJ3Nsb3QnXSxpWyd1aWQnXSkpOg0KICB0cnk6DQogICByZXF1aXJlX2N1cnJlbnQoaXRlbSxub3c9bm93KTtyZXF1aXJlX3VubG9ja2VkKGl0ZW0sbm93PW5vdykNCiAgIGlmIGl0ZW0uZ2V0KCdzZWFsZWQnLEZhbHNlKW9yIGl0ZW0uZ2V0KCdzZWFsX2NvdW50JywwKTpjb250aW51ZQ0KICAgcmV0dXJuIGl0ZW0NCiAgZXhjZXB0IFZhbHVlRXJyb3I6Y29udGludWUNCiByYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbmVlZHMgYSBjdXJyZW50IHVubG9ja2VkIG93bmVkMjY5NzEwJykNCmRlZiBfY2xvY2sobm93KToNCiBub3c9aW50KHRpbWUudGltZSgpKWlmIG5vdyBpcyBOb25lIGVsc2Ugbm93DQogaWYgdHlwZShub3cpaXMgbm90IGludCBvciBub3QgMDxub3c8MioqNjM6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHNlcnZlciBjbG9jaycpDQogcmV0dXJuIG5vdw0KZGVmIF9wcmV2aW91cyhkYixvcGVyYXRpb24sb3duZXIscGVlcixraW5kLHBheWxvYWQpOg0KIGlmIHR5cGUob3BlcmF0aW9uKWlzIG5vdCBzdHIgb3Igbm90IDE8PWxlbihvcGVyYXRpb24pPD0xNjA6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG9wZXJhdGlvbiBpZGVudGl0eScpDQogcm93PWRiLmV4ZWN1dGUoJ1NFTEVDVCByZXF1ZXN0X2hhc2gsb3duZXIscGVlcixraW5kLHN0YXR1cyxwcm9wb3NhbCBGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wZXJhdGlvbiwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIG5vdCBOb25lIGFuZCByb3dbOjRdIT0oX2RpZ2VzdChvd25lcixraW5kLHBheWxvYWQpLG93bmVyLHBlZXIsa2luZCk6cmFpc2UgVmFsdWVFcnJvcignQ29uZmxpY3RpbmcgY291cGxlIHJlcGxheScpDQogcmV0dXJuIHJvdw0KZGVmIHByb3Bvc2UoZGIsb3duZXIsYWNjb3VudCx0YXJnZXQsdGFyZ2V0X2FjY291bnQsc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbixwYXlsb2FkLG9wZXJhdGlvbiwqLGd1YXJkLGVuY29kZSxub3c9Tm9uZSk6DQogcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11dGF0aW9ucyBkaXNhYmxlZCBpbiBmcmVlLWZhcmV3ZWxsIGNvbXBhdGlibGUgcmVjb3ZlcnknKQ0KIG5vdz1fY2xvY2sobm93KTtfd3JpdGVfZ3VhcmQoZGIpO2d1YXJkKGRiKTthPV9hY3RvcihkYixvd25lcixhY2NvdW50KTtiPV9hY3RvcihkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpO2VsaWdpYmxlKGEsYikNCiBpZiBwcm9wb3NlX3JlcXVlc3QocGF5bG9hZCkhPWJbJ25hbWUnXTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb25saW5lIHRhcmdldCBuaWNrbmFtZScpDQogaWYgc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClpcyBub3QgTm9uZSBvciBzbmFwc2hvdChkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpaXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGFjdG9ycyBtdXN0IGJvdGggYmUgc29sbycpDQogX3NjaGVtYShkYik7b2xkPV9wcmV2aW91cyhkYixvcGVyYXRpb24sb3duZXIsdGFyZ2V0LDB4M2ZiLHBheWxvYWQpDQogaWYgb2xkIGlzIE5vbmU6DQogIHJpbmc9X3JpbmcoZGIsb3duZXIsbm93PW5vdykNCiAgcGVuZGluZz1kYi5leGVjdXRlKCdTRUxFQ1Qgb3BlcmF0aW9uLHByb3Bvc2VyLHJlY2lwaWVudCxwcm9wb3Nlcl9zZXNzaW9uLHJlY2lwaWVudF9zZXNzaW9uLGNyZWF0ZWRfYXQgRlJPTSBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEgV0hFUkUgcHJvcG9zZXIgSU4oPyw/KU9SIHJlY2lwaWVudCBJTig/LD8pJywob3duZXIsdGFyZ2V0LG93bmVyLHRhcmdldCkpLmZldGNoYWxsKCkNCiAgZm9yIG9wLHAsdCxwcyx0cyxjcmVhdGVkIGluIHBlbmRpbmc6DQogICBjdXJyZW50PXtvd25lcjpzZXNzaW9uLHRhcmdldDp0YXJnZXRfc2Vzc2lvbn0NCiAgIGlmIG5vdz5jcmVhdGVkKzEwIG9yIGFueSh1aWQgaW4gY3VycmVudCBhbmQgY3VycmVudFt1aWRdIT1zaWQgZm9yIHVpZCxzaWQgaW4oKHAscHMpLCh0LHRzKSkpOmRiLmV4ZWN1dGUoJ0RFTEVURSBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wLCkpDQogICBlbHNlOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBjdXJyZW50IHBlbmRpbmcgaW52aXRhdGlvbiBleGlzdHMnKQ0KICBkYi5leGVjdXRlKCdJTlNFUlQgSU5UTyBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEgVkFMVUVTKD8sPyw/LD8sPyw/LD8sPyw/LD8sPyknLChvcGVyYXRpb24sb3duZXIsdGFyZ2V0LGFjY291bnQsdGFyZ2V0X2FjY291bnQsc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbixyaW5nWyd1aWQnXSxqc29uLmR1bXBzKHJpbmcsc29ydF9rZXlzPVRydWUpLG5vdyxwYXlsb2FkKSkNCiAgb3JpZ2luYWxfcmluZz1qc29uLmR1bXBzKFtyaW5nXSxzb3J0X2tleXM9VHJ1ZSkNCiAgZGIuZXhlY3V0ZSgnSU5TRVJUIElOVE8gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIFZBTFVFUyg/LD8sPyw/LD8sPyw/LD8sPyw/LD8pJywob3BlcmF0aW9uLF9kaWdlc3Qob3duZXIsMHgzZmIscGF5bG9hZCksMHgzZmIsb3duZXIsdGFyZ2V0LHBheWxvYWQsb3BlcmF0aW9uLCdwcm9wb3NlZCcsbm93LG9yaWdpbmFsX3Jpbmcsb3JpZ2luYWxfcmluZykpDQogZWxzZToNCiAgaWYgb2xkWzQ6XSE9KCdwcm9wb3NlZCcsb3BlcmF0aW9uKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcHJvcG9zYWwgcmVjZWlwdCBzdGF0ZScpDQogIHJpbmc9X3JpbmcoZGIsb3duZXIsbm93PW5vdykNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIHByb3Bvc2VyX3Nlc3Npb24scmVjaXBpZW50X3Nlc3Npb24sY3JlYXRlZF9hdCxpdGVtX3VpZCxkZXNjcmlwdG9yIEZST00gbmF0aXZlX2NvdXBsZV9wZW5kaW5nX3YxIFdIRVJFIG9wZXJhdGlvbj0/Jywob3BlcmF0aW9uLCkpLmZldGNob25lKCkNCiBpZiByb3cgaXMgTm9uZSBvciByb3dbOjJdIT0oc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbilvciByb3dbMzpdIT0ocmluZ1sndWlkJ10scGF5bG9hZClvciBub3c+cm93WzJdKzEwOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleHBpcmVkIG9yIGNoYW5nZWQgcHJvcG9zYWwnKQ0KIGV2ZW50cz1lbmNvZGUoYSxiLEZhbHNlLCgpKQ0KIGZvciBlIGluIGV2ZW50czplbmNvZGVfZXZlbnQoZSkNCiBndWFyZChkYikNCiBfd3JpdGVfZ3VhcmQoZGIpDQogaWYgX2FjdG9yKGRiLG93bmVyLGFjY291bnQpIT1hIG9yIF9hY3RvcihkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpIT1iOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBsYXRlIGlkZW50aXR5IGNoYW5nZWQnKQ0KIHJldHVybiBldmVudHMNCmRlZiBhbnN3ZXIoZGIsb3duZXIsYWNjb3VudCxwZWVyLHBlZXJfYWNjb3VudCxzZXNzaW9uLHBlZXJfc2Vzc2lvbixwYXlsb2FkLG9wZXJhdGlvbiwqLGd1YXJkLGVuY29kZSxub3c9Tm9uZSk6DQogcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11dGF0aW9ucyBkaXNhYmxlZCBpbiBmcmVlLWZhcmV3ZWxsIGNvbXBhdGlibGUgcmVjb3ZlcnknKQ0KIG5vdz1fY2xvY2sobm93KTtfd3JpdGVfZ3VhcmQoZGIpO3BhcnNlZD1hbnN3ZXJfcmVxdWVzdChwYXlsb2FkKTtndWFyZChkYik7dGFyZ2V0PV9hY3RvcihkYixvd25lcixhY2NvdW50KTtwcm9wb3Nlcj1fYWN0b3IoZGIscGVlcixwZWVyX2FjY291bnQpO2VsaWdpYmxlKHByb3Bvc2VyLHRhcmdldCkNCiBpZihwYXJzZWRbJ3Byb3Bvc2VyJ10scGFyc2VkWydyZWNpcGllbnQnXSxwYXJzZWRbJ25hbWUnXSxwYXJzZWRbJ293bl9uYW1lJ10pIT0ocGVlcixvd25lcixwcm9wb3NlclsnbmFtZSddLHRhcmdldFsnbmFtZSddKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb3JpZ2luYWwgYW5zd2VyIGlkZW50aXRpZXMnKQ0KIGlmIG5vdCBfcHJlc2VudChkYik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG1pc3Npbmcgb3JpZ2luYWwgcHJvcG9zYWwgc2NoZW1hJykNCiBvbGQ9X3ByZXZpb3VzKGRiLG9wZXJhdGlvbixvd25lcixwZWVyLDB4M2ZlLHBheWxvYWQpDQogaWYgb2xkIGlzIG5vdCBOb25lOg0KICBzYXZlZD1zbmFwc2hvdChkYixvd25lcixhY2NvdW50KQ0KICBpZiBvbGRbNF09PSdhY2NlcHRlZCdhbmQgc2F2ZWQgaXMgbm90IE5vbmUgYW5kIHNhdmVkWydwYWlyX2lkJ109PW9wZXJhdGlvbiBhbmQgc2F2ZWRbJ3BlZXJfdWlkJ109PXBlZXI6DQogICBldmVudHM9ZW5jb2RlKHByb3Bvc2VyLHRhcmdldCxUcnVlLCgpKTtndWFyZChkYik7cmV0dXJuIGV2ZW50cw0KICBpZiBvbGRbNF09PSdyZWplY3RlZCc6ZXZlbnRzPWVuY29kZShwcm9wb3Nlcix0YXJnZXQsVHJ1ZSwoKSk7Z3VhcmQoZGIpO3JldHVybiBldmVudHMNCiAgcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHVua25vd24gYW5zd2VyIHJlY2VpcHQnKQ0KIGlmIHNuYXBzaG90KGRiLG93bmVyLGFjY291bnQpaXMgbm90IE5vbmUgb3Igc25hcHNob3QoZGIscGVlcixwZWVyX2FjY291bnQpaXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGFuc3dlciBhZnRlciByZWxhdGlvbiBjaGFuZ2VkJykNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIG9wZXJhdGlvbixwcm9wb3Nlcl9hY2NvdW50LHJlY2lwaWVudF9hY2NvdW50LHByb3Bvc2VyX3Nlc3Npb24scmVjaXBpZW50X3Nlc3Npb24saXRlbV91aWQsaXRlbV9qc29uLGNyZWF0ZWRfYXQsZGVzY3JpcHRvciBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBwcm9wb3Nlcj0/QU5EIHJlY2lwaWVudD0/JywocGVlcixvd25lcikpLmZldGNob25lKCkNCiBpZiByb3cgaXMgTm9uZSBvciByb3dbMTo1XSE9KHBlZXJfYWNjb3VudCxhY2NvdW50LHBlZXJfc2Vzc2lvbixzZXNzaW9uKW9yIG5vdz5yb3dbN10rMTAgb3Igcm93WzhdIT1fX2ltcG9ydF9fKCdlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcycsZnJvbWxpc3Q9WydkZXNjcmlwdG9yJ10pLmRlc2NyaXB0b3IodGFyZ2V0WyduYW1lJ10pOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBwZW5kaW5nIHNvdXJjZS9zZXNzaW9uL2RlYWRsaW5lJykNCiBzb3VyY2U9ZGIuZXhlY3V0ZSgnU0VMRUNUIGJlZm9yZV9qc29uLGFmdGVyX2pzb24scGF5bG9hZCxraW5kLG93bmVyLHBlZXIsc3RhdHVzLHJlcXVlc3RfaGFzaCBGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBXSEVSRSBvcGVyYXRpb249PycsKHJvd1swXSwpKS5mZXRjaG9uZSgpDQogaWYoc291cmNlIGlzIE5vbmUgb3Igc291cmNlWzBdIT1zb3VyY2VbMV1vciBqc29uLmxvYWRzKHNvdXJjZVswXSkhPVtqc29uLmxvYWRzKHJvd1s2XSldb3Igc291cmNlWzJdIT1yb3dbOF0NCiAgICBvciBzb3VyY2VbMzo3XSE9KDB4M2ZiLHBlZXIsb3duZXIsJ3Byb3Bvc2VkJylvciBzb3VyY2VbN10hPV9kaWdlc3QocGVlciwweDNmYixzb3VyY2VbMl0pKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcGVuZGluZyBsYWNrcyBleGFjdCBpbW11dGFibGUgcHJvcG9zYWwgcmluZyBwcm9kdWNlcicpDQogYmVmb3JlPWxvYWRfaXRlbXMoZGIscGVlcik7Y2hhbmdlcz1bXTtzdGF0dXM9J3JlamVjdGVkJw0KIGlmIHBhcnNlZFsnYW5zd2VyJ109PTA6DQogIHJpbmc9X3JpbmcoZGIscGVlcixub3c9bm93LHVpZD1yb3dbNV0pDQogIGlmIHJpbmchPWpzb24ubG9hZHMocm93WzZdKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcHJvcG9zYWwtYm91bmQgcmluZyBjaGFuZ2VkJykNCiAgaWYgcmluZ1snY291bnQnXT09MTpyZW1vdmUoZGIscGVlcixyaW5nKQ0KICBlbGlmIGRiLmV4ZWN1dGUoJ1VQREFURSBpbnZlbnRvcnlfaXRlbXMgU0VUIGNvdW50PWNvdW50LTEgV0hFUkUgb3duZXI9P0FORCB1aWQ9P0FORCBjb3VudD0/JywocGVlcixyaW5nWyd1aWQnXSxyaW5nWydjb3VudCddKSkucm93Y291bnQhPTE6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHJpbmcgZGViaXQgY2hhbmdlZCcpDQogIGFmdGVyPWxvYWRfaXRlbXMoZGIscGVlcik7X2RlYml0KGJlZm9yZSxhZnRlcixyaW5nWyd1aWQnXSk7cG9zaXRpb249KHJpbmdbJ2dyb3VwJ10scmluZ1snc2xvdCddKTtjaGFuZ2VzPVsocG9zaXRpb24sbmV4dCgoaSBmb3IgaSBpbiBhZnRlciBpZihpWydncm91cCddLGlbJ3Nsb3QnXSk9PXBvc2l0aW9uKSxOb25lKSldO3N0YXR1cz0nYWNjZXB0ZWQnDQogIGRiLmV4ZWN1dGUoJ0lOU0VSVCBJTlRPIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEgVkFMVUVTKD8sPyw/LD8sPyw/LD8sPyw/LDEpJywob3BlcmF0aW9uLHBlZXIsb3duZXIscGVlcl9hY2NvdW50LGFjY291bnQsbm93LHJvd1swXSxvcGVyYXRpb24scmluZ1sndWlkJ10pKQ0KICBkYi5leGVjdXRlbWFueSgnSU5TRVJUIElOVE8gbmF0aXZlX2NvdXBsZV9tZW1iZXJzX3YxIFZBTFVFUyg/LD8sPyknLCgocGVlcixwZWVyX2FjY291bnQsb3BlcmF0aW9uKSwob3duZXIsYWNjb3VudCxvcGVyYXRpb24pKSkNCiBlbHNlOmFmdGVyPWJlZm9yZQ0KIGRiLmV4ZWN1dGUoJ0lOU0VSVCBJTlRPIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBWQUxVRVMoPyw/LD8sPyw/LD8sPyw/LD8sPyw/KScsKG9wZXJhdGlvbixfZGlnZXN0KG93bmVyLDB4M2ZlLHBheWxvYWQpLDB4M2ZlLG93bmVyLHBlZXIscGF5bG9hZCxyb3dbMF0sc3RhdHVzLG5vdyxqc29uLmR1bXBzKGJlZm9yZSxzb3J0X2tleXM9VHJ1ZSksanNvbi5kdW1wcyhhZnRlcixzb3J0X2tleXM9VHJ1ZSkpKQ0KIGRiLmV4ZWN1dGUoJ0RFTEVURSBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBvcGVyYXRpb249PycsKHJvd1swXSwpKQ0KIGV2ZW50cz1lbmNvZGUocHJvcG9zZXIsdGFyZ2V0LEZhbHNlLGNoYW5nZXMpDQogZm9yIGUgaW4gZXZlbnRzOmVuY29kZV9ldmVudChlKQ0KIGd1YXJkKGRiKQ0KIGlmIHBhcnNlZFsnYW5zd2VyJ109PTA6DQogIGlmIGxvYWRfaXRlbXMoZGIscGVlcikhPWFmdGVyOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBpbnZlbnRvcnkgY2hhbmdlZCBhZnRlciBleGFjdCBkZWJpdCByZWNlaXB0JykNCiAgX2RlYml0KGJlZm9yZSxsb2FkX2l0ZW1zKGRiLHBlZXIpLHJvd1s1XSkNCiAgaWYgc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClbJ3BlZXJfdWlkJ10hPXBlZXIgb3Igc25hcHNob3QoZGIscGVlcixwZWVyX2FjY291bnQpWydwZWVyX3VpZCddIT1vd25lcjpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcmVjaXByb2NhbCBjb2xkIHNvdXJjZSBjaGFuZ2VkJykNCiBfd3JpdGVfZ3VhcmQoZGIpDQogaWYgX2FjdG9yKGRiLG93bmVyLGFjY291bnQpIT10YXJnZXQgb3IgX2FjdG9yKGRiLHBlZXIscGVlcl9hY2NvdW50KSE9cHJvcG9zZXI6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGxhdGUgc2F2ZWQgY2hhcmFjdGVyIGNoYW5nZWQnKQ0KIHJldHVybiBldmVudHMNCg==', 'size': 15544, 'sha256': 'ddb601d64ed6100187f945a34b997483f6198c9338fb9010ea032cc927d63e3c'}, 'els_server/storage/couple_closures.py': {'base64': 'IiIiRXhhY3QgbGF6eSBjbG9zdXJlIGxlZGdlciBmb3IgaHVtYW4tYXBwcm92ZWQgZnJlZSBjb3VwbGUxIGZhcmV3ZWxsLg0KT2xkIHBhaXIvYWNjZXB0YW5jZS9wcm9wb3NhbC9kZWJpdCBmYWN0cyByZW1haW4gaW1tdXRhYmxlOyBvbmx5IGFjdGl2ZSBtZW1iZXJzaGlwcw0KYXJlIHJlbW92ZWQuIE5vIEVEL2ludmVudG9yeS9yZWZ1bmQgd3JpdGVyIGFuZCBubyBndWVzc2VkIG1hcnJpYWdlIHBvbGljeS4NCiIiIg0KaW1wb3J0IGpzb24NCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlIGltcG9ydCByZWxhdGlvbnNoaXBzIGFzIHJlbA0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcyBpbXBvcnQgZmFyZXdlbGxfcmVxdWVzdA0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQNClRBQkxFPSduYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxJw0KUE9MSUNZPSdodW1hbi1mcmVlLWNvdXBsZTEtbm8tcmluZy1yZWZ1bmQtMjAyNjEwMjktdjEnDQpTQ0hFTUE9IkNSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxKHBhaXJfaWQgVEVYVCBQUklNQVJZIEtFWSBSRUZFUkVOQ0VTIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEoaWQpLG9wZXJhdGlvbiBURVhUIE5PVCBOVUxMIFVOSVFVRSxyZXF1ZXN0X2hhc2ggVEVYVCBOT1QgTlVMTCxvd25lciBJTlRFR0VSIE5PVCBOVUxMLGFjY291bnRfaWQgSU5URUdFUiBOT1QgTlVMTCxwZWVyIElOVEVHRVIgTk9UIE5VTEwscGVlcl9hY2NvdW50IElOVEVHRVIgTk9UIE5VTEwsY3JlYXRlZF9hdCBJTlRFR0VSIE5PVCBOVUxMLGZlZSBJTlRFR0VSIE5PVCBOVUxMIENIRUNLKGZlZT0wKSxyZWZ1bmQgSU5URUdFUiBOT1QgTlVMTCBDSEVDSyhyZWZ1bmQ9MCksYmVmb3JlX2pzb24gVEVYVCBOT1QgTlVMTCxhZnRlcl9qc29uIFRFWFQgTk9UIE5VTEwscGF5bG9hZCBCTE9CIE5PVCBOVUxMLHBvbGljeSBURVhUIE5PVCBOVUxMLHZlcnNpb24gSU5URUdFUiBOT1QgTlVMTCBDSEVDSyh2ZXJzaW9uPTEpKSINCg0KZGVmIGNhbm9uaWNhbCh2YWx1ZSk6cmV0dXJuIGpzb24uZHVtcHModmFsdWUsc29ydF9rZXlzPVRydWUsc2VwYXJhdG9ycz0oJywnLCc6JykpDQoNCmRlZiBwcmVzZW50KGRiLCosYmFzZT1UcnVlKToNCiBmb3VuZD1kaWN0KGRiLmV4ZWN1dGUoIlNFTEVDVCBuYW1lLHNxbCBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIobmFtZSk9PyIsKFRBQkxFLCkpKQ0KIGlmIGZvdW5kIGFuZChmb3VuZCE9e1RBQkxFOlNDSEVNQX1vciBub3QgYmFzZSk6cmFpc2UgVmFsdWVFcnJvcignVW5rbm93biBvciBvcnBoYW4gY291cGxlIGNsb3N1cmUgc2NoZW1hJykNCiBpZiBkYi5leGVjdXRlKCJTRUxFQ1QgMSBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIodGJsX25hbWUpPT9BTkQodHlwZT0ndHJpZ2dlcidPUih0eXBlPSdpbmRleCdBTkQgc3FsIElTIE5PVCBOVUxMKSkgTElNSVQgMSIsKFRBQkxFLCkpLmZldGNob25lKCk6cmFpc2UgVmFsdWVFcnJvcignVW5yZXZpZXdlZCBjb3VwbGUgY2xvc3VyZSBzY2hlbWEgZXh0ZW5zaW9uJykNCiByZXR1cm4gYm9vbChmb3VuZCkNCg0KZGVmIGluaXRpYWxpemUoZGIpOg0KIGlmIG5vdCBkYi5pbl90cmFuc2FjdGlvbjpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgY2xvc3VyZSBvdXRzaWRlIHdyaXRlciB0cmFuc2FjdGlvbicpDQogaWYgbm90IHJlbC5fcHJlc2VudChkYik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3N1cmUgcmVxdWlyZXMgb3JpZ2luYWwgYWNjZXB0ZWQgc2NoZW1hJykNCiBpZiBub3QgcHJlc2VudChkYik6ZGIuZXhlY3V0ZShTQ0hFTUEpDQogcHJlc2VudChkYikNCg0KZGVmIHBhaXJfcm93KGRiLHBhaXJfaWQpOg0KIHJvdz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBXSEVSRSBpZD0/JywocGFpcl9pZCwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignTWlzc2luZyBvcmlnaW5hbCBjb3VwbGUgcGFpcicpDQogcmV0dXJuIHJvdw0KDQpkZWYgcmVjZWlwdF9iZWZvcmUocGFpcixvd25lcixhY2NvdW50KToNCiByZXR1cm4gY2Fub25pY2FsKGRpY3QocGFpcj1saXN0KHBhaXIpLG1lbWJlcnM9c29ydGVkKFtbcGFpclsxXSxwYWlyWzNdLHBhaXJbMF1dLFtwYWlyWzJdLHBhaXJbNF0scGFpclswXV1dKSxhY3Rvcj1bb3duZXIsYWNjb3VudF0pKQ0KDQpkZWYgcmVjZWlwdF9hZnRlcihwYWlyX2lkKTpyZXR1cm4gY2Fub25pY2FsKGRpY3QocGFpcl9pZD1wYWlyX2lkLG1lbWJlcnM9W10sZmVlX0VEPTAscmluZ19yZWZ1bmQ9RmFsc2UpKQ0KDQpkZWYgY2hlY2tlZChkYixyb3cpOg0KIHBhaXJfaWQsb3BlcmF0aW9uLGRpZ2VzdCxvd25lcixhY2NvdW50LHBlZXIscGVlcl9hY2NvdW50LHN0YW1wLGZlZSxyZWZ1bmQsYmVmb3JlLGFmdGVyLHBheWxvYWQscG9saWN5LHZlcnNpb249cm93DQogcGFpcj1wYWlyX3JvdyhkYixwYWlyX2lkKQ0KIGlmKHR5cGUob3BlcmF0aW9uKWlzIG5vdCBzdHIgb3Igbm90IDE8PWxlbihvcGVyYXRpb24pPD0xNjAgb3IgcGF5bG9hZCE9Yicnb3IgZGlnZXN0IT1yZWwuX2RpZ2VzdChvd25lciwweDQxYyxwYXlsb2FkKQ0KICBvcihvd25lcixhY2NvdW50LHBlZXIscGVlcl9hY2NvdW50KW5vdCBpbigocGFpclsxXSxwYWlyWzNdLHBhaXJbMl0scGFpcls0XSksKHBhaXJbMl0scGFpcls0XSxwYWlyWzFdLHBhaXJbM10pKQ0KICBvciB0eXBlKHN0YW1wKWlzIG5vdCBpbnQgb3Igbm90IHBhaXJbNV08PXN0YW1wPDIqKjYzIG9yIGZlZSE9MCBvciByZWZ1bmQhPTAgb3IgcG9saWN5IT1QT0xJQ1kgb3IgdmVyc2lvbiE9MQ0KICBvciBiZWZvcmUhPXJlY2VpcHRfYmVmb3JlKHBhaXIsb3duZXIsYWNjb3VudClvciBhZnRlciE9cmVjZWlwdF9hZnRlcihwYWlyX2lkKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3N1cmUgaW1tdXRhYmxlIHNvdXJjZSByZWNlaXB0IGNoYW5nZWQnKQ0KIHJlbC5fcGFpcl9zbmFwc2hvdChkYixwYWlyX2lkLG93bmVyLGFjY291bnQsY2xvc2VkPVRydWUpDQogcmV0dXJuIHBhaXJfaWQNCg0KZGVmIGNsb3NlZF9wYWlycyhkYixvd25lcixhY2NvdW50KToNCiBpZiBub3QgcHJlc2VudChkYik6cmV0dXJuIHNldCgpDQogcm93cz1kYi5leGVjdXRlKCdTRUxFQ1QgYy4qRlJPTSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIGMgTEVGVCBKT0lOIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEgcCBPTiBwLmlkPWMucGFpcl9pZCBXSEVSRSBjLm93bmVyPT9PUiBjLnBlZXI9P09SIHAuYT0/T1IgcC5iPT8nLChvd25lcixvd25lcixvd25lcixvd25lcikpLmZldGNoYWxsKCkNCiByZXN1bHQ9c2V0KCkNCiBmb3Igcm93IGluIHJvd3M6DQogIGlkZW50PWNoZWNrZWQoZGIscm93KTtwYWlyPXBhaXJfcm93KGRiLGlkZW50KQ0KICBpZihvd25lcixhY2NvdW50KW5vdCBpbigocGFpclsxXSxwYWlyWzNdKSwocGFpclsyXSxwYWlyWzRdKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3NlZCBoaXN0b3J5IG93bmVyIGNoYW5nZWQnKQ0KICByZXN1bHQuYWRkKGlkZW50KQ0KIHJldHVybiByZXN1bHQNCg0KZGVmIHF1b3RlKGRiLG93bmVyLGFjY291bnQpOg0KIHNhdmVkPXJlbC5zbmFwc2hvdChkYixvd25lcixhY2NvdW50KQ0KIGlmIHNhdmVkIGlzIE5vbmUgb3Igc2F2ZWRbJ2tpbmQnXSE9MTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZXF1aXJlcyBjdXJyZW50IGNvdXBsZTEnKQ0KIHBhaXI9cGFpcl9yb3coZGIsc2F2ZWRbJ3BhaXJfaWQnXSk7cGVlcj1zYXZlZFsncGVlcl91aWQnXTtwZWVyX2FjY291bnQ9cGFpcls0XWlmIG93bmVyPT1wYWlyWzFdZWxzZSBwYWlyWzNdDQogb3RoZXI9cmVsLnNuYXBzaG90KGRiLHBlZXIscGVlcl9hY2NvdW50KQ0KIGlmIG90aGVyIGlzIE5vbmUgb3Iob3RoZXJbJ3BhaXJfaWQnXSxvdGhlclsncGVlcl91aWQnXSkhPShzYXZlZFsncGFpcl9pZCddLG93bmVyKTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZWNpcHJvY2FsIHBhaXIgY2hhbmdlZCcpDQogcmV0dXJuIGRpY3Qoc2F2ZWQsb3duZXI9b3duZXIsYWNjb3VudF9pZD1hY2NvdW50LHBlZXJfYWNjb3VudD1wZWVyX2FjY291bnQpDQoNCmRlZiBwZXJmb3JtKGRiLG93bmVyLGFjY291bnQscGF5bG9hZCxvcGVyYXRpb24sZXhwZWN0ZWQsKixndWFyZCxlbmNvZGUsbm93PU5vbmUpOg0KIHJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtdXRhdGlvbnMgZGlzYWJsZWQgaW4gZnJlZS1mYXJld2VsbCBjb21wYXRpYmxlIHJlY292ZXJ5JykNCiBmYXJld2VsbF9yZXF1ZXN0KHBheWxvYWQpDQogaWYgdHlwZShvcGVyYXRpb24paXMgbm90IHN0ciBvciBub3QgMTw9bGVuKG9wZXJhdGlvbik8PTE2MDpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgY2xvc3VyZSBvcGVyYXRpb24nKQ0KIGlmIG5vdCBkYi5pbl90cmFuc2FjdGlvbjpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZXF1aXJlcyBjYWxsZXIgd3JpdGVyJykNCiBndWFyZChkYik7cmVsLl93cml0ZV9ndWFyZChkYik7cmVsLl9hY3RvcihkYixvd25lcixhY2NvdW50KQ0KIGlmIHByZXNlbnQoZGIpOg0KICBwcmV2aW91cz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9jbG9zdXJlc192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wZXJhdGlvbiwpKS5mZXRjaG9uZSgpDQogIGlmIHByZXZpb3VzIGlzIG5vdCBOb25lOg0KICAgY2hlY2tlZChkYixwcmV2aW91cykNCiAgIGlmIHByZXZpb3VzWzM6NV0hPShvd25lcixhY2NvdW50KW9yIHByZXZpb3VzWzJdIT1yZWwuX2RpZ2VzdChvd25lciwweDQxYyxwYXlsb2FkKW9yIHJlbC5zbmFwc2hvdChkYixvd25lcixhY2NvdW50KWlzIG5vdCBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIHJlcGxheSBtZWV0cyBhbm90aGVyIHBhaXIgb3IgaWRlbnRpdHknKQ0KICAgYW5zd2VyPWVuY29kZShUcnVlKTtndWFyZChkYikNCiAgIGZvciBldmVudCBpbiBhbnN3ZXI6ZW5jb2RlX2V2ZW50KGV2ZW50KQ0KICAgcmV0dXJuIGFuc3dlcg0KIGFjdHVhbD1xdW90ZShkYixvd25lcixhY2NvdW50KQ0KIGlmIGFjdHVhbCE9ZXhwZWN0ZWQ6cmFpc2UgVmFsdWVFcnJvcignRmFyZXdlbGwgcXVvdGUgYmVsb25ncyB0byBhbm90aGVyIHBhaXIgZ2VuZXJhdGlvbicpDQogZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaW52ZW50b3J5X3N0YXRlIGltcG9ydCBsb2FkX2l0ZW1zDQogZGVmIGVjb25vbWljKCk6DQogIHJldHVybihbbG9hZF9pdGVtcyhkYix1aWQpZm9yIHVpZCBpbihvd25lcixhY3R1YWxbJ3BlZXJfdWlkJ10pXSxkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gcmV3YXJkX2JhbGFuY2VzIFdIRVJFIHVpZCBJTig/LD8pT1JERVIgQlkgdWlkJywob3duZXIsYWN0dWFsWydwZWVyX3VpZCddKSkuZmV0Y2hhbGwoKSkNCiBlY29ub215PWVjb25vbWljKCkNCiBzdGFtcD1yZWwuX2Nsb2NrKG5vdykNCiBpZiBzdGFtcDxhY3R1YWxbJ2NyZWF0ZWRfYXQnXTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCBwcmVjZWRlcyB0cnVlIHBhaXJpbmcnKQ0KIHBhaXI9cGFpcl9yb3coZGIsYWN0dWFsWydwYWlyX2lkJ10pO29sZF9wYWlycz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBPUkRFUiBCWSBpZCcpLmZldGNoYWxsKCk7b2xkX2FjdGlvbnM9ZGIuZXhlY3V0ZSgnU0VMRUNUICpGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBPUkRFUiBCWSBvcGVyYXRpb24nKS5mZXRjaGFsbCgpDQogaW5pdGlhbGl6ZShkYikNCiBkYi5leGVjdXRlKCdJTlNFUlQgSU5UTyBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIFZBTFVFUyg/LD8sPyw/LD8sPyw/LD8sPyw/LD8sPyw/LD8sMSknLChhY3R1YWxbJ3BhaXJfaWQnXSxvcGVyYXRpb24scmVsLl9kaWdlc3Qob3duZXIsMHg0MWMscGF5bG9hZCksb3duZXIsYWNjb3VudCxhY3R1YWxbJ3BlZXJfdWlkJ10sYWN0dWFsWydwZWVyX2FjY291bnQnXSxzdGFtcCwwLDAscmVjZWlwdF9iZWZvcmUocGFpcixvd25lcixhY2NvdW50KSxyZWNlaXB0X2FmdGVyKGFjdHVhbFsncGFpcl9pZCddKSxwYXlsb2FkLFBPTElDWSkpDQogaWYgZGIuZXhlY3V0ZSgnREVMRVRFIEZST00gbmF0aXZlX2NvdXBsZV9tZW1iZXJzX3YxIFdIRVJFIHBhaXJfaWQ9PycsKGFjdHVhbFsncGFpcl9pZCddLCkpLnJvd2NvdW50IT0yOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGV4YWN0bHkgdHdvIGFjdGl2ZSBtZW1iZXJzJykNCiBpZiByZWwuc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClpcyBub3QgTm9uZSBvciByZWwuc25hcHNob3QoZGIsYWN0dWFsWydwZWVyX3VpZCddLGFjdHVhbFsncGVlcl9hY2NvdW50J10paXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignRmFyZXdlbGwgYm90aCBjb2xkIHByb2plY3Rpb25zIG11c3QgYmUgc29sbycpDQogYW5zd2VyPWVuY29kZShGYWxzZSkNCiBmb3IgZXZlbnQgaW4gYW5zd2VyOmVuY29kZV9ldmVudChldmVudCkNCiBndWFyZChkYik7cmVsLl93cml0ZV9ndWFyZChkYikNCiBpZiBkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBPUkRFUiBCWSBpZCcpLmZldGNoYWxsKCkhPW9sZF9wYWlycyBvciBkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIE9SREVSIEJZIG9wZXJhdGlvbicpLmZldGNoYWxsKCkhPW9sZF9hY3Rpb25zOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGFsdGVyZWQgaW1tdXRhYmxlIHBhaXJpbmcvZGViaXQgc291cmNlJykNCiBpZiBlY29ub21pYygpIT1lY29ub215OnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIG11c3QgcHJlc2VydmUgYWxsIG93bmVkIFVJRCBpbnZlbnRvcnkgYW5kIEVEJykNCiBpZiBjaGVja2VkKGRiLGRiLmV4ZWN1dGUoJ1NFTEVDVCAqRlJPTSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIFdIRVJFIG9wZXJhdGlvbj0/Jywob3BlcmF0aW9uLCkpLmZldGNob25lKCkpIT1wYWlyWzBdOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGZpbmFsIGNsb3N1cmUgcmVjZWlwdCcpDQogcmV0dXJuIGFuc3dlcg0K', 'size': 7065, 'sha256': '4008884caac32d2e8d6393e15d095416015283c82c179c9a252925d1cc639dbe'}, 'els_server/storage/identification_ui.py': {'size': 5446, 'sha256': '9ff48abd45a634a2838a6e9efa1275a7537c655ab5901d66ae4e707c51b30555', 'base64': 'IiIiUmVzZXQgc2Nyb2xsIC0+IHVuaWRlbnRpZmllZCBpdGVtIC0+IHBhaWQtb25jZSBzY3JvbGwgYW5kIGZyZWUgaWRlbnRpZmljYXRpb24uIiIiCmltcG9ydCBzcWxpdGUzLHNlY3JldHMKZnJvbSBjb250ZXh0bGliIGltcG9ydCBjbG9zaW5nCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLnByb2Zlc3Npb25fc3RhdGUgaW1wb3J0IHJlcXVpcmVfb3duZXIKZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5pZGVudGlmaWNhdGlvbl91aSBpbXBvcnQgcmVxdWlyZV90ZW1wbGF0ZSxjYXRhbG9nLGRyYXdfaW5pdGlhbApmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50CmZyb20gZWxzX3NlcnZlci5kb21haW4uaXRlbV9sb2NrcyBpbXBvcnQgcmVxdWlyZV91bmxvY2tlZApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuaWRlbnRpZmljYXRpb25fbWVzc2FnZXMgaW1wb3J0IHJlcXVlc3QsYWNrbm93bGVkZ2VtZW50CmZyb20gZWxzX3NlcnZlci5wcm90b2NvbC5wcm90b2NvbF9jb2RlYyBpbXBvcnQgRXZlbnQKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaW52ZW50b3J5X2FjdGlvbnMgaW1wb3J0IF9pZGVudGl0eSxfcHJldmlvdXMsX2NvbW1pdApmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfc3RhdGUgaW1wb3J0IGxvYWRfaXRlbXMKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X3JlY2VpcHRfc3RhdGUgaW1wb3J0IGN1cnJlbnRfY2hhbmdlcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pdGVtX2luc3RhbmNlcyBpbXBvcnQgcmVtb3ZlCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLm5wY190cmFkZSBpbXBvcnQgYmFsYW5jZXMKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X29wdGlvbnMgaW1wb3J0IHJlcGxhY2UgYXMgcmVwbGFjZV9vcHRpb25zCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmVxdWlwbWVudF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgcmVwbGFjZSBhcyByZXBsYWNlX2lkZW50aWZpZWQKZGVmIHBlcmZvcm0ocGF0aCxvd25lcixraW5kLHBheWxvYWQsb3BlcmF0aW9uLHJhbmRiZWxvdz1zZWNyZXRzLnJhbmRiZWxvdywqLGFjY291bnRfaWQ9Tm9uZSxwcmVwYXJlPU5vbmUpOgogdWlkLG1hdGVyaWFsX3VpZD1yZXF1ZXN0KGtpbmQscGF5bG9hZCk7b3duZXIsZGlnZXN0PV9pZGVudGl0eShvd25lcixraW5kLHBheWxvYWQsb3BlcmF0aW9uKQogd2l0aCBjbG9zaW5nKHNxbGl0ZTMuY29ubmVjdChwYXRoLHRpbWVvdXQ9MTApKSBhcyBkYixkYjoKICBkYi5leGVjdXRlKCdQUkFHTUEgZm9yZWlnbl9rZXlzPU9OJyk7ZGIuZXhlY3V0ZSgnQkVHSU4gSU1NRURJQVRFJykKICBpZiBwcmVwYXJlIGlzIG5vdCBOb25lOnByZXBhcmUoKQogIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1fYWN0b3IgaW1wb3J0IHJlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcgogIHJlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcihkYixvd25lcikKICBpZiBhY2NvdW50X2lkIGlzIG5vdCBOb25lOnJlcXVpcmVfb3duZXIoZGIsb3duZXIsYWNjb3VudF9pZCkKICBvbGQ9X3ByZXZpb3VzKGRiLG9wZXJhdGlvbixkaWdlc3QpO2JlZm9yZT1sb2FkX2l0ZW1zKGRiLG93bmVyKTtlZD1iYWxhbmNlcyhkYixvd25lcilbJ2VkJ107YnlfdWlkPXtpWyd1aWQnXTppIGZvciBpIGluIGJlZm9yZX0KICBpZiBvbGQgaXMgbm90IE5vbmU6CiAgIGN1cnJlbnQ9eyhpWydncm91cCddLGlbJ3Nsb3QnXSk6aSBmb3IgaSBpbiBiZWZvcmV9CiAgIHJldHVybiBbRXZlbnQoMHgyMDEsa2luZD1raW5kKzEscGF5bG9hZD1hY2tub3dsZWRnZW1lbnQoa2luZCxlZCxjdXJyZW50X2NoYW5nZXMoZGIsb3BlcmF0aW9uLG93bmVyLGtpbmQsb2xkLGJlZm9yZSkpKV0KICBpdGVtPWJ5X3VpZC5nZXQodWlkKQogIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfZ2Vhcl9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkIGFzIGFjdGl2aXR5X3N1cHBvcnRlZCxkcmF3IGFzIGFjdGl2aXR5X2RyYXcKICBhY3Rpdml0eT1pdGVtIGlzIG5vdCBOb25lIGFuZCBhY3Rpdml0eV9zdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkKICBpZiBhY3Rpdml0eSBhbmQga2luZCE9MHg0Mzg6cmFpc2UgVmFsdWVFcnJvcignQWN0aXZpdHkgYXJtb3Igb3JkaW5hcnkgaW5pdGlhbCBpZGVudGlmaWNhdGlvbiBvbmx5JykKICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmFjY2Vzc29yeV9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkIGFzIGFjY2Vzc29yeV9zdXBwb3J0ZWQsZHJhdyBhcyBhY2Nlc3NvcnlfZHJhdwogIGFjY2Vzc29yeT1pdGVtIGlzIG5vdCBOb25lIGFuZCBhY2Nlc3Nvcnlfc3VwcG9ydGVkKGl0ZW1bJ3RlbXBsYXRlJ10pCiAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hY2Nlc3NvcnlfaWRlbnRpZmljYXRpb24gaW1wb3J0IHByb2ZpbGUgYXMgYWNjZXNzb3J5X3Byb2ZpbGUKICBpZiBhY2Nlc3NvcnkgYW5kIGFjY2Vzc29yeV9wcm9maWxlKGl0ZW1bJ3RlbXBsYXRlJ10paXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQWNjZXNzb3J5IGlkZW50aWZpY2F0aW9uIG1haW50ZW5hbmNlJykKICBpZiBhY2Nlc3Nvcnk6CiAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYWNjZXNzb3J5X2lkZW50aWZpY2F0aW9uIGltcG9ydCByZXNldF9zdXBwb3J0ZWQKICAgaWYgaXRlbVsnZ3JvdXAnXSE9MiBvciBraW5kPT0weDQzYSBhbmQgbm90IHJlc2V0X3N1cHBvcnRlZChpdGVtWyd0ZW1wbGF0ZSddKTpyYWlzZSBWYWx1ZUVycm9yKCdBY2Nlc3NvcnkgaWRlbnRpZmljYXRpb24gcmVxdWlyZXMgYW4gZWxpZ2libGUgYmFnIGl0ZW0nKQogIGlmIGl0ZW0gaXMgTm9uZSBvciBpdGVtWydjb3VudCddIT0xIG9yKGl0ZW1bJ2dyb3VwJ10hPTEgYW5kIG5vdCBhY2Nlc3NvcnkpOnJhaXNlIFZhbHVlRXJyb3IoJ093bmVkIHVuZXF1aXBwZWQgaWRlbnRpZmljYXRpb24gaXRlbSByZXF1aXJlZCcpCiAgcmVxdWlyZV90ZW1wbGF0ZShpdGVtWyd0ZW1wbGF0ZSddLHJlc2V0PWtpbmQ9PTB4NDNhKTtyZXF1aXJlX2N1cnJlbnQoaXRlbSk7cmVxdWlyZV91bmxvY2tlZChpdGVtKQogIGZyb20gZWxzX3NlcnZlci5kb21haW4uaWRlbnRpZmljYXRpb25fdWkgaW1wb3J0IGluaXRpYWxfcGVuZGluZwogIGZyb20gZWxzX3NlcnZlci5kb21haW4uaWRlbnRpZmljYXRpb25fdWkgaW1wb3J0IGNvbXBhdGliaWxpdHlfcHJvZmlsZQogIGlmIGNvbXBhdGliaWxpdHlfcHJvZmlsZShpdGVtWyd0ZW1wbGF0ZSddKWlzIG5vdCBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0NvbXBhdGliaWxpdHkgaWRlbnRpZmljYXRpb24gcmVjb3ZlcnkgZGVuaWVzIG5ldyBvcGVyYXRpb24nKQogIGlkZW50aWZpZWQ9aXRlbS5nZXQoJ2lkZW50aWZpZWQnLG5vdCBpbml0aWFsX3BlbmRpbmcoaXRlbSkpO3ByZXZpb3VzPWl0ZW0uZ2V0KCdvcHRpb25fZ3JvdXBzJyx7fSk7cG9zaXRpb25zPVsoaXRlbVsnZ3JvdXAnXSxpdGVtWydzbG90J10pXQogIGlmIGtpbmQ9PTB4NDNhOgogICBpZiBub3QgaWRlbnRpZmllZDpyYWlzZSBWYWx1ZUVycm9yKCdJdGVtIGlzIGFscmVhZHkgdW5pZGVudGlmaWVkJykKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkLHJlc2V0X3ZhbHVlcwogICByZXNldF9vcHRpb25zPXJlc2V0X3ZhbHVlcyhpdGVtWyd0ZW1wbGF0ZSddLHByZXZpb3VzLmdldCgnMScsW10pKSBpZiBzdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkgZWxzZSBbXQogICBtYXRlcmlhbD1ieV91aWQuZ2V0KG1hdGVyaWFsX3VpZCkKICAgaWYgbWF0ZXJpYWwgaXMgTm9uZSBvciBzdHIobWF0ZXJpYWxbJ3RlbXBsYXRlJ10pIG5vdCBpbiBjYXRhbG9nKClbJ21hdGVyaWFscyddOnJhaXNlIFZhbHVlRXJyb3IoJ093bmVkIG9yaWdpbmFsIHJlc2V0IHNjcm9sbCByZXF1aXJlZCcpCiAgIHJlcXVpcmVfY3VycmVudChtYXRlcmlhbCk7cmVxdWlyZV91bmxvY2tlZChtYXRlcmlhbCkKICAgaWYgbWF0ZXJpYWxbJ2NvdW50J109PTE6cmVtb3ZlKGRiLG93bmVyLG1hdGVyaWFsKQogICBlbHNlOmRiLmV4ZWN1dGUoJ1VQREFURSBpbnZlbnRvcnlfaXRlbXMgU0VUIGNvdW50PWNvdW50LTEgV0hFUkUgdWlkPT8gQU5EIG93bmVyPT8nLChtYXRlcmlhbF91aWQsb3duZXIpKQogICBwb3NpdGlvbnMuYXBwZW5kKChtYXRlcmlhbFsnZ3JvdXAnXSxtYXRlcmlhbFsnc2xvdCddKSk7dXBkYXRlZD17KipwcmV2aW91cywnMSc6cmVzZXRfb3B0aW9uc307ZmxhZz1GYWxzZQogIGVsc2U6CiAgIGlmIGlkZW50aWZpZWQ6cmFpc2UgVmFsdWVFcnJvcignSWRlbnRpZnkgcmVxdWlyZXMgYW4gdW5pZGVudGlmaWVkIGl0ZW0sIG5vdCBhIGZyZWUgcmVyb2xsJykKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkLGlkZW50aWZ5X3ZhbHVlcwogICB1cGRhdGVkPXsqKnByZXZpb3VzLCcxJzphY3Rpdml0eV9kcmF3KHJhbmRiZWxvdykgaWYgYWN0aXZpdHkgZWxzZSBhY2Nlc3NvcnlfZHJhdyhyYW5kYmVsb3csaXRlbVsndGVtcGxhdGUnXSkgaWYgYWNjZXNzb3J5IGVsc2UgaWRlbnRpZnlfdmFsdWVzKGl0ZW1bJ3RlbXBsYXRlJ10scHJldmlvdXMuZ2V0KCcxJyxbXSkscmFuZGJlbG93KSBpZiBzdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkgZWxzZSBkcmF3X2luaXRpYWwoaXRlbVsndGVtcGxhdGUnXSxyYW5kYmVsb3cpfTtmbGFnPVRydWUKICBpZiBraW5kPT0weDQzOCBhbmQgaXRlbVsndGVtcGxhdGUnXSBpbiAoMTY4OTE1LDE2ODkxNiwxNjg5MTcsMTY4OTE4KSBhbmQgbm90IHByZXZpb3VzLmdldCgnMzEnKToKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9jb252ZXJzaW9uIGltcG9ydCBkcmF3IGFzIGNvbnZlcnNpb25fZHJhdwogICB1cGRhdGVkWyczMSddPWNvbnZlcnNpb25fZHJhdyhbMCwwLDBdLHt9LHJhbmRiZWxvdykKICByZXBsYWNlX2lkZW50aWZpZWQoZGIsb3duZXIsdWlkLGlkZW50aWZpZWQsZmxhZyk7cmVwbGFjZV9vcHRpb25zKGRiLG93bmVyLHVpZCxwcmV2aW91cyx1cGRhdGVkKQogIGFmdGVyPWxvYWRfaXRlbXMoZGIsb3duZXIpO2N1cnJlbnQ9eyhpWydncm91cCddLGlbJ3Nsb3QnXSk6aSBmb3IgaSBpbiBhZnRlcn0KICB3aXJlPWFja25vd2xlZGdlbWVudChraW5kLGVkLFsocCxjdXJyZW50LmdldChwKSkgZm9yIHAgaW4gcG9zaXRpb25zXSkKICBldmVudD1FdmVudCgweDIwMSxraW5kPWtpbmQrMSxwYXlsb2FkPXdpcmUpCiAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICBlbmNvZGVfZXZlbnQoZXZlbnQpCiAgaWYgcHJlcGFyZSBpcyBub3QgTm9uZTpwcmVwYXJlKCkKICBfY29tbWl0KGRiLG9wZXJhdGlvbixkaWdlc3Qsb3duZXIsa2luZCxwb3NpdGlvbnMsYmVmb3JlLGFmdGVyKQogIHJldHVybiBbZXZlbnRdCg=='}, 'els_server/storage/fixed_cubes.py': {'size': 11428, 'sha256': 'f0e5423f8df120329ec62535de0e803e52f051e8f4dfcf97e0e509411c291d7a', 'base64': 'IiIiQ29uc3VtZSBvbmUgb3duZWQgZml4ZWQgY3ViZSBhbmQgZGVsaXZlciBpdHMgb3JpZ2luYWwgY29udGVudHMgYXRvbWljYWxseS4iIiIKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaXRlbV9hY3RvciBpbXBvcnQgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyCmltcG9ydCBzZWNyZXRzLHNxbGl0ZTMsc3RydWN0CmZyb20gY29udGV4dGxpYiBpbXBvcnQgY2xvc2luZwpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmN1YmVzIGltcG9ydCBjYXRhbG9nCmZyb20gZWxzX3NlcnZlci5kb21haW4uaW52ZW50b3J5X2l0ZW1zIGltcG9ydCBWRVJJRklFRF9URU1QTEFURVMsVEVNUExBVEVfQkFHX0dST1VQUwpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50CmZyb20gZWxzX3NlcnZlci5kb21haW4uaXRlbV9sb2NrcyBpbXBvcnQgcmVxdWlyZV91bmxvY2tlZApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuaWNlX21lc3NhZ2VzIGltcG9ydCB1c2VfcmVxdWVzdApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuY3ViZV9tZXNzYWdlcyBpbXBvcnQgcmVzdWx0CmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmludmVudG9yeV9zdGF0ZSBpbXBvcnQgbG9hZF9pdGVtcyxncmFudF9pdGVtcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfYWN0aW9ucyBpbXBvcnQgX2lkZW50aXR5LF9wcmV2aW91cyxfY29tbWl0CmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmludmVudG9yeV9tYW5hZ2VtZW50IGltcG9ydCBfdXBkYXRlcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ucGNfdHJhZGUgaW1wb3J0IGJhbGFuY2VzCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1faW5zdGFuY2VzIGltcG9ydCByZW1vdmUKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X3JlY2VpcHRfc3RhdGUgaW1wb3J0IGN1cnJlbnRfY2hhbmdlcwoKCmRlZiBfbGVnYWN5X2FjdG9yKGRiLG93bmVyLGFjY291bnRfaWQscHJlcGFyZSk6CiAgICBpZiBub3QgY2FsbGFibGUocHJlcGFyZSk6cmFpc2UgVmFsdWVFcnJvcignTGVnYWN5IGN1YmUgY3VycmVudCBzZWxlY3RlZCBhY3RvciBjYWxsYmFjayByZXF1aXJlZCcpCiAgICBwcmVwYXJlKGRiKQogICAgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyKGRiLG93bmVyKQogICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UucHJvZmVzc2lvbl9zdGF0ZSBpbXBvcnQgcmVxdWlyZV9vd25lcgogICAgcmVxdWlyZV9vd25lcihkYixvd25lcixhY2NvdW50X2lkKQoKCmRlZiBvcGVuX2N1YmUocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbixyYW5kYmVsb3c9c2VjcmV0cy5yYW5kYmVsb3csKixhY2NvdW50X2lkPU5vbmUscHJlcGFyZT1Ob25lKToKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uam9iX3Jld2FyZF9ib3hlcyBpbXBvcnQgQk9YRVMgYXMgam9iX2JveGVzCiAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZSBpbiBqb2JfYm94ZXM6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2Uuam9iX3Jld2FyZF9ib3hlcyBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbixhY2NvdW50X2lkPWFjY291bnRfaWQscHJlcGFyZT1wcmVwYXJlKQogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGU9PTcxNTAzNjoKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS53YXJkcm9iZV90aWNrZXRfYm94IGltcG9ydCBvcGVuX2JveAogICAgICAgIHJldHVybiBvcGVuX2JveChwYXRoLG93bmVyLHBheWxvYWQsb3BlcmF0aW9uLGFjY291bnRfaWQ9YWNjb3VudF9pZCkKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4ucHVibGlzaGVkXzIwMjZfYnVuZGxlcyBpbXBvcnQgZW5hYmxlZAogICAgZGVmaW5pdGlvbj1lbmFibGVkKCkuZ2V0KGV4cGVjdGVkX3RlbXBsYXRlKQogICAgaWYgZGVmaW5pdGlvbiBpcyBub3QgTm9uZToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5wdWJsaXNoZWRfMjAyNl9idW5kbGVzIGltcG9ydCBvcGVuX2J1bmRsZQogICAgICAgIHJldHVybiBvcGVuX2J1bmRsZShwYXRoLG93bmVyLHBheWxvYWQsb3BlcmF0aW9uLGRlZmluaXRpb249ZGVmaW5pdGlvbixhY2NvdW50X2lkPWFjY291bnRfaWQscHJlcGFyZT1wcmVwYXJlKQogICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5ib29zdGluZ18yMDI2X2ZvcmNlX3Jld2FyZHMgaW1wb3J0IGJveGVzIGFzIGZvcmNlX2JveGVzCiAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZSBpbiBmb3JjZV9ib3hlcygpOgogICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmJvb3N0aW5nXzIwMjZfZm9yY2VfcmV3YXJkcyBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbikKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl9wYXJ0aWNpcGF0aW9uX2dlYXIgaW1wb3J0IEJPWCxlbmFibGVkIGFzIGdlYXJfZW5hYmxlZAogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGU9PUJPWCBhbmQgZ2Vhcl9lbmFibGVkKCk6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuYm9vc3RpbmdfMjAyNl9wYXJ0aWNpcGF0aW9uX2dlYXIgaW1wb3J0IG9wZW5fZ2VhcgogICAgICAgIHJldHVybiBvcGVuX2dlYXIocGF0aCxvd25lcixwYXlsb2FkLG9wZXJhdGlvbixhY2NvdW50X2lkPWFjY291bnRfaWQscHJlcGFyZT1wcmVwYXJlKQogICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5ib29zdGluZ18yMDI2X2Zhc2hpb25fcmV3YXJkcyBpbXBvcnQgQk9YRVMsZW50cmllcyBhcyBmYXNoaW9uX2VudHJpZXMKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlIGluIEJPWEVTIGFuZCBmYXNoaW9uX2VudHJpZXMoKToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ib29zdGluZ18yMDI2X2Zhc2hpb25fcmV3YXJkcyBpbXBvcnQgb3Blbl9mYXNoaW9uCiAgICAgICAgcmV0dXJuIG9wZW5fZmFzaGlvbihwYXRoLG93bmVyLGV4cGVjdGVkX3RlbXBsYXRlLHBheWxvYWQsb3BlcmF0aW9uKQogICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5ib29zdGluZ18yMDI2X25lc3RlZF9jYXBhY2l0eSBpbXBvcnQgQk9YIGFzIGNhcGFjaXR5X2JveCxpdGVtcyBhcyBjYXBhY2l0eV9pdGVtcwogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGU9PWNhcGFjaXR5X2JveCBhbmQgY2FwYWNpdHlfaXRlbXMoKToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ib29zdGluZ18yMDI2X25lc3RlZF9jYXBhY2l0eSBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixwYXlsb2FkLG9wZXJhdGlvbikKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl90aXRsZV9yZXdhcmRzIGltcG9ydCBCT1ggYXMgdGl0bGVfYm94LGVuYWJsZWQgYXMgdGl0bGVfZW5hYmxlZAogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGU9PXRpdGxlX2JveCBhbmQgdGl0bGVfZW5hYmxlZCgpOgogICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmJvb3N0aW5nXzIwMjZfdGl0bGVfcmV3YXJkcyBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbixhY2NvdW50X2lkPWFjY291bnRfaWQscHJlcGFyZT1wcmVwYXJlKQogICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5ib29zdGluZ18yMDI2X2FjY2Vzc29yaWVzIGltcG9ydCBib3hlcyBhcyBhY2Nlc3NvcnlfYm94ZXMKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlIGluIGFjY2Vzc29yeV9ib3hlcygpOgogICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmJvb3N0aW5nXzIwMjZfYWNjZXNzb3JpZXMgaW1wb3J0IG9wZW5fYm94CiAgICAgICAgcmV0dXJuIG9wZW5fYm94KHBhdGgsb3duZXIsZXhwZWN0ZWRfdGVtcGxhdGUscGF5bG9hZCxvcGVyYXRpb24pCiAgICByZXF1ZXN0PXVzZV9yZXF1ZXN0KHBheWxvYWQpCiAgICBpZiAoYW55KHYgbm90IGluICgwLDEpIGZvciB2IGluIChyZXF1ZXN0LmZsYWcxLHJlcXVlc3QuZmxhZzIscmVxdWVzdC5mbGFnMykpCiAgICAgICAgb3IgZXhwZWN0ZWRfdGVtcGxhdGUgbm90IGluIGNhdGFsb2coKSk6cmFpc2UgVmFsdWVFcnJvcignVW5zdXBwb3J0ZWQgZml4ZWQgY3ViZSB1c2UnKQogICAgcm93PWNhdGFsb2coKVtleHBlY3RlZF90ZW1wbGF0ZV0KICAgIG93bmVkX3Jld2FyZD1yb3cuZ2V0KCdvd25lZF9yZXdhcmRfYm94JyxGYWxzZSkKICAgICMgQm90aCBmaXhlZCBhbmQgc2VsZWN0ZWQgY3ViZSBxdWFudGl0eSBjYWxsYmFja3Mgc2VuZCBDb3VudCBoZXJlLgogICAgIyBaZXJvIGlzIHRoZSBvcmlnaW5hbCBvbmUtYm94IHJvdXRlOyBvbmUgZXhwbGljaXRseSByZXF1ZXN0cyBvbmUgYm94LgogICAgIyBCdWxrIGNvdW50cyByZW1haW4gdW5zdXBwb3J0ZWQ6IG5ldmVyIGNvbnN1bWUgb25lIGZvciBhIGxhcmdlciByZXF1ZXN0LgogICAgaWYgcmVxdWVzdC5vcHRpb24gbm90IGluICgwLDEpOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ1Vuc3VwcG9ydGVkIGZpeGVkIGN1YmUgcXVhbnRpdHknKQogICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5yZWdpb25hbF9ib3NzX2N1YmVzX2xlZ2FjeSBpbXBvcnQgQk9YRVMscG9vbF9mb3IKICAgIGxlZ2FjeT1leHBlY3RlZF90ZW1wbGF0ZSBpbiBCT1hFUwogICAgZ3VhcmRlZD1sZWdhY3kgb3Igb3duZWRfcmV3YXJkIG9yIHJvdy5nZXQoJ3BldF9leHBlZGl0aW9uJyxGYWxzZSkgb3Igcm93LmdldCgnc2VjcmV0X2ZyYWdtZW50X2JveCcsRmFsc2UpCiAgICBncm93aW5nPShleHBlY3RlZF90ZW1wbGF0ZT09MTY4ODg5IGFuZCByb3cuZ2V0KCdncm93aW5nX2FkdmVudHVyZV9raXQnKWlzIFRydWUpCiAgICBpZiBvd25lZF9yZXdhcmQ6b3V0cHV0PU5vbmUKICAgIGVsaWYgcm93WydzZWxlY3Rpb25fY291bnQnXToKICAgICAgICBpZiBsZW4ocmVxdWVzdC5jaG9pY2VzKSE9MTpyYWlzZSBWYWx1ZUVycm9yKCdTZWxlY3QgZXhhY3RseSBvbmUgbmF0aXZlIGN1YmUgaXRlbScpCiAgICAgICAgb3V0cHV0PW5leHQoKGUgZm9yIGUgaW4gcm93WydlbnRyaWVzJ10gaWYgZVsndGVtcGxhdGUnXT09cmVxdWVzdC5jaG9pY2VzWzBdKSxOb25lKQogICAgICAgIGlmIG91dHB1dCBpcyBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0Nob2ljZSBpcyBvdXRzaWRlIHRoaXMgY3ViZScpCiAgICBlbHNlOgogICAgICAgIGlmIHJlcXVlc3QuY2hvaWNlczpyYWlzZSBWYWx1ZUVycm9yKCdGaXhlZCBjdWJlIGRvZXMgbm90IGFjY2VwdCBhIGNob2ljZScpCiAgICAgICAgb3V0cHV0PU5vbmUgaWYgcm93LmdldCgncmFuZG9tJylvciBncm93aW5nIGVsc2Ugcm93WydlbnRyaWVzJ11bMF0KICAgIG93bmVyLGRpZ2VzdD1faWRlbnRpdHkob3duZXIsMHgxOTYsc3RydWN0LnBhY2soJz5pJyxleHBlY3RlZF90ZW1wbGF0ZSkrcGF5bG9hZCxvcGVyYXRpb24pCiAgICB3aXRoIGNsb3Npbmcoc3FsaXRlMy5jb25uZWN0KHBhdGgsdGltZW91dD0xMCkpIGFzIGRiLGRiOgogICAgICAgIGRiLmV4ZWN1dGUoJ1BSQUdNQSBmb3JlaWduX2tleXM9T04nKTtkYi5leGVjdXRlKCdCRUdJTiBJTU1FRElBVEUnKTtyZXF1aXJlX2FjdGl2ZV9jaGFyYWN0ZXIoZGIsb3duZXIpCiAgICAgICAgaWYgZ3VhcmRlZDpfbGVnYWN5X2FjdG9yKGRiLG93bmVyLGFjY291bnRfaWQscHJlcGFyZSkKICAgICAgICBpZiBncm93aW5nOgogICAgICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmdyb3dpbmdfYWR2ZW50dXJlX2tpdCBpbXBvcnQgb3V0cHV0c19mb3IKICAgICAgICAgICAgcm9sZT1kYi5leGVjdXRlKCdTRUxFQ1QgdW5pdF9jbGFzcyBGUk9NIGNoYXJhY3RlcnMgV0hFUkUgdWlkPT8nLChvd25lciwpKS5mZXRjaG9uZSgpCiAgICAgICAgICAgIGlmIHJvbGUgaXMgTm9uZTpyYWlzZSBWYWx1ZUVycm9yKCdHcm93aW5nIGtpdCBvd25lciBtaXNzaW5nJykKICAgICAgICAgICAga2l0X291dHB1dHM9b3V0cHV0c19mb3Iocm9sZVswXSkKICAgICAgICBvbGQ9X3ByZXZpb3VzKGRiLG9wZXJhdGlvbixkaWdlc3QpO2JlZm9yZT1sb2FkX2l0ZW1zKGRiLG93bmVyKTtiYWxhbmNlPWJhbGFuY2VzKGRiLG93bmVyKQogICAgICAgIGlmIG9sZCBpcyBub3QgTm9uZToKICAgICAgICAgICAgZXZlbnRzPV91cGRhdGVzKGN1cnJlbnRfY2hhbmdlcyhkYixvcGVyYXRpb24sb3duZXIsMHgxOTYsb2xkLGJlZm9yZSkpK3Jlc3VsdChiYWxhbmNlWydlZCddKQogICAgICAgICAgICBpZiBndWFyZGVkOgogICAgICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICAgICAgICAgICAgICAgIGZvciBldmVudCBpbiBldmVudHM6ZW5jb2RlX2V2ZW50KGV2ZW50KQogICAgICAgICAgICAgICAgX2xlZ2FjeV9hY3RvcihkYixvd25lcixhY2NvdW50X2lkLHByZXBhcmUpCiAgICAgICAgICAgIHJldHVybiBldmVudHMKICAgICAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZT09NzIyNTMxOnJhaXNlIFZhbHVlRXJyb3IoJ1NlbGVjdGlvbjcyMjUzMSBuZXcgb3BlcmF0aW9ucyBwYXVzZWQgaW4gcmVhZGVyLXByZXNlcnZpbmcgQ291bnQxIHJlY292ZXJ5JykKICAgICAgICBpdGVtPW5leHQoKGkgZm9yIGkgaW4gYmVmb3JlIGlmIGlbJ3VpZCddPT1yZXF1ZXN0LnVpZCksTm9uZSkKICAgICAgICBpZiBpdGVtIGlzIE5vbmUgb3IgaXRlbVsndGVtcGxhdGUnXSE9ZXhwZWN0ZWRfdGVtcGxhdGUgb3IgaXRlbVsnZ3JvdXAnXSE9cm93LmdldCgnZ3JvdXAnLDQpOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdGaXhlZCBjdWJlIGRvZXMgbm90IG1hdGNoIG93bmVkIHByZXZpZXdlZCBpbnN0YW5jZScpCiAgICAgICAgcmVxdWlyZV9jdXJyZW50KGl0ZW0pO3JlcXVpcmVfdW5sb2NrZWQoaXRlbSkKICAgICAgICBpZiBiYWxhbmNlWydyZXZpc2lvbiddPj0yKio2My0xOnJhaXNlIFZhbHVlRXJyb3IoJ0ZpeGVkIGN1YmUgcmV2aXNpb24gb3ZlcmZsb3cnKQogICAgICAgIGlmIGxlZ2FjeToKICAgICAgICAgICAgcm9sZT1kYi5leGVjdXRlKCdTRUxFQ1QgdW5pdF90eXBlLHVuaXRfY2xhc3MgRlJPTSBjaGFyYWN0ZXJzIFdIRVJFIHVpZD0/Jywob3duZXIsKSkuZmV0Y2hvbmUoKQogICAgICAgICAgICBpZiByb2xlIGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignTGVnYWN5IGN1YmUgb3duZXIgbWlzc2luZycpCiAgICAgICAgICAgIHJvdz1wb29sX2Zvcihyb3csKnJvbGUpCiAgICAgICAgaWYgcm93LmdldCgncmFuZG9tJyk6CiAgICAgICAgICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4ucmVnaW9uYWxfYm9zc19jdWJlcyBpbXBvcnQgZHJhdwogICAgICAgICAgICBvdXRwdXQ9ZHJhdyhyb3cscmFuZGJlbG93KDEwMDAwKSkKICAgICAgICBvd25lZF9vdXRwdXRzPU5vbmUKICAgICAgICBpZiBvd25lZF9yZXdhcmQ6CiAgICAgICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLnNlYWxfcXVlc3RzIGltcG9ydCBsb2FkX2NoYXJhY3RlcgogICAgICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLm93bmVkX3Jld2FyZF9ib3hlcyBpbXBvcnQgc2VsZWN0ZWRfb3V0cHV0cyxwbGFuX2ZvcixEQVRBX1NIQQogICAgICAgICAgICBjaGFyYWN0ZXI9bG9hZF9jaGFyYWN0ZXIoZGIsb3duZXIsYWNjb3VudF9pZCkKICAgICAgICAgICAgb3duZWRfb3V0cHV0cz1zZWxlY3RlZF9vdXRwdXRzKGV4cGVjdGVkX3RlbXBsYXRlLGNoYXJhY3RlcixyZXF1ZXN0LmNob2ljZXMpCiAgICAgICAgICAgIGlmIGl0ZW0uZ2V0KCdzZWFsZWQnLEZhbHNlKTpyYWlzZSBWYWx1ZUVycm9yKCdVbnNlYWwgb3duZWQgcmV3YXJkIGJveCBiZWZvcmUgb3BlbmluZycpCiAgICAgICAgcmVnaW9uYWxfc291cmNlPU5vbmUKICAgICAgICBpZiBsZWdhY3k6CiAgICAgICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLnJlZ2lvbmFsX2Jvc3NfY3ViZV9zb3VyY2UgaW1wb3J0IF9Pd25lZEN1YmVTb3VyY2UKICAgICAgICAgICAgcmVnaW9uYWxfc291cmNlPV9Pd25lZEN1YmVTb3VyY2UoZGIsb3duZXIsaXRlbSxvdXRwdXQpCiAgICAgICAgc291cmNlPShpdGVtWydncm91cCddLGl0ZW1bJ3Nsb3QnXSkKICAgICAgICBpZiBpdGVtWydjb3VudCddPT0xOnJlbW92ZShkYixvd25lcixpdGVtKQogICAgICAgIGVsc2U6ZGIuZXhlY3V0ZSgnVVBEQVRFIGludmVudG9yeV9pdGVtcyBTRVQgY291bnQ9Y291bnQtMSBXSEVSRSB1aWQ9PyBBTkQgb3duZXI9PycsKGl0ZW1bJ3VpZCddLG93bmVyKSkKICAgICAgICBpZiByZWdpb25hbF9zb3VyY2UgaXMgbm90IE5vbmU6cmVnaW9uYWxfc291cmNlLmRlYml0X2NvbXBsZXRlKCkKICAgICAgICBvdXRwdXRzPW93bmVkX291dHB1dHMgaWYgb3duZWRfcmV3YXJkIGVsc2Uga2l0X291dHB1dHMgaWYgZ3Jvd2luZyBlbHNlKG91dHB1dCwpCiAgICAgICAgcGxhbj1bXQogICAgICAgIGlmIG5vdCBvd25lZF9yZXdhcmQ6CiAgICAgICAgICAgIGZvciBzZWxlY3RlZCBpbiBvdXRwdXRzOgogICAgICAgICAgICAgICAgcXVhbnRpdHk9c2VsZWN0ZWRbJ3F1YW50aXR5J10KICAgICAgICAgICAgICAgIHdoaWxlIHF1YW50aXR5OgogICAgICAgICAgICAgICAgICAgIGRlbHRhPW1pbihxdWFudGl0eSw5OSk7cXVhbnRpdHktPWRlbHRhCiAgICAgICAgICAgICAgICAgICAgcGxhbi5hcHBlbmQoZGljdCh0ZW1wbGF0ZT1zZWxlY3RlZFsndGVtcGxhdGUnXSxtZXRhZGF0YT1WRVJJRklFRF9URU1QTEFURVNbc2VsZWN0ZWRbJ3RlbXBsYXRlJ11dLAogICAgICAgICAgICAgICAgICAgICAgICBncm91cD1URU1QTEFURV9CQUdfR1JPVVBTW3NlbGVjdGVkWyd0ZW1wbGF0ZSddXSxxdWFudGl0eT1kZWx0YSkpCiAgICAgICAgICAgICAgICAgICAgaWYgZ3Jvd2luZzpwbGFuWy0xXVsnZW5oYW5jZW1lbnQnXT1zZWxlY3RlZFsnZW5oYW5jZW1lbnQnXQogICAgICAgIHJld2FyZF9zb3VyY2U9Tm9uZQogICAgICAgIGlmIG93bmVkX3Jld2FyZDoKICAgICAgICAgICAgaW1wb3J0IHRpbWUsdXVpZAogICAgICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJhaWRfcmV3YXJkX2l0ZW1zIGltcG9ydCBfaXNzdWVfc291cmNlCiAgICAgICAgICAgIGVwb2NoPWludCh0aW1lLnRpbWUoKSk7cGxhbj1wbGFuX2ZvcihleHBlY3RlZF90ZW1wbGF0ZSxjaGFyYWN0ZXIscmVxdWVzdC5jaG9pY2VzLGVwb2NoKQogICAgICAgICAgICBpZGVudGl0eT1kaWN0KHBvbGljeT0nb3duZWQtcmV3YXJkLWJveGVzLTIwMjYxMDMxLXYxJyxkZWZpbml0aW9uX3NoYTI1Nj1EQVRBX1NIQSwKICAgICAgICAgICAgICAgIHRlbXBsYXRlPWV4cGVjdGVkX3RlbXBsYXRlLG93bmVyPW93bmVyLHVpZD1pdGVtWyd1aWQnXSxjaGFyYWN0ZXI9Y2hhcmFjdGVyLGNob2ljZXM9bGlzdChyZXF1ZXN0LmNob2ljZXMpLGVwb2NoPWVwb2NoKQogICAgICAgICAgICBkZWYgYXV0aG9yaXplKGRiKToKICAgICAgICAgICAgICAgIF9sZWdhY3lfYWN0b3IoZGIsb3duZXIsYWNjb3VudF9pZCxwcmVwYXJlKQogICAgICAgICAgICAgICAgcmV0dXJuIFRydWUKICAgICAgICAgICAgcmV3YXJkX3NvdXJjZT1faXNzdWVfc291cmNlKGRiLG93bmVyLHN0cih1dWlkLnV1aWQ1KHV1aWQuTkFNRVNQQUNFX1VSTCwnb3duZWQtYm94Oicrb3BlcmF0aW9uKSksJ2JveCcsaWRlbnRpdHkscGxhbixhdXRob3JpemUpCiAgICAgICAgaWYgcm93LmdldCgnc2VjcmV0X2ZyYWdtZW50X2JveCcpOgogICAgICAgICAgICAjIFNhbWUgZXhhY3Qgb3duZWQtYm94IGRlYml0IGFuZCBmYWN0b3J5IGF1dGhvcml0eSB1c2VkIGJ5IGN1cnJlbnQKICAgICAgICAgICAgIyByZXdhcmQgYm94ZXM7IHRoaXMgZG9lcyBub3QgZ2xvYmFsbHkgcmVvcGVuIGNvbXBhdGliaWxpdHkgZ2Vhci4KICAgICAgICAgICAgaW1wb3J0IHV1aWQKICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5yYWlkX3Jld2FyZF9pdGVtcyBpbXBvcnQgX2lzc3VlX3NvdXJjZQogICAgICAgICAgICBpZGVudGl0eT1kaWN0KHBvbGljeT1yb3dbJ3BvbGljeSddLHRlbXBsYXRlPWV4cGVjdGVkX3RlbXBsYXRlLG93bmVyPW93bmVyLAogICAgICAgICAgICAgICAgdWlkPWl0ZW1bJ3VpZCddLG91dHB1dD1vdXRwdXQsYm94X2RlYml0PTEpCiAgICAgICAgICAgIGRlZiBzZWNyZXRfZ3VhcmQoZGIpOgogICAgICAgICAgICAgICAgX2xlZ2FjeV9hY3RvcihkYixvd25lcixhY2NvdW50X2lkLHByZXBhcmUpCiAgICAgICAgICAgICAgICByZXR1cm4gVHJ1ZQogICAgICAgICAgICByZXdhcmRfc291cmNlPV9pc3N1ZV9zb3VyY2UoZGIsb3duZXIsc3RyKHV1aWQudXVpZDUodXVpZC5OQU1FU1BBQ0VfVVJMLCdzZWNyZXQtZnJhZ21lbnQtYm94Oicrb3BlcmF0aW9uKSksCiAgICAgICAgICAgICAgICAnYm94JyxpZGVudGl0eSxwbGFuLHNlY3JldF9ndWFyZCkKICAgICAgICBncmFudHM9Z3JhbnRfaXRlbXMoZGIscGxhbixvd25lcixyZWdpb25hbF9jdWJlX3NvdXJjZT1yZWdpb25hbF9zb3VyY2UscmFpZF9yZXdhcmRfc291cmNlPXJld2FyZF9zb3VyY2UpCiAgICAgICAgaWYgb3duZWRfcmV3YXJkOgogICAgICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLm93bmVkX3Jld2FyZF9ib3hlcyBpbXBvcnQgZmluYWxpemVfZ3JhbnRzCiAgICAgICAgICAgIGZpbmFsaXplX2dyYW50cyhkYixvd25lcixncmFudHMsb3V0cHV0cykKICAgICAgICBhZnRlcj1sb2FkX2l0ZW1zKGRiLG93bmVyKTtjdXJyZW50PXsoaVsnZ3JvdXAnXSxpWydzbG90J10pOmkgZm9yIGkgaW4gYWZ0ZXJ9CiAgICAgICAgcG9zaXRpb25zPXNvcnRlZCh7c291cmNlLCpbKGlbJ2dyb3VwJ10saVsnc2xvdCddKSBmb3IgaSBpbiBncmFudHNdfSkKICAgICAgICBldmVudHM9cmVzdWx0KGJhbGFuY2VbJ2VkJ10sWyhwLGN1cnJlbnQuZ2V0KHApKSBmb3IgcCBpbiBwb3NpdGlvbnNdLFsoc2VsZWN0ZWRbJ3RlbXBsYXRlJ10sc2VsZWN0ZWRbJ3F1YW50aXR5J10pZm9yIHNlbGVjdGVkIGluIG91dHB1dHNdKQogICAgICAgIGlmIGdyb3dpbmcgb3IgZ3VhcmRlZDoKICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICAgICAgICAgICAgZm9yIGV2ZW50IGluIGV2ZW50czplbmNvZGVfZXZlbnQoZXZlbnQpCiAgICAgICAgZGIuZXhlY3V0ZSgnVVBEQVRFIHJld2FyZF9iYWxhbmNlcyBTRVQgcmV2aXNpb249cmV2aXNpb24rMSBXSEVSRSB1aWQ9PycsKG93bmVyLCkpCiAgICAgICAgX2NvbW1pdChkYixvcGVyYXRpb24sZGlnZXN0LG93bmVyLDB4MTk2LHBvc2l0aW9ucyxiZWZvcmUsYWZ0ZXIpCiAgICAgICAgaWYgZ3VhcmRlZDpfbGVnYWN5X2FjdG9yKGRiLG93bmVyLGFjY291bnRfaWQscHJlcGFyZSkKICAgICAgICByZXR1cm4gZXZlbnRzCg=='}}

def repair_guard_payloads():
    import base64
    expected = {'els_server/storage/relationships.py','els_server/storage/couple_closures.py','els_server/storage/identification_ui.py','els_server/storage/fixed_cubes.py'}
    need(isinstance(REPAIR_RECOVERY_GUARD_PAYLOADS,dict) and set(REPAIR_RECOVERY_GUARD_PAYLOADS)==expected,
         'Exact four Repair recovery guard bindings pending')
    result={}
    for name,row in REPAIR_RECOVERY_GUARD_PAYLOADS.items():
        raw=base64.b64decode(row['base64'],validate=True)
        need(len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'Repair guard byte binding differs')
        result[name]=raw
    return result

def repair_database_paths(workspace):
    return [workspace/'state/integrated.sqlite3',workspace/'state/friends/accounts.sqlite3']

def repair_database_state(workspace):
    result={}
    for path in repair_database_paths(workspace):
        no_links(path)
        result[str(path)]={'exists':path.exists(),'typed_sha256':managed_database_snapshot(path)if path.exists()else None}
    return result

def repair_writer_barriers(root,workspace,stack):
    # Both original SaveLease paths are held even for absent stores. SQLite is
    # opened only for an existing store; observation never creates a player DB.
    import sqlite3
    from contextlib import closing
    ns={};exec(compile((root/'els_server/storage/lifecycle.py').read_bytes(),'<installed Repair recovery SaveLease>','exec'),ns)
    for path in repair_database_paths(workspace):
        no_links(path);stack.enter_context(ns['SaveLease'](path))
        if path.exists():
            connection=stack.enter_context(closing(sqlite3.connect(path,timeout=3)))
            connection.execute('BEGIN IMMEDIATE');stack.callback(connection.rollback)

def repair_original_restore_allowed(j,current_state):
    # Missing/old journal fields are not an authorization to restore old code.
    before=j.get('repair_database_before')
    return(j.get('repair_recovery_schema')==1 and j.get('repair_writer_admission_opened')is False
           and j.get('repair_guarded_candidate')is None
           and isinstance(before,dict) and len(before)==2 and before==current_state)

def repair_guarded_documents(workspace,metadata,commit,new_rows,formal,additions,token):
    need(re.fullmatch('[a-f0-9]{32}',token or '')is not None,'Invalid Repair recovery token')
    need(len(new_rows)==1880 and len(formal)==1342,'Recovery requires the complete signedLOCAL/C3 source')
    docs,installed,pointer=generated_documents(workspace,metadata,commit,new_rows,formal,additions)
    guarded=metadata['release']+'-guarded-'+token[:12]
    guards=repair_guard_payloads()
    for name,raw in guards.items():
        need(name in formal and name in installed,'Guard is not a complete C3 source member')
        installed[name]={'path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    marker=json.loads(docs['local-first-run.json']);marker['release']=guarded
    docs['local-first-run.json']=encoded(marker)
    installed['local-first-run.json']={'path':'local-first-run.json','size':len(docs['local-first-run.json']),'sha256':hashlib.sha256(docs['local-first-run.json']).hexdigest()}
    flags=dict(recovery_only=True,compatible_read_only=False,complete_C3_reader_and_data=True,all_three_guards=True,
               selection_reader_compatible_recovery=True,all_five_selection_readers_retained=True,new_722531_operations_paused=True,
               original_parent_code=False,player_database_restore=False,guarded_paths=sorted(guards),
               source_binding_sha256=REPAIR_SOURCE_SET,source_business_files=1342)
    business=json.loads(docs['local-business-manifest.json']);business.update(flags,release=guarded,
        files=[installed[name]for name in sorted(set(formal)|additions)])
    docs['local-business-manifest.json']=encoded(business)
    business_hash=hashlib.sha256(docs['local-business-manifest.json']).hexdigest()
    docs['client-bundle-manifest.json']=encoded(dict(release=guarded,channel='local',files=[installed[name]for name in sorted(installed)],**flags))
    docs['release-snapshot.json']=encoded(dict(release=guarded,channel='local',status='Repair-compatible-guarded-recovery-only',
        repository_commit=commit,local_business_manifest_sha256=business_hash,fresh_save_imported=False,**flags))
    pointer.update(flags,release=guarded,path='releases/local/'+guarded,manifest_sha256=business_hash,
        verified=False,first_initialization=False,recovery_of=metadata['release'],recovery_observation_complete=False)
    need(len(installed)==1879,'Signed LOCAL recovery must retain generated config and marker')
    return docs,installed,pointer,guards

def repair_guarded_tree(runtime,workspace,metadata,new_rows,formal,additions,j,u):
    commit=(j.get('candidate')or{}).get('repository_commit')or j['target']
    docs,installed,pointer,guards=repair_guarded_documents(workspace,metadata,commit,new_rows,formal,additions,j['token'])
    target=under(workspace,pointer['path'])
    if not target.exists():
        need(shutil.disk_usage(workspace).free>sum(r['size']for r in installed.values())+512*1024*1024,'Insufficient space for complete compatible recovery')
        stage=Path(tempfile.mkdtemp(prefix='.repair-guarded-',dir=target.parent))
        j['repair_guard_stage']=str(stage);u.atomic(Path(j['journal']),j)
        for name,row in new_rows.items():
            verify(runtime,row);dst=under(stage,name);dst.parent.mkdir(parents=True,exist_ok=True)
            if name in guards:write_new(dst,guards[name])
            else:shutil.copyfile(under(runtime,name),dst)
        for name,raw in docs.items():
            dst=under(stage,name);dst.parent.mkdir(parents=True,exist_ok=True);write_new(dst,raw)
        managed_verify_tree(stage,installed,docs)
        need(not target.exists(),'Recovery target appeared');stage.rename(target)
    managed_verify_tree(target,installed,docs)
    return target,pointer,docs,installed

def repair_stop_writers(workspace,j,u,psutil,old,target):
    # A restart can create its Popen and fail before returning its identity.
    # Discover only canonical, exact installed roots through the mature normal
    # stop contract; unknown argv, a foreign listener or a live lease refuses.
    op=Path(j['journal']).parent
    roots=[old['root']]
    if target.exists()and target not in roots:roots.append(target)
    if j.get('repair_guarded_candidate'):
        root=under(workspace,j['repair_guarded_candidate']['path'])
        if root.exists()and root not in roots:roots.append(root)
    for index,root in enumerate(roots):
        stop=op/('repair-stop-'+str(index)+'-'+uuid.uuid4().hex);stop.mkdir()
        u.stop_owned(root,workspace,psutil,stop)
    doc,_,_=u.config_paths(old['root'],workspace);u.port_idle(doc['port']);u.idle(psutil)

def repair_settle_failure(runtime,workspace,metadata,new_rows,formal,additions,j,old,u,psutil,old_service,
                          observation_seconds=120,interrupted=False,fault=None):
    from contextlib import ExitStack
    current_path=workspace/'releases/local/current.json';current=read(current_path)
    allowed=[j['parent']]+[p for p in(j.get('candidate'),j.get('repair_guarded_candidate'))if p is not None]
    need(current in allowed,'Foreign current prevents Repair recovery; no code or DB restored')
    j['repair_safe_to_release']=False;u.atomic(Path(j['journal']),j)
    target=under(workspace,(j.get('candidate')or{'path':'releases/local/'+metadata['release']})['path'])
    repair_stop_writers(workspace,j,u,psutil,old,target)
    with ExitStack()as stack:
        repair_writer_barriers(old['root'],workspace,stack)
        state=None
        try:state=repair_database_state(workspace)
        except BaseException:pass # No readable two-store proof means never choose old code.
        if repair_original_restore_allowed(j,state):
            need(read(current_path)==current,'Current moved during parent recovery admission')
            u.atomic(current_path,old['pointer'])
            j.update(phase='interrupted-code-restored'if interrupted else'code-restored',repair_recovery_mode='exact-parent-before-new-writer',repair_safe_to_release=False)
            u.atomic(Path(j['journal']),j)
            area=Path(j['journal']).parent/('parent-observation-'+uuid.uuid4().hex);area.mkdir()
            _,_,save=u.config_paths(old['root'],workspace)
            j['repair_parent_observation']=u.smoke(old['root'],save,area,observation_seconds)
            need(repair_database_state(workspace)==state,'Original DB changed during parent recovery observation')
            managed_verify_tree(old['root'],old['installed'],old['documents'])
        else:
            guarded,pointer,docs,installed=repair_guarded_tree(runtime,workspace,metadata,new_rows,formal,additions,j,u)
            need(read(current_path)==current,'Current moved during guarded recovery admission')
            j['repair_guarded_candidate']=pointer;j['phase']='guarded-ready';u.atomic(Path(j['journal']),j)
            u.atomic(current_path,pointer);j['phase']='guarded-promoted';u.atomic(Path(j['journal']),j)
            # A failure after this point deliberately leaves full C3 plus all
            # three guards selected. Never fall through to the old pointer.
            need(state is not None,'Guarded reader retained; original DB integrity requires review')
            if fault:fault('after-guarded-promotion')
            area=Path(j['journal']).parent/('guarded-observation-'+uuid.uuid4().hex);area.mkdir()
            _,_,save=u.config_paths(guarded,workspace)
            proof=u.smoke(guarded,save,area,observation_seconds)
            need(repair_database_state(workspace)==state,'Original DB changed during guarded observation')
            managed_verify_tree(guarded,installed,docs);need(read(current_path)==pointer,'Guarded pointer changed')
            # Keep the pointer byte-stable for repeated recovery; qualification
            # lives in the separate journal/receipt, not an invented acceptance.
            j.update(phase='guarded-code-preserved',repair_recovery_mode='complete-nine-leaf-four-guards',
                     repair_guarded_observation=proof,repair_safe_to_release=False)
            u.atomic(Path(j['journal']),j)
            u.atomic(Path(j['journal']).parent/'repair-recovery.json',dict(ok=True,guarded=True,root=str(guarded),pointer=pointer,
                observation=proof,original_databases_preserved=True,player_database_restore=False,original_parent_code=False))
            j['repair_safe_to_release']=True;u.atomic(Path(j['journal']),j)
            return 'guarded'
    # Restart the exact original service only after the proven unchanged-store
    # branch and after releasing its SaveLease/SQL barriers.
    restarted=u.restart(old['root'],workspace,old_service,Path(j['journal']).parent)
    repair_require_service_ready(restarted,old['root'],workspace,u,psutil)
    j['repair_safe_to_release']=True;u.atomic(Path(j['journal']),j)
    return 'parent'

def repair_require_service_ready(restarted,root,workspace,u,psutil):
    if not restarted:return
    import socket,time
    doc,_,_=u.config_paths(root,workspace);deadline=time.monotonic()+45
    while True:
        need(psutil.pid_exists(restarted['pid'])and time.monotonic()<deadline,'Recovered original service is not ready')
        try:
            with socket.create_connection(('127.0.0.1',doc['port']),timeout=1)as connection:
                need(bool(connection.recv(64)),'Recovered original service is not ready')
            return
        except OSError:time.sleep(.25)

def repair_publication_locks(workspace,j,u):
    from contextlib import contextmanager
    @contextmanager
    def hold():
        paths=[workspace/'analysis/coordination-20261015'/n for n in('active-publication.lock','publication-record.lock')]
        identity=dict(schema=u.SCHEMA,token=j['token'],pid=os.getpid(),created=j['created'],operation='local-oneclick-updater',journal=j['journal'])
        held={};admitted=False
        try:
            for path in paths:
                no_links(path);path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('x',encoding='utf8')as f:json.dump(identity,f);f.flush();os.fsync(f.fileno())
                held[path]=path.stat().st_ino
            admitted=True;yield
        finally:
            if admitted and j.get('repair_safe_to_release')is True:
                need(read(no_links(Path(j['journal'])))==j and j.get('phase')in('complete','guarded-code-preserved','code-restored','interrupted-code-restored'),
                     'Repair release admission was not durably committed; publication locks retained')
            if not admitted or j.get('repair_safe_to_release')is True:
                for path,inode in held.items():
                    need(path.stat().st_ino==inode and read(path)==identity,'Repair recovery lock owner changed');path.unlink()
    return hold()

def repair_recovery_owner(workspace):
    # The Windows byte-range lock is released by the OS on process death. Its
    # persistent file is not a stale-lock authority and is never unlinked.
    from contextlib import contextmanager
    import msvcrt
    @contextmanager
    def hold():
        path=no_links(workspace/'state/local-updater/repair-recovery-owner.lock')
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_BINARY,0o600)
        locked=False
        try:
            with os.fdopen(fd,'r+b',buffering=0)as handle:
                inode=os.fstat(handle.fileno()).st_ino
                need(path.stat().st_ino==inode and path.stat().st_nlink==1,'Recovery owner lock path changed')
                handle.seek(0)
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);locked=True
                except OSError:raise RuntimeError('Another Repair recovery owns the exclusive OS lock')
                try:
                    handle.seek(0);handle.write(encoded(dict(pid=os.getpid(),token=uuid.uuid4().hex)))
                    handle.truncate();os.fsync(handle.fileno())
                    need(path.stat().st_ino==inode,'Recovery owner lock replaced');yield
                    need(path.stat().st_ino==inode,'Recovery owner lock changed during recovery')
                finally:
                    if locked:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        except BaseException:raise
    return hold()

def repair_managed_recover(runtime,workspace,metadata,new_rows,formal,additions):
    with repair_recovery_owner(workspace):
        return repair_managed_recover_owned(runtime,workspace,metadata,new_rows,formal,additions)

def repair_managed_recover_owned(runtime,workspace,metadata,new_rows,formal,additions):
    contract=managed_policy(metadata,new_rows);u=managed_updater()
    paths=[workspace/'analysis/coordination-20261015'/n for n in('active-publication.lock','publication-record.lock')]
    present=[p for p in paths if p.exists()]
    if not present:return
    inodes={p:p.stat().st_ino for p in present}
    identity=read(no_links(present[0]));need(identity.get('schema')==u.SCHEMA and identity.get('operation')=='local-oneclick-updater'
        and all(read(no_links(p))==identity for p in present),'Foreign Repair recovery lock')
    contract=structure_journal_contract(workspace,u,contract,identity['journal'])
    path,j=managed_journal(workspace,u,contract,identity['journal'])
    need(j.get('repair_recovery_schema')==1 and j['token']==identity['token']and j['created']==identity['created'],'Unknown Repair journal; preserve runtime')
    old=managed_old_state(workspace,contract,j['parent']);psutil=u.psutil_for(old['root']);u.idle(psutil)
    try:need(abs(psutil.Process(identity['pid']).create_time()-identity['created'])>.01,'Repair updater still owns this journal')
    except psutil.NoSuchProcess:pass
    if j.get('candidate'):
        _,_,expected=generated_documents(workspace,metadata,j['candidate']['repository_commit'],new_rows,formal,additions)
        need(j['candidate']==expected,'Unknown Repair normal candidate')
    if j.get('repair_guarded_candidate'):
        commit=(j.get('candidate')or{}).get('repository_commit')or j['target']
        _,_,expected,_=repair_guarded_documents(workspace,metadata,commit,new_rows,formal,additions,j['token'])
        need(j['repair_guarded_candidate']==expected,'Unknown guarded recovery pointer')
    if j['phase']=='complete':
        need(read(workspace/'releases/local/current.json')==j.get('candidate'),'Completed Repair current differs')
        docs,installed,_=generated_documents(workspace,metadata,j['candidate']['repository_commit'],new_rows,formal,additions)
        managed_verify_tree(under(workspace,j['candidate']['path']),installed,docs)
    else:
        stopped=path.parent/'stopped-service.json';old_service=read(stopped)if stopped.exists()else None
        repair_settle_failure(runtime,workspace,metadata,new_rows,formal,additions,j,old,u,psutil,old_service,interrupted=True)
    for p in present:need(p.stat().st_ino==inodes[p]and p.stat().st_nlink==1 and read(no_links(p))==identity,'Repair recovery lock changed');p.unlink()

def repair_recovery_pointer(workspace,metadata):
    p=read(workspace/'releases/local/current.json')
    return(p.get('source_release')==REPAIR_SOURCE_RELEASE and p.get('source_formal_manifest_sha256')==REPAIR_FORMAL
        and p.get('recovery_of')==metadata['release']and p.get('recovery_only')is True)


def managed_upgrade(runtime, workspace, repository, commit, metadata, new_rows, formal, additions,
                    documents, installed_rows, new_pointer, observation_seconds=120, fault=None):
    import time
    from contextlib import ExitStack
    contract = managed_policy(metadata, new_rows)
    need(contract is not None, 'Managed predecessor was not signed')
    contract = structure_select(contract, read(workspace / 'releases/local/current.json'))
    old = managed_old_state(workspace, contract)
    old_bytes = (workspace / 'releases/local/current.json').read_bytes()
    u = managed_updater()
    psutil = u.psutil_for(old['root'])
    u.idle(psutil)
    queue = workspace / 'analysis/user-issues-01a16dd4-20261024-v1/publish-queue-coordination-20261025-v1/status.json'
    need(not queue.exists() or u.read(queue).get('release_queue_open') is True, 'Managed publication queue is closed')
    doc, dbs, save = u.config_paths(old['root'], workspace)
    need(doc.get('state_file') == str(workspace / 'state/integrated.sqlite3'), 'Managed save must retain its original path')
    op = no_links(workspace / 'state/local-updater' / ('managed-' + uuid.uuid4().hex))
    op.mkdir(parents=True)
    journal_path = op / 'journal.json'
    j = dict(schema=u.SCHEMA, kind=MANAGED_KIND, policy_sha256=contract['policy_sha256'], token=uuid.uuid4().hex,
             created=psutil.Process().create_time(), journal=str(journal_path), phase='preparing', parent=old['pointer'],
             repository=str(repository), target=commit, player_database_restore=False,
             repair_recovery_schema=1, repair_writer_admission_opened=False, repair_safe_to_release=False)
    target = under(workspace / 'releases/local', metadata['release'])
    registry = workspace / ('state/local-updater/managed-structure-prepared.json' if structure_target(metadata) else 'state/local-updater/managed-identity-prepared.json')
    if target.exists():
        need(registry.is_file(), 'Existing unowned target preserved')
        registration = u.read(no_links(registry))
        prior_path, prior = managed_journal(workspace, u, contract, registration['journal'])
        need(registration.get('token') == prior['token'], 'Prepared managed target token differs')
        need(prior.get('parent') == old['pointer'] and prior.get('candidate'), 'Prepared managed target owner differs')
        recorded = prior['candidate'].get('repository_commit')
        documents, installed_rows, new_pointer = generated_documents(workspace, metadata, recorded, new_rows, formal, additions)
        need(prior['candidate'] == new_pointer, 'Prepared managed target pointer differs')
        managed_verify_tree(target, installed_rows, documents)
    u.atomic(journal_path, j)
    old_service = restarted = None
    promoted = False
    for name in ('active-publication.lock', 'publication-record.lock'):
        no_links(workspace / 'analysis/coordination-20261015' / name)
    with repair_publication_locks(workspace, j, u):
        try:
            need((workspace / 'releases/local/current.json').read_bytes() == old_bytes, 'Managed current changed before admission')
            git_unchanged(repository, commit)
            u.idle(psutil)
            old_service = u.stop_owned(old['root'], workspace, psutil, op)
            u.port_idle(doc['port'])
            with ExitStack() as stack:
                repair_writer_barriers(old['root'], workspace, stack)
                j['repair_database_before'] = repair_database_state(workspace)
                u.atomic(journal_path, j)
                before = {str(p): managed_database_snapshot(p) for p in dbs}
                original_digest = {str(p): u.dbdigest(p) for p in dbs}
                for p in dbs:
                    u.api_backup(p, op / 'backups' / p.relative_to(workspace))
                (op / 'parent-pointer.raw.json').write_bytes(old_bytes)
                u.atomic(op / 'backup.json', dict(ok=True, existing_database_count=len(dbs), SQLite_API=True,
                                                typed_full_schema_and_rows=before, player_database_restore=False))
                if fault: fault('after-backup')
                if not target.exists():
                    stage = Path(tempfile.mkdtemp(prefix='.managed-stage-', dir=target.parent))
                    j['stage'] = str(stage)
                    u.atomic(journal_path, j)
                    for row in new_rows.values():
                        src = under(runtime, row['path']); verify(runtime, row)
                        dst = under(stage, row['path']); dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(src, dst)
                    for name, data in documents.items():
                        dst = under(stage, name); dst.parent.mkdir(parents=True, exist_ok=True); write_new(dst, data)
                    managed_verify_tree(stage, installed_rows, documents)
                    j.update(phase='ready-to-promote', candidate=new_pointer)
                    u.atomic(journal_path, j); u.atomic(registry, dict(journal=str(journal_path), token=j['token']))
                    need(not target.exists(), 'Managed immutable target appeared')
                    stage.rename(target)
                else:
                    j.update(phase='ready-to-promote', candidate=new_pointer)
                    u.atomic(journal_path, j); u.atomic(registry, dict(journal=str(journal_path), token=j['token']))
                need((target / 'config/server.toml').read_bytes() == old['documents']['config/server.toml'], 'Managed configuration changed')
                managed_verify_tree(target, installed_rows, documents)
                pre = op / 'private-preflight'; pre.mkdir()
                proof = u.smoke(target, save, pre, min(3, observation_seconds))
                need(all(managed_database_snapshot(Path(p)) == v for p, v in before.items()), 'Original DB changed before promotion')
                need((workspace / 'releases/local/current.json').read_bytes() == old_bytes, 'Managed current changed before promotion')
                git_unchanged(repository, commit)
                if fault: fault('before-pointer-write')
                need((workspace / 'releases/local/current.json').read_bytes() == old_bytes, 'Managed current changed at promotion CAS')
                u.atomic(workspace / 'releases/local/current.json', new_pointer); promoted = True
                j['phase'] = 'promoted'; u.atomic(journal_path, j)
                if fault: fault('after-promotion')
                observed = op / 'private-observation'; observed.mkdir()
                proof = u.smoke(target, save, observed, observation_seconds)
                need(all(managed_database_snapshot(Path(p)) == v and u.dbdigest(Path(p)) == original_digest[p]
                         for p, v in before.items()), 'Original DB changed during managed upgrade')
                need(read(workspace / 'releases/local/current.json') == new_pointer, 'Managed current changed during observation')
                managed_verify_tree(target, installed_rows, documents)
                need(repair_database_state(workspace)==j['repair_database_before'], 'Two original stores changed before writer admission')
                j['repair_writer_admission_opened']=True
                u.atomic(journal_path,j) # Durable before either lease or SQL barrier is released.
            if fault: fault('after-writer-admission')
            restarted = u.restart(target, workspace, old_service, op)
            if fault: fault('after-new-service-restart')
            if restarted:
                import socket
                deadline = time.monotonic() + 45
                while True:
                    need(psutil.pid_exists(restarted['pid']) and time.monotonic() < deadline, 'Managed service restart failed')
                    try:
                        with socket.create_connection(('127.0.0.1', doc['port']), timeout=1) as s:
                            need(bool(s.recv(64)), 'Managed service is not ready')
                        break
                    except OSError:
                        time.sleep(.25)
            if fault: fault('before-completion')
            j['phase'] = 'complete'; u.atomic(journal_path, j)
            result = dict(ok=True, workspace=str(workspace), root=str(target), release=metadata['release'], migrated=True,
                          reused=False, existing_databases=len(dbs), observation_seconds=proof['seconds'],
                          original_typed_rows_and_schema_unchanged=True, player_database_restore=False)
            u.atomic(op / 'completion.json', result)
            j['repair_safe_to_release']=True; u.atomic(journal_path,j)
            return result
        except BaseException:
            repair_settle_failure(runtime,workspace,metadata,new_rows,formal,additions,j,old,u,psutil,old_service,
                                  observation_seconds=observation_seconds,fault=fault)
            raise


def initialize(runtime, workspace, repository, commit, runtime_manifest):
    repair_require_bindings()
    runtime, workspace, repository = map(no_links, (runtime, workspace, repository))
    need(all(path == path.resolve() for path in (runtime, workspace, repository)),
         'Noncanonical installation directories are refused')
    need(repository.is_dir() and runtime.is_dir(), 'Runtime or Git repository directory is missing')
    need(re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', commit or '') is not None, 'Invalid pinned Git commit')
    need(workspace == repository / '.runtime-cache' / 'unified-local', 'Unexpected first local workspace')
    need(Path(git(repository, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == repository.resolve(),
         'Select the Git repository root')
    git_unchanged(repository, commit)
    manifest_rows = rows(read(runtime_manifest))
    need('python/python.exe' in manifest_rows and 'local-bootstrap-source.json' in manifest_rows,
         'Signed LOCAL package entry points are missing')
    for index, (path, row) in enumerate(manifest_rows.items(), 1):
        need(not path.casefold().startswith(('state/', 'logs/', 'run/')) and
             path.casefold() not in ('config/server.toml', 'local-first-run.json', 'client-bundle-manifest.json',
                                     'local-business-manifest.json', 'release-snapshot.json'),
             'Signed source package contains machine state or generated manifests')
        need(not path.casefold().endswith(('.sqlite', '.sqlite3', '.db')) or
             path == 'els_server/data/client/catalog.sqlite3', 'Signed source package contains a player database')
        need(not path.casefold().endswith(('.pem', '.key', '.pfx', '.p12', '.env', '.sqlite3-wal', '.sqlite3-shm')),
             'Signed source package contains private machine state')
        verify(runtime, row)
        if index % 100 == 0:
            progress(2 + 10 * index // len(manifest_rows), '正在校验完整本地运行组件…')
    metadata = read(runtime / 'local-bootstrap-source.json')
    need(repair_target(metadata), 'Dedicated repair bootstrap requires exact final repair metadata')
    repair_policy(metadata,manifest_rows)
    if metadata.get('source_release') == STRUCTURE_SOURCE_RELEASE:
        structure_policy(metadata, manifest_rows)
    formal, overrides, additions = source_binding(repository, commit, runtime, manifest_rows, metadata)
    documents, installed_rows, pointer = generated_documents(workspace, metadata, commit,
                                                             manifest_rows, formal, additions)
    progress(35, '已核对签名组件与 Git 本地版本，正在准备独立安装…')
    workspace.mkdir(parents=True, exist_ok=True)
    no_links(workspace)
    with installation_lock(workspace):
        current = workspace / 'releases/local/current.json'
        if current.exists():
            repair_managed_recover(runtime, workspace, metadata, manifest_rows, formal, additions)
            need(not repair_recovery_pointer(workspace,metadata), 'Complete C3 compatible guarded recovery is retained; normal writer admission requires a separately qualified forward repair')
            if managed_is_old(workspace, metadata):
                result = managed_upgrade(runtime, workspace, repository, commit, metadata, manifest_rows, formal,
                                         additions, documents, installed_rows, pointer)
            else:
                result = check_existing(workspace, metadata, manifest_rows, documents)
            git_unchanged(repository, commit)
            return result
        releases = under(workspace, 'releases/local')
        releases.mkdir(parents=True, exist_ok=True)
        target = under(releases, metadata['release'])
        if target.exists():
            # A crash may occur after complete immutable promotion but before
            # publishing current.json. Only an exactly matching complete tree
            # can be adopted; no existing file, configuration or save is changed.
            for name, data in documents.items():
                path = under(target, name)
                need(path.is_file() and path.read_bytes() == data,
                     'An incomplete or changed local installation exists; no files were replaced')
            for row in installed_rows.values():
                verify(target, row)
            git_unchanged(repository, commit)
            atomic_new(current, encoded(pointer))
            return {'ok': True, 'workspace': str(workspace), 'root': str(target),
                    'release': metadata['release'], 'reused': True, 'recovered': True}
        stage = Path(tempfile.mkdtemp(prefix='.first-install-', dir=releases))
        try:
            for index, (path, row) in enumerate(manifest_rows.items(), 1):
                destination = under(stage, path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(under(runtime, path), destination)
                verify(stage, row)
                if index % 100 == 0:
                    progress(35 + 55 * index // len(manifest_rows), '正在安装本地运行组件…')
            for name, data in documents.items():
                write_new(stage / name, data)
            for row in installed_rows.values():
                verify(stage, row)
            git_unchanged(repository, commit)
            need(not current.exists() and not target.exists(), 'Local installation changed concurrently')
            no_links(target)
            stage.rename(target)
            # Exclusive creation never replaces a concurrently published pointer.
            atomic_new(current, encoded(pointer))
            progress(100, '本地版本初始化完成，角色与存档将在首次启动时独立生成。')
            return {'ok': True, 'workspace': str(workspace), 'root': str(target),
                    'release': metadata['release'], 'reused': False}
        finally:
            if stage.exists():
                need(stage.parent == releases and stage.name.startswith('.first-install-'), 'Unsafe cleanup target')
                no_links(stage)
                shutil.rmtree(stage)
            # A promoted immutable runtime is retained on pointer I/O failure for diagnosis.
            # No automatic cleanup ever removes an installed tree or user state.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'workspace', 'repository', 'runtime-manifest', 'result'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args(argv)
    try:
        result = initialize(args.runtime, args.workspace, args.repository, args.commit, args.runtime_manifest)
        code = 0
    except Exception as error:
        result = {'ok': False, 'error': str(error), 'player_database_imported': False}
        code = 2
    # The caller chooses a new private result path; never replace another invocation.
    write_new(args.result, encoded(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
