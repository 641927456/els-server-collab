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

Branching rooms
---------------
A room may also use ``kind == 3`` to name its *exits* instead of a monster. In
``Dungeon_Devildom_Side1.lua`` (34710) stage0 part1 declares the three templates
8168/8169/8170 - the ``关卡1/2/3触发对象`` - and stage4 part0 declares 8171/8172
for ``关卡5/6``. All of them are ``active=false`` class-103 ``IS_NPC`` objects,
so the room has no live hostile at all: ``kind == 0`` excludes them from its
clear check, ``kind == 3`` demands their death, and ``script_gate`` needs one
live hostile before it will fire. The client picks the door and retires the
trigger inside its own scene, so no report ever arrives and the run cannot leave
the very first junction. Such a row adds ``exits``: the subset of its pinned
markers this build admits. ``poll_ready`` still takes the first satisfied
condition in source order, so the run enters exactly one branch; the others stay
closed instead of stalling the run.

A pinned boss may also be several actors on one point. 34730 stage2 stacks
8192 (200 gauge lines), the three 巨人之手 8201/8202/8203 (150 each) and the heart
8282 (250) on spawn point 1; the client composites them into a single body and
only the heart ever reports a death. ``boss_core_relaxation`` lets such a room
settle on its heart and waives the body parts from both the clear requirement
and the client's 0xb8 check. The heart itself still has to die.

缇尔诺格 theme park (Devildom4)
-------------------------------
The five routes reachable from the 主题公园入口 reuse both shapes. 34770
stage0/stage3 declare the ``DM_DUMMY`` 8345 as an active hostile and 34800
stage1/stage3 do the same with the ``LEVER_MANAGER_n`` 8399/8400/8401; the
client retires them inside its own scene, and the live run
``9fd8df0c-a40c-40c6-96a7-56aab4c89cf8`` proves it for 34800 (stage1 part0
holds kill records for keys 0-7 only, and the lever manager is key 8). Their
kind3 rooms name class-103 markers instead: 34760 stage3 names 8412
``DROP_DUMMY``, 34770 stage2 names 8345, 34770 stage5 names 8344 ``BOSS_END``
and 34800 stage2 names 8432 ``CLEAR_DUMMY``/8397 ``BOSS_MIDDLE_END``. 34770
stage1 is another junction: 8335/8336/8337 ``STAGE2/3/4_TRIGGER`` lead to
stages 2/3/4, which all reconverge on the stage5 boss. 34780 stage2 closes on
the 8359 script door but declares the class-103 boss hands 8361/8362 as active
hostiles, so ``script_gate`` now receives the pinned stand-ins as dead before
its room-clear check; the real boss 8351 still has to die.

34800 stage2 is the one room whose markers do report: this build ends the
middle-boss scene at a scripted HP threshold, so the client sends the native
flag-255 expiry of 8397/8432 and 8392 never reports a combat death. The row
carries ``retirement``; ``part_marker_retirement`` admits only that pinned
expiry, and the source order then picks 8432 -> stage 3 or 8397 -> stage 4.

34760 stage2 has no declared combat actor at all: it is a summon arena whose
waves arrive through 0x2ce and are recorded with the client's clear flag. Its
pinned row carries ``portal``: the empty fence must not end the part on arrival,
so the room settles only on the client's own 0xb8, exactly like ``kind == 5``.
34790 needs no waiver (160 second timer, then the real boss 8370).

34760 stage0 part1 also declares plain combat monsters (8287/8288/8289) that
the client can retire itself: the two 8288s at points 29/31 only ever send the
native flag-255 expiry DTO, which the combat pipeline drops without a reply, so
the kind==0 fence never clears. ``NATIVE_EXPIRY_ROOMS`` pins that exact room
and its declared non-boss templates; only their initialized-HP native expiry is
recorded, acknowledged and settled. Every other dungeon, room, boss and dynamic
summon stays on the normal rewarded combat path.

34780 puppet theatre stage 0 part 2 (kind == 5)
-----------------------------------------------
The third room of ``Dungeon_Devildom4_Puppet.lua`` closes with ``kind == 5``:
``portal_lines`` 18/19/20/21, ``required`` empty, ``delay`` 3. The server waits
for ``portal_requested``, i.e. the client's own 0xb8 for *this* part. In the live
session 20261031-150518 the client emits one 0xb8 per part, 0.2 s after
``begin_substage``: it is the queued tail of the previous transition, so its
payload is the old part and ``handle`` routes it through the ``late`` path.
Across every recorded session 462/462 0xbb requests follow a server 0xba within
2.5 s, so the client never retries a part end on its own. The seven declared
hostiles died by 07:17:20.690 and no 0xb8 followed for the next 17 minutes: no
0xba, no 0xbb, no part end, no clear, and the player had to quit the map.

``portal_exit`` pins that one room (identity, stage, part, graph sha and the
``Dungeon_Devildom4_Puppet.lua`` sha in the route manifest). Once every declared
live hostile is dead the room settles exactly like a ``kind == 0`` room, so the
client receives its regular 0xba/0xbb part end. No other room, dungeon or part
is admitted, and a living hostile still blocks the fence.

