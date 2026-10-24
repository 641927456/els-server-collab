"""Auto-accept eligible Lv.99 region entry tasks for every character.

The client does not offer these entry tasks by itself once a character reaches
Lv.99 in the current build, so the server accepts each eligible task once and
pushes the normal new-task notification. Eligibility, objectives, claims and
map admission still run through the ordinary region/quest storage.
"""
from contextlib import closing
import sqlite3
import time


def entries():
    from els_server.domain.region_quests import region_catalog
    result = set()
    for row in region_catalog().data['regions'].values():
        quest = row['requirement'].get('RequireQuestID')
        if quest:
            result.add(int(quest))
    return tuple(sorted(result))


def periodic(s):
    from els_server.domain.quest_flow import enabled
    if not enabled(s) or s.role != 'game' or s.phase != 'town_ready':
        return []
    if s.account.store is None or s.account.store.uid != s.account.uid:
        return []
    character = s.account.character()
    if character is None or character['level'] != 99:
        return []
    location = s.account.get_location()
    from els_server.domain.boosting_2026_region_entries import resume
    from els_server.protocol.protocol_codec import encode_event
    with closing(sqlite3.connect(s.account.store.path, timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        messages = resume(db, s.account.uid, s.account.account_id, now=int(time.time()),
                          location=('town', location['map']), entries=entries())
        for message in messages:
            encode_event(message)
    return messages
