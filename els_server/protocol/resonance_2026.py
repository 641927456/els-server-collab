"""Original 0x610 resonance state notice, fixed dx11_260923 client.

D36480 selects D38470 for 0x610; DAD100 reads its full packed DTO.
Only level and enabled have established semantic names here. Every other
scalar and allocation page is explicit so a later level update cannot silently
zero existing point/page/period state. This codec alone grants no eligibility.
"""
from dataclasses import dataclass
import struct
from els_server.protocol.protocol_codec import Event


def bounded(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid resonance field: ' + name)
    return value


@dataclass(frozen=True)
class ResonanceState:
    level: int
    field04: int
    field0c: int
    enabled: bool
    pages: tuple
    field21: int
    field25: int
    field29: int
    field31: int
    field32: int
    field3a: int
    field3b: int

    def notice(self):
        bounded(self.level, 0, 2**31-1, 'level')
        for name in ('field0c', 'field21', 'field25'):
            bounded(getattr(self, name), -2**31, 2**31-1, name)
        for name in ('field04', 'field29', 'field32'):
            bounded(getattr(self, name), 0, 2**64-1, name)
        for name in ('field31', 'field3a', 'field3b'):
            bounded(getattr(self, name), 0, 255, name)
        if type(self.enabled) is not bool:
            raise ValueError('Explicit resonance enabled flag required')
        if type(self.pages) is not tuple or len(self.pages) > 256:
            raise ValueError('Invalid resonance page map')
        page_ids = set()
        rows = []
        for page, values in self.pages:
            bounded(page, 0, 255, 'page')
            if page in page_ids or type(values) is not tuple or len(values) > 2**32-1:
                raise ValueError('Duplicate page or invalid allocation vector')
            page_ids.add(page)
            entries = []
            for key, value in values:
                bounded(key, -2**31, 2**31-1, 'allocation key')
                bounded(value, -2**31, 2**31-1, 'allocation value')
                entries.append(struct.pack('>ii', key, value))
            rows.append(struct.pack('>BI', page, len(entries)) + b''.join(entries))
        payload = struct.pack('>iQiBI', self.level, self.field04, self.field0c,
                              int(self.enabled), len(rows)) + b''.join(rows)
        payload += struct.pack('>iiQBQBB', self.field21, self.field25, self.field29,
                               self.field31, self.field32, self.field3a, self.field3b)
        return Event(0x201, kind=0x610, payload=payload)