Disable any rule by setting its switch false or deleting the config.
"""
import copy
import functools
import json
import math
import struct

from els_server.paths import PROJECT_ROOT

CONFIG = PROJECT_ROOT / 'config/local_dungeon_flow.json'


@functools.lru_cache(maxsize=1)
def rules():
    try:
        rule = json.loads(CONFIG.read_bytes())
    except FileNotFoundError:
        return {'script_gate_relaxation': False, 'scene_object_exit': False,
                'part_marker_relaxation': False, 'dummy_hostile_relaxation': False,
                'boss_core_relaxation': False, 'summon_activation': False,
                'native_expiry_relaxation': False, 'portal_exit_relaxation': False,
                'inactive_hitbox_omission': False, 'cage_object_relaxation': False,
                'part_audit': False}
    if rule.get('schema_version') != 1 or rule.get('provenance') != 'local_dungeon_flow':
        raise ValueError('Local dungeon flow identity')
    switches = {}
    for name in ('script_gate_relaxation', 'scene_object_exit', 'part_marker_relaxation',
                 'dummy_hostile_relaxation', 'boss_core_relaxation', 'summon_activation',
                 'native_expiry_relaxation', 'portal_exit_relaxation',
                 'inactive_hitbox_omission', 'cage_object_relaxation', 'part_audit'):
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


def dummy_hostile_relaxation():
    return rules()['dummy_hostile_relaxation']


def boss_core_relaxation():
    return rules()['boss_core_relaxation']


def summon_activation():
    return rules()['summon_activation']


def native_expiry_relaxation():
    return rules()['native_expiry_relaxation']


def portal_exit_relaxation():
    return rules()['portal_exit_relaxation']


def inactive_hitbox_omission():
    return rules()['inactive_hitbox_omission']


def cage_object_relaxation():
    return rules()['cage_object_relaxation']


def part_audit():
    return rules()['part_audit']


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


# Pinned active actor that can never satisfy a room clear: either a class-103
# stand-in the client retires inside its own scene (drop table / cutscene
# costume), or a source spawn this client build places outside the playable
# scene so it can never be damaged. Neither ever reaches ``run.defeated``, and
# while the row is declared active it blocks the room's kind==0 "every live
# hostile is dead" condition: the real boss dies but the part never ends - no
# 0xba, no portal, no clear record, no settlement. A room row waives exactly
# the actors listed in ``sources``; every real boss of the same room is still
# required to die.
DUMMY_HOSTILE_SOURCES = (
    {
        'identity': 34720, 'stage': 2, 'part': 0,
        'graph_sha': '3238ea8132e0b1dec4e803f2c8f5970563f748175967416e73a224ba4d0f5c62',
        'sources': (
            {'script': 'DEVILDOM_SIDE2_DROP_DUMMY_BOSS.lua',
             'script_sha': '3129dd26b840746a44eefcd3c08a0c619632603c5392e3ce38fae29178464f53',
             'class_id': 103,
             'source': {'template': 8262, 'source_index': 3, 'points': [5], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 普鲁纳姆外围-普雷加斯的迷宫 (34710) final room: the two 8260 演出马甲
    # stand-ins sit beside the real F_BOSS pair 8155/8156 and never report.
    {
        'identity': 34710, 'stage': 7, 'part': 0,
        'graph_sha': '2211ae6755c22eeb3fde663258faf497831ab045f43b66c21848cb1eafcaba58',
        'sources': (
            {'script': 'DEVILDOM_SIDE1_DROP_DUMMY_MIDDLE.lua',
             'script_sha': 'c1a4527e9b0e184731b55144424d0dcaa96589797c354c4ea6c59028b6f1d788',
             'class_id': 103,
             'source': {'template': 8260, 'source_index': 5, 'points': [1], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM_SIDE1_DROP_DUMMY_MIDDLE.lua',
             'script_sha': 'c1a4527e9b0e184731b55144424d0dcaa96589797c354c4ea6c59028b6f1d788',
             'class_id': 103,
             'source': {'template': 8260, 'source_index': 6, 'points': [1], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 普鲁纳姆外围-普雷加斯的迷宫 (34710) 关卡5 第2段: the map declares six 8162
    # ``DEVILDOM_SIDE1_SPECIAL.lua`` spawns (points 6/7/9/12/14/16). This client
    # build leaves the point-14 instance inside the sealed gate device and never
    # lets the player damage it: in sessions 20261030-233948 and 20261031-105444
    # the other five 8162s and every other hostile of the room report 0xad while
    # key 15 stays at its untouched 1000 hp until the map unloads, so the
    # kind==0 fence never clears. Waive exactly that declared row; the room's
    # other 13 hostiles still have to die.
    {
        'identity': 34710, 'stage': 4, 'part': 1,
        'graph_sha': '2211ae6755c22eeb3fde663258faf497831ab045f43b66c21848cb1eafcaba58',
        'sources': (
            {'script': 'DEVILDOM_SIDE1_SPECIAL.lua',
             'script_sha': 'd733ead97ddb9cf7d7bb1e546b36420ad090eed816712c6c5018fbeb42185b90',
             'class_id': 0,
             'source': {'template': 8162, 'source_index': 13, 'points': [14], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 缇尔诺格 (Devildom4) 主题公园五张图。同一类 class-103 场景对象以 active
    # 形态混在 kind==0/5 的清场判定里，客户端在自己场景里退场，服务端收不到
    # 0xad，房间永不结算。每行只放行一个 (identity, stage, part) 里的一个
    # declared source；同房真怪/BOSS 仍旧必须死。
    # 34760 主题公园 关卡3 第1段: the only declared actor is 8291
    # ``DEVILDOM4_THEMEPARK_SUMMON.lua`` (class-103, gage true, no_drop true).
    # The stage declares no other npc, so its self-retirement is the room's only
    # exit signal; nothing else can ever satisfy the kind==0 fence.
    # This room is a summon arena: every wave monster arrives through the
    # client's 0x2ce and is recorded with the activation flag the client sent
    # (clear), so no declared actor can ever carry the room. ``portal`` keeps
    # the waived manager from ending the part while the room loads; only the
    # client's own end signal closes it. The 20261031-135523 run splits the
    # roster in two shapes:
    # * fight waves, 8300/8410 at y 6281-6769 and 8299 at y 6365.71, descend to
    #   the y 3020 arena floor and die in seconds;
    # * 13 8300/8410 stand-ins park on the audience plane y 7318.31982421875,
    #   z 30 for the whole run, never descend and never report a death. Those
    #   are the theatre stands' audience, waived by ``audience`` below.
    {
        'identity': 34760, 'stage': 2, 'part': 0, 'portal': True,
        'graph_sha': 'ff7a84eb43a539de17c9f0432ac2056f4ab29abd0fd3fdc11ef81a3a82123571',
        'audience': {'templates': (8300, 8410), 'y': 7318.31982421875, 'z': 30.0,
                     'tolerance': 1.0},
        'sources': (
            {'script': 'DEVILDOM4_THEMEPARK_SUMMON.lua',
             'script_sha': '6802aaec1be4045980ac03260962b312d17143ba856c3929b695fcf81ca05fd0',
             'class_id': 103,
             'source': {'template': 8291, 'source_index': 1, 'points': [5], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34770 戏法屋 关卡1 第1段: the ``DM_DUMMY`` 8345 stands beside the real
    # mascots and five active class-103 8308 ``BOX`` breakables (points 1-5).
    # The boxes are retired inside the client scene like the dummy, so the
    # kind==0 fence could never clear: the mascots die but the part stalls.
    {
        'identity': 34770, 'stage': 0, 'part': 0,
        'graph_sha': 'aae2cb6f388206f17adbe42a572a207531a4bb6abc8637bd42d4fa07f116ea00',
        'sources': (
            {'script': 'DEVILDOM4_TRICKYHOUSE_DM_DUMMY.lua',
             'script_sha': 'f23caf21a066ff72b6c771cf3ccd18afa12cf40345f74af9710997ec33f1151a',
             'class_id': 103,
             'source': {'template': 8345, 'source_index': 1, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOX.lua',
             'script_sha': 'a1b627e63db905735eb6cc8e0eeb55b59e78775f75b2e5e3c5606e6450eff6ab',
             'class_id': 103,
             'source': {'template': 8308, 'source_index': 2, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOX.lua',
             'script_sha': 'a1b627e63db905735eb6cc8e0eeb55b59e78775f75b2e5e3c5606e6450eff6ab',
             'class_id': 103,
             'source': {'template': 8308, 'source_index': 3, 'points': [2], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOX.lua',
             'script_sha': 'a1b627e63db905735eb6cc8e0eeb55b59e78775f75b2e5e3c5606e6450eff6ab',
             'class_id': 103,
             'source': {'template': 8308, 'source_index': 4, 'points': [3], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOX.lua',
             'script_sha': 'a1b627e63db905735eb6cc8e0eeb55b59e78775f75b2e5e3c5606e6450eff6ab',
             'class_id': 103,
             'source': {'template': 8308, 'source_index': 5, 'points': [4], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOX.lua',
             'script_sha': 'a1b627e63db905735eb6cc8e0eeb55b59e78775f75b2e5e3c5606e6450eff6ab',
             'class_id': 103,
             'source': {'template': 8308, 'source_index': 6, 'points': [5], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34770 戏法屋 关卡3: the same ``DM_DUMMY`` 8345 at point 21, beside the
    # rook/bishop/mascot line-up.
    {
        'identity': 34770, 'stage': 3, 'part': 0,
        'graph_sha': 'aae2cb6f388206f17adbe42a572a207531a4bb6abc8637bd42d4fa07f116ea00',
        'sources': (
            {'script': 'DEVILDOM4_TRICKYHOUSE_DM_DUMMY.lua',
             'script_sha': 'f23caf21a066ff72b6c771cf3ccd18afa12cf40345f74af9710997ec33f1151a',
             'class_id': 103,
             'source': {'template': 8345, 'source_index': 26, 'points': [21], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34770 戏法屋 关卡4 第2段 (kind==5 fence): two active class-103 8308 BOX
    # breakables at points 18/21 sit beside the rook/bishop/mascot wave and the
    # inactive 8343 manager. The client retires the boxes itself, so the fence
    # could never clear and the stage 5 boss was unreachable.
    {
        'identity': 34770, 'stage': 4, 'part': 1,
        'graph_sha': 'aae2cb6f388206f17adbe42a572a207531a4bb6abc8637bd42d4fa07f116ea00',
        'sources': (
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOX.lua',
             'script_sha': 'a1b627e63db905735eb6cc8e0eeb55b59e78775f75b2e5e3c5606e6450eff6ab',
             'class_id': 103,
             'source': {'template': 8308, 'source_index': 1, 'points': [18], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': 3, 'source_key_code': 3,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOX.lua',
             'script_sha': 'a1b627e63db905735eb6cc8e0eeb55b59e78775f75b2e5e3c5606e6450eff6ab',
             'class_id': 103,
             'source': {'template': 8308, 'source_index': 2, 'points': [21], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': 3, 'source_key_code': 3,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34780 傀儡剧场 关卡3 BOSS 房: the two ``HAND`` limbs 8361/8362 are
    # class-103 stage objects next to the real 8351 boss. The room's kind==3
    # requirement is the inactive 8359 BOSS_END door (script_gate), whose room
    # clear would otherwise demand a death report for both limbs.
    {
        'identity': 34780, 'stage': 2, 'part': 0,
        'graph_sha': 'fb970b012befc3465c8d61bce1bbb2856cc7587b34cb87b5722dc8a55caebaa0',
        'sources': (
            {'script': 'DEVILDOM4_PUPPET_HAND_L.lua',
             'script_sha': '29bb5cf22fff1cd28ebb968fc0a7a48e2f090fcaadd24548c47ea0fce762edce',
             'class_id': 103,
             'source': {'template': 8361, 'source_index': 4, 'points': [16], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_PUPPET_HAND_R.lua',
             'script_sha': '91aadc63d3689e2e43543b43a81e69677c0b44dc2542d976c9a528fe0bcb4e75',
             'class_id': 103,
             'source': {'template': 8362, 'source_index': 3, 'points': [15], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34800 影子伯爵的城堡: every lever room declares one active
    # ``LEVER_MANAGER_n`` next to the mobs and 16 inactive levers. The live run
    # 9fd8df0c stopped at stage1 part0 with accepted kills only for keys 0-7;
    # its key 8 (8399, class-103) and the levers left the client scene without a
    # 0xad, so the kind==0 fence never cleared.
    {
        'identity': 34800, 'stage': 1, 'part': 0,
        'graph_sha': '3239dda07b43a5705f1a21ecbf3bf0f8c05ad4419b7ec3447170003e7affabee',
        'sources': (
            {'script': 'DEVILDOM4_SHADOW_LEVER_MANAGER_0.lua',
             'script_sha': '49677dd232b5dedb2e250278776e3f64d506c34629090e82d6256ecf95c7fb42',
             'class_id': 103,
             'source': {'template': 8399, 'source_index': 9, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    {
        'identity': 34800, 'stage': 1, 'part': 1,
        'graph_sha': '3239dda07b43a5705f1a21ecbf3bf0f8c05ad4419b7ec3447170003e7affabee',
        'sources': (
            {'script': 'DEVILDOM4_SHADOW_LEVER_MANAGER_1.lua',
             'script_sha': '3a81383770112121bc0387553ceb927cf05d8f11a26e9b67a45047e0f2a3de19',
             'class_id': 103,
             'source': {'template': 8400, 'source_index': 15, 'points': [17], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    {
        'identity': 34800, 'stage': 1, 'part': 2,
        'graph_sha': '3239dda07b43a5705f1a21ecbf3bf0f8c05ad4419b7ec3447170003e7affabee',
        'sources': (
            {'script': 'DEVILDOM4_SHADOW_LEVER_MANAGER_2.lua',
             'script_sha': '144d60131ec77cb937fe638b609177445ef9deb829ef911041c4eaf6a451539c',
             'class_id': 103,
             'source': {'template': 8401, 'source_index': 9, 'points': [29], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # stage3 is the branch the pinned 8432 marker leads into; it repeats the
    # 8400/8401 managers at point 1 in its own lever rooms.
    {
        'identity': 34800, 'stage': 3, 'part': 0,
        'graph_sha': '3239dda07b43a5705f1a21ecbf3bf0f8c05ad4419b7ec3447170003e7affabee',
        'sources': (
            {'script': 'DEVILDOM4_SHADOW_LEVER_MANAGER_1.lua',
             'script_sha': '3a81383770112121bc0387553ceb927cf05d8f11a26e9b67a45047e0f2a3de19',
             'class_id': 103,
             'source': {'template': 8400, 'source_index': 12, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    {
        'identity': 34800, 'stage': 3, 'part': 1,
        'graph_sha': '3239dda07b43a5705f1a21ecbf3bf0f8c05ad4419b7ec3447170003e7affabee',
        'sources': (
            {'script': 'DEVILDOM4_SHADOW_LEVER_MANAGER_2.lua',
             'script_sha': '144d60131ec77cb937fe638b609177445ef9deb829ef911041c4eaf6a451539c',
             'class_id': 103,
             'source': {'template': 8401, 'source_index': 9, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage1 part2: the class-0 8827
    # ``DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY1`` at source_index 9/points 38
    # is retired inside the client scene, while the real wing hostiles report
    # normally. Leaving it active keeps the kind==0 fence and the client's 0xb8
    # waiting for an actor that never dies. Every real hostile still must die.
    {
        'identity': 35080, 'stage': 1, 'part': 2,
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'sources': (
            {'script': 'DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY1.lua',
             'script_sha': '065662cc5b21494cd0dd8b63659fcff9534152322c7514abff189629190e2b5d',
             'class_id': 0,
             'source': {'template': 8827, 'source_index': 9, 'points': [38], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage1 part4: the same class-0 clear dummy 8827 at
    # source_index 4/points 71, retired in the client scene like the part2 one.
    {
        'identity': 35080, 'stage': 1, 'part': 4,
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'sources': (
            {'script': 'DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY1.lua',
             'script_sha': '065662cc5b21494cd0dd8b63659fcff9534152322c7514abff189629190e2b5d',
             'class_id': 0,
             'source': {'template': 8827, 'source_index': 4, 'points': [71], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage2 part1: two stand-ins share the mid-boss room, the
    # class-0 8828 ``...STAGE_CLEAR_DUMMY2`` (source_index 4/points 29, active,
    # no_drop true) and the class-103 8941 ``...DROP_DUMMY_MIDDLE_BOSS``
    # (source_index 5/points 2). Both are retired by the client, so the fence
    # never clears; the room's three real 8812 bosses are still required to die.
    {
        'identity': 35080, 'stage': 2, 'part': 1,
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'sources': (
            {'script': 'DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY2.lua',
             'script_sha': '94ffcee6462390f0415fc1d6b11f9c45e20878632fef391acb9220d145678977',
             'class_id': 0,
             'source': {'template': 8828, 'source_index': 4, 'points': [29], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_DROP_DUMMY_MIDDLE_BOSS.lua',
             'script_sha': '681e2717929017252ace0200b771b7fb73056046fed3a5da8bebd16e54cedc38',
             'class_id': 103,
             'source': {'template': 8941, 'source_index': 5, 'points': [2], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage2 part2: the class-0 8828 clear dummy at
    # source_index 1/points 1 sits in the next mid-boss room and is retired by
    # the client scene, so only that declared row is waived.
    {
        'identity': 35080, 'stage': 2, 'part': 2,
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'sources': (
            {'script': 'DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY2.lua',
             'script_sha': '94ffcee6462390f0415fc1d6b11f9c45e20878632fef391acb9220d145678977',
             'class_id': 0,
             'source': {'template': 8828, 'source_index': 1, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage4 part0 (boss room): the real 8810 boss dies but the
    # kind==0 fence still counts five stand-ins - the class-0 FAKE_BOSS pair
    # 8835/8836 (source_index 2/3, boss true, boss_lines 150) plus the class-103
    # drop dummies 8831/8839/8940. Every pinned row keeps its boss/boss_lines
    # fields because the comparison skips only ``active``. 8810 must still die.
    {
        'identity': 35080, 'stage': 4, 'part': 0,
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'sources': (
            {'script': 'DEVILDOM5_GOLDCASTLE_FAKE_BOSS1.lua',
             'script_sha': 'fb8e587a8146dea016e45ef62668d34f948c04169f3aba4e1617c450925228b9',
             'class_id': 0,
             'source': {'template': 8835, 'source_index': 2, 'points': [2], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': True, 'boss_lines': 150, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_FAKE_BOSS2.lua',
             'script_sha': 'ec81f1776fd0028ec18d889160796918017b41d260b5ca5f508ac9b88f4627d3',
             'class_id': 0,
             'source': {'template': 8836, 'source_index': 3, 'points': [3], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': True, 'boss_lines': 150, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_DROP_DUMMY1.lua',
             'script_sha': 'b07e1fa2e4c4f879e07744d8ef39dec683e30c4f128ab0ae179b1c6255ac7894',
             'class_id': 103,
             'source': {'template': 8831, 'source_index': 9, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_DROP_DUMMY2.lua',
             'script_sha': '6bbb6c7adb813a9de922aaced595371c6db8018c3d6af743e756fd6cce3849bc',
             'class_id': 103,
             'source': {'template': 8839, 'source_index': 10, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_DROP_DUMMY3.lua',
             'script_sha': 'c4635947d9fdbac04c16c3b2a285a86df63d054ec3627e5e7a81aa90e408cc93',
             'class_id': 103,
             'source': {'template': 8940, 'source_index': 11, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
)
DUMMY_HOSTILES = {(row['identity'], row['stage'], row['part']): row for row in DUMMY_HOSTILE_SOURCES}


def dummy_hostile(run, npc):
    """True for a pinned drop dummy that can never satisfy a room clear."""
    if not dummy_hostile_relaxation():
        return False
    row = DUMMY_HOSTILES.get((run.identity, run.stage, run.part))
    if row is None:
        return False
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)):
        return False
    from els_server.game_data import client_data
    for pinned in row['sources']:
        source = pinned['source']
        if (npc.get('start_point') != source['points'][0]
                or any(npc.get(k) != v for k, v in source.items() if k != 'active')):
            continue
        if run.catalog.manifest['source_sha256'].get(pinned['script']) != pinned['script_sha']:
            continue
        native = client_data().npc(source['template'])
        if native['class_id'] == pinned['class_id'] and native['is_npc'] is True:
            return True
    return False


def _portal_row(run):
    """The pinned room whose exit proof is the client's own end signal."""
    if not dummy_hostile_relaxation():
        return None
    row = DUMMY_HOSTILES.get((run.identity, run.stage, run.part))
    if row is None or not row.get('portal'):
        return None
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)):
        return None
    return row


