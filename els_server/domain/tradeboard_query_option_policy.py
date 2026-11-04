"""Reviewable LOCAL search composition, never an asserted official DB rule.

The native client qualifies the field/option-ID/group namespaces, not the
server-side AND/OR composition. This independent candidate has no dispatcher,
automatic binding, SQL, producer or economic effect. It leaves the frozen
seven-leaf query component and its explicit closed defaults unchanged.
"""
from els_server.domain.inventory_items import validate_item, item_body
from els_server.protocol.tradeboard_metadata_item import read_item

POLICY = 'local-native-option-id-query-v1'


def _ids(values):
    if type(values)is not tuple or any(type(v)is not int or not 0<v<2**31 for v in values):
        raise ValueError('Positive actual option-ID tuple required; zero is only an empty-slot/cache placeholder')
    return frozenset(values)


def _native(row):
    # Full formal inventory validation and encoder; request data never creates
    # options and no template definition substitutes for the actual instance.
    return read_item(item_body(validate_item(row['item'])))


def quick_option_match(row, requested):
    """LOCAL: any requested named option ID in any of the 33 native groups.

    The actual client's 2D07BB0 derives the quick option-name cache from all
    groups. This composition is expressly local; repeated request IDs do not
    imply quantities or distinct slots. Empty input is no constraint.
    """
    wanted=_ids(requested)
    if not wanted:return True
    return any(wanted.intersection(group)for group in _native(row).option_groups)


def full_option_match(row, kind, requested_groups):
    """LOCAL: AND of nonempty controls; each control ORs its resolved IDs.

    Magic controls use only native socket group0; additional/identification
    controls only group1. There is no fallback to reforge, circuit or another
    group's numerically equal option. An empty control adds no condition.
    """
    if kind not in ('magic_socket','random_identification'):raise ValueError('Unknown full option namespace')
    maximum=6 if kind=='magic_socket'else 5
    if type(requested_groups)is not tuple or len(requested_groups)>maximum:raise ValueError('Current native control bound')
    groups=tuple(_ids(values)for values in requested_groups)
    if not any(groups):return True
    actual=_native(row).option_groups[0 if kind=='magic_socket'else 1]
    return all(not wanted or wanted.intersection(actual)for wanted in groups)
