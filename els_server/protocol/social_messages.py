"""Current DX11 town/chat readers. See friends-coop-20261015 native witnesses.

Unknown social channels stay unsupported; sender identity always comes from
the authenticated session, never the request's name/UID fields.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32,u32,u16,wstring


class Reader:
    def __init__(self,payload):
        if not isinstance(payload,bytes) or len(payload)>4096:raise ValueError('Social payload bound')
        self.payload=payload;self.offset=0

    def take(self,size):
        end=self.offset+size
        if end>len(self.payload):raise ValueError('Truncated social payload')
        value=self.payload[self.offset:end];self.offset=end;return value

    def scalar(self,fmt):return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))[0]

    def text(self,maximum=512):
        size=self.scalar('I')
        if size%2 or size>maximum*2:raise ValueError('Social text bound')
        text=self.take(size).decode('utf-16le',errors='strict')
        if any(ord(c)<32 or ord(c)==127 for c in text):raise ValueError('Social control character')
        return text

    def end(self):
        if self.offset!=len(self.payload):raise ValueError('Trailing social fields')


def chat_request(payload,*,details=False):
    # 1267850 writes type, sub-type, target UID, three strings, int, Q,
    # bool, int, Q, int, then DB3520's attachment map. No item-link sending.
    r=Reader(payload)
    channel=r.scalar('B');subtype=r.scalar('B');target=r.scalar('Q')
    # Original12278B0: recipient, actual message, auxiliary string.
    # A plain native message has an empty auxiliary string.
    recipient=r.text(24);message=r.text(200);auxiliary=r.text(200)
    # The installed third-only protocol replay remains compatible.
    text=message or auxiliary
    reserved=r.scalar('i');target2=r.scalar('Q');flag=r.scalar('B')
    value=r.scalar('i');opaque=r.scalar('Q');index=r.scalar('i');attachments=r.scalar('I')
    r.end()
    if channel not in (0,1,4) or subtype!=0 or attachments or not text.strip():
        raise ValueError('Unsupported chat channel or attachment')
    if flag:
        # Same-build native built-ins observed on the wire and registered by
        # 1240CE0/1241930. 87's original consumer interprets their text itself.
        # Keep custom/purchased motions and all unverified variants closed.
        builtins={2506:'/笑',2508:'/哈哈',2509:'/哭',2513:'/生气',2515:'/不要'}
        if (flag!=1 or channel!=0 or recipient or auxiliary
            or target!=0xffffffffffffffff or reserved!=-1
            or target2!=0xffffffffffffffff or opaque!=0 or index!=0
            or builtins.get(value)!=message):
            raise ValueError('Unsupported native built-in chat command')
    if channel==4 and not recipient:raise ValueError('Whisper recipient missing')
    if details:return dict(channel=channel,text=text,recipient=recipient,target_uid=target)
    return channel,text


def chat_ack(result=0):
    # Native1228BD0 forwards failures to751120 ->79B330. Error -1 is
    # outside the original0..C4D table and resolves to an empty string.
    # Code1 is the client's existing generic failure, not a success.
    if result==-1:result=1
    return Event(0x201,kind=0x86,payload=i32(result))


def chat_notice(character,account_id,text,channel=0,*,recipient=None):
    # 1229200: type, account Q, int, character Q, name, name, target Q,
    # subtype, message, suffix, int, Q, int, DB3650 attachment map.
    data=bytes([channel])+struct.pack('>QiQ',account_id,-1,character['uid'])
    if channel==4 and recipient is None:raise ValueError('Whisper recipient missing')
    data+=wstring(character['name'])+wstring(recipient['name'] if recipient else '')+struct.pack('>Q',recipient['uid'] if recipient else 0)+b'\0'
    data+=wstring(text)+wstring('')+i32(0)+bytes(8)+i32(-1)+u32(0)
    return Event(0x201,kind=0x87,payload=data)


def appearance_item(item,*,native_instance=False):
    # D9A9D0 public item DTO (37F), not the full D9A550 inventory DTO.
    # DTO+0C is bag group and +0D is slot. Public fields differ from inventory.
    # 87E060 preserves group/slot when installing the worn record.
    # 33 option vectors and both three-int arrays have required fixed counts.
    # The original public instance layout is common to every character family.
    # The legacy compact branch remains only for explicit older fixture callers.
    if not native_instance:
        data=struct.pack('>QIBhBiB',item['uid'],item['template'],item.get('metadata',1),item['slot'],0,item['count'],0)
        return data+u32(0)+u32(33)+bytes(33*4)+u32(0)+bytes(9)+b'\xff'+u32(3)+bytes(12)+u32(3)+bytes(12)+bytes(8)
    enhancement=0
    if 'enhancement' in item:
        from els_server.domain.equipment_enhancement import validate
        enhancement=validate(item['template'],item['enhancement'])
    # DTO+0F -> instance+18 is signed enhancement. DTO+10 -> instance+94
    # is an appearance-template override; inventory count does not belong here.
    data=struct.pack('>QIBhbiB',item['uid'],item['template'],item['group'],item['slot'],enhancement,item.get('appearance_template',0),0)
    attributes=u32(0)
    if 'attributes' in item:
        from els_server.domain.equipment_attributes import validate_slots
        slots=validate_slots(item['template'],item['attributes'])
        if any(slots):attributes=u32(4)+struct.pack('>4i',*slots)
    # D9A9D0 reads this first vector into DTO+15. 87E060 copies its
    # four entries into the remote instance+1C..28 before installation.
    groups={}
    if 'option_groups' in item:
        from els_server.domain.sage_sockets import validate as validate_options
        groups=validate_options(item['template'],item['option_groups'])
    # D9A9D0 DTO+2D is the same exact33 vector array as inventory DTO+25.
    # Keep existing validated per-instance options in the public worn record.
    options=u32(33)+b''.join(u32(len(groups.get(str(n),[])))+b''.join(struct.pack('>i',v) for v in groups.get(str(n),[])) for n in range(33))
    reforge_level=0
    if 'reforge' in item or '13' in groups:
        from els_server.domain.equipment_reforge_rules import DEFAULT,validate_instance
        validate_instance(item)
        reforge_level=item.get('reforge',DEFAULT)[0]
    # D9A9D0 DTO+356 -> 87E060 instance+180 -> 198E220 reforge stats.
    # Public appearance carries the level; inventory-only life/failures stay out.
    return data+attributes+options+u32(0)+b'\0'+struct.pack('>i',reforge_level)+bytes(4)+b'\xff'+struct.pack('>IiiiIiii',3,*item.get('dye_colors',[0,0,0]),3,*item.get('appearance_colors',[0,0,0]))+bytes(8)


def town_member(character,location,items=()):
    # DA0E50 -> packed DTO 20D, independently replayed with empty optional
    # vectors/maps: 250 bytes. Offsets below are WIRE offsets, not DTO RVAs.
    raw=bytearray(250)
    struct.pack_into('>Q',raw,0,character['uid'])
    struct.pack_into('>H',raw,12,character['unit_class'])
    from els_server.domain.character_rules import transcendental_stage
    struct.pack_into('>i',raw,14,transcendental_stage(character))
    raw[18]=0xff;raw[21]=character['level']
    if character.get('unit_type')==10:
        from els_server.protocol.luciel_messages import active_preference
        raw[18]=active_preference(character)
        raw[20]=character['level'];raw[21]=0
    # DA0E50 reads the field after both appearance vectors into DTO+62;
    # 87E060 copies it into the remote actor's encoded title.
    struct.pack_into('>i',raw,30,character.get('title',0))
    struct.pack_into('>fff',raw,34,*location['xyz'])
    raw[47]=location['board'];struct.pack_into('>H',raw,48,location['progress'])
    # 87E060 installs the first vector into native equipped slots (group 9).
    # Group 1 is the equipment BAG, not worn gear. Never publish bag items as
    # equipment. The second native appearance/alternate vector stays empty.
    worn=[i for i in items if i['group']==9]
    equipment=u32(len(worn))+b''.join(appearance_item(i,native_instance=True) for i in worn)
    alternate=u32(0)
    # Replace three variable fields from right to left, preserving witnessed
    # offsets. Optional pet/mount/guild state stays empty.
    return bytes(raw[:8])+wstring(character['name'])+bytes(raw[12:22])+equipment+alternate+bytes(raw[30:])


def town_members(added=(),removed=()):
    # 30D59B0 consumes vector<DA0E50>, then vector<Q>. Both may be empty.
    return Event(0x201,kind=0x22a,payload=u32(len(added))+b''.join(town_member(*row) for row in added)+u32(len(removed))+b''.join(struct.pack('>Q',v) for v in removed))


def town_movement(uid,payload):
    from els_server.storage.local_state import movement_location
    movement_location(payload,'dx11_260923')
    # 20F0580: Q UID, xyz, bool, board, ushort, key vector, bool,
    # Q, int, byte, int, int. Never relay a request envelope or claimed UID.
    count=struct.unpack_from('>I',payload,12)[0];tail=16+2*count
    data=struct.pack('>Q',uid)+payload[:12]+payload[tail:tail+4]+payload[12:tail]
    data+=b'\0'+bytes(8)+i32(0)+payload[tail+4:tail+5]+payload[tail+5:tail+9]+payload[-4:]
    return Event(0x201,kind=0x22e,payload=data)


def party_invite_request(payload,*,details=False,settings=False):
    # 2E0D310 / 2BDD530. Decode all fields, while party policy is server-owned.
    r=Reader(payload);uid=r.scalar('Q');name=r.text(24);reason=r.scalar('i')
    kind=r.scalar('B');dungeon=r.scalar('i')
    fields=[r.scalar('B') for _ in range(6)]
    title=r.text(80);limits=[r.scalar('i'),r.scalar('i')]
    tail=[r.scalar('B') for _ in range(3)];value=r.scalar('i');r.end()
    if not name or reason not in (-1,0) or kind not in (0,1,3):raise ValueError('Unsupported party invitation')
    if kind==3:
        from els_server.domain.raid_party import raid_definition
        if raid_definition(dungeon) is None:raise ValueError('Unsupported native raid invitation')
    if settings:return dict(uid=uid,name=name,dungeon=dungeon,kind=kind,fields=tuple(fields))
    return (uid,name,dungeon) if details else (uid,name)


def party_invite_ack(character=None,result=0):
    c=character or {'uid':0,'name':'','unit_class':0}
    return Event(0x201,kind=0x137,payload=i32(result)+struct.pack('>Q',c['uid'])+wstring(c['name'])+u16(c['unit_class'])+wstring(''))


def party_invited(inviter,target):
    return Event(0x201,kind=0x138,payload=struct.pack('>QQ',inviter['uid'],target['uid'])+wstring(inviter['name'])+bytes([inviter['level']])+wstring('')+u16(inviter['unit_class'])+wstring(''))


def party_answer_request(payload):
    r=Reader(payload);first=r.scalar('Q');second=r.scalar('Q');accepted=r.scalar('B')
    reason=r.scalar('i');flag=r.scalar('B');reserved=r.scalar('Q');r.end()
    if accepted not in (0,1) or flag:raise ValueError('Invalid invitation answer')
    return first,second,bool(accepted)


def party_answer_ack(uid=0,result=0):return Event(0x201,kind=0x13a,payload=struct.pack('>iQi',result,uid,0))


def party_removed(uid=0,reason=0):return Event(0x201,kind=0x13c,payload=struct.pack('>Qi',uid,reason))


def party_info(identity,count,dungeon=30000,*,name='Friends',raid=False,recruitment=None):
    # DA01F0 zero-vector witness: 83 bytes. Native 2376A50 copies these
    # fields into PartyManager's room settings; normal party type is 1.
    from els_server.domain.raid_party import raid_definition
    source=raid_definition(dungeon) if raid else None
    if raid and source is None:raise ValueError('Invalid raid room source')
    maximum=source['maximum'] if source else recruitment['maximum'] if recruitment else 4
    if type(count) is not int or not 1<=count<=maximum:raise ValueError('Party count')
    raw=bytearray(83);struct.pack_into('>Q',raw,0,identity);raw[8]=3 if raid else 1
    # DA01F0 ->2376A50: joined count ->settings+10; maximum ->+14;
    # difficulty ->+0C. Membership must never overwrite difficulty.
    raw[13]=count;raw[14]=maximum;raw[15]=1;struct.pack_into('>i',raw,16,dungeon)
    raw[20]=0;raw[21]=1;raw[25]=1
    if recruitment is not None:
        raw[21]=0;raw[32]=int(recruitment['published'])
        struct.pack_into('>i',raw,33,recruitment['region'])
        raw[37:39]=bytes(recruitment['flags'])
        struct.pack_into('>i',raw,39,recruitment['listed'])
        struct.pack_into('>q',raw,43,recruitment['sort_key'])
    return bytes(raw[:9])+wstring(name)+bytes(raw[13:])


def party_member(identity,session,index,leader=False,ready=False):
    # DA0840 (1D1): party, slot, account, connection, character, class,
    # stage, name, level, flags. Original 2E1D300 consumes 52 as leader.
    c=session.account.character();raw=bytearray(185)
    struct.pack_into('>QiQQQH',raw,0,identity,index,session.identity['id'],session.identity['id'],c['uid'],c['unit_class'])
    from els_server.domain.character_rules import transcendental_stage
    struct.pack_into('>i',raw,38,transcendental_stage(c));raw[46]=c['level']
    raw[53]=int(ready);raw[54]=int(leader)
    location=session.account.get_location()
    struct.pack_into('>f',raw,73,location['xyz'][0]);struct.pack_into('>f',raw,77,location['xyz'][1])
    struct.pack_into('>i',raw,102,location['map'])
    struct.pack_into('>i',raw,172,0)  # normal party group
    return bytes(raw[:42])+wstring(c['name'])+bytes(raw[46:])


def party_snapshot(party):
    members=party['members'];identity=party['id']
    recruitment=party.get('recruitment')
    payload=i32(0)+u32(1)+party_info(identity,len(members),party['dungeon'],name=recruitment['title'] if recruitment else 'Challenge' if party.get('solo_challenge') or party.get('challenge') else 'Friends',raid=party.get('raid_party',False),recruitment=recruitment)
    payload+=u32(len(members))+b''.join(party_member(identity,s,index,s is party['leader'],s in party['ready']) for index,s in enumerate(members))
    payload+=u32(0)+wstring('')+u16(0)+wstring('')
    return Event(0x201,kind=0x13b,payload=payload)


def party_ready_notice(uid,ready,result=0):
    return Event(0x201,kind=0x14d,payload=struct.pack('>iQB',result,uid,int(ready))+wstring('')+b'\0')
