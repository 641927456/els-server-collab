"""Prepare native career refreshes inside the shop's transaction."""
import struct


def notifications(db,uid,character,location,before,after,replayed):
    from els_server.domain.character_rules import default_slots
    from els_server.storage.inventory_state import load_items
    from els_server.storage.reward_state import validate_balances
    from els_server.protocol.career_messages import career_notice,stage_notice
    from els_server.protocol.dungeon_messages import return_user_sync
    from els_server.protocol.local_messages import skill_slots_initialization
    if character['uid']!=uid:raise ValueError('Career refresh owner mismatch')
    if not replayed:
        if character['revision']!=before['revision']:raise ValueError('Stale career refresh')
        character=dict(character,**after)
    row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(uid,)).fetchone()
    if row and len(row[0])!=88:raise ValueError('Invalid career skill preset')
    slots=struct.unpack('>22i',row[0]) if row else default_slots(character)
    balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
    items=load_items(db,uid)
    if not replayed and before['unit_class']!=character['unit_class']:
        answer=[career_notice(character,location,slots,balances,items)]
    else:
        answer=[return_user_sync(location,slots,balances,items,character,inventory_updates=[])]
    if not replayed and (before['transcendence'],before['master'])!=(character['transcendence'],character['master']):
        answer.append(stage_notice(character))
    return answer+[skill_slots_initialization(slots,uid,character)]
