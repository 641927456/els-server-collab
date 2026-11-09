"""Original ordinary-fatigue absolute notification, native BA9820/kind241."""
import struct
from els_server.protocol.protocol_codec import Event

def notification(current):
    if type(current)is not int or not 0<=current<=4800:
        raise ValueError('Original ordinary fatigue bounds')
    return Event(0x201,kind=0x241,payload=struct.pack('>i',current))

def fields(state):
    if type(state)is not dict or state.get('maximum')!=4800:
        raise ValueError('Ordinary fatigue snapshot shape')
    notification(state['current'])
    return {'0x2fe':struct.pack('>i',4800),'0x302':struct.pack('>i',state['current'])}
