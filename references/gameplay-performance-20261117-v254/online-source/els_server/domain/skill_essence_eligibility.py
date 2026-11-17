"""Equipped sources for native periodic and special-active essence consumers.

CN 260923 option 224304..224307 (set 30156, four pieces) populates
option+548. Native 193FE00 sends 460 for skill types 7/14/15/16.
Damage, effect lifetime and casting remain in the original client.
"""
from els_server.game_data import client_data
from els_server.storage.inventory_state import load_items
from els_server.domain.ordinary_accessories import accepts_equipped,definitions
from els_server.domain.item_expiration import expired
from els_server.domain.equipment_requirements import class_matches


def _fire_set_equipped(db,character,*,now):
    selected=0
    if character['unit_type']==10:
        from els_server.storage.luciel_state import state,active_state
        from els_server.domain.tutorial_accessory import effective_style
        selected=effective_style(dict(character,luciel_style=state(db,character['uid'])['style'],
                                      luciel_active_unit=active_state(db,character['uid'])['active_unit']))
    data=client_data();rules=definitions();count=0
    for item in load_items(db,character['uid'],bag_groups=(9,)):
        if not accepts_equipped(item) or expired(item,now=now):continue
        rule=rules[item['template']]
        if int(item['slot'] not in rule['main_slots'])!=selected:continue
        if rule['companion_only'] and character['unit_type']!=10:continue
        record=data.item(item['template'])['record']
        if not class_matches(character['unit_class'],record[0xd3]):continue
        if int.from_bytes(record[0x24:0x28],'little')==30156:count+=1
    return count>=4


def eligible(db,character,*,now,periodic=False):
    if _fire_set_equipped(db,character,now=now):return True
    from els_server.storage.titles import equipped
    from els_server.domain.title_essence import rule_for
    from els_server.domain.titles import definition
    from els_server.domain.title_option_data import catalog
    title=equipped(db,character['uid'],now)
    if not title:return False
    if periodic:return rule_for(title) is not None
    options=catalog()
    return any(options[value].get('m_fUseStoneForSpecialActiveIncreaseRate',0)>0
               and not options[value].get('PVP_ONLY')
               for key,value in definition(title).get('SOCKET_OPTION',{}).items()
               if key!='0' and value in options)
