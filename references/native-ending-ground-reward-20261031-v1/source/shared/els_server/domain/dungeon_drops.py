"""Ground spawns and pickup acknowledgements for the verified DX11 reader.

C25B90 CF -> State v3C0 BA6560 -> 2C1AC10 -> Game v2F0 1AB5380.
The CF layout is shared by verified bag potions, immediate food and ED coins.
Physical spawn and pickup are separate gates; spawning grants no inventory/ED.
"""
from els_server.domain.hunter_chest_rules import ground_templates
from els_server.domain.fishing_bait_loot import TEMPLATES as BAIT_TEMPLATES
import math
import struct
from els_server.protocol.protocol_codec import Event

def ground_drop_notice(drop_id, xyz, native_tail=(0, 0, 0),uid=1001,*,template=77000):
    from els_server.domain.drop_pickup import GROUND_TEMPLATES
    from els_server.domain.dungeon_equipment_loot_rules import TEMPLATES as EQUIPMENT_LOOT_TEMPLATES
    from els_server.domain.dungeon_loot_catalog import TEMPLATES as NORMAL_LOOT_TEMPLATES,descriptor
    from els_server.domain.dungeon_source_loot import TEMPLATES as SOURCE_TEMPLATES,descriptor as source_descriptor
    from els_server.domain.native_script_loot import TEMPLATES as SCRIPT_TEMPLATES,descriptor as script_descriptor
    if type(template) is not int or template not in GROUND_TEMPLATES|EQUIPMENT_LOOT_TEMPLATES|NORMAL_LOOT_TEMPLATES|SOURCE_TEMPLATES|SCRIPT_TEMPLATES|ground_templates()|BAIT_TEMPLATES:raise ValueError('Unverified ground template')
    if template in SCRIPT_TEMPLATES:script_descriptor(template)
    if template in SOURCE_TEMPLATES:source_descriptor(template)
    if template in NORMAL_LOOT_TEMPLATES:descriptor(template)
    from els_server.domain.dungeon_material_loot_catalog import TEMPLATES as MATERIAL_TEMPLATES,descriptor as material_descriptor
    if template in MATERIAL_TEMPLATES:material_descriptor(template)
    if type(drop_id) is not int or not 1 <= drop_id < 2**31:
        raise ValueError('Drop instance ID bound')
    if not isinstance(xyz, (tuple, list)) or len(xyz) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1_000_000 for v in xyz):
        raise ValueError('Drop position bound')
    if not isinstance(native_tail, (tuple, list)) or len(native_tail) != 3 or any(type(v) is not int or not -2**31 <= v < 2**31 for v in native_tail):
        raise ValueError('Drop native context bound')
    # i32 template, i32 instance ID, bool, float, set<Q>, signed byte.
    # Source 1032000 confirms first i32 is used for template lookup and second
    # identifies the drop. The other fields retain the parsed prototype values.
    # Set<Q> semantics and the three trailing integers remain under investigation.
    payload = struct.pack('>Iii?fIQb3f3i', 1, template, drop_id, False, 0.0, 1, uid, 0, *xyz, *native_tail)
    return Event(0x201, kind=0xcf, payload=payload)

def ground_pickup_notice(drop_id,uid=1001,*,template=77000,ed=0,bonus_ed=0):
    from els_server.domain.drop_pickup import GROUND_TEMPLATES,GROUND_ED
    from els_server.domain.dungeon_equipment_loot_rules import TEMPLATES as EQUIPMENT_LOOT_TEMPLATES
    from els_server.domain.dungeon_loot_catalog import TEMPLATES as NORMAL_LOOT_TEMPLATES,descriptor
    from els_server.domain.dungeon_source_loot import TEMPLATES as SOURCE_TEMPLATES,descriptor as source_descriptor
    from els_server.domain.native_script_loot import TEMPLATES as SCRIPT_TEMPLATES,descriptor as script_descriptor
    if type(template) is not int or template not in GROUND_TEMPLATES|EQUIPMENT_LOOT_TEMPLATES|NORMAL_LOOT_TEMPLATES|SOURCE_TEMPLATES|SCRIPT_TEMPLATES|ground_templates()|BAIT_TEMPLATES:raise ValueError('Unverified ground template')
    if template in SCRIPT_TEMPLATES:script_descriptor(template)
    if template in SOURCE_TEMPLATES:source_descriptor(template)
    if template in NORMAL_LOOT_TEMPLATES:descriptor(template)
    from els_server.domain.dungeon_material_loot_catalog import TEMPLATES as MATERIAL_TEMPLATES,descriptor as material_descriptor
    if template in MATERIAL_TEMPLATES:material_descriptor(template)
    if any(type(v) is not int or not 0<=v<=2**31-1 for v in (ed,bonus_ed)) or (template not in GROUND_ED and (ed or bonus_ed)):raise ValueError('Ground currency amount')
    if type(drop_id) is not int or not 1<=drop_id<2**31:
        raise ValueError('Pickup notice identity bound')
    # C4E1C0 -> DC6FD0 reads map<Q, pair<i32, i32>>. Both integers
    # are required before the trailing byte/bool/u16, even for a potion.
    # 1AB6160 -> 1AE1F20 consumes the pair only for currency templates;
    # potion quantity comes from the subsequent D3 inventory delta.
    # 1AB6160 recognizes the three coin IDs; 1AE1F20 adds both i32 values
    # to the local owner's ED. The second value is the committed bonus ED.
    # Food instead follows 1AE1750 -> 1AB9D20 and its native effect table.
    return Event(0x201,kind=0xd2,payload=struct.pack('>Qiib?QIQiib?H',uid,template,drop_id,0,False,0,1,uid,ed,bonus_ed,0,False,0))

potion_drop_notice=ground_drop_notice
potion_pickup_notice=ground_pickup_notice

def pickup_inventory_notice(items):
    from els_server.domain.inventory_items import inventory_payload
    # BA6C70 -> DD46E0 -> original Unit inventory updater 197DAD0.
    return Event(0x201,kind=0xd3,payload=inventory_payload(items))