def dummy_portal(run):
    """True for a pinned room whose only exit proof is the client's own request.

    34760 stage 2 is a summon arena: its waves arrive through 0x2ce and are
    recorded clear, so the declared roster never holds a live hostile. Ending the
    part as soon as the empty fence clears would skip the fight; only the
    client's own 0xbb/0xb8 (or ``arena_finished``'s silence) can close it.
    """
    return _portal_row(run) is not None


# A wave stream with a 37.5 s cadence (20261031-135523: 14:33:09, 14:33:47,
# 14:34:24, 14:35:02) never goes quiet this long while the show is running.
ARENA_QUIET_SECONDS = 60.0


def arena_audience(run, npc):
    """True for the pinned stand audience of the 34760 summon arena.

    The audience rows are ordinary 8300/8410 summons, but the client parks them
    on the audience plane above the arena (y=7318.31982421875, z=30) where they
    never descend or take damage. Fight waves of the same templates spawn at
    y<=6769.31 on the arena floor, so the spawn plane separates them.
    """
    row = _portal_row(run)
    audience = row.get('audience') if row is not None else None
    if not audience or npc.get('template') not in audience['templates'] or not npc.get('dynamic'):
        return False
    xyz = npc.get('spawn_xyz')
    if xyz is None:
        return False
    return (abs(xyz[1] - audience['y']) <= audience['tolerance']
            and abs(xyz[2] - audience['z']) <= audience['tolerance'])


def arena_client_end(run):
    """Record the client's own part-end request for a pinned arena."""
    if _portal_row(run) is not None:
        run.arena_show_over = True


def arena_finished(run):
    """True once the pinned arena's show is over.

    The client sends 0xbb/0xb8 when its own scene ends and stays silent through
    the show's empty wave gaps, so its own request is the proof. A full minute
    without an admitted wave is the fallback for a script that never reports.
    """
    if _portal_row(run) is None:
        return False
    if getattr(run, 'arena_show_over', False):
        return True
    last = getattr(run, 'dynamic_last_at', None)
    return bool(getattr(run, 'dynamic_count', 0)) and last is not None \
        and run.clock() - last >= ARENA_QUIET_SECONDS


