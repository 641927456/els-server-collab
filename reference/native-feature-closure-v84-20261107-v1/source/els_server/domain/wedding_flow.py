"""Native reservation, personalized tickets, lobby and additional invitations."""
from contextlib import closing
import sqlite3,time
from els_server.protocol import wedding_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import weddings as storage,relationship_mail

KINDS=frozenset((0x887,0x889,0x88c,0x88e,0x408))


def _ticket_capture(s,*,phases=('player_initialized','skill_ui_ready',
        'initialization_confirmed','map_loading','square_accepted','town_ready')):
    """408 is also emitted during the original character initialization."""
    from els_server.domain.equipment_chip_flow import reset_authority,current_lease
    def current():
        reset_authority(s)
        if (not current_lease(s)or s.role!='game'or s.client_build!='dx11_260923'or not s.item_test
                or 0x28 not in s.completed or s.phase not in phases):
            raise ValueError('Wedding current selected ticket reader')
        a=s.account
        return (a,a.store,a.root,s.identity),(a.uid,a.account_id,s.shop_session_id,s.phase)
    refs,values=current()
    def same():
        try:r,v=current()
        except(ValueError,AttributeError):return False
        return v==values and all(a is b for a,b in zip(r,refs))
    def guard(db):
        if not same():raise ValueError('Wedding selected ticket reader changed')
    return same,guard


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in KINDS:return None
    kind=event.kind
    try:
        app=getattr(s,'application',None)
        if kind!=0x887 and app is not None and app.world.weddings.room(s)is not None:
            same,guard=app.world.weddings.capture(s)
        elif kind==0x408:same,guard=_ticket_capture(s)
        else:
            from els_server.domain.relationship_flow import capture
            same,guard=capture(s)
        if (event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
                or type(sequence)is not int or not 0<sequence<2**32):
            raise ValueError('Wedding native request envelope')
        request=wire.request(kind,event.payload);account=s.account
        operation=f'{s.shop_session_id}:wedding:{account.uid}:{sequence}'
        with closing(sqlite3.connect(account.store.path,timeout=10))as db,db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE'if kind in(0x887,0x88e)else'BEGIN')
            guard(db);now=int(time.time())
            if kind==0x887:
                answer=storage.reserve(db,account.uid,account.account_id,request,event.payload,operation,
                    now=now,guard=guard,issue=relationship_mail.reservation,
                    encode=lambda row,changes,replayed:[wire.inventory_ack(0x888,changes)])
            elif kind==0x88e:
                answer=storage.invite(db,account.uid,account.account_id,request,event.payload,operation,
                    now=now,guard=guard,encode=lambda changes,replayed:[wire.inventory_ack(0x88f,changes)])
            elif kind==0x889:
                rows,pages=storage.lobby(db,request['page'],now=now);answer=[wire.lobby(rows,pages)]
            elif kind==0x88c:
                row,guests=storage.detail(db,account.uid,account.account_id,request['reservation'],now=now)
                answer=[wire.detail(row,guests)]
            else:
                entries=storage.ticket_information(db,account.uid,account.account_id,request['tickets'],now=now)
                answer=[wire.ticket_information(entries)]
            for reply in answer:encode_event(reply)
            guard(db)
        return answer
    except(ValueError,sqlite3.Error,OverflowError,AttributeError,KeyError,TypeError):
        if 'same'not in locals()or not same():return []
        if kind in(0x887,0x88e):return [wire.inventory_ack(kind+1,result=-1)]
        if kind==0x889:return [wire.lobby((),1,result=-1)]
        if kind==0x88c:return [wire.detail(result=-1)]
        return [wire.ticket_information((),result=-1)]
