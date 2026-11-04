"""Canonical server skill notices and original owned-Unit source semantics.

This reads server-produced bytes after successful writes. It does not accept a
client rank report, resend55B, infer a new Unit lifetime or select a runtime.
55B restores ordinary ranks/unsealed IDs, but its preset's Force vectors are
not applied by13A34F0/8F67D0. Owned full copies and6D1 have their own8FA130
consumer. Empty Force vectors retain existing native entries; explicit zero
entries clear them. The caller must bind new-Unit construction separately.
"""
from dataclasses import dataclass,replace
import struct
from els_server.protocol.protocol_codec import Event

ZERO_FORCE=((0,0),)*11


class _Reader:
    def __init__(self,raw):
        if type(raw)is not bytes or len(raw)>1024*1024:
            raise ValueError('Bounded canonical server skill bytes required')
        self.raw=raw;self.at=0

    def take(self,n):
        if n<0 or self.at+n>len(self.raw):
            raise ValueError('Truncated canonical skill source')
        value=self.raw[self.at:self.at+n];self.at+=n;return value

    def value(self,fmt):
        return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))

    def count(self,limit):
        n,=self.value('I')
        if n>limit:raise ValueError('Canonical skill vector bound')
        return n

    def finish(self):
        if self.at!=len(self.raw):raise ValueError('Trailing canonical skill bytes')


def _records(reader,*,slots=False,seal_history=False):
    count=reader.count(22 if slots else 4096)
    if slots and count!=22:raise ValueError('Canonical22 skill slots required')
    values=[]
    for _ in range(count):
        sid,rank,metadata,flag=reader.value('iBiB')
        if (sid<0 or (sid==0 and (not slots or rank!=0)) or sid>0 and rank==0
                or metadata!=0 or flag not in(range(4)if seal_history else(0,))):
            raise ValueError('Canonical native skill record required')
        values.append((sid,rank))
    # Owning different grades of the same Force is legal. Ordinary learned
    # maps and selected slots remain unique by ID; owned rows use(ID,rank).
    occupied=[(sid,rank)if seal_history else sid for sid,rank in values if sid]
    if len(set(occupied))!=len(occupied):raise ValueError('Duplicate skill record')
    return tuple(values)


def _ids(reader):
    values=tuple(reader.value('i')[0]for _ in range(reader.count(4096)))
    if any(s<=0 for s in values)or len(set(values))!=len(values):
        raise ValueError('Distinct unsealed skill identities required')
    return tuple(sorted(values))


@dataclass(frozen=True)
class Preset:
    slots:tuple
    traits:tuple
    # None means the current empty vectors: retain, not an11-entry clear.
    forces:object


def _tail(reader,slots):
    traits=tuple(reader.value('ii')for _ in range(reader.count(4096)))
    if (any(s<=0 or not 1<=n<=22 for s,n in traits)
            or len({s for s,n in traits})!=len(traits)):
        raise ValueError('Canonical skill trait map required')
    groups=[];sizes=[]
    for maximum in(3,8):
        count=reader.count(maximum);sizes.append(count)
        if count not in(0,maximum):raise ValueError('Complete native Force vector required')
        values=[]
        for _ in range(count):
            sid,rank,flag=reader.value('iBB')
            if sid<0 or (sid==0)!=(rank==0)or flag!=0:
                raise ValueError('Canonical Force source record required')
            values.append((sid,rank))
        groups.extend(values)
    if sizes not in([0,0],[3,8]):raise ValueError('Matched canonical Force vectors required')
    occupied=[s for s,rank in groups if s]
    if len(set(occupied))!=len(occupied):raise ValueError('Duplicate selected Force identity')
    return Preset(slots,tuple(sorted(traits)),tuple(groups)if groups else None)


def _preset(reader):
    return _tail(reader,_records(reader,slots=True))


@dataclass(frozen=True)
class Initialization:
    owner:int
    learned:tuple
    unsealed:tuple
    preset:Preset
    selected:int
    page_count:int


def initialization(raw):
    """Exact current55B shape, including dormant pages and final IDs."""
    reader=_Reader(raw);owner,=reader.value('Q');count=reader.count(3)
    if not 0<owner<2**63 or not 1<=count<=3:
        raise ValueError('Canonical owned skill initialization required')
    pages={}
    for _ in range(count):
        key,=reader.value('B')
        if key>=count or key in pages:raise ValueError('Distinct ordinary page keys required')
        pages[key]=_preset(reader)
    learned=tuple(sorted(_records(reader)))
    if reader.take(17)!=bytes(17):raise ValueError('Unqualified55B auxiliary source')
    selected,total=reader.value('BB')
    if total!=count or not 1<=selected<=total:raise ValueError('Current ordinary page selection required')
    unsealed=_ids(reader);reader.finish()
    return Initialization(owner,learned,unsealed,pages[selected-1],selected,total)


