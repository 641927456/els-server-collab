"""Item-aware mail DTOs; the frozen ED-only codec remains unchanged."""
import struct
from els_server.protocol import mail_messages as base
from els_server.protocol.local_messages import wstring
from els_server.domain.inventory_items import item_body,inventory_payload,fixture
from els_server.domain.fashion_state import move_ack

list_request=base.list_request
read_request=base.read_request
delete_ack=base.delete_ack


def header(row):
    item=row.get('item') if row.get('claimed_at') is None else None
    if item is None:return base.header(row)
    ed=base.attachment(row)
    return (struct.pack('>QBiQ',row['id'],row.get('mail_type',5),item['template'],ed)+item_body(item)
        +wstring(row.get('recipient',''))+wstring(row['sender'])+wstring(row['title'])
        +struct.pack('>BH',int(row.get('read_at') is None),0)+wstring(base.date(row['expires_at'])))


def list_ack(rows=(),total=0,page=1,folder=0,result=0):
    return (struct.pack('>iiI',result,total,len(rows))+b''.join(header(r) for r in rows)
        +struct.pack('>iBBB',page,folder,0,0))


def detail(row):
    item=row.get('item') if row.get('claimed_at') is None else None
    if item is None:return base.detail(row)
    return (struct.pack('>QQQBi',row['id'],0,row['created_at'],row.get('mail_type',5),item['template'])
        +wstring(row.get('recipient',''))+wstring(row['sender'])+wstring(row['title'])+wstring(row['body'])
        +struct.pack('>BH',int(row.get('read_at') is None),0)+wstring(base.date(row['expires_at']))
        +struct.pack('>QQ',base.attachment(row),0)+item_body(item)+struct.pack('>Q',row['expires_at']))


def read_ack(row=None,result=0):
    return base.read_ack(result=result) if row is None else struct.pack('>i',result)+detail(row)+bytes(8)


def claim_ack(ids=(),ed=0,changes=None,result=0,*,counts=None):
    changes=changes or {};counts=counts or {}
    # Summary quantities come from the same transaction's newly claimed escrow.
    # Retry summaries remain empty; absolute inventory and ED still synchronize.
    if set(counts)-set(ids):raise ValueError('Foreign mail summary')
    rows=[]
    for mid in ids:
        values=counts.get(mid,{})
        if (type(values) is not dict or len(values)>128 or any(
                type(k) is not int or not 0<k<2**31 or type(v) is not int or not 0<v<2**31
                for k,v in values.items())):raise ValueError('Invalid mail summary')
        rows.append(struct.pack('>QBI',mid,0,len(values))
            +b''.join(struct.pack('>ii',k,v) for k,v in sorted(values.items()))
            +inventory_payload([item for _,item in changes.get(mid,[]) if item is not None])
            +struct.pack('>Q',ed))
    return struct.pack('>iI',result,len(ids))+b''.join(rows)+bytes(8)


def refresh(changes):
    # 105 handles empty source positions and replacements as absolute rows.
    unique={tuple(pos):item for pos,item in changes}
    return move_ack(list(unique.items()))


class _Cursor:
    def __init__(self,raw):self.raw=raw;self.pos=0
    def take(self,n):
        if n<0 or self.pos+n>len(self.raw):raise ValueError('Truncated mail claim hint')
        value=self.raw[self.pos:self.pos+n];self.pos+=n;return value
    def number(self,n=4):return int.from_bytes(self.take(n),'big')
    def count(self,maximum):
        n=self.number()
        if n>maximum:raise ValueError('Mail hint vector bound')
        return n
    def boolean(self):
        if self.number(1)>1:raise ValueError('Mail hint boolean')
    def item(self):
        # Existing pinned D9A550 grammar. Unsupported dynamic maps are rejected;
        # all supported server item encoders use the fixed empty defaults.
        for f in fixture()['fields']:
            offset=int(f['offset'],0)
            if offset==0xd:self.take(4*self.count(4))
            elif offset==0x25:
                if self.count(33)!=33:raise ValueError('Mail hint option array')
                for _ in range(33):self.take(4*self.count(64))
            elif offset==0x350:
                raw=self.take(self.count(256))
                if len(raw)%2:raise ValueError('Mail hint UTF16 length')
                raw.decode('utf-16le')
            elif offset in (0x37d,0x389):
                if self.count(3)!=3:raise ValueError('Mail hint fixed triple')
                self.take(12)
            elif offset in (0x33d,0x3ec):
                expected=bytes.fromhex(f['wire_hex'])
                if self.take(len(expected))!=expected:raise ValueError('Unsupported mail hint state')
            else:self.take(len(bytes.fromhex(f['wire_hex'])))


def selection_request(payload,claim=False):
    if not claim:return base.selection_request(payload)
    if not isinstance(payload,bytes) or not 18<=len(payload)<=262144:raise ValueError('Mail claim size')
    c=_Cursor(payload);n=c.count(10)
    if not n:raise ValueError('Empty mail claim')
    ids=[c.number(8) for _ in range(n)]
    if len(set(ids))!=n or any(not 0<i<2**63 for i in ids):raise ValueError('Mail claim identities')
    seen=set()
    # 2E14A1A -> 2BDD990 writes vector<39-byte native claim DTO>.
    # Hints are parsed for framing only. No hint contributes an asset, owner,
    # slot, quantity or balance to a database operation.
    for _ in range(c.count(10)):
        mid=c.number(8)
        if mid not in ids or mid in seen:raise ValueError('Foreign or duplicate claim hint')
        seen.add(mid);c.boolean()
        c.take(c.count(128)*8)  # map<i32 template,i32 count>
        for _ in range(c.count(128)):
            c.take(11);c.item();c.boolean();c.take(8)
        c.take(8)
    c.boolean();c.boolean()
    if c.pos!=len(payload):raise ValueError('Trailing mail claim data')
    return ids
