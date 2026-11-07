"""Compose selected678 participation/tasks and518 facts/awards explicitly.

The caller supplies the already verified stores and local policies. Importing
this module changes no default runtime. It does not add online-title entries,
icons, growth milestones or an unverified attendance make-up policy.
"""
import struct


def reward_rows(payload):
    """Read the verified full4B6 layout without discarding other providers."""
    if type(payload) is not bytes or not 4 <= len(payload) <= 65536:
        raise ValueError('Reward snapshot bound')
    count, = struct.unpack_from('>I', payload)
    if count > 16384:
        raise ValueError('Reward row count bound')
    offset = 4
    rows = {}
    for _ in range(count):
        if offset + 8 > len(payload):
            raise ValueError('Truncated reward row')
        rid, size = struct.unpack_from('>iI', payload, offset)
        offset += 8
        if rid <= 0 or rid in rows or not 1 <= size <= 256 or offset + size*10 > len(payload):
            raise ValueError('Invalid reward row')
        items = tuple(struct.unpack_from('>iiH', payload, offset+i*10) for i in range(size))
        offset += size*10
        if any(t <= 0 or n <= 0 or period > 32767 for t, n, period in items):
            raise ValueError('Invalid reward item')
        rows[rid] = items
    if offset != len(payload):
        raise ValueError('Unexpected reward snapshot tail')
    return rows


class GrowthAttendanceCampaign:
    def __init__(self, *, participation, growth, attendance, catalog, other_reward_rows):
        self.participation, self.growth, self.attendance = participation, growth, attendance
        self.catalog = catalog
        # Validate and copy explicit other providers at construction, rather
        # than keeping a mutable startup mapping owned by the caller.
        self.rows = reward_rows(catalog.notice(existing=other_reward_rows).payload)
        if participation.catalog.digest != catalog.digest or attendance.catalog.digest != catalog.digest:
            raise ValueError('Campaign reward catalogs differ')
        self.online = attendance.online

    def handle(self, session, event, sequence):
        for provider in (self.participation, self.growth, self.attendance):
            answer = provider.handle(session, event, sequence)
            if answer is not None:
                return answer
        return None

    def capture(self, session):
        self.growth.capture(session)
        self.attendance.capture(session)

    def prepare_clear(self, session):
        return self.attendance.prepare_clear(session)

    def finalize(self, session, replies):
        if not self.participation.enabled(session):
            return replies
        # Group challenge sessions may be inside a caller-owned write
        # transaction. All providers recover/project only after that commit.
        if getattr(session, 'reward_transaction', None) is not None:
            return replies
        rows = dict(self.rows)
        has_table = False

        def collect(events):
            nonlocal has_table
            output = []
            for event in events:
                if event.event_id != 0x201 or event.kind != 0x4b6:
                    output.append(event)
                    continue
                has_table = True
                for rid, items in reward_rows(event.payload).items():
                    if rid in rows and rows[rid] != items:
                        raise ValueError('Conflicting provider reward row')
                    rows[rid] = items
            return output

        output = collect(replies)
        for provider in (self.participation, self.growth, self.attendance):
            # Frozen individual providers reject a second full table. Gather
            # each table before the next provider sees the shared projection.
            output = collect(provider.finalize(session, output))
        if has_table:
            table = self.catalog.notice(existing=rows)
            if len(table.payload) > 65536:
                raise ValueError('Combined reward snapshot bound')
            output.insert(0, table)
        return output
