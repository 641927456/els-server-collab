"""Finite source retirements for the current Master Road solo rooms.

Each listed room's only exit is a kind-3 condition naming its DROP1 wrapper
(7803 Rosso normal, 7810 Rosso Hell, 7655 Ventus Hell). All of the room's
declared actors are client-scripted Master Road controllers: one class-0 boss
and the remaining class-103 wrappers. The client retires them inside its own
scene with a native flag-255 expiry (source=killer=2**64-1, one zero readiness
entry for the owner, empty contribution/counters), exactly like the Devildom
markers and the Memory8 sentinels.

The generic combat path rejects flag 255 at ``d['flag'] not in (0,1)`` before
it can reach ``run.defeated``, so the wrapper report was dropped and
``condition_ready`` stayed false. The 20261030-153805 session shows the shape
directly for 34390: three 0xad frames of 160 bytes, zero 0xae/0xaf replies, the
boss key-0 HP falling to max/1000 and all five actors destroyed only on leaving.
The 20261030-173830 session shows both sides: 34390 clears on the admitted
key-3 retirement, while 34400's two 160-byte retirement reports get no reply
and no 0xba/0xc1 follows.

This module authenticates only the reports the client already sent for the
declared rows of the listed rooms. It invents no actor, kill, quest, loot or
clear result: the original kind-3 condition and the original portal gate still
decide the part.
"""
import copy
import math
import struct

# Code-first recovery disables only the new admission; keep this reader.
MASTER_ROAD_RETIREMENTS_ENABLED = True
MAX_UID = 2**64 - 1
_WIRE_KEYS = ('script', 'script_sha', 'class_id')


def _row(source):
    return {k: v for k, v in source.items() if k not in _WIRE_KEYS}


