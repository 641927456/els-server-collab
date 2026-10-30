"""Complete ordered8623B0 resistance arithmetic from qualified sources.

The middle source list and service/post state must come from their own native
producers. Option order is separate from the ordinary combat-power collector.
"""
from els_server.domain import native_resistance_item_options as item_options
from els_server.domain import native_legacy_socket_condition as legacy
from els_server.domain import native_circuit_attribute_inputs as circuit
from els_server.domain import native_resistance_option as options
from els_server.domain import native_resistance_finalization as finalization
from els_server.domain import native_armor_resistance as armor
from els_server.domain import native_resistance_skills as skills
from els_server.domain import native_pve_rank_coefficient as pve
from els_server.domain.native_rank_coefficient import coefficient
from els_server.domain import native_resistance_middle_inputs as middle


def finish(value,definitions,*,skill_values,service_values,resonance_value,
           post_option_ids,mode,rank,pve_context):
    # Post options merge into the running vector, never an options-only sum.
    value=finalization.add(value,skill_values)
    if service_values is not None:value=finalization.add(value,service_values)
    value=finalization.add(value,(resonance_value,)*6)
    callbacks=[]
    if not mode:
        for identity in post_option_ids:
            definition=definitions.get(identity)
            if definition is None or not options.eligible(definition,mode=mode):continue
            value=options.merge(value,definition,rank_factor=coefficient(rank),
                pve_rank_factor=pve.factor(definition,**pve_context),weight=1.)
            callbacks.append((identity,1.))
    return dict(values=tuple(500. if v>500. else v for v in value),callbacks=tuple(callbacks))


def calculate(items,worn,definitions,skill_definitions,query_ranks,*,mode,rank,
              pve_context,middle_sources,piece_counts,service_values,resonance_value,
              post_option_ids):
    if type(mode)is not int or mode not in(0,1):raise ValueError('Native resistance mode required')
    if type(items)is not tuple or type(post_option_ids)is not tuple:
        raise ValueError('Complete ordered resistance sources required')
    from els_server.game_data import client_data
    data=client_data();lookup={row['uid']:row for row in items};value=(0.,)*6;callbacks=[]
    factor=coefficient(rank)
    def append(pairs):
        nonlocal value
        for identity,weight in pairs:
            definition=definitions.get(identity)
            if definition is None or not options.eligible(definition,mode=mode):continue
            value=options.merge(value,definition,rank_factor=factor,
                pve_rank_factor=pve.factor(definition,**pve_context),weight=weight)
            callbacks.append((identity,weight))
    for secondary,selected in((False,worn['selected']),(True,worn['secondary_selected'])):
        for uid in selected:
            row=worn['bound'][uid];item=lookup[uid]
            if not secondary and data.item(item['template'])['item_type']==2:
                value=finalization.add(value,armor.values(tuple(item.get('attributes',(0,0,0,0)))))
            allow4=False
            if not secondary:
                requirement=legacy.requirement(row['template_options'],definitions)
                if requirement is not None:
                    quantity,minimum=requirement
                    # Current source thresholds are zero. A nonnegative native
                    # count always satisfies those, without inventing a count.
                    if quantity>0 and minimum<=0:allow4=True
                    elif quantity>0:
                        allow4=legacy.enabled(row['template_options'],definitions,piece_count=piece_counts[uid])
            active=worn['activation'];weighted=()
            if not secondary and active[0x50]and any(p[0]==0x50 for p in row['properties']):
                weighted=circuit.collect(row['template_id'],row['option_vectors'][0x2d8])
            append(item_options.collect(row['option_vectors'],row['properties'],row['template_options'],
                secondary=secondary,allow4=allow4,allow26=active[0x4a],allow27=active[0x4e],
                allow_circuit=active[0x50],circuit_options=weighted,circuit_state=worn['circuit_state']))
    result=middle.merge(value,definitions,middle_sources,mode=mode,rank=rank,pve_context=pve_context)
    value=result['values'];callbacks.extend(result['callbacks'])
    append(tuple((identity,source.weight)for source in worn['set_callbacks']for identity in source.option_ids))
    skill_values=skills.values(skill_definitions,
        {sid:query_ranks.get(sid,0)for sid,_,_,_ in skills.SKILLS},pvp=bool(mode))
    result=finish(value,definitions,skill_values=skill_values,service_values=service_values,
        resonance_value=resonance_value,post_option_ids=post_option_ids,mode=mode,rank=rank,pve_context=pve_context)
    return dict(values=result['values'],callbacks=tuple(callbacks)+result['callbacks'])
