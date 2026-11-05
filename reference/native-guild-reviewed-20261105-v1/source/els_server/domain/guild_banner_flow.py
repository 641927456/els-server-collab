"""Original F1 banner toggle, using actual guild appearance and loaded peers."""
from contextlib import closing
import sqlite3,struct,time
from els_server.protocol.protocol_codec import encode_event
from els_server.protocol.guild_system_messages import reply
from els_server.protocol.guild_emblem_messages import collection
from els_server.domain.guild_emblems import rows
from els_server.storage.guild_membership_state import snapshot


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x7e0:return None
    try:
        if (not s.item_test or s.client_build!='dx11_260923'or s.role!='game'
            or s.phase not in('town_ready','dungeon_active','guild_agit_ready')
            or event.payload not in(b'\0',b'\1')or event.performers not in((),(0,))
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Guild banner native actor/envelope')
        # This shared capture covers ordinary actors of every class; only the
        # separate LuCiel preference writers impose the LuCiel family check.
        from els_server.domain.luciel_state import style_context,validate_style_context
        captured=style_context(s)
        with closing(sqlite3.connect(s.account.store.path))as db:
            db.execute('BEGIN');saved=snapshot(db,s.account.uid,s.account.account_id)
            if saved is None:raise ValueError('Guild banner actual membership')
            if s.phase=='guild_agit_ready':
                from els_server.domain.guild_agit_flow import bank_capture
                bank_capture(s)[1](db)
            active=event.payload==b'\1';appearance=rows(saved['system'],int(time.time()),equipped_only=True)
            notice=reply(0x7e2,struct.pack('>Q?',s.account.uid,active)+collection(appearance))
            answer=[reply(0x7e1,bytes(4)),notice]
            from els_server.domain.party_commands import _prepared_boxes
            boxes=_prepared_boxes([(peer,[notice])for peer in captured['targets']],answer)
            for e in answer:encode_event(e)
            validate_style_context(s,captured)
        for peer,box in boxes.items():peer.mailbox=box
        s.guild_banner=dict(active=active,guild=saved['id'],appearance=appearance,phase=s.phase,
                           map=s.active_map,session=s.shop_session_id)
        return answer
    except(ValueError,sqlite3.Error,OverflowError):return [reply(0x7e1,struct.pack('>i',1))]
