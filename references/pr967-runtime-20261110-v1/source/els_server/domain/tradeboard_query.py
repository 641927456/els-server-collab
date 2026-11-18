"""Read-only authoritative offer selection; no market producer or SQL writer.

Stable price/template/listing tie order is an explicit local query policy.
Unknown instance consumers fail explicitly; they never become empty success.
"""
from dataclasses import dataclass
import copy
from els_server.domain.inventory_items import validate_item, item_body
from els_server.domain.tradeboard_template_predicate import catalog_facts, NativeStaticSelector, matches_static
from els_server.protocol.tradeboard_query_messages import listing, query_reply
from els_server.protocol.tradeboard_metadata_item import read_item
from els_server.domain.tradeboard_metadata import ActiveOffer, ActiveOfferSnapshot, ACTIVE_OFFER_SOURCE

SOURCE='trade_board_listings/current-active-read-v1'
ORDER_POLICY='local-unit-price-template-listing-ascending-v1'

class QueryNotReady(ValueError):pass

@dataclass(frozen=True)
class OfferSnapshot:
    source:str
    now:int
    ready:bool
    rows:tuple

@dataclass(frozen=True)
class QueryPage:
    rows:tuple
    more:bool
    policy:str=ORDER_POLICY

def read_snapshot(db,now,read_offers):
    """Adapter for the sole ledger owner's real read_offers(db, now) contract."""
    if type(now)is not int or now<=0 or not callable(read_offers):raise QueryNotReady('Bound server clock and ledger reader required')
    if not db.in_transaction or db.execute('PRAGMA query_only').fetchone()!=(1,):raise QueryNotReady('Actual query-only SQL transaction required')
    rows=read_offers(db,now)
    if not isinstance(rows,(list,tuple)):raise QueryNotReady('Actual ledger reader did not return rows')
    snapshot=OfferSnapshot(SOURCE,now,True,tuple(copy.deepcopy(rows)))
    _rows(snapshot)
    return snapshot

def _rows(snapshot):
    if type(snapshot)is not OfferSnapshot or snapshot.source!=SOURCE or snapshot.ready is not True or type(snapshot.now)is not int or snapshot.now<=0 or type(snapshot.rows)is not tuple:
        raise QueryNotReady('Actual complete active-offer snapshot unavailable')
    seen=set()
    for row in snapshot.rows:
        listing(row) # Exact full-instance reader and current source fields.
        if row['listing_id']in seen or row['expires_at']<=snapshot.now:raise QueryNotReady('Duplicate or nonactive authoritative offer')
        seen.add(row['listing_id'])
    return snapshot.rows

def _key(row):return(row['unit_price'],row['item']['template'],row['listing_id'])

def _page(rows,values,limit):
    if type(limit)is not int or not 1<=limit<=65536:raise QueryNotReady('Bound actual query batch size required')
    cursor=tuple(values.get(n,0)for n in('cursor_price','cursor_template','cursor_listing_id'))
    if any(cursor):
        if not all(type(n)is int and n>0 for n in cursor):raise ValueError('Incomplete native continuation cursor')
        rows=[r for r in rows if _key(r)>cursor]
    ordered=sorted(rows,key=_key);return QueryPage(tuple(ordered[:limit]),len(ordered)>limit)

def simple(snapshot,limit):
    """Natural A00 01/00 refresh: rows from the actual current SQL snapshot."""
    return _page(_rows(snapshot),{},limit)


def metadata_snapshot(snapshot,revision):
    """Same actual read transaction/rows for the four native metadata namespaces.

    revision is an internal ledger snapshot label supplied by its owner; it is
    not a client sequence, a second SQL query or an offer authority.
    """
    if type(revision)is not str or not revision:raise QueryNotReady('Bound actual snapshot revision required')
    return ActiveOfferSnapshot(ACTIVE_OFFER_SOURCE,revision,True,True,
        tuple(ActiveOffer(row['listing_id'],item_body(row['item']),True)for row in _rows(snapshot)))


def _positive_ids(values):
    if any(type(v)is not int or not 0<v<2**31 for v in values):raise ValueError('Exact positive native ID namespace required')


