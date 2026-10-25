"""Resolve two original Lithia script retirements without a client DTO hook.

Original 16E1760 -> 19E1ED0 preserves its zero index; 16D2090 enriches the
actor position without adding its UID. Do not treat every zero as a new kill.
The paired source graph and original LineMap identify these two stationary
controllers only. All other ambiguous reports retain the existing rejection.
"""
from els_server.domain.formal_npc_hp import initialized_maximum
import struct

SOURCE_SHA256 = '58100b652696632565633fc432e4bc070cd1b3587a5503f05cb7d257cd24d640'
# Tutorial_Lithia_Stage0_LineMap.lua, plaintext SHA256
# 8f5772927b412c57e80216a5e53d31a5bca0cd7556fff42c4791a7155a0953a4.
# Dummy5 stays at AddStartPos(8). END's original start reaction calls
# GetStartPosition(11)/SetPositionForce, despite its spawn START_POS=12.
CONTROLLERS = {
    2: (9288, 8, (9246.69, 301.0, 46743.0), False),
    3: (9289, 12, (10638.9, 301.0, 46743.0), True),
}


def original_controller(session, run, report):
    """Return a uniquely witnessed controller, never guess a zero-index UID.

    Caller has checked event ownership, phase and the active run identity.
    Keeping those checks here also fences use by another future caller.
    """
    if (session.first_story_entry is None
            or session.first_story_entry['run'] is not run
            or session.dungeon_run is not run
            or session.phase != 'dungeon_active'
            or not session.dungeon_substage_synced
            or session.account.character()['unit_type'] != 15
            or run.identity != 35240 or run.stage != 0
            or run.graph['source_sha256'] != SOURCE_SHA256
            or run.part not in CONTROLLERS):
        return None
    if (report['index'] != 0 or report['flag'] != 255
            or report['status'] != 1
            or report['source'] != 2**64-1 or report['killer'] != 2**64-1
            or report['last_uid'] != 0 or report['extra_uid'] != 0
            or report['contribution'] or report['counters']
            or report['readiness'] != {session.account.uid: 0}):
        return None
    template, start_point, position, no_drop = CONTROLLERS[run.part]
    # Compare original wire float32 values exactly, not a generous XYZ radius.
    expected = struct.pack('>6f', 0.0, 0.0, 0.0, *position)
    if struct.pack('>6f', *report['xyz']) != expected:
        return None
    matches = [npc for npc in run.current['npcs']
               if npc['template'] == template and npc['active']
               and npc['start_point'] == start_point
               and npc['hp'] == initialized_maximum(run,npc)
               and report['hp_bits'] == struct.unpack('>I',struct.pack('>f',initialized_maximum(run,npc)))[0]
               and npc['no_drop'] is no_drop and npc['offset'] == [0, 0, 0]]
    return matches[0] if len(matches) == 1 else None
