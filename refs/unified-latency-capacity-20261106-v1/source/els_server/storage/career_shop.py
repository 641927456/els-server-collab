"""Prepare native career refreshes inside the shop's transaction."""
import struct


def notifications(db,uid,character,location,before,after,replayed):
    from els_server.domain.character_rules import default_slots
    from els_server.storage.inventory_state import load_items
    from els_server.storage.reward_state import validate_balances
    from els_server.protocol.career_messages import career_notice,stage_notice,current_skill_notices
    from els_server.protocol.dungeon_messages import return_user_sync
    from els_server.protocol.local_messages import skill_slots_initialization
    if character['uid']!=uid:raise ValueError('Career refresh owner mismatch')
    original_account=('account_id'in character,character.get('account_id'))
    if not replayed:
        if character['revision']!=before['revision']:raise ValueError('Stale career refresh')
        character=dict(character,**after)
    # The same career writer may have raised the account Collection rank.
    # Refresh this field from that writer, not the caller's pre-change view.
    from els_server.storage.el_search_collection import snapshot as collection_snapshot
    saved_owner=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
    if saved_owner is None:raise ValueError('Career refresh owner mapping required')
    if original_account[0]and(type(original_account[1])is not int or original_account[1]!=saved_owner[0]):raise ValueError('Career caller account identity')
    if 'account_id'in character and(type(character['account_id'])is not int or character['account_id']!=saved_owner[0]):raise ValueError('Career refresh account identity')
    if saved_owner is not None:
        from els_server.storage.seal_quests import load_character
        current=load_character(db,uid,saved_owner[0])
        if any(current[k]!=character[k]for k in('unit_class','level','revision')):raise ValueError('Career refresh projection mismatch')
        for key in('account_id','title','title_completed_quests','skill_traits','ordinary_skill_pages','force_inventory','force_slots','cleared_dungeons'):
            character[key]=current[key]
        collection=collection_snapshot(db,uid,saved_owner[0])
        if collection is not None:character=dict(character,el_search_collection=collection)
    row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(uid,)).fetchone()
    if row and len(row[0])!=88:raise ValueError('Invalid career skill preset')
    slots=struct.unpack('>22i',row[0]) if row else default_slots(character)
    balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
    items=load_items(db,uid)
    if not replayed and before['unit_class']!=character['unit_class']:
        answer=[career_notice(character,location,slots,balances,items)]
    elif not replayed:
        answer=[return_user_sync(location,slots,balances,items,character,inventory_updates=[])]
    else:
        # The live actor already has the current career. Replaying D9 also
        # reopens unrelated entry/unlock UI; current ranks/slots follow below.
        answer=[]
    if not replayed and (before['transcendence'],before['master'])!=(character['transcendence'],character['master']):
        answer.append(stage_notice(character))
    rebuild=(not replayed and before['unit_class']==character['unit_class'] and not before['master'])
    return answer+current_skill_notices(character,slots,rebuild=rebuild)+[skill_slots_initialization(slots,uid,character)]
