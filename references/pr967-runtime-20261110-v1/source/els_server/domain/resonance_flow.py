"""Current absolute full-unit scalar sync for shared ERP, no acquisition replay."""


def _trace(message):
    # state/ is gitignored; this is the only view of what the ERP panel gets.
    try:
        import os,time
        root=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root,'state','resonance.log'),'a',encoding='utf-8') as handle:
            handle.write('%s %s\n'%(time.strftime('%H:%M:%S'),message))
    except Exception:pass


def synchronize(s,messages):
 if s.role!='game' or s.phase not in ('town_ready','dungeon_active') or s.client_build!='dx11_260923' or s.account.store is None or s.account.characters is None:return messages
 from els_server.storage.resonance_state import state
 current=state(s.account.store.path,s.account.uid,s.account.account_id)
 if not current['enabled']:return messages
 from els_server.domain.resonance_allocation_flow import synchronize as allocation_sync
 key=(current['account_id'],current['revision'],s.account.uid)
 if getattr(s,'resonance_sync_key',None)==key:return allocation_sync(s,messages,current)
 notice=s.saved_user_sync(resonance_snapshot=current)
 from els_server.protocol.protocol_codec import encode_event
 encode_event(notice);s.resonance_sync_key=key
 _trace('sync uid=%r level=%r exp=%r rev=%r dto_bytes=%d'
        %(s.account.uid,current.get('level'),current.get('experience'),current.get('revision'),len(notice.payload)))
 return allocation_sync(s,[*messages,notice],current)
