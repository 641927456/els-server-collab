"""Auto-accept the Lv.99 El Resonance unlock quest (local policy).

The client does not offer quest 37100 by itself at level 99, so the server
accepts it once the character reaches 99 and pushes the normal new-task
notification. Claiming it still runs the ordinary quest transaction.
"""
from els_server.protocol import quest_messages as wire

QUEST = 37100
START_NPC = 10017


def periodic(s):
    from els_server.domain.quest_flow import enabled
    if not enabled(s) or s.role != 'game' or s.phase != 'town_ready':
        return []
    character = s.account.character()
    if character is None or character['level'] < 99:
        return []
    from els_server.domain.quest_flow import store
    state = store(s).snapshot()
    if any(row['id'] == QUEST for row in state['active']):
        return []
    if any(row['id'] == QUEST for row in state['completed']):
        return []
    def encode(result):
        row = next((row for row in result['state']['active'] if row['id'] == QUEST), None)
        return [wire.accepted(row)] if row else []
    try:
        result = store(s).action('accept', {'quest': QUEST, 'npc': START_NPC},
                                 s.shop_session_id+':resonance-unlock:'+str(s.account.uid), encode)
    except (ValueError, KeyError, TypeError):
        return []
    return list(result.get('events', ()))
