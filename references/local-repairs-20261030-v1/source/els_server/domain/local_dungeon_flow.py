"""Local dungeon-flow supplements; every rule is opt-in through config.

Why this exists
---------------
``DungeonRun.condition_ready`` implements the client's part transition table.
For ``kind == 3`` it collects every actor whose template appears in the
condition's ``required`` list and demands that *all* of them are dead.

Some maps list a SMALLGATE script object there instead of a combat actor. In
``dungeon_besma_dragon_nest_expert.lua`` the final parts of stage 0 and stage 1
require template 145 (the dragon-nest door), which the graph declares as::

    {"template": 145, "active": false, "no_drop": true, "ally": false, "team": 1}

That is the same shape ``kind == 0`` deliberately excludes from its clear check
(``if n['active'] and n.get('team',1)!=0``). Requiring the death of an actor the
rest of the model treats as non-combat is self-contradictory: the door never
reports a retirement, ``poll_ready()`` stays false, ``periodic()`` never sets
``part_end_notified``, and the client's 0xbb request is dropped. The player
clears the room and the portal never opens.

The ``kind == 1`` key_code conditions have the same trap. In
``dungeon_altera_nasod_factory_expert.lua`` (纳斯德生产基地) the final parts of
stage 0 and stage 1 require ``key_code 1``, which the graph assigns to template
156 (``SMALLGATE_BESMA_AIR_SHIP``) declared exactly like the dragon-nest door.
The map script destroys the door itself when its 小boss dies; the server-side
condition then waits forever for a combat death that never happens.

What the relaxation does
------------------------
A ``kind == 3`` condition is also satisfied when *all* of these hold:

* the switch ``script_gate_relaxation`` is on,
* every required template in this room is an inactive script object
  (``active`` false, ``no_drop`` true, ``ally`` false, ``team`` 1),
* the room declares at least one active hostile and every one of them is dead.

The same holds for a ``kind == 1`` condition whose ``required`` key_codes match
only such script objects. Combat-shaped requirements (``active`` true) are never
relaxed, so a map that really does want a living monster killed still has to
kill it.

Scene objects pinned by source
------------------------------
A class-100 door is inert, so ``script_door`` recognises it by shape. 厄泰拉核心
(30302) stage 2 part 0 needs a different treatment: its only actor is template
343 (``NUI_PD_MONSTER``), declared ``active=true / gage=true / no_drop=false /
key_code=1`` with 9225 hp - combat-shaped, but from ``class_id 103`` with
``IS_NPC`` true, the same scene-object family as the Lithia Memory2 flowers
(template 9323). Those flowers proved that such an actor leaves the scene
through the native flag-255 retirement, which the generic combat path discards
before it can reach ``run.defeated``. ``PD_Monster.lua`` is used nowhere else in
the pinned graph set, and its single appearance is exactly this boss gate, so
the room's only exit condition can never be satisfied from a combat report.

``scene_object_gate`` therefore waives a requirement only for an actor matching
one finite ``SCENE_OBJECT_SOURCES`` row: dungeon, stage, part, the whole
declared source row, the graph's ``source_sha256``, the script name pinned in
the route manifest, and the native ``class_id`` / ``IS_NPC`` identity. Every
other hostile in the room still has to die, and no other map, stage, part or
template is admitted.

Part markers in 尼格摩尔 (Devildom2)
------------------------------------
Four of the five Devildom2 routes close a part with a ``kind == 3`` condition
whose template is a class-103 ``IS_NPC`` script marker (``*_END`` / ``*_CLEAR``
/ ``*_START``) rather than a monster: 34340 ``Dungeon_Devildom2_Residence``
stage0 part1 (7587, ``DEVILDOM2_RESIDENCE_STAGE1_START.lua``), 34350
``Dungeon_Devildom2_Factory`` stage0 part0 (7568) and stage1 part0 (7570, plus
the 7553 boss-event marker), 34360 ``Dungeon_Devildom2_Portal`` stage1 part0
(7605) and stage2 part0 (7607). The client retires these markers inside its own
scene: the runtime capture of 34340 (session 20261029-215610) shows the marker
created at the part load and destroyed without a single 0xad report, followed by
a 0xb8 portal request the server answered with -1. The part's only actor is that
marker, so ``script_gate`` (which needs one live hostile) cannot open it either,
and the exit never opens.

34360 stage 0 part 0 is the same shape one layer out: its condition names the
real boss 7593, but the room also declares the ``_STAGE0_END`` marker 7603 as
``active``/``no_drop``, so the 0xb8 check would keep the gate shut after the
boss dies. That room is pinned with ``required`` untouched: only the marker is
waived, the boss still has to be killed.

``part_marker_gate`` waives only the pinned markers of one room. The condition's
``required`` list must equal the row's, every matched actor must re-verify
against the whole declared source row, the graph ``source_sha256`` and the
script sha in the route manifest, and the native identity must stay class-103
``IS_NPC``. Every other living actor of the room still has to die, so a real
boss or mob is never skipped: 34340 stage1, 34350 stage1's boss 7551 and
34360 stage0's boss 7593 keep their combat requirement.

Disable any rule by setting its switch false or deleting the config.
"""
import functools
import json

