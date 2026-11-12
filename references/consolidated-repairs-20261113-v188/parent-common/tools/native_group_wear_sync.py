from pathlib import Path
import hashlib,json,re,struct
W=Path(__file__).resolve().parent
EXE='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
def virtuals(snapshot):
    slots=(0x1398,0x1388,0x1360,0x1368,0x758,0x1358,0x1418,0x2a0,0x2a8,0x2f8,0x6c0,0x1500,0x1508)
    rows={};base=0x140000000
    for match in re.finditer(rb'\.\?AVCX2GU[^@\0]+@@\0',snapshot):
        typ=match.start()-16;start=0
        while True:
            p=snapshot.find(struct.pack('<I',typ),start)
            if p<0:break
            start=p+4;loc=p-12
            if loc<0:continue
            sig,offset,ctor,t,hier,selfrva=struct.unpack_from('<6I',snapshot,loc)
            if sig!=1 or offset!=0 or selfrva!=loc or t!=typ or not 0<hier<len(snapshot)-16:continue
            count,array=struct.unpack_from('<II',snapshot,hier+8)
            if not 1<=count<=64 or not 0<array<len(snapshot)-count*4:continue
            names=[]
            for n in range(count):
                descriptor=struct.unpack_from('<I',snapshot,array+n*4)[0]
                if not 0<descriptor<len(snapshot)-24:break
                td=struct.unpack_from('<I',snapshot,descriptor)[0]
                if not 0<td<len(snapshot)-64:break
                names.append(snapshot[td+16:td+160].split(b'\0')[0])
            if b'.?AVCX2GUUser@@'not in names:continue
            cursor=0
            while True:
                q=snapshot.find(struct.pack('<Q',base+loc),cursor)
                if q<0:break
                cursor=q+8;vt=q+8
                if vt%8 or vt+max(slots)+8>len(snapshot):continue
                values={slot:struct.unpack_from('<Q',snapshot,vt+slot)[0]-base for slot in slots}
                if not all(0<fn<0x3e00000 for fn in values.values()):continue
                rows[vt]=dict(name=match.group()[:-1].decode(),functions=values)
    if not rows or not any(v['name']=='.?AVCX2GUEve@@'for v in rows.values()):raise ValueError('Native player RTTI hierarchy')
    return rows
def source(snapshot,exe):
    if exe!=EXE or hashlib.sha256(snapshot).hexdigest()!=IMAGE:raise ValueError('Group wear build identity')
    # The existing stack adapter verifies6D56C0's prologue before its attach.
    # Pin the immutable body here; check returned template identity at use.
    rvas=(0xbaa6f0,0x680b50,0x3b6e1d0,0x1aa4580,0x15a0b0,0x15a100,0x234b280,0x98bfc0,0x7ebc80,0x7efc10,0x6d56e0,0x197f570,0x197e5f0,0x197fa60,0x85d5e0,0x85ce30,0x1ac13a0,0x1ac18a0,0x1ac1610,0x18c3a00,0x18c2e40)
    tables=virtuals(snapshot);rvas=tuple(set(rvas)|{fn for row in tables.values()for fn in row['functions'].values()}|{0x1bdd4f0,0x19245e0,0x1950650,0x1950890})
    s=(W/'group_wear_sync.js').read_text('utf8');assert s.count('__GROUP_WEAR_PINS__')==1 and s.count('__GROUP_WEAR_VIRTUALS__')==1
    return s.replace('__GROUP_WEAR_PINS__',json.dumps({r:snapshot[r:r+8].hex()for r in rvas})).replace('__GROUP_WEAR_VIRTUALS__',json.dumps(tables))
