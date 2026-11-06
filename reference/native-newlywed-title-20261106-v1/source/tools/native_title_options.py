"""Reuse an existing native20% option for the approved newlywed title only."""
from pathlib import Path
import json


def compose(snapshot,template):
    # The parent cache composer has already verified the executable and image.
    anchor=' installElsGuildNativePower();'
    if template.count(anchor)!=1:raise ValueError('Title option initialization anchor')
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    token='__TITLE_OPTION_PINS__'
    if raw.count(token)!=1:raise ValueError('Title option source contract')
    pins={r:snapshot[r:r+16].hex()for r in(0xfe7560,0x216fe40,0x2181ed0,0xb11a90)}
    raw=raw.replace(token,json.dumps(pins))
    replacement=' installElsTitleOptionData();\n'+anchor
    result=template.replace(anchor,replacement)
    if result.replace(replacement,anchor)!=template:raise ValueError('Title option composition inverse')
    return raw+'\n'+result
