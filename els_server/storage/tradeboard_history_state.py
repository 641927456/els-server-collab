"""Exact read-only original purchases, visible only after whole seller pickup.

No receipt/history is created or backfilled. Sale time is the original locked
purchase clock. The price column is explicitly user-authorized per-purchase gross ED before
fee. Original source/price/time values remain separate; no pickup time is used.
"""
from dataclasses import dataclass
from els_server.storage.trade_board_state import exists, listing, POLICY, TABLE, ACTIONS, RECEIPTS, settlement_receipts
from els_server.storage.game_mail import _active_owner
from els_server.protocol.tradeboard_history_messages import Row,reply


@dataclass(frozen=True)
class HistoryRecord:
    source_id:int
    operation:str
    item:dict
    unit_price:int
    gross_ed:int
    quantity:int
    traded_at:int


def _purchases(db,r,now):
    # Original shared verifier validates every paired A06 and exact continuous
    # settlement intervals, returned pieces, whole gross and fee differences.
    settlement_receipts(db,r)
    purchases=db.execute('''SELECT p.operation,p.buyer_account_id,p.buyer_uid,p.quantity,p.gross_ed,
      p.source_item_uid,p.digest,p.purchased_at,p.policy,i.owner,i.kind,i.request_hash
      FROM trade_board_purchases p LEFT JOIN inventory_action_receipts i ON i.operation_id=p.operation
      WHERE p.listing_id=?''',(r['id'],)).fetchall()
    quantity=gross=0;result=[]
    for p in purchases:
        if(type(p[0])is not str or not p[0]or any(type(p[k])is not int or p[k]<=0 for k in(1,2,3,4,5))or
           p[4]!=p[3]*r['unit_price']or p[5]!=r['item_uid']or p[8]!=POLICY or p[9:12]!=(p[2],0xa08,p[6])or
           type(p[7])is not int or not r['created_at']<=p[7]<r['expires_at']or not p[7]<=r['last_moment']<=now):
            raise ValueError('Actual original purchase time/quantity/source/receipt mismatch')
        quantity+=p[3];gross+=p[4]
        result.append(HistoryRecord(r['id'],p[0],dict(r['item'],count=p[3]),r['unit_price'],p[4],p[3],p[7]))
    if(quantity,gross)!=(r['sold_count'],r['gross_ed']):raise ValueError('Claimed ledger has no exact paired purchase totals')
    return result


def read_records(db,owner,account_id,now):
    if(not db.in_transaction or db.execute('PRAGMA query_only').fetchone()!=(1,)or
       any(type(v)is not int or not 0<v<2**63 for v in(owner,account_id))or
       type(now)is not int or not 0<now<2**40):raise ValueError('Actual owner and readonly snapshot required')
    _active_owner(db,account_id,owner)
    if not exists(db,TABLE):return []
    if not all(exists(db,name)for name in(ACTIONS,RECEIPTS,'inventory_action_receipts')):
        raise ValueError('Original history has no complete paired receipt schema')
    # This is the exact new, uninstalled original-writer schema. Unknown older
    # tables explicitly fail; a reader never migrates or invents sale times.
    columns=[r[1]for r in db.execute('PRAGMA table_info(trade_board_purchases)')]
    if columns!=['operation','buyer_account_id','buyer_uid','listing_id','quantity','gross_ed','source_item_uid','digest','purchased_at','policy']:
        raise ValueError('Actual timestamped original purchase schema required')
    selected=db.execute('''SELECT p.listing_id FROM trade_board_purchases p JOIN trade_board_listings l ON l.id=p.listing_id
      WHERE l.seller_uid=? AND l.state='claimed' AND l.sold_count>0
      ORDER BY p.purchased_at DESC,p.operation DESC LIMIT 30''',(owner,)).fetchall()
    records=[]
    for identity in dict.fromkeys(row[0]for row in selected):
        r=listing(db,identity)
        if(r is None or (r['seller_uid'],r['seller_account_id'],r['state'])!=(owner,account_id,'claimed')or
           not 0<r['sold_count']<=r['original_count']or r['remaining']or
           not r['gross_ed']==r['claimed_gross_ed']>0 or r['claimed_sold_count']!=r['sold_count']or type(r['last_moment'])is not int or
           not r['created_at']<=r['last_moment']<=now):raise ValueError('Actual completed whole claimed source required')
        records.extend(_purchases(db,r,now))
    return sorted(records,key=lambda r:(r.traded_at,r.operation),reverse=True)[:30]


def wire_rows(records,*,amount='gross_ed'):
    if type(records)not in(list,tuple)or len(records)>30 or any(type(r)is not HistoryRecord for r in records):
        raise ValueError('Exact selected original history records required')
    if amount!='gross_ed':
        raise ValueError('User-authorized history column is actual per-purchase gross ED')
    return [Row(index=index,source_id=r.source_id,item=r.item,traded_price=getattr(r,amount),opaque_419=0,
                quantity=r.quantity,traded_at=r.traded_at)for index,r in enumerate(records)]


def response(db,owner,account_id,now,*,amount='gross_ed'):
    return reply(wire_rows(read_records(db,owner,account_id,now),amount=amount))
