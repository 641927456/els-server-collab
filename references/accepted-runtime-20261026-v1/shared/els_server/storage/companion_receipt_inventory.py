"""Refresh a pet receipt's historical slot and its surviving current source UID."""

def current_changes(items,old):
    if old is None:return []
    positions=[(old['group'],old['slot'])]
    source=next((item for item in items if item['uid']==old['uid']),None)
    if source is not None:
        position=(source['group'],source['slot'])
        if position not in positions:positions.append(position)
    by_position={(item['group'],item['slot']):item for item in items}
    return [(position,by_position.get(position)) for position in positions]


def delta(items,old):
    changes=current_changes(items,old)
    return dict(updates=[item for _,item in changes if item is not None],
        removed=old if changes and changes[0][1] is None else None)
