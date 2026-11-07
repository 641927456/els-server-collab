"""Pinned678 participation codecs; no qualification or activation decision.

D2D only acknowledges result and refreshes the event UI. It carries neither
bound UID nor resonance state. D29 is the separate binding notification;
complete resonance synchronization remains the session coordinator's job.
"""
import struct
from els_server.protocol.protocol_codec import Event


def participation_request(payload):
    if type(payload) is not bytes or payload:
        raise ValueError('Original D2C body must be empty')


def participation_reply(*, result):
    if type(result) is not int or not -(2**31)<=result<2**31:
        raise ValueError('Signed original participation result required')
    return Event(0x201,kind=0xd2d,payload=struct.pack('>i',result))


def binding_notice(*, character_uid):
    if type(character_uid) is not int or not 0<=character_uid<2**64:
        raise ValueError('Original bound UID required')
    return Event(0x201,kind=0xd29,payload=struct.pack('>Q',character_uid))
