"""Stage-transition persistence for a player's own summon (哨兵).

The client destroys the server-spawned sentry actor when a stage transition
rebuilds the scene from the cached 0xB2 population packet, and reports nothing.
The server is the actor authority, so it re-creates the summon in the new room
from the original request.

This lives beside ``summons`` instead of inside it: the accepted release profile
pins ``els_server/domain/summons.py`` byte for byte (the file is its own source),
so the request/spawn primitives there cannot grow. The state it needs
(``run.summon_payloads`` / ``run.respawn_payloads`` / ``run.summon_key_ceiling``)
is already allocated by ``dungeon_routes.DungeonRun``.

Disable ``STAGE_SUMMON_PERSISTENCE_ENABLED`` to restore the pre-fix wipe.
"""
from els_server.domain.summons import sentry_spawn


STAGE_SUMMON_PERSISTENCE_ENABLED=True


def retain_sentry(run, key, payload):
    if run is None or not STAGE_SUMMON_PERSISTENCE_ENABLED:return
    run.summon_payloads[key]=bytes(payload)
    # A sentry identity is never re-issued inside one run: the client's own
    # expiry report for the destroyed actor can outlive the stage rebuild and
    # would otherwise be applied to the summoned actor that took its key.
    run.summon_key_ceiling=max(getattr(run,'summon_key_ceiling',16),key+1)


def carry_summons(session):
    """Move still-live sentries out of a stage's retired identity space."""
    run=session.dungeon_run
    if run is None or not STAGE_SUMMON_PERSISTENCE_ENABLED:return
    pending=getattr(run,'summon_payloads',{})
    solo=frozenset(getattr(session,'dungeon_participants',(session.account.uid,)))==frozenset((session.account.uid,))
    run.respawn_payloads={key:payload for key,payload in pending.items()
                          if solo and key in session.summon_keys and key not in session.summon_deaths}
    run.summon_payloads={}


def respawn_summons(session):
    run=session.dungeon_run
    pending=getattr(run,'respawn_payloads',None) if run is not None else None
    if not pending:return []
    run.respawn_payloads={}
    # Late import: dungeon_spawns reaches the session's roster, not this module.
    from els_server.domain.dungeon_spawns import occupied_slots
    reply=[]
    for key,payload in sorted(pending.items()):
        if occupied_slots(session)>=80:break
        session.summon_next_key=max(session.summon_next_key,getattr(run,'summon_key_ceiling',16))
        while (session.summon_next_key in run.reserved_keys or session.summon_next_key in session.summon_keys
               or session.summon_next_key in run.summon_payloads):
            session.summon_next_key+=1
        try:notice=sentry_spawn(payload,session.account.uid,session.summon_next_key)
        except ValueError:continue
        session.summon_keys.add(session.summon_next_key)
        retain_sentry(run,session.summon_next_key,payload)
        session.summon_next_key+=1
        reply.append(notice)
    return reply