def _copied_parts(raw):
    """Current character field14E (CD7160), not a whole Unit parser.

    The owned87A6E0 branch skips the ordinary restoration when the current
    Game+C8+A0 UID matches. Its preset Force vectors still go through8FA130.
    """
    reader=_Reader(raw);_records(reader,slots=True)
    expansions=reader.count(2)
    seen=set()
    for _ in range(expansions):
        key,state,date=reader.value('iiI')
        if key not in(0,1)or key in seen or state not in(0,2)or date!=0:
            raise ValueError('Canonical current skill expansion source required')
        seen.add(key)
    _records(reader)
    if reader.take(4)!=bytes(4):raise ValueError('Unqualified copied skill auxiliary vector')
    _ids(reader)
    if reader.take(2)!=b'\1\1':raise ValueError('Canonical copied ordinary page bytes required')
    preset=_preset(reader);extra=_records(reader,seal_history=True)
    if reader.take(1)!=b'\0':raise ValueError('Unqualified copied skill status')
    reader.finish();return preset,tuple(sorted(extra))


def copied_preset(raw):
    return _copied_parts(raw)[0]


def copied_extra(raw):
    return _copied_parts(raw)[1]


@dataclass(frozen=True)
class CopyReceipt:
    event:Event
    owner:int
    preset:Preset
    extra:tuple


@dataclass(frozen=True)
class UpdateReceipt:
    epoch:object
    event:Event
    owner:int
    removed_extra:object=None


def bind_copy(event,fields):
    """Bind the shared writer's exact Unit fields to an actual2A/D9 prefix.

    Fields must come from the writer that built this batch, not from a later
    SQL read. Prefix comparison includes every Unit byte; no substring search
    or guessed variable-width offset can attest a different transmitted source.
    No new-Unit constructor claim is inferred from a2A packet.
    """
    if(type(event)is not Event or event.event_id!=0x201 or event.kind not in(0x2a,0xd9)
            or type(fields)is not tuple or not fields):
        raise ValueError('Actual owned copy Event and immutable writer fields required')
    if any(type(row)is not tuple or len(row)!=2 or type(row[0])is not str
           or type(row[1])is not bytes for row in fields):
        raise ValueError('Original shared character field tuples required')
    mapping=dict(fields)
    if len(mapping)!=len(fields)or '0x14e'not in mapping:
        raise ValueError('Distinct complete copied skill field required')
    raw=b''.join(value for name,value in fields);prefix=4 if event.kind==0x2a else 0
    if(len(raw)<17 or event.payload[prefix:prefix+len(raw)]!=raw
            or prefix and event.payload[:4]!=bytes(4)):
        raise ValueError('Writer fields do not match the transmitted complete Unit')
    owner,=struct.unpack_from('>Q',raw,9)
    if not 0<owner<2**63:raise ValueError('Copied owned UID required')
    preset,extra=_copied_parts(mapping['0x14e'])
    return CopyReceipt(event,owner,preset,extra)


