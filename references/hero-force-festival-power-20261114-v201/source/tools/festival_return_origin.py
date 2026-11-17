"""Compose the digest-bound authoritative festival-return input consumer."""
from native_support import script

def compose(template):
    anchor='  clearInterval(timer);'
    if template.count(anchor)!=1:raise ValueError('Festival return startup anchor')
    return script('festival_return_origin')+'\nlet elsFestivalReturnOriginHook=null;\n'+template.replace(anchor,anchor+'\n  elsFestivalReturnOriginHook=installElsFestivalReturnOrigin();')
