"""Original ED shop purchase dispatch for the account-wide assist service."""
import hashlib,sqlite3,time
from contextlib import closing
from els_server.domain.resonance_assist import SKU
from els_server.protocol.shop_messages import ed_purchase_request,ed_purchase_ack

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x80f:return None
    try:products=ed_purchase_request(event.payload)
    except ValueError:return None
    if not any(sku==SKU for sku,_ in products):return None
    from els_server.domain.ariel_attendance_flow import context,validate
    from els_server.storage.sqlite_timing import write_transaction
    from els_server.storage.resonance_assist import purchase,period
    from els_server.protocol.protocol_codec import encode_event
    from els_server.protocol.gm_messages import scrolling_notice
    try:
        if (products!=((SKU,1),) or not s.ed_catalog_loaded
            or type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Assist original shop request')
        captured=context(s)
        operation=f'{s.shop_session_id}:resonance-assist:{s.account.uid}:{sequence}'
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            db.execute('PRAGMA foreign_keys=ON')
            with write_transaction(db):
                validate(s,captured)
                now=int(time.time())
                ed=purchase(db,s.account.uid,s.account.account_id,operation,hashlib.sha256(event.payload).hexdigest(),now)
                saved=period(db,s.account.account_id)
                remaining=max(0,saved[1]-now)
                message=(f'共鸣经验助力账号共享，剩余{(remaining+86399)//86400}天；350级以下3倍、350至499级2倍，与常驻10倍相乘。'
                         if remaining else '该次购买已处理，共鸣经验助力已到期。')
                events=[ed_purchase_ack(0,[],ed),scrolling_notice(message)]
                for answer in events:encode_event(answer)
                validate(s,captured)
        return events
    except ValueError:return [ed_purchase_ack(-1,[],0)]