# Finite source-pinned rooms whose ``kind == 5`` exit never receives the
# client's own portal request. This build emits 0xb8 only as the queued tail of
# the previous transition (payload = old part), so ``portal_requested`` can
# never be set for the new part and ``periodic()`` never announces its end.
# Such a row lets the room settle on the same proof every ``kind == 0`` room
# uses: every declared live hostile is dead.
PORTAL_EXIT_SOURCES = (
    # 34780 傀儡剧场 关卡1 第3段: 7 active hostiles, kind==5 with portal lines
    # 18/19/20/21. The client's only 0xb8 for this part is the queued one from
    # the previous transition (20261031-150518 07:17:02.793, 0.2 s after the
    # part began); after the last death at 07:17:20.690 no further request
    # arrived for 17 minutes, so the run could not leave the map.
    {
        'identity': 34780, 'stage': 0, 'part': 2,
        'graph_sha': 'fb970b012befc3465c8d61bce1bbb2856cc7587b34cb87b5722dc8a55caebaa0',
        'script': 'Dungeon_Devildom4_Puppet.lua',
        'script_sha': 'fb970b012befc3465c8d61bce1bbb2856cc7587b34cb87b5722dc8a55caebaa0',
    },
    # 35080 黄金城 文物馆 (Artifact Exhibit) 两个跳跃平台房间, kind==3 on the
    # indestructible 8826 manager + 8821 traps. Official setting: the player
    # removes the barrier by stepping on the correct golden platform, so there
    # is nothing to kill. This build never sends 0xb8 in that room (0 requests
    # across 20261031-215816/225124/231403), because the client only emits 0xbb
    # after a server 0xba, so a hard 0xb8 requirement can never be met. The
    # client's own part-end request carries the same proof and is admitted by
    # ``client_end``; the 8826 retirement still settles the room through the
    # ordinary kind==3 requirement.
    {
        'identity': 35080, 'stage': 3, 'part': 0,
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'script': 'Dungeon_Devildom5_GoldCastle.lua',
        'script_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'client_end': True,
    },
    {
        'identity': 35080, 'stage': 3, 'part': 1,
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'script': 'Dungeon_Devildom5_GoldCastle.lua',
        'script_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'client_end': True,
    },
)
PORTAL_EXITS = {(row['identity'], row['stage'], row['part']): row for row in PORTAL_EXIT_SOURCES}


def portal_exit_room(run):
    """True for a pinned room whose exit is the client's own 0xb8, switch aside.

    Callers use this to keep a pinned room from falling through to another
    relaxation when ``portal_exit_relaxation`` is off: the room must stay
    exactly as stuck as it was before the rule, never settle on entry.
    """
    return (run.identity, run.stage, run.part) in PORTAL_EXITS


def portal_exit(run):
    """True for the pinned room whose kind==5 exit settles on its own clear."""
    if not portal_exit_relaxation():
        return False
    row = PORTAL_EXITS.get((run.identity, run.stage, run.part))
    if row is None:
        return False
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)):
        return False
    return run.catalog.manifest['source_sha256'].get(row['script']) == row['script_sha']


def portal_exit_client_end(run):
    """Record the client's own part-end request for a pinned puzzle room.

    The 文物馆 rooms never send 0xb8, and this build's 0xbb is only emitted
    after a server 0xba, so a pinned room that insists on 0xb8 deadlocks: no
    completion proof -> no 0xba -> no 0xbb -> no 0xb8. The client's own
    part-end request for the current part is the same scene-end proof the
    pinned arenas already consume (``arena_client_end``), so it is recorded
    here for the rows that declare ``client_end``.
    """
    row = PORTAL_EXITS.get((run.identity, run.stage, run.part))
    if row is not None and row.get('client_end'):
        # Keyed by the room it was reported for: parts repeat across stages.
        run.portal_exit_over = (run.stage, run.part)


def portal_exit_settled(run):
    """True once a pinned puzzle room carries the client's own end proof."""
    row = PORTAL_EXITS.get((run.identity, run.stage, run.part))
    if row is None or not row.get('client_end'):
        return False
    return getattr(run, 'portal_exit_over', None) == (run.stage, run.part)


# 普鲁纳姆外围-普雷加斯的迷宫 (34730) 关卡3 stacks five boss-gauge actors on
# the same spawn point: 8192 ``巨魔像普雷加斯`` (200 lines, 144e9 hp), the three
# ``巨人之手`` 8201/8202/8203 (150 lines each) and 8282 ``巨魔像普雷加斯``
# ``DEVILDOM_SIDE3_STAGE2_HEART_DUMMY.lua`` (250 lines). The client composites
# them into one body, so only the heart ever reports a death: the live save holds
# one 8282 kill and none of the other four, while the room's condition is
# ``kind 3`` on the class-103 ``关卡3结束演出`` 8266, i.e. it falls back to
# ``script_gate`` -> ``_room_clear`` and waits for four corpses that never arrive.
# The heart therefore carries the room, and the body parts are waived from the
# clear fence - both in ``condition_ready`` and in the client's 0xb8 request.
BOSS_CORE_SOURCES = (
    {
        'identity': 34730, 'stage': 2, 'part': 0,
        'graph_sha': 'bd2b9052797964385dc187e32b18bb9cd7665c92c5599e1880238db60bb2797c',
        'heart': {'script': 'DEVILDOM_SIDE3_STAGE2_HEART_DUMMY.lua',
                  'script_sha': '645a25d0cdf52f9839ec2d23f0d86d1569bfa06a26801af43ea01258ef9139c2',
                  'class_id': 0,
                  'source': {'template': 8282, 'source_index': 5, 'points': [1], 'active': True,
                             'gage': True, 'ally': False, 'team': 1, 'no_drop': False,
                             'right': False, 'boss': True, 'boss_lines': 250,
                             'key_code': -1, 'source_key_code': -1, 'rate': 100,
                             'offset': [0, 0, 0]}},
        'body': (8192, 8201, 8202, 8203),
    },
    # 35110 ironwall stage0 part0: the boss is one composed spawn point. The
    # class-0 8901 ``DEVILDOM5_IRONWALL_STAGE0_BOSS_BODY`` (source_index 24,
    # boss true, boss_lines 200) is the only part the client reports dead; the
    # 8902 LEG and 8903 CANNON stand beside it and never report, so the room
    # clear and the 0xb8 check stall after the body dies. Waive the limbs only.
    {
        'identity': 35110, 'stage': 0, 'part': 0,
        'graph_sha': '1e010c5a23db8aaf3acc9bbbb7a7db93d705c7e3fc995cbc817ce01842711877',
        'heart': {'script': 'DEVILDOM5_IRONWALL_STAGE0_BOSS_BODY.lua',
                  'script_sha': 'dc5539f8ee8c44e6fc4cfee710b7b22472a2baa73efc352d5c39fb17b0da1851',
                  'class_id': 0,
                  'source': {'template': 8901, 'source_index': 24, 'points': [1], 'active': True,
                             'gage': True, 'ally': False, 'team': 1, 'no_drop': False,
                             'right': False, 'boss': True, 'boss_lines': 200,
                             'key_code': -1, 'source_key_code': -1, 'rate': 100,
                             'offset': [0, 0, 0]}},
        'body': (8902, 8903),
    },
    # 35110 ironwall stage2 part0: the same heart+body shape. The class-0 8905
    # ``DEVILDOM5_IRONWALL_STAGE2_BOSS`` (source_index 1, boss true, boss_lines
    # 200) carries the room, while 8906/8907 are the hands the client composites
    # into it and never reports. The 8933 BOSS_END marker of the room is still
    # handled by its part marker row.
    {
        'identity': 35110, 'stage': 2, 'part': 0,
        'graph_sha': '1e010c5a23db8aaf3acc9bbbb7a7db93d705c7e3fc995cbc817ce01842711877',
        'heart': {'script': 'DEVILDOM5_IRONWALL_STAGE2_BOSS.lua',
                  'script_sha': '0fb9f4dec5d7f209c1e68d21669eb7459a0e7ddeb08bd627fbb5eb49e7b54de0',
                  'class_id': 0,
                  'source': {'template': 8905, 'source_index': 1, 'points': [1], 'active': True,
                             'gage': True, 'ally': False, 'team': 1, 'no_drop': False,
                             'right': False, 'boss': True, 'boss_lines': 200,
                             'key_code': -1, 'source_key_code': -1, 'rate': 100,
                             'offset': [0, 0, 0]}},
        'body': (8906, 8907),
    },
)
BOSS_CORES = {(row['identity'], row['stage'], row['part']): row for row in BOSS_CORE_SOURCES}


def _boss_core_row(run):
    if not boss_core_relaxation():
        return None
    row = BOSS_CORES.get((run.identity, run.stage, run.part))
    if row is None:
        return None
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)):
        return None
    return row


def boss_core(run, npc):
    """True for a pinned boss body part the client never reports dead."""
    row = _boss_core_row(run)
    if row is None:
        return False
    return npc['template'] in row['body']


