"""Native wardrobe exchange: opening 51C/51D and the register/apply writes.

The original branches live inline in local_session, which holds live session
objects and therefore cannot be re-executed in place. Handling them here keeps
the same guards, snapshot and encode-before-validate ordering while letting a
fix take effect without stopping the server or dropping the client.

Opening: the inventory button sends the usual single zero performer, but the
original branch required an empty performer list, so every opening was dropped
without a reply and the panel never initialised.
"""
import os
import time
import traceback

_DEBUG=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),'state','wire-debug.log')
_OPS=frozenset((0x4af,0x4b1,0xbee,0x4f4,0x565,0x6d7,0xad6))


def _dbg(text):
    # TEMPORARY diagnostics: state/ is gitignored. Remove before committing.
    try:
        with open(_DEBUG,'a',encoding='utf-8') as handle:handle.write(time.strftime('%H:%M:%S ')+text+'\n')
    except Exception:pass


def _live(module):
    import importlib
    path=getattr(module,'__file__',None)
    try:stamp=(os.path.getmtime(path),os.path.getsize(path))
    except (OSError,TypeError):return module
    if getattr(module,'SOURCE_STAMP',None)==stamp:return module
    try:module=importlib.reload(module)
    except Exception:return module
    module.SOURCE_STAMP=stamp
    return module


def handle(s,event,sequence):
    if event.kind==0x51c:return _opening(s,event,sequence)
    if event.kind in _OPS:return _operation(s,event,sequence)
    return None


def _opening(s,event,sequence):
    from els_server.protocol.wardrobe_messages import opening_request
    if (not s.item_test or s.client_build!='dx11_260923' or event.event_id!=0x202
        or s.role!='game' or s.phase!='town_ready' or type(sequence)is not int
        or not 1<=sequence<2**32 or event.performers not in ((),(0,))
        or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
        _dbg('51C envelope phase=%r role=%r performers=%r uid=%#x mode=%r'
            %(s.phase,s.role,tuple(event.performers or ()),event.uid,event.payload_mode))
        return []
    try:
        opening_request(event.payload)
        from els_server.domain import avatar_set_flow as avatar_sets
        captured=_live(avatar_sets).context(s)
        from els_server.storage import wardrobe as storage
        reply=_live(storage).opening_info(s.account.store.path,s.account.uid,s.account.account_id,
            validate=lambda:_live(avatar_sets).validate(s,captured))
        _dbg('51C ok %r'%[hex(e.kind)for e in reply])
        return reply
    except ValueError:
        _dbg('51C rejected\n'+traceback.format_exc())
        return []


def _operation(s,event,sequence):
    from els_server.protocol.wardrobe_messages import acknowledgement
    kind=event.kind
    if not s.item_test or s.client_build!='dx11_260923' or event.event_id!=0x202:return None
    if (s.role!='game' or s.phase!='town_ready' or type(sequence)is not int
        or not 1<=sequence<2**32 or event.performers!=(0,)
        or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
        _dbg('%X envelope phase=%r performers=%r payload=%s'%(kind,s.phase,tuple(event.performers or ()),event.payload.hex()))
        return [acknowledgement(kind,result=-1)]
    operation=s.shop_session_id+':wardrobe:'+str(s.account.uid)+':'+str(sequence)
    try:
        from els_server.domain.tutorial_accessory import wear_context,validate_wear_context
        captured=wear_context(s)
        from els_server.storage import wardrobe as storage
        answer=_live(storage).change(s.account.store.path,s.account.uid,s.account.account_id,kind,
            event.payload,operation,validate=lambda:validate_wear_context(s,captured))
        reply=answer if isinstance(answer,list)else[answer]
        _dbg('%X ok payload=%s reply=%r'%(kind,event.payload.hex(),[hex(e.kind)for e in reply]))
        return reply
    except ValueError as error:
        result=getattr(error,'result',-1)
        # WardrobeError carries the native message code the client renders
        # (1499 timed, 1505 sealed, 1503 wrong position, 1506 unregistered...);
        # plain ValueErrors keep the generic refusal.
        if type(result)is not int or result<=0:result=-1
        _dbg('%X rejected result=%d payload=%s'%(kind,result,event.payload.hex()))
        return [acknowledgement(kind,result=result)]
