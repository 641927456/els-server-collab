"""Read-only evidence from accepted combat reports and existing server gates."""
from collections import Counter
from math import isclose
from time import monotonic

from els_server.anti_cheat import dungeon_signal, summon_received

SENTRY_TEMPLATE = 384
TRACKED_SUMMONS = frozenset((SENTRY_TEMPLATE, 2958, 2959, 2960, 2961))
SUMMON_BURST_THRESHOLD = 3
SUMMON_WINDOW_SECONDS = 2.0


def prepare_summon_observation(session, templates, *, run_id, map_id, scope, sequence):
    """Count qualified entity requests for audit without inferring skill cooldown."""
    app = getattr(session, 'application', None)
    detector = getattr(app, 'anti_cheat', None)
    if detector is None:
        return None
    requested = Counter(template for template in templates if template in TRACKED_SUMMONS)
    if not requested:
        return None
    actor = (session.account.uid, scope, run_id)
    previous = getattr(session, '_combat_summon_observation', None)
    now = monotonic()
    active = {}
    if previous is not None and previous[0] == actor:
        active = previous[1].copy()
    for template, count in requested.items():
        times = tuple(at for at in active.get(template, ()) if now - at < SUMMON_WINDOW_SECONDS)
        if len(times) + count > SUMMON_BURST_THRESHOLD:
            detector.record('player_summon_burst', session.account.account_id, scope=scope, outcome='observed',
                            character_id=actor[0], run_id=run_id, map_id=map_id,
                            request_sequence=sequence, npc_template=template,
                            recent_summons_at_least=len(times), requested_summons=count)
        # Only the most recent samples can change the next threshold check.
        active[template] = (times + (now,) * min(count, SUMMON_BURST_THRESHOLD))[-SUMMON_BURST_THRESHOLD:]
    return actor, active


def dungeon_summon_observation(session, templates, sequence):
    run = session.dungeon_run
    return prepare_summon_observation(session, templates,
        run_id=run.run_id if run is not None else session.reward_run_id,
        map_id=run.identity if run is not None else session.dungeon_id,
        scope='dungeon', sequence=sequence)


def early_timed_condition(session, run, selected_flags):
    if run.started_at is None or run.encounter is not None or run.chaos is not None:
        return
    asserted = [condition for flag, condition in zip(selected_flags, run.current['conditions']) if flag]
    if not asserted or any(condition['kind'] != 6 for condition in asserted):
        return
    required = min(condition['seconds'] for condition in asserted)
    elapsed = run.clock() - run.started_at
    # Ignore contacts close to the server gate. The native client and server
    # start their part clocks at different points of the load handshake.
    if 0 <= elapsed and required - elapsed >= 1:
        dungeon_signal(session, 'premature_timed_condition', elapsed_seconds=round(elapsed, 3),
                       required_seconds=required)


def damage_conflict(statistics, uid):
    damage = statistics['damage']
    # The six fields are accumulated separately and encoded as binary32.
    for scope, offset in (('total', 0), ('self', 3)):
        total, boss, normal = (values.get(uid, 0.0) for values in damage[offset:offset+3])
        if not isclose(total, boss + normal, rel_tol=0.01, abs_tol=1.0):
            return dict(damage_scope=scope, total_damage=total, boss_damage=boss, normal_damage=normal)
    return None


def dungeon_damage(session, statistics):
    uid = session.account.uid
    conflict = damage_conflict(statistics, uid)
    if conflict is not None:
        dungeon_signal(session, 'inconsistent_damage_totals', outcome='observed', **conflict)
    run = session.dungeon_run
    map_id = run.identity if run is not None else session.dungeon_id
    cap = session.application.config.anti_cheat_max_solo_damage_per_second.get(map_id)
    if cap is None or session.dungeon_participants != frozenset((uid,)):
        return
    # The statistic is cumulative. Compare it to the entire run's server
    # clock, using the upper end of the integer-second bucket.
    seconds = session.dungeon_clock.seconds() + 1
    total = statistics['damage'][0].get(uid, 0.)
    if total > cap * seconds:
        dungeon_signal(session, 'high_solo_damage_rate', outcome='observed',
                       total_damage=total, elapsed_upper_seconds=seconds, configured_damage_per_second=cap)


def sentry_summon(session, single_template):
    if single_template != SENTRY_TEMPLATE:
        return
    received = summon_received(session)
    if received is None:
        return
    minimum = session.application.config.anti_cheat_sentry_min_interval_ms
    if not minimum:
        return
    run = session.dungeon_run
    generation = (session.reward_run_id, run.stage, run.part, run.started_at) if run is not None else (
        session.reward_run_id, session.gate_stage, 0)
    previous = getattr(session, '_anti_cheat_sentry', None)
    streak = 0
    gap = 0.
    if previous is not None and previous[0] == generation:
        gap = (received - previous[1]) * 1000
        if 0 < gap < minimum:
            streak = previous[2] + 1
            if streak == 2:
                dungeon_signal(session, 'rapid_sentry_summons', outcome='observed', skill_id=25000,
                               npc_template=single_template, intervals=streak,
                               previous_interval_ms=round(previous[3], 3), interval_ms=round(gap, 3),
                               configured_minimum_ms=minimum)
    session._anti_cheat_sentry = (generation, received, streak, gap)
