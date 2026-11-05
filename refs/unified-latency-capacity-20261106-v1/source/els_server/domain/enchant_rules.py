"""Native-verified enchant counting and normal pricing; no inventory mutation."""
from els_server.game_data import client_data

def attribute_count(slots):
    if len(slots)!=4 or any(type(v) is not int or not -(2**31)<=v<2**31 for v in slots):
        raise ValueError('Exactly four native i32 attribute slots required')
    # 2ECE240 reads inventory+1C,+20,+24,+28 and counts positive IDs.
    return sum(v>0 for v in slots)

def normal_item_quote(template,slots):
    data=client_data();item=data.item(template)
    if item['item_type'] not in (1,2):raise ValueError('Weapon or armor required')
    raw=item['record'];level=raw[0xd9] or raw[0xd1];grade=(item['flags4']>>20)&15
    count=attribute_count(slots);weapon=item['item_type']==1
    price=data.enchanting.normal_ed_cost(count,weapon,level,grade)
    return dict(template=template,existing_count=count,is_weapon=weapon,equipment_level=level,
                grade=grade,normal_ed_cost=price,fee_waiver_applied=False,
                eligibility_verified=False,authorizes_transaction=False,
                source='Native 2E8A040 argument mapping and GetAttribEnchantRequiredED')


def attribute_quote(template,slots,target):
    """Read-only native UI inputs and restrictions; never authorizes a mutation."""
    data=client_data();catalog=data.enchanting
    compatible=catalog.elements_compatible(slots,target)
    quote=normal_item_quote(template,slots);definition=data.item(template)
    capacity=definition['record'][0xd8]
    open_slot=slots.index(0) if 0 in slots else None
    available=0<capacity<=4 and quote['existing_count']<capacity and open_slot is not None
    material=None
    if available and compatible:
        material=catalog.normal_material_cost(quote['is_weapon'],quote['existing_count'],quote['equipment_level'],quote['grade'])
        material['template']=catalog.material_template(target)
        # All seven material templates exist in the pinned current catalog.
        material['name']=data.item(material['template']).get('name')
    return dict(**quote,target_element=target,element_compatible=compatible,
                template_slot_capacity=capacity,first_empty_slot=open_slot,
                can_add_by_slot_rules=available and compatible,material=material,
                random_result_pending=target==7,
                source_rules='Native 2E881F0 / 1A080B0 / 1A083C0; quote only, ownership and full eligibility are not checked')