# The tables below are byte-for-byte the declared rows of the imported route
# graph, plus the pinned script identity from the route manifest. Only the
# rooms whose client retirement was observed are listed.
ROOMS = {
    34390: {
        'graph_sha': '8da85dcaca627f50d6a5bbacfa06507929f8e358a5be630e02b0f8577869642d',
        'sources': {
            0: {'template': 7800, 'source_index': 1, 'points': [36], 'active': True,
                'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': True, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_BOSS.lua', 'class_id': 0,
                'script_sha': '623b5c779d2b390fd7c5e6b2352a339fb640d6bf3f3cb341b2e9346addd1f8a3'},
            1: {'template': 7801, 'source_index': 2, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_START_EVENT.lua', 'class_id': 103,
                'script_sha': 'f37b8e1fd41898ebb90920e2f7c5b76cb0e2dd0b23785218a62214216cea4991'},
            2: {'template': 7802, 'source_index': 3, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DM.lua', 'class_id': 103,
                'script_sha': '35235a877aa668e43d8e63088fd2d1fedbc7097fc5b4119eb199aa28739b67e1'},
            3: {'template': 7803, 'source_index': 4, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DROP1.lua', 'class_id': 103,
                'script_sha': '1471b2f290381cd34d5ac11009f735d84ccefa6c2162b63a916f946d3c90255e'},
            4: {'template': 7804, 'source_index': 5, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DROP2.lua', 'class_id': 103,
                'script_sha': '110e072302b563c9cc56e82972f4abcf6e130511467d0168913cdcb65f4841a8'},
        },
    },
    34400: {
        'graph_sha': 'd7dadf378781f4872d6f62bb09adfa4d2a0e7b43b3cbbf67c09e93936767e110',
        'sources': {
            0: {'template': 7807, 'source_index': 1, 'points': [36], 'active': True,
                'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': True, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_BOSS_HELL.lua', 'class_id': 0,
                'script_sha': '38a1c32cc105a282809a73fe53d09c1747e908636d9203546139fa43963db66a'},
            1: {'template': 7808, 'source_index': 2, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_START_EVENT_HELL.lua', 'class_id': 103,
                'script_sha': '8e1db9ee4a3e679628d6dba481bd22050683498acd75e94a47ac869b0a618ea4'},
            2: {'template': 7809, 'source_index': 3, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DM_HELL.lua', 'class_id': 103,
                'script_sha': '399b482b0223cb9b51e6ba2e9eb31f2074744b5b577eedc8cd050b48c06d9dcd'},
            3: {'template': 7810, 'source_index': 4, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DROP1_HELL.lua', 'class_id': 103,
                'script_sha': '177e3af87de7ed4b66b087f72a15225df1f9cb2bc674255a8b7b8a8ccdfc814e'},
            4: {'template': 7811, 'source_index': 5, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DROP2_HELL.lua', 'class_id': 103,
                'script_sha': '8bfbc7f2e9cb6e95d6658ab04e7ee0157946fd38f9fd6449c264f92d8d4ad9fc'},
            5: {'template': 7812, 'source_index': 6, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DROP3_HELL.lua', 'class_id': 103,
                'script_sha': 'bfdd8f4275a55a163e5f932ce2da41c800d2b0e322a98ee6517180c796b3ea05'},
            6: {'template': 7815, 'source_index': 7, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_DROP3_HELL.lua', 'class_id': 103,
                'script_sha': 'bfdd8f4275a55a163e5f932ce2da41c800d2b0e322a98ee6517180c796b3ea05'},
            7: {'template': 7813, 'source_index': 8, 'points': [5], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_ROSSO_PHASE2_EVENT_HELL.lua', 'class_id': 103,
                'script_sha': '12e486308f0e8413c59809157e4f0602aebd8ac66e0b3d386096e6f0fb189342'},
        },
    },
    34420: {
        'graph_sha': '93ac0876a5ad462005f157c1c833f7ac8a9920d30cfb869aca8eef1be2210e4b',
        'sources': {
            0: {'template': 7650, 'source_index': 1, 'points': [1], 'active': True,
                'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': True, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_BOSS_HELL.lua', 'class_id': 0,
                'script_sha': '3cc1be45543db179651d9ded73bb79933f7ff64a614dbe1cd3d86f50b88e97d7'},
            1: {'template': 7653, 'source_index': 2, 'points': [4], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_START_EVENT_HELL.lua', 'class_id': 103,
                'script_sha': '49b3a311841e800b2b516240ff730ce25b0b1424baed8d439d5eecb0b39a3526'},
            2: {'template': 7654, 'source_index': 3, 'points': [4], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_DM_HELL.lua', 'class_id': 103,
                'script_sha': 'fc9b4a929f733b80e1c2a8ae0cb52dbe95711ff30b800c481b822622b06879fd'},
            3: {'template': 7655, 'source_index': 4, 'points': [4], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_DROP1_HELL.lua', 'class_id': 103,
                'script_sha': 'ecf7c5c8bd1a392317a63bd1c761cfcf122b6161184fbd29de622142c3adcf6b'},
            4: {'template': 7656, 'source_index': 5, 'points': [4], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_DROP2_HELL.lua', 'class_id': 103,
                'script_sha': '6c8e8aebb1ddda1ee1236fb918ad805bd397cd4e82e12f5833113959d75bcb1e'},
            5: {'template': 7657, 'source_index': 6, 'points': [4], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_DROP3_HELL.lua', 'class_id': 103,
                'script_sha': '0c1debf75ebead293b8d21f53b52fd7bfce08b522f5474d277d7d8867cf78aef'},
            6: {'template': 7659, 'source_index': 7, 'points': [4], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_DROP4_HELL.lua', 'class_id': 103,
                'script_sha': '09431db6022e44ab7ca4d7e39ed24589a9f29b4f828b169287f4711f750f7be0'},
            7: {'template': 7658, 'source_index': 8, 'points': [4], 'active': False,
                'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                'rate': 100, 'offset': [0, 0, 0],
                'script': 'MD_VENTUS_PHASE2_EVENT_HELL.lua', 'class_id': 103,
                'script_sha': '8b3efb1ec63d46d39557870f62ca63f08b070c4e45b08bc1489d412aac611b43'},
        },
    },
}
# Compatibility names for the original Rosso-normal reader/tests.
SOURCES = ROOMS[34390]['sources']
GRAPH_SHA = ROOMS[34390]['graph_sha']


