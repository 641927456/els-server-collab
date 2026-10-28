"""Whole8F8D50 over explicit ordered native channels and selected preset.

This does not infer a missing preset, effective rank or source ownership. The
native main channel has an unchecked row access; reject an unsafe source rather
than reproduce an out-of-bounds read or invent a zero contribution.
"""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_skill_stat_inputs import load

MAIN_FIELDS=(6,7,8,11,12)


def _rows(rows, *, ordered_map, signed_rank=False):
    if type(rows) is not tuple:
        raise ValueError('Explicit native channel tuple required')
    keys=[]
    for row in rows:
        if type(row) is not tuple or len(row)!=2:
            raise ValueError('Native skill/rank pair required')
        sid,rank=row
        if type(sid) is not int or not 0<=sid<2**32 or type(rank) is not int:
            raise ValueError('Native skill/rank widths required')
        if not (-2**31<=rank<2**31 if signed_rank else 0<=rank<=255):
            raise ValueError('Native rank width exceeded')
        keys.append(sid)
    if ordered_map and keys!=sorted(set(keys)):
        raise ValueError('Original map iteration requires unique sorted keys')


def collect(definitions, main, presets, selected_index, extra):
    _rows(main,ordered_map=True)
    _rows(extra,ordered_map=False)
    if type(presets) is not tuple or type(selected_index) is not int or not 0<=selected_index<=65535:
        raise ValueError('Explicit preset vector and native uint16 selection required')
    for rows in presets:
        _rows(rows,ordered_map=True,signed_rank=True)
    out=[f32(0.)]*13

    def add(rows,channel):
        for sid,rank in rows:
            if sid not in definitions:
                raise ValueError('Unqualified skill definition lookup')
            definition=definitions[sid]
            if definition is None or channel==0 and rank>30:
                continue
            if definition['m_eType'] not in ((1,2,3,4,8) if channel==0 else (1,2,3,4)):
                continue
            values=load(definition)
            if not values:
                continue
            if not 1<=rank<=len(values):
                if channel==0:
                    raise ValueError('Main channel would read outside qualified STAT rows')
                continue
            record=values[rank-1]
            for slot in (MAIN_FIELDS if channel==0 else range(6,13)):
                out[slot]=f32(record[slot]+out[slot])

    add(main,0)
    # The native early exit skips BOTH remaining channels when no valid preset
    # exists. An empty selected map is valid and still permits the extra vector.
    if selected_index>=len(presets):
        return tuple(out)
    add(presets[selected_index],1)
    add(extra,2)
    return tuple(out)
