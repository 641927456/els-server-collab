"""Retire superseded career tasks in their caller's existing transaction."""
from els_server.domain.seal_quests import quest_catalog,superseded_by_career


def obsolete_ids(db,uid,character):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return ()
    rows=tuple(db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,)))
    if not rows:return ()
    catalog=quest_catalog();removed=[]
    for q, in rows:
        quest=catalog.quests.get(q)
        if quest is not None and superseded_by_career(character,quest):removed.append(q)
    return tuple(removed)


def retire(db,uid,character):
    if not db.in_transaction:raise ValueError('Career task cleanup requires its original writer')
    removed=obsolete_ids(db,uid,character)
    if removed:db.executemany('DELETE FROM character_quests WHERE owner=? AND quest=?',((uid,q)for q in removed))
    return removed


def live_removals(db,uid,character,removed=()):
    """Native removals for retired careers and accepted, now-owned seal tasks."""
    from els_server.domain.seal_quests import skill_quest_hidden
    from els_server.domain.skill_unlocks import unsealed_skills
    from els_server.protocol.quest_messages import cancelled
    if character['uid']!=uid:raise ValueError('Quest cleanup owner mismatch')
    rows=tuple(db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,)))if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='character_quests'").fetchone()else ()
    saved={q for q, in rows};catalog=quest_catalog();seals=unsealed_skills(character)
    ids={q for q in removed if q not in saved}
    for q in saved:
        definition=catalog.quests.get(q)
        if definition is not None and skill_quest_hidden(character,definition,seals):ids.add(q)
    return [cancelled(q)for q in sorted(ids)]
