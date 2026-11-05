"""Original 0x612/0x614 replies for verified operations with no item changes.

These replies carry a full selected-page allocation map. Original consumers
overwrite entries without clearing missing stats, so all15current stats must
be present, including zeros. Reset/expansion inventory updates are not encoded.
"""
import struct
from els_server.domain.resonance_2026_allocations import ResonanceAllocations
from els_server.protocol.protocol_codec import Event


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid resonance reply integer')
    return value


def snapshot_reply(*, kind, result, progress, page_state, original_definition,
                   trailing_value, inventory_updates):
    """Project explicit committed account/page snapshots, without defaults.

    Caller owns the read transaction, freshness, original eligibility and result
    code. A historical mutation receipt alone is not a fresh state snapshot.
    trailing_value remains opaque; it is never inferred from the wall clock.
    """
    integer(kind, 0, 65535)
    if kind not in (0x612, 0x614):
        raise ValueError('Unsupported resonance reply')
    integer(result, -2**31, 2**31-1)
    integer(progress.level, 1, 999)
    integer(progress.cumulative_experience, 0, 2**63-1)
    integer(trailing_value, 0, 2**64-1)
    if type(inventory_updates) is not tuple or inventory_updates:
        raise ValueError('Inventory mutation reply not implemented')
    if type(page_state.enabled) is not bool or type(page_state.pages) is not tuple:
        raise ValueError('Explicit persisted character state required')
    count = integer(len(page_state.pages), 1, 4)
    selected = integer(page_state.selected_page, 1, count)
    for i, page in enumerate(page_state.pages, 1):
        if type(page.page_id) is not int or page.page_id != i:
            raise ValueError('Incomplete persisted page set')
    page = page_state.pages[selected-1]
    rules = ResonanceAllocations.from_original(original_definition)
    validated = rules.add(current=page.points, additions=(),
                          available_points=page.available_points, bonus_points=())
    points = dict(validated.points)
    payload = struct.pack('>iiQiBI', result, progress.level,
                          progress.cumulative_experience, validated.remaining_points,
                          int(page_state.enabled), 3)
    for tab in range(3):
        rows = sorted((stat.stat_id, points.get(stat.stat_id, 0))
                      for stat in rules.stats if stat.tab == tab)
        payload += struct.pack('>BI', tab, len(rows))
        payload += b''.join(struct.pack('>ii', *row) for row in rows)
    payload += struct.pack('>IQBB', 0, trailing_value, selected, count)
    return Event(0x201, kind=kind, payload=payload)
