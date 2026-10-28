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

Disable by setting ``script_gate_relaxation`` false or deleting the config.
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
        return {'script_gate_relaxation': False}
    if rule.get('schema_version') != 1 or rule.get('provenance') != 'local_dungeon_flow':
        raise ValueError('Local dungeon flow identity')
    switch = rule.get('script_gate_relaxation', False)
    if type(switch) is not bool:
        raise ValueError('Local dungeon flow switch')
    return {'script_gate_relaxation': switch}


def script_gate_relaxation():
    return rules()['script_gate_relaxation']


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