from els_server.paths import PROJECT_ROOT

CONFIG = PROJECT_ROOT / 'config/local_dungeon_flow.json'


@functools.lru_cache(maxsize=1)
def rules():
    try:
        rule = json.loads(CONFIG.read_bytes())
    except FileNotFoundError:
        return {'script_gate_relaxation': False, 'scene_object_exit': False,
                'part_marker_relaxation': False}
    if rule.get('schema_version') != 1 or rule.get('provenance') != 'local_dungeon_flow':
        raise ValueError('Local dungeon flow identity')
    switches = {}
    for name in ('script_gate_relaxation', 'scene_object_exit', 'part_marker_relaxation'):
        switch = rule.get(name, False)
        if type(switch) is not bool:
            raise ValueError('Local dungeon flow switch')
        switches[name] = switch
    return switches


def script_gate_relaxation():
    return rules()['script_gate_relaxation']


def scene_object_exit():
    return rules()['scene_object_exit']


def part_marker_relaxation():
    return rules()['part_marker_relaxation']


# Finite source-pinned admissions. A row waives exactly one declared actor.
SCENE_OBJECT_SOURCES = (
    {
        'identity': 30302, 'stage': 2, 'part': 0,
        'graph_sha': '92fb9a602537def90092736f0403c60aefa3cee613a3947cbc67a4422f8b8b15',
        'script': 'PD_Monster.lua',
        'script_sha': '7d7d9b099e03007f3c9a4f90bad0beb3994b07fa0d216dc894423e10433b233f',
        'class_id': 103,
        'source': {'template': 343, 'source_index': 1, 'points': [4], 'active': True,
                   'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                   'boss': False, 'boss_lines': 1, 'key_code': 1, 'source_key_code': 1,
                   'rate': 100, 'offset': [0, 0, 0]},
    },
)


def script_door(n):
    """The exact non-combat door shape kind 0 already excludes from clears."""
    return not n['active'] and not n.get('ally') and n.get('no_drop') and n.get('team', 1) == 1


def _room_clear(npcs, dead):
    live = [n for n in npcs if n['active'] and n.get('team', 1) != 0]
    return bool(live) and all(n['key'] in dead for n in live)


def script_gate(npcs, dead, required):
    """True when the required templates are script doors and the room is clear."""
    if not script_gate_relaxation():
        return False
    gates = [n for n in npcs if n['template'] in required]
    if not gates:
        return False
    # Only script-owned doors. A combat actor must still be killed.
    if not all(script_door(n) for n in gates):
        return False
    return _room_clear(npcs, dead)


def key_code_gate(npcs, dead, required):
    """True when the required key_codes match only script doors and the room is clear."""
    if not script_gate_relaxation():
        return False
    gates = [n for n in npcs if n['key_code'] in required]
    if not gates:
        return False
    if not all(script_door(n) for n in gates):
        return False
    return _room_clear(npcs, dead)


def scene_object_npc(run, npc):
    """True for the one source-pinned scene object this part admits."""
    if not scene_object_exit():
        return False
    row = next((r for r in SCENE_OBJECT_SOURCES if (r['identity'], r['stage'], r['part'])
                == (run.identity, run.stage, run.part)), None)
    if row is None:
        return False
    source = row['source']
    if (any(npc.get(k) != v for k, v in source.items() if k != 'active')
            or npc.get('start_point') != source['points'][0]):
        return False
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)
            or run.catalog.manifest['source_sha256'].get(row['script']) != row['script_sha']):
        return False
    from els_server.game_data import client_data
    native = client_data().npc(source['template'])
    return native['class_id'] == row['class_id'] and native['is_npc'] is True


def scene_object_gate(run, npcs, dead, matched):
    """True when the unmet requirements are pinned scene objects and the room is clear.

    The client owns the scene these objects leave, so the server stops waiting for
    a combat report it cannot receive. Real hostiles in the same room are still
    required to die.
    """
    if not matched or not all(scene_object_npc(run, n) for n in matched):
        return False
    live = [n for n in npcs if n['active'] and n.get('team', 1) != 0
            and not scene_object_npc(run, n)]
    return all(n['key'] in dead for n in live)