@dataclass(frozen=True)
class SkillSources:
    owner:int
    learned:object=None
    unsealed:object=None
    forces:object=None
    extra:object=None

    def constructed(self):
        """Caller has qualified a new owned native SkillManager lifetime."""
        return SkillSources(self.owner,(),(),ZERO_FORCE,())

    def copied(self,receipt,event):
        if(type(receipt)is not CopyReceipt or receipt.event is not event
                or receipt.owner!=self.owner):
            raise ValueError('Exact same-owned transmitted copy receipt required')
        forces=receipt.preset.forces
        #87B33E is the join target of the owner/null guards. The extra
        #902B60 replacement always runs, unlike ordinary rank restoration.
        return replace(self,extra=receipt.extra,**({}if forces is None else{'forces':forces}))

    def written(self,event,*,ordinary_page_ready,receipt=None):
        if type(event)is not Event or type(ordinary_page_ready)is not bool:
            raise ValueError('Actual written server Event and page context required')
        if event.event_id!=0x201:return self
        if event.kind==0x55b:
            state=initialization(event.payload)
            if state.owner!=self.owner:return self
            return replace(self,learned=state.learned,unsealed=state.unsealed)
        if event.kind==0x6cb:
            reader=_Reader(event.payload);result,=reader.value('i')
            sid,rank,metadata,flag=reader.value('iBiB');reader.finish()
            if result:return self
            if sid<=0 or rank==0 or metadata or flag not in range(4):
                raise ValueError('Canonical learned Force extra-rank record required')
            rows=None if self.extra is None else tuple(sorted(set(self.extra)|{(sid,rank)}))
            return replace(self,extra=rows)
        if event.kind==0x6cf:
            if len(event.payload)<13:raise ValueError('Canonical Force extraction prefix required')
            result,sid,rank=struct.unpack_from('>iiB',event.payload)
            if result:return self
            # Variable inventory records remain the original producer's work.
            # The receipt carries its exact removal pair, bound to the same
            # Event/prefix; this is not an independent inventory decoder.
            if (type(receipt)is not UpdateReceipt or receipt.event is not event
                    or receipt.owner!=self.owner or receipt.removed_extra!=(sid,rank)):
                return replace(self,extra=None)
            if sid<=0 or rank==0:raise ValueError('Canonical extracted Force pair required')
            rows=None if self.extra is None else tuple(p for p in self.extra if p!=(sid,rank))
            return replace(self,extra=rows)
        if event.kind==0x131:
            reader=_Reader(event.payload);result,=reader.value('i')
            learned=_records(reader);ids=_ids(reader);reader.finish()
            if result:return self
            # An increment cannot establish a complete pre-existing source.
            ranks=None if self.learned is None else tuple(sorted((dict(self.learned)|dict(learned)).items()))
            unsealed=None if self.unsealed is None else tuple(sorted(set(self.unsealed)|set(ids)))
            return replace(self,learned=ranks,unsealed=unsealed)
        if event.kind==0x123:
            reader=_Reader(event.payload);result,index,sid,other,other_sid=reader.value('5i');reader.finish()
            if result:return self
            if not 0<=index<22 or not -1<=other<22 or sid<0 or other_sid<0:
                raise ValueError('Canonical ordinary skill slot change required')
            return self  #8F8560 changes slots, not learned/unsealed/Force sources.
        if event.kind==0x6d1:
            reader=_Reader(event.payload);result,=reader.value('i')
            if result:
                if reader.take(16)!=bytes(16):raise ValueError('Canonical Force refusal required')
                reader.finish();return self
            preset=_preset(reader);reader.finish()
            return self if preset.forces is None else replace(self,forces=preset.forces)
        if event.kind==0x484:
            reader=_Reader(event.payload);result,page,a,b=reader.value('4i')
            if result:
                # Current refusal is fixed22 empty records, unnamedu16s,
                # three empty maps/vectors, then four empty preset containers.
                if reader.take(256)!=struct.pack('>I',22)+bytes(252):
                    raise ValueError('Canonical ordinary page refusal required')
                reader.finish();return self
            if not 1<=page<=3 or a or b:raise ValueError('Canonical ordinary page response required')
            fixed_slots=_records(reader,slots=True)
            if reader.take(4)!=bytes(4):raise ValueError('Canonical unnamed page fields required')
            # Same traits/Force tail as a preset, with an independently
            # encoded fixed22 prefix. Parse both and require identical content.
            fixed=_tail(reader,fixed_slots);preset=_preset(reader);reader.finish()
            if fixed!=preset:
                raise ValueError('Inconsistent current ordinary page sources')
            if not ordinary_page_ready:return replace(self,forces=None)
            return self if preset.forces is None else replace(self,forces=preset.forces)
        return self

    def matches_extra(self,expected):
        if (type(expected)is not tuple or len(expected)>4096
                or any(type(row)is not tuple or len(row)!=2
                    or type(row[0])is not int or not 0<row[0]<2**31
                    or type(row[1])is not int or not 1<=row[1]<=255 for row in expected)
                or tuple(sorted(set(expected)))!=expected):
            raise ValueError('Complete canonical independent extra-rank source required')
        return self.extra is not None and self.extra==expected

    def matches(self,canonical55b):
        """Ordinary/unsealed/Force rank-source equivalence only.

        Traits, action bonuses, slot timers and independent Actor/source-group
        contexts are deliberately not attested by this rank-source ledger.
        The complete attribute source factory must validate those separately.
        """
        if(type(canonical55b)is not Event or canonical55b.event_id!=0x201
                or canonical55b.kind!=0x55b):
            raise ValueError('Canonical55B source comparison required')
        expected=initialization(canonical55b.payload)
        return(self.owner==expected.owner and self.learned==expected.learned
               and self.unsealed==expected.unsealed
               and self.forces==(expected.preset.forces or ZERO_FORCE))
