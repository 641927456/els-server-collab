"""Current saved costume-accessory rows -> original Unit730 registration input.

The supported restoration788 explicitly writes base context0 at Unit2912/2914
and sorts all rows by slot(index2), including equal-index rows on both sides.
No equipment-preset unlock/switch metadata or pending unacknowledged UI state
is invented. Normal restoration/acknowledgement ordering is a delivery concern.
"""


def build(snapshot):
    character=snapshot['character'];owner=snapshot['owner']
    if character['uid']!=owner:
        raise ValueError('Owned registration source differs')
    source=character['avatar_set_source']
    if type(source)is not dict or set(source)!={'revision','rows'}:
        raise ValueError('Complete same-snapshot avatar selection source required')
    revision=source['revision'];rows=source['rows']
    if type(revision)is not int or not 0<=revision<2**63 or type(rows)is not tuple:
        raise ValueError('Canonical saved avatar revision and immutable rows required')
    if revision==0:
        if rows:raise ValueError('Unsaved registration source must be empty')
        # Empty registrations make the preset operand irrelevant in867440/
        #198A0A0. This0 is not a claim that an uninitialized native word is0.
        return dict(preset=0,registrations=(),restoration=None,preset_is_relevant=False)
    if any(type(row)is not tuple for row in rows):
        raise ValueError('Immutable canonical avatar registration records required')
    from els_server.protocol.avatar_set_messages import restoration
    event=restoration(rows)  # Same finite6/12-row/current base-context contract.
    ordered=tuple(sorted(rows,key=lambda row:row[2]))
    return dict(preset=0,registrations=ordered,restoration=event,preset_is_relevant=True)