def source_rule(run, npc):
    """Pure identity check for one declared actor; no class-wide alias."""
    if run is None:
        return None
    room = ROOMS.get(run.identity)
    if (room is None or (run.stage, run.part) != (0, 0)
            or npc.get('dynamic') or npc.get('key') not in room['sources']):
        return None
    spec = room['sources'][npc['key']]
    row = _row(spec)
    if (run.graph['source_sha256'] != room['graph_sha']
            or run.graph != run.catalog.graph(run.identity)
            or run.catalog.manifest['source_sha256'].get(spec['script']) != spec['script_sha']
            or any(npc.get(k) != v for k, v in row.items() if k != 'active')
            or npc.get('start_point') != row['points'][0]):
        return None
    groups = run.graph['stages']['0']['parts']['0']['groups']
    declared = [n for g in groups for n in g['npcs'] if n.get('source_index') == row['source_index']]
    if declared != [row]:
        return None
    actors = [n for n in run.current['npcs'] if n.get('key') == npc['key']
              or n.get('template') == row['template'] and n.get('source_index') == row['source_index']]
    if len(actors) != 1 or actors[0] is not npc:
        return None
    from els_server.game_data import client_data
    native = client_data().npc(row['template'])
    if (native['class_id'] != spec['class_id'] or native['script'] != spec['script']
            or native['is_npc'] is not True):
        return None
    from els_server.domain.formal_npc_hp import initialized_maximum
    hp = initialized_maximum(run, row)
    if npc.get('hp') != hp:
        return None
    return dict(source=row, hp=hp)


def handle(s, event, report):
    """Acknowledge only an admitted original retirement, after encoding all replies."""
    if not MASTER_ROAD_RETIREMENTS_ENABLED:
        return None
    run = s.dungeon_run
    if run is None:
        return None
    room = ROOMS.get(run.identity)
    if room is None or (run.stage, run.part) != (0, 0):
        return None
    if report['flag'] != 255 or report['index'] not in room['sources']:
        return None
    actors = [n for n in run.current['npcs'] if n.get('key') == report['index']]
    if len(actors) != 1:
        return []
    npc = actors[0]
    rule = source_rule(run, npc)
    if rule is None:
        return []
    owner = s.account.uid
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    from els_server.domain.summons import valid_sentry_death
    hp = struct.unpack('>f', struct.pack('>I', report['hp_bits']))[0]
    if (event.event_id != 0x202 or event.kind != 0xad or event.performers != (0,)
            or event.uid != MAX_UID or event.target_uid != MAX_UID or event.payload_mode != 0
            or s.role != 'game' or s.phase != 'dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or not current_lease(s)
            or getattr(s, 'reward_transaction', None) is not None
            or getattr(s, 'reward_run_id', None) != run.run_id
            or frozenset(getattr(s, 'dungeon_participants', (owner,))) != frozenset((owner,))
            or not valid_sentry_death(report, owner)
            or any(not math.isfinite(v) or abs(v) > 1e7 for v in report['xyz'])
            # The client clamps a dying gauge boss to max/1000, so the report
            # carries that floor rather than the initialized maximum.
            or not 0 < hp <= rule['hp']):
        return []
    key = npc['key']
    from els_server.domain.dungeon_lifecycle import death_ack, empty_reward_death_notice
    from els_server.protocol.protocol_codec import encode_event
    previous = run.defeated.get(key)
    if previous is not None:
        return [death_ack()] if previous == event.payload else []
    shadow = copy.copy(s)
    shadow.dungeon_run = copy.copy(run)
    shadow.dungeon_clock = copy.copy(s.dungeon_clock)
    shadow.dungeon_run.defeated = {**run.defeated, key: bytes(event.payload)}
    shadow.defeated_npcs = shadow.dungeon_run.defeated
    from els_server.domain.dungeon_flow import periodic
    replies = [death_ack(), empty_reward_death_notice(key, report['killer'])] + periodic(shadow)
    for reply in replies:
        encode_event(reply)
    for name in ('defeated', 'next', 'ready_at'):
        setattr(run, name, getattr(shadow.dungeon_run, name))
    # ``active`` is the part-load spawn flag, not life state: the ordinary
    # combat death path leaves it true, and quest kill events read it.
    s.defeated_npcs = run.defeated
    s.part_end_notified = shadow.part_end_notified
    s.dungeon_clock.total = shadow.dungeon_clock.total
    s.dungeon_clock.started = shadow.dungeon_clock.started
    return replies
