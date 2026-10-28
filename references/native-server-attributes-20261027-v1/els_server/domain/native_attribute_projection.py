"""Compose qualified source phases in original 888CA0 float32 order.

The caller owns snapshot consistency, eligibility, effective ranks and mode.
Every contribution and extension is explicit. This function never estimates a
missing source, persists player state or changes naked protocol inputs.
"""


def compose(base, equipped_flat, option_flat, learned_flat, query_ranks,
            definitions, unit_selections, rules, *, phase_pvp, unit_pvp,
            naked_extension5, naked_extension16, flat_attack_extension,
            flat_defense_extension, extra_hp, title_direct):
    from els_server.domain.native_passive_attributes import apply, apply_naked, f32

    vectors = (base, equipped_flat, option_flat, learned_flat, title_direct)
    if any(type(v) is not tuple or len(v) != 7 for v in vectors):
        raise ValueError('All five qualified native seven-field sources required')
    checked = [tuple(f32(value) for value in row) for row in vectors]
    bare, equipped, options, learned, title = checked
    naked = apply_naked(bare, query_ranks, definitions, pvp=phase_pvp,
                        extension5=naked_extension5,
                        extension16=naked_extension16)
    # 888F81..889046 adds flat option sources, flat equipped sources, learned
    # flat sources and the modified naked vector. Percentages use this single
    # basis; one passive must not magnify the preceding passive's contribution.
    basis = [f32(f32(f32(a+b)+c)+d)
             for a, b, c, d in zip(options, equipped, learned, naked)]
    # 88904F..889082 adds the current title after the four-source basis. It
    # must not be folded into equipped_flat: float32 additions are ordered.
    basis = [f32(value+extra) for value,extra in zip(basis,title)]
    basis[0] = f32(basis[0] + f32(extra_hp))
    return apply(tuple(basis), query_ranks, definitions, unit_selections, rules,
                 phase_pvp=phase_pvp, unit_pvp=unit_pvp,
                 flat_attack=flat_attack_extension,
                 flat_defense=flat_defense_extension)


def compose_power(base, equipped_flat, option_flat, learned_flat, query_ranks,
                  definitions, unit_selections, rules, *, phase_pvp, unit_pvp,
                  naked_pvp, naked_extension5, naked_extension16,
                  flat_attack_extension, flat_defense_extension, extra_hp,
                  title_direct):
    """896870 has its own basis; it does not consume888CA0's final seven.

    896AA5 calls861940 with forced-mode disabled, so the caller supplies the
    actual native Unit/world mode separately. 896AAA..896D26 accumulates naked,
    equipment, learned, title, then options. Fixed HP follows8978C0 instead of
    preceding it. Reusing the wire vector only coincides on some inputs.
    """
    from els_server.domain.native_passive_attributes import apply, apply_naked, f32
    vectors = (base, equipped_flat, option_flat, learned_flat, title_direct)
    if any(type(v) is not tuple or len(v) != 7 for v in vectors):
        raise ValueError('All five qualified native power sources required')
    bare, equipped, options, learned, title = [tuple(map(f32, v)) for v in vectors]
    naked = apply_naked(bare, query_ranks, definitions, pvp=naked_pvp,
                        extension5=naked_extension5, extension16=naked_extension16)
    basis = tuple(f32(f32(f32(f32(f32(0.+a)+b)+c)+d)+e)
                  for a,b,c,d,e in zip(naked,equipped,learned,title,options))
    result = list(apply(basis, query_ranks, definitions, unit_selections, rules,
                        phase_pvp=phase_pvp, unit_pvp=unit_pvp,
                        flat_attack=flat_attack_extension,
                        flat_defense=flat_defense_extension))
    result[0] = f32(f32(result[0]+0.)+f32(extra_hp))
    return tuple(result)
