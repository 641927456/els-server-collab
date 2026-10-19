"""Native F4 selection identities for verified ordinary reward items."""
from els_server.domain.seal_quests import sequence

def options(quest):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES
    from els_server.game_data import client_data
    config=quest['SelectReward'];rows=sequence(config.get('m_vecSelectItem',{}))
    if sequence(config.get('m_vecItem',{})):raise ValueError('Unknown quest selection field')
    if not rows:return ()
    if type(config.get('m_iSelectionCount')) is not int or config['m_iSelectionCount']!=1:raise ValueError('Unsupported quest selection count')
    ids=set()
    for r in rows:
        t=r['m_iItemID']
        if type(t) is not int or t in ids or t not in VERIFIED_TEMPLATES:raise ValueError('Unverified quest selection item')
        if r['m_iPeriod'] or r['m_sSocketOption'] or type(r['m_iQuantity']) is not int or not 1<=r['m_iQuantity']<=99:raise ValueError('Unsupported quest selection item')
        # D1CEF0 filters item bytes D2/D3 by unit and class rank tables.
        # Restricted choices remain limited to exact source quest13; the claim
        # rechecks the current SQL character through the native class predicate.
        if any(client_data().item(t)['record'][o] for o in (0xd2,0xd3)):
            from els_server.domain.town_dialogue import catalog
            from els_server.domain.acquisition_policy import require_acquirable
            if quest!=catalog()['quests']['13']:raise ValueError('Restricted quest selection item')
            require_acquirable(t)
        ids.add(t)
    return rows

def selected_rewards(quest,choices=(),*,character=None):
    rows=options(quest)
    if not isinstance(choices,(tuple,list)):raise ValueError('Quest selection identities')
    if len(choices)!=(1 if rows else 0):raise ValueError('Quest selection count')
    if not rows:return ()
    pair=choices[0]
    if (not isinstance(pair,(tuple,list)) or len(pair)!=2
        or any(type(v) is not int for v in pair) or pair[0]!=pair[1]):raise ValueError('Quest selection identity')
    found=next((r for r in rows if r['m_iItemID']==pair[0]),None)
    if found is None:raise ValueError('Quest selection outside reward list')
    from els_server.game_data import client_data
    record=client_data().item(found['m_iItemID'])['record']
    unit,required=record[0xd2],record[0xd3]
    if unit or required:
        from els_server.domain.equipment_requirements import class_matches
        if (not isinstance(character,dict) or type(character.get('unit_type')) is not int
            or type(character.get('unit_class')) is not int
            or not class_matches(character['unit_class'],required)
            or client_data().unit(character['unit_class'])['unitType']!=character['unit_type']
            or unit and unit!=character['unit_type']):
            raise ValueError('Quest selected item career requirement')
    return (found,)
