"""Same-snapshot main equipment sources shared by the original collectors.

Every mutable Unit context is explicit. This acquires no database generation,
changes no item and does not combine the separate ordinary/resistance orders.
Secondary Artifact equipment and non-item sources retain their own consumers.
"""
from dataclasses import dataclass
from els_server.domain import native_worn_source_inputs as inputs
from els_server.domain import native_worn_item_inputs as worn
from els_server.domain import native_armor_option_activation as armor
from els_server.domain import native_item_attribute_sources as item_sources
from els_server.domain import native_set_sources as sets
from els_server.domain import native_set_pieces as pieces
from els_server.domain import native_set_conditions as conditions
from els_server.domain import native_option_colors as colors
from els_server.domain.native_item_attribute_options import canonical_circuit_state
from els_server.domain.native_option_collector import OptionSource


@dataclass(frozen=True)
class WornContext:
    selector:int
    armor_selector:int
    mode_side:bool
    owner_status:tuple
    special_mode_level:int
    preset:int
    registrations:tuple
    main_overrides:dict
    secondary_overrides:dict
    include_bit7:bool
    force900404:bool
    rank_factor:float


def build(items,character,context,*,at):
    if type(context)is not WornContext:
        raise ValueError('Complete qualified native worn context required')
    if type(items)is not tuple or type(character)is not dict:
        raise ValueError('Same-snapshot owned items and character required')
    from els_server.game_data import client_data
    data=client_data();main,secondary=inputs.equipment_vectors(items)
    lookup={row['uid']:row for row in items}
    records={uid:data.item(lookup[uid]['template'])['record']for uid in main+secondary}
    bound={uid:inputs.bind(lookup[uid],records[uid],colors.catalog(),
        owner_status=context.owner_status,at=at)for uid in main+secondary}
    membership=inputs.category77_membership(tuple(row['template_id']for row in bound.values()))
    def select(vector,selector):
        return worn.collect(vector,bound,(),(),selector=selector,
            current_class=character['unit_class'],feature77=membership,
            special_mode_level=context.special_mode_level,mode_side=context.mode_side)
    selected=select(main,context.selector)
    secondary_selected=select(secondary,context.selector)
    activation=armor.flags(tuple(bound[uid]for uid in select(main,context.armor_selector)),records)
    circuit_state=canonical_circuit_state()
    callbacks=tuple(source for uid in selected
        for source in item_sources.callbacks(bound[uid],records[uid],
            character_level=character['level'],category77=membership[bound[uid]['template_id']],
            activation=activation,circuit_state=circuit_state,rank_factor=context.rank_factor))
    definitions=sets.catalog()['definitions']
    artifact=character['artifact']
    counts=pieces.collect(tuple(bound[uid]for uid in selected),tuple(bound[uid]for uid in secondary_selected),
        definitions,context.registrations,preset=context.preset,selector=context.selector,
        main_overrides=context.main_overrides,fashion_overrides=context.secondary_overrides,
        include_bit7=context.include_bit7,profile_level=artifact['evolution']if artifact else 0,
        force900404=context.force900404)
    set_callbacks=[];active_sets=[]
    for identity,(qualifier,count)in sorted(counts.items()):
        definition=definitions[identity]
        ids=conditions.select_effect_ids(definition['ordinary'],definition['qualified'],qualifier,count)
        if ids:
            active_sets.append(identity)
            set_callbacks.append(OptionSource(ids,definition['level_override']if definition['level_override']>0
                else character['level'],0,context.rank_factor,1.))
    deadlines=tuple(bound[uid]['valid_before']for uid in main+secondary if bound[uid]['valid_before']is not None)
    return dict(main=main,secondary=secondary,bound=bound,records=records,selected=selected,
        secondary_selected=secondary_selected,
        activation=activation,category77=membership,circuit_state=circuit_state,
        item_callbacks=callbacks,set_callbacks=tuple(set_callbacks),set_counts=counts,
        active_sets=tuple(active_sets),valid_before=min(deadlines)if deadlines else None)
