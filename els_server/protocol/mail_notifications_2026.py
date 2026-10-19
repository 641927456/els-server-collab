"""Original 1CE mail notification layout; no activation or reward trigger.

2DDA540 case1CE -> 2DE5700 replaces the unread map and preview vector.
Callers owe a complete, character-authorized snapshot, including other mail
folders. Sending only the new activity count would erase other unread counts.
Preview title, sender andtemplate lookup key are recovered from794B25.
The specific retail2026 values andfinalflag remain explicit andunverified. No synthetic defaults are sent to players.
"""
import struct
from dataclasses import dataclass
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event


@dataclass(frozen=True)
class MailNoticeRow:
    letter_type: int
    title: str
    sender: str
    template_key: int
    ed: int
    item: dict | None

    def encode(self):
        if type(self.letter_type) is not int or not 0 <= self.letter_type <= 127:
            raise ValueError('Original signed-byte mail type required')
        if type(self.template_key) is not int or not -2**31 <= self.template_key < 2**31:
            raise ValueError('Explicit signed mail template key required')
        if type(self.ed) is not int or not 0 <= self.ed < 2**63:
            raise ValueError('Invalid mail ED')
        for value in (self.title, self.sender):
            if type(value) is not str or '\0' in value or len(value.encode('utf-16le')) > 4000:
                raise ValueError('Invalid bounded mail preview text')
        if self.item is not None and type(self.item) is not dict:
            raise TypeError('Trusted server item required')
        from els_server.domain.inventory_items import item_body
        from els_server.protocol.mail_messages import empty_item
        item_wire = empty_item() if self.item is None else item_body(self.item)
        return (struct.pack('>B', self.letter_type) + wstring(self.title) + wstring(self.sender)
                + struct.pack('>iQ', self.template_key, self.ed) + item_wire)


def notice(*, unread_counts, rows, flag):
    """All five LLT folders, fully scoped previews, explicit trailing bool.

    The encoder does not fetch player state, issue mail or infer delivery/claim
    state from an icon. Its payload must be emitted after the owning DB commit.
    """
    if (type(unread_counts) is not dict or any(type(k) is not int for k in unread_counts)
            or set(unread_counts) != set(range(5))):
        raise ValueError('Complete five-folder unread snapshot required')
    if (any(type(v) is not int or not 0 <= v < 2**31 for v in unread_counts.values())
            or sum(unread_counts.values()) >= 2**31):
        raise ValueError('Invalid unread count')
    # Serialization guard only; this is not a recovered mailbox capacity rule.
    if type(rows) not in (list, tuple) or len(rows) > 256 or any(type(r) is not MailNoticeRow for r in rows):
        raise ValueError('Bounded explicit mail previews required')
    if type(flag) is not bool:
        raise ValueError('Explicit original trailing flag required')
    payload = (struct.pack('>I', 5)
               + b''.join(struct.pack('>Bi', k, unread_counts[k]) for k in range(5))
               + struct.pack('>I', len(rows)) + b''.join(r.encode() for r in rows)
               + bytes([flag]))
    return Event(0x201, kind=0x1ce, payload=payload)
