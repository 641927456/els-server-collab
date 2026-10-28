"""Original9871D0 scalar/data wrapper with explicit native caller context."""
from els_server.domain.native_option_data_merge import merge_attribute_data,level_factor
from els_server.domain.native_option_scalar_merge import merge_scalar_phase


def merge_option_record(destination, source, destination_data, source_data, *,
                        level, kind, source_line, unit_line, condition_enabled,
                        condition_kind, condition_scale, condition_value,
                        pvp, pvp_rate, weight):
    # Original9871D0 runs985360 before9859A0 checks the source class line.
    # Keep that order; moving the metadata predicate across phases changes it.
    data=merge_attribute_data(destination_data,source_data,
        level_factor=level_factor(level),
        condition_kind=condition_kind if condition_enabled==1 else 0,
        condition_value=condition_value,condition_scale=condition_scale)
    scalars=merge_scalar_phase(destination,source,kind=kind,
        source_line=source_line,unit_line=unit_line,
        condition_enabled=condition_enabled,condition_kind=condition_kind,
        condition_scale=condition_scale,condition_value=condition_value,
        pvp=pvp,pvp_rate=pvp_rate,weight=weight)
    return scalars,data
