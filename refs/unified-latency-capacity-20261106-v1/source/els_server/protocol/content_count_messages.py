"""C05 complete snapshot: raid pity, account dye and owned Mirror memory."""
import struct
from els_server.protocol.protocol_codec import Event

def notification(db,owner,account_id,*,raid_values=None):
    from els_server.storage.wardrobe import counts,present
    from els_server.storage.silver_mirror_state import read
    if not db.in_transaction:raise ValueError('Complete content count snapshot requires one SQL view')
    counts(db,owner,account_id)
    dye=list(db.execute('SELECT palette,points FROM wardrobe_dye_points WHERE account_id=? ORDER BY palette',(account_id,)))if present(db,'wardrobe_dye_points')else[]
    if len(dye)>47 or any(type(v)is not int or not 0<=v<2**31 for k,v in dye):raise ValueError('Content dye snapshot bounds')
    state=read(db,owner)
    groups={2:dye,3:[(1,state['memory'])]}
    from els_server.storage.raid_economy_state import progress
    from els_server.protocol.raid_economy_protocol import point_group
    expected=[(n,progress(db,owner,'accessory:'+str(n))[0],t)for n,t in((1,136175),(2,136179),(3,30876))]
    if raid_values is not None and list(raid_values)!=expected:raise ValueError('Raid content count snapshot changed source values')
    payload=point_group(expected)+struct.pack('>I',len(groups))
    for group,rows in sorted(groups.items()):
        payload+=struct.pack('>iI',group,len(rows))+b''.join(struct.pack('>iq',k,v)for k,v in rows)
    return Event(0x201,kind=0xc05,payload=payload)