def boss_core_cleared(run):
    """True once every pinned heart of the room has died."""
    row = _boss_core_row(run)
    if row is None:
        return False
    heart = row['heart']
    if run.catalog.manifest['source_sha256'].get(heart['script']) != heart['script_sha']:
        return False
    from els_server.game_data import client_data
    if client_data().npc(heart['source']['template'])['class_id'] != heart['class_id']:
        return False
    hearts = [n for n in run.current['npcs']
              if n['template'] == heart['source']['template']
              and n.get('start_point') == heart['source']['points'][0]]
    if not hearts:
        return False
    return all(n['key'] in run.defeated for n in hearts)


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


# A declaration with ``active`` false is a scene object the client owns. Shipped
# with the activation flag clear (wire 0x4e / raw 0x2c, see
# ``dungeon_spawns.py``) the client builds a hit box and no body, so the object
# stays invisible but keeps blocking. Most rooms place such markers off the
# walking line; 35080 stage3 part0 stacks the inactive elevator manager (8832)
# on point 1, the only approach to the TRAP1 row and the same point as the active
# stage-3 manager (8826). Players are then stopped at x≈2373 at every height
# (20261031-231403, 20261031-225124, 20261101-103256), i.e. the barrier's left
# side, even after the visible barrier is solved. This room's exit only requires
# 8826, so omitting the inactive duplicate changes no clear fence.
INACTIVE_HITBOX_OMISSIONS = {
    (35080, 3, 0): {
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'template': 8832, 'source_index': 2, 'points': [1], 'active': False,
        'script': 'DEVILDOM5_GOLDCASTLE_ELEVATOR_MANAGER.lua',
        'script_sha': '0524d320b5095af4263f4dd26650b0ad8f9c5e4215de569d4365b801c27f9755',
        'class_id': 103,
    },
}


def inactive_hitbox_omitted(identity, graph_sha, stage, part, source):
    """True for the one declared actor whose invisible hit box cannot be removed."""
    if not inactive_hitbox_omission():
        return False
    row = INACTIVE_HITBOX_OMISSIONS.get((identity, stage, part))
    if row is None or graph_sha != row['graph_sha']:
        return False
    if (source['template'] != row['template'] or source['source_index'] != row['source_index']
            or source['points'] != row['points'] or bool(source['active']) != row['active']):
        return False
    from els_server.game_data import client_data
    native = client_data().npc(row['template'])
    return (native['class_id'] == row['class_id'] and native['is_npc'] is True
            and native['script'] == row['script'])


# 35090「地下植物馆」把不可摧毁的 CAGE（8844，DEVILDOM5_UNDERGROUND_CAGE.lua，
# class 0）声明成 active / team 1 的敌对目标。kind==0 的清场判定要求所有
# active 且 team!=0 的 actor 报死亡，而 CAGE 在客户端只是场景笼子：20261101-152014
# 里 8846/8847 全体在 15:29:51 前死完，4 个 cage 到 15:31:45 卸图时 hp 仍是
# 665642944（一次伤害都没吃、一次销毁都没有），pve_kill_experience 里 35090 也
# 从没有过 8844 的击杀。只在这一副本的四个房间豁免它们（stage1 part0-2 的 kind==0
# 清场，以及 stage2 part0 的 kind==3 标记房——后者的 live 栅栏同样会把这四个笼子
# 算成「还活着」），真正的成员怪（8846/8847）与 BOSS 仍必须全灭才能推进。
CAGE_OBJECTS = {
    (35090, 1, 0): {'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
                    'template': 8844, 'class_id': 0,
                    'script': 'DEVILDOM5_UNDERGROUND_CAGE.lua',
                    'script_sha': '5e8f26c85247c7188be09260ff72435242519471ea92a7f156c79641ac6e87c4'},
    (35090, 1, 1): {'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
                    'template': 8844, 'class_id': 0,
                    'script': 'DEVILDOM5_UNDERGROUND_CAGE.lua',
                    'script_sha': '5e8f26c85247c7188be09260ff72435242519471ea92a7f156c79641ac6e87c4'},
    (35090, 1, 2): {'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
                    'template': 8844, 'class_id': 0,
                    'script': 'DEVILDOM5_UNDERGROUND_CAGE.lua',
                    'script_sha': '5e8f26c85247c7188be09260ff72435242519471ea92a7f156c79641ac6e87c4'},
    # stage2 part0 closes with a kind==3 marker (8857), but part_marker_gate's
    # live fence counts the same four cages as living hostiles.
    (35090, 2, 0): {'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
                    'template': 8844, 'class_id': 0,
                    'script': 'DEVILDOM5_UNDERGROUND_CAGE.lua',
                    'script_sha': '5e8f26c85247c7188be09260ff72435242519471ea92a7f156c79641ac6e87c4'},
}


