"""Current DTO+10E membership for source-backed completed dungeon IDs.

DCFE50 reads count then key, i32, i32, byte, wstring, bool, i32, wstring.
85E1F0 uses the zero/empty value below for a newly established record. Grades,
names and ranking fields are not reconstructed from the local seconds column.
General admission unlocks and canonical-entry aliases are separate work.
"""
import struct


def completed_map(identities):
    rows=tuple(identities)
    if any(type(i) is not int or not 1<=i<=2**31-1 for i in rows):
        raise ValueError('Completed dungeon identity')
    if len(set(rows))!=len(rows):
        raise ValueError('Duplicate completed dungeon identity')
    # Two int32, signed byte, empty wide string, bool, int32, empty wide string.
    value=bytes(8)+b'\0'+bytes(4)+b'\0'+bytes(4)+bytes(4)
    return struct.pack('>I',len(rows))+b''.join(struct.pack('>i',i)+value for i in sorted(rows))