# Finite source-pinned rooms. ``markers`` is every script marker the room
# declares, including the required one; anything else alive still has to die.
PART_MARKERS = {
    (34340, 0, 1): {
        'graph_sha': 'e0995cf9f2274bbb9b763fb384c46062ea87915428d4dca313c03d5fc4ecb3e1',
        'required': (7587,),
        'markers': (
            {'script': 'DEVILDOM2_RESIDENCE_STAGE1_START.lua',
             'script_sha': '72664ed1e03b4c3a049f85a603f2a2e6680cbaa845dc681ccdb842291d9ca0dd',
             'source': {'template': 7587, 'source_index': 1, 'points': [10], 'active': False,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    (34350, 0, 0): {
        'graph_sha': 'da42ed2edc201421e8d6a0ecaaf4ade75217b4785c08ff010a0850c81da6d6c0',
        'required': (7568,),
        'markers': (
            {'script': 'DEVILDOM2_FACTORY_STAGE0_CLEAR.lua',
             'script_sha': '016d3153978e98ef72eef076ed79b44d321a9cc7d6012328cf716a09e70fe0e9',
             'source': {'template': 7568, 'source_index': 1, 'points': [1], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    (34350, 1, 0): {
        'graph_sha': 'da42ed2edc201421e8d6a0ecaaf4ade75217b4785c08ff010a0850c81da6d6c0',
        'required': (7570,),
        'markers': (
            {'script': 'DEVILDOM2_FACTORY_STAGE1_DUMMY.lua',
             'script_sha': '5f364676772e514ca350cbe3ecf97f2293ab726f4a19fbfa573c13cedc25d006',
             'source': {'template': 7570, 'source_index': 4, 'points': [1], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM2_FACTORY_BOSS_EVENT.lua',
             'script_sha': '3bce8177ac1368ca77b3a7b013ed6e941f7890317ca840844cf9719ab82849d9',
             'source': {'template': 7553, 'source_index': 3, 'points': [1], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    (34360, 0, 0): {
        'graph_sha': 'e5c9b9d1e6553e2e30a112a0fc06515ec73d02f0fc5bb8d5aa534efde650d214',
        'required': (7593,),
        'markers': (
            {'script': 'DEVILDOM2_PORTAL_STAGE0_END.lua',
             'script_sha': 'd98dbd5ebebde924fd6deffcf17b969f631c654f6bd67d80e83ffd2370c12ed7',
             'source': {'template': 7603, 'source_index': 22, 'points': [29], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    (34360, 1, 0): {
        'graph_sha': 'e5c9b9d1e6553e2e30a112a0fc06515ec73d02f0fc5bb8d5aa534efde650d214',
        'required': (7605,),
        'markers': (
            {'script': 'DEVILDOM2_PORTAL_STAGE1_END.lua',
             'script_sha': 'ea902683f4c16a78f2e3e41dee9fad9b294ce9fd1688a11393034de364df157b',
             'source': {'template': 7605, 'source_index': 17, 'points': [58], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    (34360, 2, 0): {
        'graph_sha': 'e5c9b9d1e6553e2e30a112a0fc06515ec73d02f0fc5bb8d5aa534efde650d214',
        'required': (7607,),
        'markers': (
            {'script': 'DEVILDOM2_PORTAL_STAGE2_END.lua',
             'script_sha': '847a32b2a5436f9c50e527f84cd417e4dbb3ef123bd46cda03239db2d43b7b67',
             'source': {'template': 7607, 'source_index': 39, 'points': [1], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
}


def part_marker(run, npc, row):
    """True for a declared marker of this pinned room, verified by source."""
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)):
        return False
    from els_server.game_data import client_data
    for marker in row['markers']:
        source = marker['source']
        if (npc.get('template') != source['template']
                or any(npc.get(k) != v for k, v in source.items() if k != 'active')
                or npc.get('start_point') != source['points'][0]):
            continue
        if run.catalog.manifest['source_sha256'].get(marker['script']) != marker['script_sha']:
            continue
        native = client_data().npc(source['template'])
        if native['class_id'] == 103 and native['is_npc'] is True:
            return True
    return False


def part_marker_npc(run, npc):
    """True for a marker of the pinned room the run currently stands in."""
    if not part_marker_relaxation():
        return False
    row = PART_MARKERS.get((run.identity, run.stage, run.part))
    return row is not None and part_marker(run, npc, row)


def part_marker_gate(run, npcs, dead, required):
    """True when a pinned room's requirement is its own script markers.

    The client retires them inside its own scene, so no combat report exists.
    Every other living actor of the room must still be dead.
    """
    if not part_marker_relaxation():
        return False
    row = PART_MARKERS.get((run.identity, run.stage, run.part))
    if row is None or set(required) != set(row['required']):
        return False
    matched = [n for n in npcs if n['template'] in required]
    if not matched or not all(part_marker(run, n, row) for n in matched):
        return False
    live = [n for n in npcs if n['active'] and n.get('team', 1) != 0
            and not part_marker(run, n, row)]
    return all(n['key'] in dead for n in live)
