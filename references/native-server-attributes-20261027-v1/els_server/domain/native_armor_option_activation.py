"""8A2430/8A1DB0/8A1EC0/8A1FD0 four-position property activation."""
import struct


def flags(selected,records):
    """Already native-selected main equipment, in original template order."""
    if type(selected)is not tuple:raise ValueError('Original ordered main selection required')
    first={}
    for row in selected:
        record=records[row['uid']]
        if type(record)is not bytes or len(record)!=232:raise ValueError('Complete original item record required')
        native_flags=struct.unpack_from('<I',record,4)[0]
        if native_flags!=row['flags4']:raise ValueError('Selected native flags differ from source record')
        if native_flags&1:continue
        position=record[0xd5]
        if position in(8,9,10,11):first.setdefault(position,row)
    def active(row,key):
        if not any(p[0]==key for p in row['properties']):return False
        offset={0x4a:0x248,0x4e:0x2a8}.get(key)
        # Original96B970/96B900 test vector length, not whether IDs are nonzero.
        return offset is None or bool(row['option_vectors'][offset])
    return {key:all(position in first and active(first[position],key)
        for position in(8,9,10,11))for key in(0x4a,0x4e,0x50)}