def cage_object(run, npc):
    """True for a pinned scene cage that never reports a combat death."""
    if not cage_object_relaxation():
        return False
    row = CAGE_OBJECTS.get((run.identity, run.stage, run.part))
    if row is None or run.graph['source_sha256'] != row['graph_sha']:
        return False
    if npc.get('template') != row['template'] or not npc.get('active'):
        return False
    from els_server.game_data import client_data
    native = client_data().npc(row['template'])
    return (native['class_id'] == row['class_id'] and native['is_npc'] is True
            and native['script'] == row['script'])


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
    # 普鲁纳姆外围-普雷加斯的迷宫 (34710) 两处分岔房。房间里的 actor 全是
    # 「关卡N触发对象」: 模板 8168/8169/8170 对应关卡1/2/3，8171/8172 对应
    # 关卡5/6，全部 class-103 / IS_NPC / active=false，kind==0 的「清场」
    # 判定本来就把它们排除在外，kind==3 却要求它们死亡。玩家走进哪个触发
    # 对象由客户端决定，服务端既收不到退场上报、也收不到分支编号，于是
    # 出口条件永远不满足，这张图连第一个分岔都过不去。
    # ``exits`` 只钉死本构建实际走的那两个分支；poll_ready 按源顺序取第一个
    # 满足的条件，所以 (0,1) 走 8169(关卡2)、(4,0) 走 8171(关卡5)。
    # 8168(关卡1) 不在 exits 内：stage1 全房间只有 5 个 8211「特殊型怪物_
    # 爆弹」召唤替身，服务端批不出召唤物，进去就是一间打不动的空房。
    (34710, 0, 1): {
        'graph_sha': '2211ae6755c22eeb3fde663258faf497831ab045f43b66c21848cb1eafcaba58',
        'required': (8169,),
        'exits': (8169, 8170),
        'markers': (
            {'script': 'DEVILDOM_SIDE1_STAGE1_TRIGGER.lua',
             'script_sha': '2bef85aa1563c823dd75b0e3274da74b02ca48776d9922c6b86a2175533daaf6',
             'source': {'template': 8168, 'source_index': 2, 'points': [16], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM_SIDE1_STAGE2_TRIGGER.lua',
             'script_sha': '8bcd3c7f5329b3fa70f8fefdca4a36e08021bd6631ec82fdb4b44b3e294d467f',
             'source': {'template': 8169, 'source_index': 3, 'points': [17], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM_SIDE1_STAGE3_TRIGGER.lua',
             'script_sha': '7184db8090f59ddac2d8bdd8fdf070270924594b300cb6e2d015d3740fd6efbc',
             'source': {'template': 8170, 'source_index': 4, 'points': [18], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM_SIDE1_SPECIAL_GOLD.lua',
             'script_sha': '20f0a23491c09e98eb12cd5141391d8bdde91d00fc7a690862f799ed5a96dca7',
             'source': {'template': 8174, 'source_index': 1, 'points': [18], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    (34710, 4, 0): {
        'graph_sha': '2211ae6755c22eeb3fde663258faf497831ab045f43b66c21848cb1eafcaba58',
        'required': (8171,),
        'exits': (8171, 8172),
        'markers': (
            {'script': 'DEVILDOM_SIDE1_STAGE5_TRIGGER.lua',
             'script_sha': '33af9a7bb1f0d24c4cb92845db56198d656792e3d48a4ec614f64113839574ee',
             'source': {'template': 8171, 'source_index': 2, 'points': [1], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM_SIDE1_STAGE6_TRIGGER.lua',
             'script_sha': '09bc1c4cb336475b9b1d4fc6dc91fd4bbfa384d6b65d4209117bb8369f713b58',
             'source': {'template': 8172, 'source_index': 3, 'points': [2], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM_SIDE1_SPECIAL_GOLD.lua',
             'script_sha': '20f0a23491c09e98eb12cd5141391d8bdde91d00fc7a690862f799ed5a96dca7',
             'source': {'template': 8174, 'source_index': 1, 'points': [1], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 缇尔诺格 (Devildom4) 主题公园五张图：kind==3 条件点名 class-103 场景对象。
    # 这些对象由客户端在自己的场景里退场，服务端永远收不到 0xad；而房间里的
    # 真 BOSS/小怪仍旧必须死（part_marker_gate 的 live 检查）。34790 不需要
    # 任何豁免：它的 kind==3 要求的是会正常报死亡的真 BOSS 8370。
    # 34760 主题公园 关卡4 BOSS 房: required 8412 ``DROP_DUMMY``; the 8286 boss
    # and its 8293 START marker share the room.
    (34760, 3, 0): {
        'graph_sha': 'ff7a84eb43a539de17c9f0432ac2056f4ab29abd0fd3fdc11ef81a3a82123571',
        'required': (8412,),
        'markers': (
            {'script': 'DEVILDOM4_THEMEPARK_DROP_DUMMY.lua',
             'script_sha': 'e9bb704846a5ec01910f49bda5e5ff5ad0dba635ae0ba9c7e187e8d7faca1a1f',
             'source': {'template': 8412, 'source_index': 3, 'points': [5], 'active': True,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34770 戏法屋 关卡2 岔路口: the three ``STAGE_n_TRIGGER`` objects are the
    # junction's doors, exactly like 34710's 关卡N触发对象. All three sub-areas
    # (stages 2/3/4) are playable here, so every trigger is an exit; poll_ready
    # takes the first satisfied condition, i.e. stage 2.
    (34770, 1, 0): {
        'graph_sha': 'aae2cb6f388206f17adbe42a572a207531a4bb6abc8637bd42d4fa07f116ea00',
        'required': (8335,),
        'exits': (8335, 8336, 8337),
        'markers': (
            {'script': 'DEVILDOM4_TRICKYHOUSE_STAGE2_TRIGGER.lua',
             'script_sha': 'a24eb07e4eeb45058539c0cd03fbdcdbbbe85c598d6800562cee327307bab50b',
             'source': {'template': 8335, 'source_index': 3, 'points': [2], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_STAGE3_TRIGGER.lua',
             'script_sha': 'd59457bcc99c0fd4ee37ca8ad962518ab42cb79e3fff198f1f85ae9e3d497187',
             'source': {'template': 8336, 'source_index': 4, 'points': [2], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_TRICKYHOUSE_STAGE4_TRIGGER.lua',
             'script_sha': 'e63da459e4dd67a76721207e9bd4906d8de9e116d458696b88c7d72fd1c7a0bb',
             'source': {'template': 8337, 'source_index': 5, 'points': [2], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34770 戏法屋 关卡3: required 8345 DM_DUMMY; the king/queen bosses (8302,
    # 8303) still have to die.
    (34770, 2, 0): {
        'graph_sha': 'aae2cb6f388206f17adbe42a572a207531a4bb6abc8637bd42d4fa07f116ea00',
        'required': (8345,),
        'markers': (
            {'script': 'DEVILDOM4_TRICKYHOUSE_DM_DUMMY.lua',
             'script_sha': 'f23caf21a066ff72b6c771cf3ccd18afa12cf40345f74af9710997ec33f1151a',
             'source': {'template': 8345, 'source_index': 11, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34770 戏法屋 关卡6 BOSS 房: required 8344 BOSS_END; boss 8301 still dies.
    (34770, 5, 0): {
        'graph_sha': 'aae2cb6f388206f17adbe42a572a207531a4bb6abc8637bd42d4fa07f116ea00',
        'required': (8344,),
        'markers': (
            {'script': 'DEVILDOM4_TRICKYHOUSE_BOSS_END.lua',
             'script_sha': '882648271339de3ca8ba2c4d1012ba9e6d37fba48c6efa03291ddcf2e2d55a8a',
             'source': {'template': 8344, 'source_index': 2, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 34800 影子伯爵 关卡3 中 BOSS 房: two conditions name 8432 CLEAR_DUMMY and
    # 8397 BOSS_MIDDLE_END. Both are active class-103 scene objects; this build
    # ends the middle-boss scene at a scripted HP threshold, so the client
    # retires a marker with its native flag-255 expiry and 8392 never reports a
    # combat death. ``retirement`` admits that exact report for either marker
    # and then lets the source order pick 8432 -> stage 3 or 8397 -> stage 4.
    (34800, 2, 0): {
        'graph_sha': '3239dda07b43a5705f1a21ecbf3bf0f8c05ad4419b7ec3447170003e7affabee',
        'required': (8432,),
        'retirement': True,
        'markers': (
            {'script': 'DEVILDOM4_SHADOW_CLEAR_DUMMY.lua',
             'script_sha': 'c99c7da0a8305bfbf5a552b5cbb8c9bd3f12b8b9f2e1b60346e815d28616ca4a',
             'source': {'template': 8432, 'source_index': 3, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM4_SHADOW_BOSS_MIDDLE_END.lua',
             'script_sha': '5e6d62cda7811038221d166a099276e824a1afa6f1da1cfb2f8f48b3de10def7',
             'source': {'template': 8397, 'source_index': 2, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage3 part0 = 文物馆 (Artifact Exhibit). Official
    # setting: the barrier is indestructible and the 8821 ``...TRAP1`` (Dark Elf
    # Traps) behind it are never killed; the player removes the barrier by
    # stepping on the correct golden platform, and the class-0 8826
    # ``...STAGE3_MANAGER`` retires inside the client scene once the puzzle is
    # solved. Neither the traps nor the manager is a combat actor, so the room
    # settles on the manager's pinned flag-255 retirement, or on the client's
    # own 0xb8 for this part (portal_exit row), never on a kill.
    (35080, 3, 0): {
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'required': (8826,),
        'retirement': True,
        # Every declared actor of this room is a marker, so the generic
        # clear-fence is vacuously true and would settle the room on entry.
        'retirement_only': True,
        'markers': (
            {'script': 'DEVILDOM5_GOLDCASTLE_STAGE3_MANAGER.lua',
             'script_sha': 'faa1d3fc49c5919b6409af41cbd21b236b6d27315ddeab8eb0e3edda05b19220',
             'class_id': 0,
             'source': {'template': 8826, 'source_index': 1, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 3, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 4, 'points': [2], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 5, 'points': [3], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 6, 'points': [4], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 7, 'points': [5], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage3 part1: the second Artifact Exhibit platforming
    # room. Same shape as part0: the class-0 8826 manager at source_index
    # 1/points 6 and the four 8821 traps (points 6-9) are indestructible scene
    # objects, so the room settles on the manager's flag-255 retirement or on
    # the client's own 0xb8, never on a kill.
    (35080, 3, 1): {
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'required': (8826,),
        'retirement': True,
        'retirement_only': True,
        'markers': (
            {'script': 'DEVILDOM5_GOLDCASTLE_STAGE3_MANAGER.lua',
             'script_sha': 'faa1d3fc49c5919b6409af41cbd21b236b6d27315ddeab8eb0e3edda05b19220',
             'class_id': 0,
             'source': {'template': 8826, 'source_index': 1, 'points': [6], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 2, 'points': [6], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 3, 'points': [7], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 4, 'points': [8], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_GOLDCASTLE_TRAP1.lua',
             'script_sha': '437cd98f46c8e9786e41008a6074ad855b6532b5a64cb5809aaaf07e225eb7e2',
             'class_id': 0,
             'source': {'template': 8821, 'source_index': 5, 'points': [9], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35080 goldcastle stage3 part2: the class-0 8829
    # ``...STAGE_CLEAR_DUMMY3`` at source_index 2/points 11 is the room's only
    # kind==3 requirement. It is waived here instead of retired, because the
    # real boss 8811 shares the room and must still die; a flag-255 retirement
    # would settle the part while 8811 is alive.
    (35080, 3, 2): {
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'required': (8829,),
        'markers': (
            {'script': 'DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY3.lua',
             'script_sha': '68ff2da9e5e6dff090083b3389474bd26c5ac0c20196b759bb9fb81c1c9ab8c8',
             'class_id': 0,
             'source': {'template': 8829, 'source_index': 2, 'points': [11], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35090 underground stage0 part0: the kind==3 requirement is the class-103
    # 8853 ``...WATER_MANAGER_1`` at source_index 2/points 35, which the client
    # retires in its own scene. Waiving it still leaves the room's 14 real
    # monsters required to die.
    (35090, 0, 0): {
        'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
        'required': (8853,),
        'markers': (
            {'script': 'DEVILDOM5_UNDERGROUND_WATER_MANAGER_1.lua',
             'script_sha': '63879402bf0b5b171ae81ad85a1bf21c9771c4c33463e6dc20c935adcb747734',
             'class_id': 103,
             'source': {'template': 8853, 'source_index': 2, 'points': [35], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35090 underground stage0 part1: the same 8853 water manager at
    # source_index 2/points 38; the 15 real monsters of the room still must die.
    (35090, 0, 1): {
        'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
        'required': (8853,),
        'markers': (
            {'script': 'DEVILDOM5_UNDERGROUND_WATER_MANAGER_1.lua',
             'script_sha': '63879402bf0b5b171ae81ad85a1bf21c9771c4c33463e6dc20c935adcb747734',
             'class_id': 103,
             'source': {'template': 8853, 'source_index': 2, 'points': [38], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35090 underground stage2 part0: the class-103 8857 ``...UP_DOOR`` at
    # source_index 3/points 31 is an active scene door the client retires.
    # Waiving it keeps the room's 16 real monsters required to die.
    (35090, 2, 0): {
        'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
        'required': (8857,),
        'markers': (
            {'script': 'DEVILDOM5_UNDERGROUND_UP_DOOR.lua',
             'script_sha': '1ca170a38f1bd7b42447ccda5e69218fcd691a40d169a27e3414da92b79c727f',
             'class_id': 103,
             'source': {'template': 8857, 'source_index': 3, 'points': [31], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35090 underground stage2 part1: the kind==3 requirement is the class-103
    # 8868 ``...DM`` at source_index 13/points 30, retired in the client scene.
    # The real boss 8843 of the room is still required to die.
    (35090, 2, 1): {
        'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
        'required': (8868,),
        'markers': (
            {'script': 'DEVILDOM5_UNDERGROUND_DM.lua',
             'script_sha': '4513914c632d702afc29b12dcbb9c706b576c0039c92c197629360686320b451',
             'class_id': 103,
             'source': {'template': 8868, 'source_index': 13, 'points': [30], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35090 underground stage3 part0 (boss room): two class-103 end markers share
    # point 6 - 8859 ``...BOSS_END`` (source_index 4) and 8861 ``...BOSS_END1``
    # (source_index 5). Both are retired by the client, so both rows are waived;
    # the real boss 8841 must still die.
    (35090, 3, 0): {
        'graph_sha': '72bddd85273702560b22616f5cf47795128f0ecafae674ac23c74ee1d380fcfc',
        'required': (8859,),
        'markers': (
            {'script': 'DEVILDOM5_UNDERGROUND_BOSS_END.lua',
             'script_sha': '1a76050f20e4012dd0c8b6ca09445a8f8211ec682377dc628cc1a85d53d9c88a',
             'class_id': 103,
             'source': {'template': 8859, 'source_index': 4, 'points': [6], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
            {'script': 'DEVILDOM5_UNDERGROUND_BOSS_END1.lua',
             'script_sha': '4b776312410ff4d4efe3493b6038101260504b428de69613752597db9da0c30f',
             'class_id': 103,
             'source': {'template': 8861, 'source_index': 5, 'points': [6], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35100 arena stage0 part1: the room declares a single actor, the class-103
    # 8877 ``...ELEVATOR_TRIGGER_1`` at source_index 1/points 11, which is the
    # kind==3 requirement itself. The client retires it in its own scene, so the
    # pinned row treats it as the room's own script marker; no hostile is left.
    (35100, 0, 1): {
        'graph_sha': '4f9fd1bf57aa26c0c686728b5ace50c9f7221ebbd0bcc27a248acbccc4b712c6',
        'required': (8877,),
        'markers': (
            {'script': 'DEVILDOM5_ARENA_ELEVATOR_TRIGGER_1.lua',
             'script_sha': 'a054f1eceb6a82fc8c460951362887cd856a3666630dd5f2526e44c849184670',
             'class_id': 103,
             'source': {'template': 8877, 'source_index': 1, 'points': [11], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35100 arena stage1 part0: this room declares two kind==3 branches, the
    # fail exit 8881 (kind 4) and the success exit 8880. Only the success branch
    # is pinned in ``exits``, so poll_ready skips the fail one. ``combat`` keeps
    # the real boss 8874 out of the marker waiver: it must still die, while the
    # inactive class-103 8880 ``...ELEVATOR_TRIGGER_SUCESS`` is waived.
    (35100, 1, 0): {
        'graph_sha': '4f9fd1bf57aa26c0c686728b5ace50c9f7221ebbd0bcc27a248acbccc4b712c6',
        'required': (8874, 8880),
        'exits': (8874, 8880),
        'combat': (8874,),
        'markers': (
            {'script': 'DEVILDOM5_ARENA_ELEVATOR_TRIGGER_SUCESS.lua',
             'script_sha': 'c4a9a0d6ced0b98793c421117eca83fed55abca027dc4e3de75ff4de7f1b7c1b',
             'class_id': 103,
             'source': {'template': 8880, 'source_index': 3, 'points': [1], 'active': False,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35100 arena stage2 part0: the same two-branch shape, fail exit 8881 versus
    # success exit 8880. Only the success branch is in ``exits``; the real boss
    # 8873 is declared in ``combat`` and still has to die, while the inactive
    # class-103 8880 trigger is waived.
    (35100, 2, 0): {
        'graph_sha': '4f9fd1bf57aa26c0c686728b5ace50c9f7221ebbd0bcc27a248acbccc4b712c6',
        'required': (8873, 8880),
        'exits': (8873, 8880),
        'combat': (8873,),
        'markers': (
            {'script': 'DEVILDOM5_ARENA_ELEVATOR_TRIGGER_SUCESS.lua',
             'script_sha': 'c4a9a0d6ced0b98793c421117eca83fed55abca027dc4e3de75ff4de7f1b7c1b',
             'class_id': 103,
             'source': {'template': 8880, 'source_index': 3, 'points': [1], 'active': False,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35100 arena stage3 part0: the kind==3 requirement is the inactive
    # class-103 8882 ``...BOSS_START`` at source_index 2/points 1. The client
    # owns that cutscene marker; the real boss 8872 is still required to die.
    (35100, 3, 0): {
        'graph_sha': '4f9fd1bf57aa26c0c686728b5ace50c9f7221ebbd0bcc27a248acbccc4b712c6',
        'required': (8882,),
        'markers': (
            {'script': 'DEVILDOM5_ARENA_BOSS_START.lua',
             'script_sha': '75fdaf3ca1973d8e3234a00c3a75b6cbf055b19c54d211c914a6fa440fd76bbf',
             'class_id': 103,
             'source': {'template': 8882, 'source_index': 2, 'points': [1], 'active': False,
                        'gage': False, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35100 arena stage4 part0 (final boss room): the kind==3 requirement is the
    # inactive class-103 8883 ``...BOSS_END`` at source_index 2/points 1, a
    # cutscene marker of the client. The real boss 8871 must still die.
    (35100, 4, 0): {
        'graph_sha': '4f9fd1bf57aa26c0c686728b5ace50c9f7221ebbd0bcc27a248acbccc4b712c6',
        'required': (8883,),
        'markers': (
            {'script': 'DEVILDOM5_ARENA_BOSS_END.lua',
             'script_sha': '97baa3d29c7aa7731c02976169a7353baa3726b20b7a8e345d0c6adde2fa175c',
             'class_id': 103,
             'source': {'template': 8883, 'source_index': 2, 'points': [1], 'active': False,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': False, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35110 ironwall stage1 part0: the kind==3 requirement is the class-103
    # 8931 ``...STAGE1_BOSS_END`` at source_index 2/points 1, retired in the
    # client scene. The real boss 8904 of the room is still required to die.
    (35110, 1, 0): {
        'graph_sha': '1e010c5a23db8aaf3acc9bbbb7a7db93d705c7e3fc995cbc817ce01842711877',
        'required': (8931,),
        'markers': (
            {'script': 'DEVILDOM5_IRONWALL_STAGE1_BOSS_END.lua',
             'script_sha': '8eddd45eb9d0402750cf4ea4989be2387eca37afac4d9c282300a8fc98f1f314',
             'class_id': 103,
             'source': {'template': 8931, 'source_index': 2, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
    # 35110 ironwall stage2 part0 (final boss room): the class-103 8933
    # ``...STAGE2_BOSS_END`` at source_index 8/points 1 is retired in the client
    # scene and also blocks the 0xb8 check. The room's heart+hands boss shape is
    # pinned in BOSS_CORE_SOURCES, and the real heart 8905 still has to die.
    (35110, 2, 0): {
        'graph_sha': '1e010c5a23db8aaf3acc9bbbb7a7db93d705c7e3fc995cbc817ce01842711877',
        'required': (8933,),
        'markers': (
            {'script': 'DEVILDOM5_IRONWALL_STAGE2_BOSS_END.lua',
             'script_sha': '5d69f21fe6a46d0983b202d662eb257607bf2affb2e68144d35e9c3b0fd2a76a',
             'class_id': 103,
             'source': {'template': 8933, 'source_index': 8, 'points': [1], 'active': True,
                        'gage': True, 'ally': False, 'team': 1, 'no_drop': True, 'right': False,
                        'boss': False, 'boss_lines': 1, 'key_code': -1, 'source_key_code': -1,
                        'rate': 100, 'offset': [0, 0, 0]}},
        ),
    },
}


def part_marker_source(run, npc, row):
    """The matched declared marker source of this pinned room, else None."""
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)):
        return None
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
        if native['class_id'] == marker.get('class_id', 103) and native['is_npc'] is True:
            return source
    return None


def part_marker(run, npc, row):
    """True for a declared marker of this pinned room, verified by source."""
    return part_marker_source(run, npc, row) is not None


def part_marker_npc(run, npc):
    """True for a marker of the pinned room the run currently stands in."""
    if not part_marker_relaxation():
        return False
    row = PART_MARKERS.get((run.identity, run.stage, run.part))
    return row is not None and part_marker(run, npc, row)


def part_marker_gate(run, npcs, dead, required):
    """True when a pinned room's requirement is its own script markers.

    The client retires them inside its own scene, so no combat report exists.
    Every other living actor of the room must still be dead. A junction row may
    declare several ``exits``: the run takes whichever exit condition the source
    order reaches first, exactly like ``poll_ready`` does for any other part.
    """
    if not part_marker_relaxation():
        return False
    row = PART_MARKERS.get((run.identity, run.stage, run.part))
    if row is None:
        return False
    # A room whose whole roster is markers has an empty live fence, so this
    # gate would report "cleared" the moment the part loads. Its row must
    # settle through a retirement or the client's own end proof instead.
    if row.get('retirement_only'):
        return False
    exits = row.get('exits') or row['required']
    if not required or not set(required) <= set(exits):
        return False
    matched = [n for n in npcs if n['template'] in required]
    combat = set(row.get('combat', ()))
    if not matched or not all(n['template'] in combat or part_marker(run, n, row) for n in matched):
        return False
    live = [n for n in npcs if n['active'] and n.get('team', 1) != 0
            and not part_marker(run, n, row) and not cage_object(run, n)]
    return all(n['key'] in dead for n in live)


def part_marker_retirement(s, event, report):
    """Admit a pinned marker's native retirement instead of a combat death.

    In some pinned rooms the client ends its class-103 markers inside its own
    scene and sends only the original flag-255 expiry DTO. The combat pipeline
    rejects that shape, so the room's ``kind == 3`` requirement could never be
    met. Only a room whose row declares ``retirement`` consumes it, the actor
    is identified by its pinned source row, and the report must carry the
    initialized maximum. A real combat report of the same actor returns None
    and keeps the normal rewarded path.
    """
    if not part_marker_relaxation():
        return None
    run = getattr(s, 'dungeon_run', None)
    if run is None:
        return None
    row = PART_MARKERS.get((run.identity, run.stage, run.part))
    if row is None or not row.get('retirement'):
        return None
    npc = next((n for n in run.current['npcs'] if n.get('key') == report['index']), None)
    if npc is None:
        return None
    source = part_marker_source(run, npc, row)
    if source is None:
        return None
    if report['flag'] != 255:
        return None
    owner = s.account.uid
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    from els_server.domain.summons import valid_sentry_death
    if (event.event_id != 0x202 or event.kind != 0xad or event.performers != (0,)
            or event.uid != 2**64 - 1 or event.target_uid != 2**64 - 1 or event.payload_mode != 0
            or s.role != 'game' or s.phase != 'dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or not current_lease(s)
            or getattr(s, 'reward_transaction', None) is not None
            or getattr(s, 'reward_run_id', None) != run.run_id
            or frozenset(getattr(s, 'dungeon_participants', (owner,))) != frozenset((owner,))
            or s.account.character()['unit_type'] != 15
            or not valid_sentry_death(report, owner)
            or any(not math.isfinite(v) or abs(v) > 1e7 for v in report['xyz'])):
        return []
    from els_server.domain.formal_npc_hp import initialized_maximum
    hp = initialized_maximum(run, source)
    if npc.get('hp') != hp or report['hp_bits'] != struct.unpack('>I', struct.pack('>f', hp))[0]:
        return []
    key = npc['key']
    from els_server.domain.dungeon_lifecycle import death_ack, empty_reward_death_notice
    from els_server.protocol.protocol_codec import encode_event
    previous = run.defeated.get(key)
    if previous is not None:
        if previous != event.payload or npc.get('active') is not False:
            return []
        replies = [death_ack()]
        for reply in replies:
            encode_event(reply)
        return replies
    if npc.get('active') is not True:
        return []
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
    npc['active'] = False
    s.defeated_npcs = run.defeated
    s.part_end_notified = shadow.part_end_notified
    s.dungeon_clock.total = shadow.dungeon_clock.total
    s.dungeon_clock.started = shadow.dungeon_clock.started
    return replies


# Finite source-pinned rooms whose declared monsters can leave through the
# client's own native flag-255 expiry instead of a combat report. A row names
# the exact room, graph and templates; the actor must still be the source row
# the graph declares for that room, at its initialized maximum HP.
NATIVE_EXPIRY_ROOMS = {
    # 34760 主题公园 关卡1 第2段: two 8288 INCUBUS (points 29/31) are retired
    # by the client scene (balloon explosions) and report only the flag-255
    # expiry; 20261031-132142 leaves keys 26/28 alive until teardown while the
    # other seven hostiles report normal combat deaths.
    (34760, 0, 1): {
        'graph_sha': 'ff7a84eb43a539de17c9f0432ac2056f4ab29abd0fd3fdc11ef81a3a82123571',
        'scripts': {
            8287: ('DEVILDOM4_THEMEPARK_SUCUBUS.lua',
                   '85469bb6f5cb19bc53a678f6a3c6f8cf32059eccbfa29e2077021ca7ee894021'),
            8288: ('DEVILDOM4_THEMEPARK_INCUBUS.lua',
                   '9284345465595398d7e4c9059580565c392aed0ba165a032f928305992182ff2'),
        },
    },
    # 35080 goldcastle hub (stage0 part0): the five class-0 portal markers
    # 8827/8828/8829/8830/8832 are retired by the client inside its own scene.
    # Session 20261031-160216 sends one 0xad with flag 255 at 08:12:25.664 and
    # the combat path drops it, so the kind==3 condition never sees the doors
    # dead and all five actors stay alive until the map unloads. Only this hub
    # is pinned; stage3 part2's 8829 stays a part marker, never a retirement.
    (35080, 0, 0): {
        'graph_sha': '7be2bc7bc6636de6a7bb5d62e9e90e470ad65f6a5153f1e9617d75fe48fb549c',
        'scripts': {
            8827: ('DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY1.lua',
                   '065662cc5b21494cd0dd8b63659fcff9534152322c7514abff189629190e2b5d'),
            8828: ('DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY2.lua',
                   '94ffcee6462390f0415fc1d6b11f9c45e20878632fef391acb9220d145678977'),
            8829: ('DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY3.lua',
                   '68ff2da9e5e6dff090083b3389474bd26c5ac0c20196b759bb9fb81c1c9ab8c8'),
            8830: ('DEVILDOM5_GOLDCASTLE_STAGE_CLEAR_DUMMY4.lua',
                   'dddaafc01e4fc9dd08d4e87d96b542bf3a908e64ead78a73e3b4fd6151d8c7fe'),
            8832: ('DEVILDOM5_GOLDCASTLE_ELEVATOR_MANAGER.lua',
                   '0524d320b5095af4263f4dd26650b0ad8f9c5e4215de569d4365b801c27f9755'),
        },
    },
}


def declared_source(run, npc):
    """The graph row this roster actor was built from, else None."""
    stage = run.graph['stages'].get(str(run.stage))
    part = None if stage is None else stage['parts'].get(str(run.part))
    if part is None:
        return None
    for group in part['groups']:
        for source in group['npcs']:
            if (npc.get('template') != source['template']
                    or npc.get('start_point') != source['points'][0]
                    or any(npc.get(k) != v for k, v in source.items() if k != 'active')):
                continue
            return source
    return None


def native_expiry_retirement(s, event, report):
    """Admit a declared monster's native retirement in a pinned room.

    The client ends some actors inside its own scene (environment kills) and
    sends only the original flag-255 expiry DTO. The combat pipeline rejects
    that shape, so the room's clear fence could never see the actor dead and
    the part stalled. Only a room whose row pins the template consumes it, the
    actor must be the source row the graph declares, and the report must carry
    its initialized maximum. A normal combat report of the same actor returns
    None and keeps the rewarded path.
    """
    if not native_expiry_relaxation():
        return None
    run = getattr(s, 'dungeon_run', None)
    if run is None:
        return None
    row = NATIVE_EXPIRY_ROOMS.get((run.identity, run.stage, run.part))
    if row is None:
        return None
    if (run.graph['source_sha256'] != row['graph_sha']
            or run.graph != run.catalog.graph(run.identity)):
        return None
    npc = next((n for n in run.current['npcs'] if n.get('key') == report['index']), None)
    if npc is None or npc.get('template') not in row['scripts']:
        return None
    if npc.get('boss') is not False or npc.get('dynamic'):
        return None
    source = declared_source(run, npc)
    if source is None or source['boss'] or not source['active']:
        return None
    if report['flag'] != 255:
        return None
    from els_server.game_data import client_data
    script, script_sha = row['scripts'][source['template']]
    native = client_data().npc(source['template'])
    if (native['script'] != script
            or run.catalog.manifest['source_sha256'].get(script) != script_sha):
        return None
    owner = s.account.uid
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    from els_server.domain.summons import valid_sentry_death
    if (event.event_id != 0x202 or event.kind != 0xad or event.performers != (0,)
            or event.uid != 2**64 - 1 or event.target_uid != 2**64 - 1 or event.payload_mode != 0
            or s.role != 'game' or s.phase != 'dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or not current_lease(s)
            or getattr(s, 'reward_transaction', None) is not None
            or getattr(s, 'reward_run_id', None) != run.run_id
            or frozenset(getattr(s, 'dungeon_participants', (owner,))) != frozenset((owner,))
            or not valid_sentry_death(report, owner)
            or any(not math.isfinite(v) or abs(v) > 1e7 for v in report['xyz'])):
        return []
    from els_server.domain.formal_npc_hp import initialized_maximum
    hp = initialized_maximum(run, source)
    if npc.get('hp') != hp or report['hp_bits'] != struct.unpack('>I', struct.pack('>f', hp))[0]:
        return []
    key = npc['key']
    from els_server.domain.dungeon_lifecycle import death_ack, empty_reward_death_notice
    from els_server.protocol.protocol_codec import encode_event
    previous = run.defeated.get(key)
    if previous is not None:
        if previous != event.payload or npc.get('active') is not False:
            return []
        replies = [death_ack()]
        for reply in replies:
            encode_event(reply)
        return replies
    if npc.get('active') is not True:
        return []
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
    npc['active'] = False
    s.defeated_npcs = run.defeated
    s.part_end_notified = shadow.part_end_notified
    s.dungeon_clock.total = shadow.dungeon_clock.total
    s.dungeon_clock.started = shadow.dungeon_clock.started
    return replies
