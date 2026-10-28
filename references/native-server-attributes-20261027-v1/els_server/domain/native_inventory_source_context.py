"""Inventory context of the same owned complete Unit copy, not a raw default.

The typed Unit constructor binds inventory.owner to its Unit. The original
copy binds each instance318 to that owner and copies306 to Unit7BD. These
values describe the complete-copy source; actual written-copy attribution is
still required by the delivery cursor before publishing calculated results.
"""
from els_server.domain.native_current_character_inputs import build as current_inputs
from els_server.domain.native_worn_item_inputs import SPECIAL_IDS


def build(snapshot, *, previous_rank):
    from els_server.protocol.local_messages import character_unit_fields
    current=current_inputs(snapshot,previous_rank=previous_rank)
    fields=character_unit_fields(items=snapshot['items'],character=snapshot['character'],
        slots=snapshot['ordinary_slots'])
    status=dict(fields)['0x306']
    if type(status)is not bytes or len(status)!=1 or status[0]not in(0,1):
        raise ValueError('Qualified original copied inventory owner status required')
    #198B8D0 reads Game.user30 only for these precise template IDs. Outside
    #that branch its operand is irrelevant. Do not infer a player authority
    #level or silently include a special item while its source is unqualified.
    if any(row['template']in SPECIAL_IDS for row in snapshot['items']):
        raise ValueError('Special item requires independently qualified user30 source')
    return dict(character_inputs=current,owner_status=(True,bool(status[0])),
        special_mode_level=0,special_mode_operand_is_relevant=False)
