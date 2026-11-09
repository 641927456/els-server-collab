"""Late-region NPC recipes through the shared original 223 writer."""
from contextlib import closing
from functools import partial
from pathlib import Path
import sqlite3
import struct

from els_server.protocol.fish_exchange_messages import acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.protocol.purifier_exchange_messages import ExchangeRequest


RECIPES = {
    **{(40271,136230,5,t,3):(t,1) for t in (168915,168916,168917)},
    (40271,136230,20,0,1):(168918,1),
    **{(40274,30856,45,t,3):(t,1) for t in range(30857,30863)},
    **{(40274,30863,45,t,3):(t,1) for t in range(30864,30870)},
    (40273,136116,200,0,1):(136112,1),
    (40273,136116,300,0,1):(136115,1),
    **{(40257,136140,15,t,3):(t,3) for t in (136109,136110,136111)},
    (40310,136181,4,0,1):(136198,1),
}
INPUTS = frozenset((key[0],key[1]) for key in RECIPES)
TOWNS = {40257:1010, 40271:20013, 40273:20013, 40274:20013, 40310:1011}


def _source(request, db, owner, operation, plan, validate):
    from els_server.domain.raid_reward_items import _issue_source

    def authorize(writer):
        validate()
        return writer is db

    return _issue_source(db,owner,operation,"npc_trade",
        dict(house=request.house,source=request.source,source_quantity=request.source_quantity),
        plan,authorize)


def _reserve_weekly(db, now, owner, template):
    from els_server.storage.raid_economy_state import week_at
    db.execute("""CREATE TABLE IF NOT EXISTS town_growth_exchange_weekly (
        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE, week TEXT NOT NULL,
        template INTEGER NOT NULL, PRIMARY KEY (owner,week,template))""")
    changed = db.execute("""INSERT INTO town_growth_exchange_weekly VALUES (?,?,?)
        ON CONFLICT DO NOTHING""",(owner,week_at(now),template)).rowcount
    if not changed:
        raise ValueError("Reward already exchanged this week")


def handle(session,event,sequence):
    if (event.event_id,event.kind)!=(0x202,0x223) or len(event.payload)!=37:
        return None
    request=ExchangeRequest(*struct.unpack(">iQiiiiiBi",event.payload))
    if (request.house,request.source)==(40272,136115):
        from els_server.domain.purifier_exchange_flow import handle as purifier
        return purifier(session,event,sequence)
    if (request.house,request.source) not in INPUTS:
        return None
    exchange_type=request.exchange_type if request.exchange_type in (1,3) else 3
    try:
        from els_server.domain.housing_access_flow import capture
        same,guard=capture(session)
        town=TOWNS[request.house]
        if (session.active_map!=town or event.performers!=(0,) or event.payload_mode!=0
                or event.uid!=event.target_uid or event.uid!=2**64-1
                or type(sequence)is not int or not 1<=sequence<2**32):
            raise ValueError("Growth exchange current actor and NPC scene")
        weekly=request.source==136230 or (request.source,request.source_quantity)==(136116,300)
        if ((request.source_uid,request.native_flag,request.native_index)!=(0,1,0)
                or request.quantity<1 or weekly and request.quantity!=1):
            raise ValueError("Growth exchange original manual request")
        recipe=RECIPES.get((request.house,request.source,request.source_quantity,
                            request.destination,request.exchange_type))
        if recipe is None:
            raise ValueError("Growth exchange original recipe")
        template,quantity=recipe
        from els_server.storage.material_exchange import exchange
        account=session.account
        operation=f"{session.shop_session_id}:{account.uid}:town-growth:{sequence}"
        reserve=partial(_reserve_weekly,owner=account.uid,template=template) if weekly else None
        factory=partial(_source,request) if request.house in (40257,40273,40310) else None
        return exchange(account.store.path,account.uid,town,event.payload,operation,request,
                        account_id=account.account_id,source_quantity=request.source_quantity,
                        destination=template,output_quantity=quantity,guard=guard,reserve=reserve,source_factory=factory,
                        acknowledgement=partial(acknowledgement,exchange_type=exchange_type))
    except (ValueError,sqlite3.Error):
        if "same" not in locals() or not same():
            return []
        account=session.account
        with closing(sqlite3.connect(Path(account.store.path).resolve().as_uri()+"?mode=ro",uri=True)) as db:
            row=db.execute("""SELECT b.ed FROM reward_balances b JOIN character_owners o ON b.uid=o.uid
                WHERE b.uid=? AND o.account_id=?""",(account.uid,account.account_id)).fetchone()
        return [Event(0x201,kind=0x224,payload=acknowledgement(row[0],result=-1,exchange_type=exchange_type))] if row else []
