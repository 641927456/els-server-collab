"""Record a refused ED request without reading or writing player state."""
import struct


def refusal(session,event,messages):
    if event.event_id!=0x202 or event.kind!=0x80f:return None
    results=[struct.unpack_from('>i',m.payload)[0]for m in messages
             if m.event_id==0x201 and m.kind==0x810 and len(m.payload)>=4]
    if not results or all(result==0 for result in results):return None
    # The largest accepted request is 100 (u32 SKU,u16 count) pairs plus u32.
    # Keep malformed requests bounded and explicitly retain their original size.
    payload=event.payload[:604]
    return dict(uid=session.account.uid,phase=session.phase,role=session.role,
                catalog_loaded=session.ed_catalog_loaded,results=results,
                payload_bytes=len(event.payload),payload_hex=payload.hex(),
                rejection=getattr(session,'_shop_purchase_rejection',None))
