"""Server-owned refinement contribution matching original 198E380.

Refinement is added after the native template/enhancement calculation and only
to positive base fields. The two weapon-variance fields are left alone. This
module does not alter the naked-stat DTO or write inventory/player state.
"""
import math
import struct


def refinement_scale_for_mode(mode):
    """Original SetReforgingStatPVP(0.4) ->6C2E90 ->manager+7C0.

    The current reforge catalog already pins the complete source registration
    table. This does not infer a multiplier from another gameplay formula.
    """
    if type(mode) is not int or mode not in (0, 1):
        raise ValueError('Explicit native equipment mode required')
    from els_server.domain.equipment_reforge_rules import catalog
    if catalog()['source_resource_sha256'] != 'cd622db6fe266e6a28323c1eb0e16a565def39f7008c1e21858684b7548f4738':
        raise ValueError('Unqualified native refinement scale source')
    return _f32(.4) if mode else None


def _f32(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Finite native refinement stat required')
    try:
        result = struct.unpack('<f', struct.pack('<f', value))[0]
    except (OverflowError, struct.error) as error:
        raise ValueError('Native refinement float32 bound') from error
    if not math.isfinite(result):
        raise ValueError('Native refinement float32 overflow')
    return result


def merge_refinement(base, refinement, *, scale):
    """198E405..198E48D; scale=None is the original false scaling flag."""
    if any(type(values) is not tuple or len(values) != 7 for values in (base, refinement)):
        raise ValueError('Explicit native seven-field refinement inputs required')
    original = tuple(_f32(value) for value in base)
    additional = tuple(_f32(value) for value in refinement)
    multiplier = None if scale is None else _f32(scale)
    out = list(original)
    for index in (0, 1, 2, 5, 6):
        if original[index] > 0:
            value = additional[index]
            if multiplier is not None:
                value = _f32(value * multiplier)
            out[index] = _f32(original[index] + value)
    return tuple(out)


def instance_attributes(item, character, *, mode, refinement_scale):
    """Use current validated instance state and the existing qualified table."""
    from els_server.domain.character_stats import equipment_attributes
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.equipment_reforge_rules import cumulative_stats, validate_instance
    if type(mode) is not int or mode not in(0,1):
        raise ValueError('Explicit native equipment mode required')
    if item['template'] in definitions():
        from els_server.domain.instance_stats import normal_instance_attributes
        from els_server.domain.equipment_enhancement import validate
        enhancement=validate(item['template'],item['enhancement']) if 'enhancement'in item else 0
        base=tuple(normal_instance_attributes(item['template'],character,enhancement=enhancement,mode=mode))
    else:
        base=tuple(equipment_attributes(item['template'],character))
    if 'reforge' not in item:
        return base
    validate_instance(item)
    level = item['reforge'][0]
    additional = tuple(cumulative_stats(item['template'], level))
    return merge_refinement(base, additional, scale=refinement_scale)
