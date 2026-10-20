"""0x611 allocation request for the pinned 2026 client; no network activation.

D387F0 groups signed pending deltas by original m_usTabIndex and appends
the selected character page. This positive planner stays unchanged; the
native flow has a separately bounded710106reward-coin refund transaction.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class ResonanceAllocationRequest:
    groups: tuple
    selected_page: int

    @classmethod
    def decode(cls, payload):
        if type(payload) is not bytes or not 5 <= len(payload) <= 140:
            raise ValueError('Invalid resonance request size')
        offset = 0

        def take(fmt):
            nonlocal offset
            size = struct.calcsize(fmt)
            if offset + size > len(payload):
                raise ValueError('Truncated resonance allocation request')
            result = struct.unpack_from(fmt, payload, offset)
            offset += size
            return result

        count, = take('>I')
        if count > 3:
            raise ValueError('Too many resonance categories')
        groups = []
        seen_groups = set()
        seen_stats = set()
        for _ in range(count):
            tab, length = take('>BI')
            if tab not in (0, 1, 2) or tab in seen_groups or length > 15-len(seen_stats):
                raise ValueError('Invalid resonance category')
            seen_groups.add(tab)
            values = []
            for _ in range(length):
                stat, delta = take('>ii')
                if stat in seen_stats:
                    raise ValueError('Duplicate resonance stat')
                seen_stats.add(stat)
                values.append((stat, delta))
            groups.append((tab, tuple(values)))
        page, = take('>B')
        if offset != len(payload):
            raise ValueError('Trailing resonance request bytes')
        return cls(tuple(groups), page)

    def plan_positive(self, *, rules, selected_page, current, available_points, bonus_points):
        """Accept only the current authoritative page and positive/no-op edits.

        A caller must perform ownership, enabled, revision and transaction checks.
        No page creation, page switch, refund, persistence or success is implied.
        """
        if type(selected_page) is not int or not 1 <= selected_page <= 4:
            raise ValueError('Authoritative selected page required')
        if type(self.selected_page) is not int or self.selected_page != selected_page:
            raise ValueError('Allocation page is stale or unowned')
        if type(self.groups) is not tuple or len(self.groups) > 3:
            raise ValueError('Invalid resonance groups')
        additions = []
        tabs = set()
        stats = set()
        for group in self.groups:
            if type(group) is not tuple or len(group) != 2:
                raise ValueError('Invalid resonance category')
            tab, values = group
            if type(tab) is not int or tab not in (0, 1, 2) or tab in tabs or type(values) is not tuple:
                raise ValueError('Invalid resonance category')
            tabs.add(tab)
            for pair in values:
                if type(pair) is not tuple or len(pair) != 2:
                    raise ValueError('Invalid resonance delta')
                stat, delta = pair
                definition = rules.stat(stat)
                if definition.tab != tab or stat in stats:
                    raise ValueError('Misgrouped or duplicate resonance stat')
                stats.add(stat)
                if type(delta) is not int or not 0 <= delta < 2**31:
                    raise ValueError('Refund/reset policy is not implemented')
                if delta:
                    additions.append((stat, delta))
        return rules.add(current=current, additions=tuple(additions),
                         available_points=available_points, bonus_points=bonus_points)
