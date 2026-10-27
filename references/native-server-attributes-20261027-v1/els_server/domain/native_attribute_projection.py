"""Compose qualified source phases in original 888CA0 float32 order.

The caller owns snapshot consistency, eligibility, effective ranks and mode.
Every contribution and extension is explicit. This function never estimates a
missing source, persists player state or changes naked protocol inputs.
"""


def compose(base, equipped_flat, option_flat, learned_flat, query_ranks,
            definitions, unit_selections, rules, *, phase_pvp, unit_pvp,
            naked_extension5, naked_extension16, flat_attack_extension,
            flat_defense_extension, extra_hp):
    from els_server.domain.native_passive_attributes import apply, apply_naked, f32

    vectors = (base, equipped_flat, option_flat, learned_flat)
    if any(type(v) is not tuple or len(v) != 7 for v in vectors):
        raise ValueError('All four qualified native seven-field sources required')
    checked = [tuple(f32(value) for value in row) for row in vectors]
    bare, equipped, options, learned = checked
    naked = apply_naked(bare, query_ranks, definitions, pvp=phase_pvp,
                        extension5=naked_extension5,
                        extension16=naked_extension16)
    # 888F81..889046 adds flat option sources, flat equipped sources, learned
    # flat sources and the modified naked vector. Percentages use this single
    # basis; one passive must not magnify the preceding passive's contribution.
    basis = [f32(f32(f32(a+b)+c)+d)
             for a, b, c, d in zip(options, equipped, learned, naked)]
    basis[0] = f32(basis[0] + f32(extra_hp))
    return apply(tuple(basis), query_ranks, definitions, unit_selections, rules,
                 phase_pvp=phase_pvp, unit_pvp=unit_pvp,
                 flat_attack=flat_attack_extension,
                 flat_defense=flat_defense_extension)
