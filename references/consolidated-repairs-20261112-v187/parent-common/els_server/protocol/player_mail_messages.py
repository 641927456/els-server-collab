"""Current-build ordinary 1CF branches independently witnessed in native code.

Only branches 0..4 have complete original-writer witnesses. Other static
branches remain unsupported. Both privileged/guild mode flags are rejected
by the business layer, regardless of their encoded branch.
"""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.protocol.local_messages import wstring


@functools.lru_cache(maxsize=1)
def grammars():
    raw=(PROJECT_ROOT/'els_server/data/player_mail_variants.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='2636a84dbac68c59794dd0664d5ca3b137d436706466ca74bfff0ee343ec74c5':
        raise ValueError('Native player mail grammar changed')
    doc=json.loads(raw)
    if (doc['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
            or [r['variant'] for r in doc['variants']]!=list(range(5))):
        raise ValueError('Unverified player mail grammar')
    return doc['variants']


def _decode(raw,grammar):
    pos=0;out={}
    def take(n):
        nonlocal pos
        if n<0 or pos+n>len(raw):raise ValueError('Truncated mail field')
        value=raw[pos:pos+n];pos+=n;return value
    for field in grammar['fields']:
        kind=field['kind']
        if kind in ('noise','wstring'):
            n=struct.unpack('>I',take(4))[0]
            if kind=='noise':
                if not 4<=n<=16:raise ValueError('Native padding bound')
                take(n);continue
            if n%2 or n>{'recipient':24,'title':160,'body':4000}[field['field']]:
                raise ValueError('Mail text bound')
            out[field['field']]=take(n).decode('utf-16le')
        else:
            out[field['field']]=int.from_bytes(take({'byte':1,'u32':4,'u64':8}[kind]),'big')^int(field['mask'],0)
    if (pos!=len(raw) or out['flag']>1 or out['extra']>1 or out['count']>99
            or out['ed']>70_000_000_000 or out['item']>=2**63
            or not 2<=len(out['recipient'])<=12 or not out['title']
            or bool(out['item'])!=bool(out['count'])):
        raise ValueError('Invalid ordinary mail fields')
    return out


def send_request(raw):
    if not isinstance(raw,bytes) or not 30<=len(raw)<=8192:raise ValueError('Ordinary mail size')
    matches=[]
    for grammar in grammars():
        try:matches.append(_decode(raw,grammar))
        except (ValueError,OverflowError,UnicodeError,struct.error):pass
    if len(matches)!=1:raise ValueError('Unknown or ambiguous native mail branch')
    return matches[0]


def send_ack(ed=0,recipient='',result=0):
    # 2DE4EB0: result, current absolute ED, inventory vector, recipient name.
    return struct.pack('>iQI',result,ed,0)+wstring(recipient)