def quick(snapshot,values,limit,*,catalog=None,option_match=None,usable=None):
    """A0C main/quick search: resolved name IDs plus the native static sets.

    DTO+10 is a vector of resolved OPTION IDs, not template IDs. DTO+6A is
    NameCheckUsableItem. Both selected comparisons require their own proven
    consumers; no AND/OR option rule or character eligibility is guessed here.
    The client already performs its separate CF1150 context branch when
    creating the template-ID set. This server slice uses the common name-path
    static predicate and never recreates that client context from the packet.
    """
    for name in('ids_00','ids_80','ids_90'):_positive_ids(values[name])
    if any(type(v)is not int or not 0<=v<2**31 for v in values['ids_10']):raise ValueError('Exact option ID vector required')
    if values['ids_10']and not callable(option_match):raise QueryNotReady('Quick option-vector consumer unavailable')
    if type(values['flag_6a'])is not bool:raise ValueError('Exact usability boolean required')
    if values['flag_6a']and not callable(usable):raise QueryNotReady('Current-character usability consumer unavailable')
    selector=NativeStaticSelector(values['category'],values['mode_29'],values['set_2a'],(),
                                  values['set_3a'],values['set_4a'],values['set_5a'])
    selected=[]
    for row in _rows(snapshot):
        item=validate_item(row['item']);facts=catalog_facts(item['template'],catalog)
        if not matches_static(facts,selector):continue
        templates,pets,mounts=(values[n]for n in('ids_00','ids_80','ids_90'))
        if templates or pets or mounts:
            known=item['template']in templates
            if pets and facts.item_type_bucket==12:
                known=known or read_item(item_body(item)).pet_data_id in pets
            if mounts and facts.item_type_bucket==13:
                known=known or read_item(item_body(item)).mount_data_id in mounts
            if not known:continue
        if values['ids_10']:
            matched=option_match(row,values['ids_10'])
            if type(matched)is not bool:raise QueryNotReady('Unknown quick option-vector comparison')
            if not matched:continue
        if values['flag_6a']:
            matched=usable(row)
            if type(matched)is not bool:raise QueryNotReady('Unknown current-character usability comparison')
            if not matched:continue
        selected.append(row)
    return _page(selected,values,limit)

def full(snapshot,values,limit,*,catalog=None,option_match=None,pet_growth=None):
    """Qualified A0A static slice plus exact stored-instance predicates.

    option_match(row, kind, groups) and pet_growth(row, requested) are separately bound
    source consumers. Missing consumers reject selected filters, never guess.
    """
    if values['ids_dc']:raise QueryNotReady('A0A final ID namespace consumer not qualified')
    _positive_ids(values['template_ids']);_positive_ids(values['mount_data_ids'])
    selector=NativeStaticSelector(values['category'],values['mode_11'],
                                  values['set_12'],values['set_22'],values['set_32'],
                                  values['set_42'],values['set_52'])
    for name in('enchant_range','reforge_range','price_range'):
        lo,hi=values[name]
        if lo>hi:raise ValueError('Reversed native range')
    requested_options=(('magic_socket',values['option_groups_66']),
                       ('random_identification',values['option_groups_7e']))
    if len(requested_options[0][1])>6 or len(requested_options[1][1])>5:raise ValueError('Current native search-control count')
    if any(any(group for group in groups)for _,groups in requested_options) and not callable(option_match):raise QueryNotReady('Original option query consumer unavailable')
    growth=tuple(values[n]for n in('cheer','patience','expert','concentration'))
    if any(growth)and not callable(pet_growth):raise QueryNotReady('Pet growth field consumer unavailable')
    selected=[]
    for row in _rows(snapshot):
        item=validate_item(row['item']);facts=catalog_facts(item['template'],catalog)
        if not matches_static(facts,selector):continue
        ids=values['template_ids'];mounts=values['mount_data_ids']
        if ids or mounts:
            known=item['template']in ids
            if mounts and facts.item_type_bucket==13:
                native=read_item(item_body(item));known=known or native.mount_data_id in mounts
            if not known:continue
        if not values['price_range'][0]<=row['unit_price']<=values['price_range'][1]:continue
        if not values['enchant_range'][0]<=item.get('enhancement',0)<=values['enchant_range'][1]:continue
        reforge=item.get('reforge',[0,0,0])[0]
        if not values['reforge_range'][0]<=reforge<=values['reforge_range'][1]:continue
        if values['seal_count']!=255:
            definition=(catalog.item(item['template'])if catalog is not None else __import__('els_server.game_data',fromlist=['client_data']).client_data().item(item['template']))
            maximum=definition['record'][0xd7];used=item.get('seal_used',0)
            if maximum==255 or used>maximum:raise QueryNotReady('Special or unqualified remaining-seal counter')
            if maximum-used!=values['seal_count']:continue
        options_pass=True
        for kind,groups in requested_options:
            if not any(group for group in groups):continue
            matched=option_match(row,kind,groups)
            if type(matched)is not bool:raise QueryNotReady('Unknown option-query comparison')
            if not matched:options_pass=False;break
        if not options_pass:continue
        if any(growth):
            if facts.item_type_bucket!=12:continue
            matched=pet_growth(row,growth)
            if type(matched)is not bool:raise QueryNotReady('Exact pet growth-query comparison required')
            if not matched:continue
        selected.append(row)
    return _page(selected,values,limit)

def reply(kind,page,*,result=0,text=''):
    if type(page)is not QueryPage:raise QueryNotReady('Qualified actual query page required')
    # A01's byte is an adoption flag. A0B/D's bool signals more batches.
    return query_reply(kind,page.rows,result=result,flag=(not result and(kind==0xa01 or page.more)),text=text)
