"""A18/A19 current active-offer minimum reference; no sale-history invention."""
from els_server.domain.tradeboard_query import _rows, _page, QueryNotReady
from els_server.domain.tradeboard_template_predicate import catalog_facts
from els_server.domain.inventory_items import item_body
from els_server.protocol.tradeboard_metadata_item import read_item
from els_server.protocol.tradeboard_minimum_messages import Request, reply


def minimum(snapshot, selected, limit, *, catalog=None):
    """Use the already qualified actual complete active-ledger snapshot only.

    Local reviewed price/template/listing ordering makes the first row the
    actual lowest available unit price. The caller chooses its reviewed batch
    bound; native 10-row presentation and official sample-count guidance do
    not establish this server query's batch limit.
    """
    if type(selected)is not Request:raise ValueError('Exact A18 request required')
    if not 0<selected.template<2**31:raise ValueError('Exact positive template required')
    if selected.auxiliary:raise QueryNotReady('A18 conditional first CItem vector namespace consumer not qualified')
    if min(selected.pet_data_id,selected.mount_data_id)<0:raise ValueError('Positive native data-ID namespace required')
    facts=catalog_facts(selected.template,catalog)
    if selected.pet_data_id and facts.item_type_bucket!=12:raise ValueError('Pet data-ID requires native type12')
    if selected.mount_data_id and facts.item_type_bucket!=13:raise ValueError('Mount data-ID requires native type13')
    rows=[]
    for row in _rows(snapshot):
        if row['item']['template']!=selected.template:continue
        if selected.pet_data_id or selected.mount_data_id:
            native=read_item(item_body(row['item']))
            if selected.pet_data_id and native.pet_data_id!=selected.pet_data_id:continue
            if selected.mount_data_id and native.mount_data_id!=selected.mount_data_id:continue
        rows.append(row)
    return _page(rows,{},limit)


def response(snapshot, selected, limit, *, catalog=None):
    page=minimum(snapshot,selected,limit,catalog=catalog)
    # Third i32 is read but never consumed by the actual handler. Preserve a
    # neutral0; do not claim it is total count, price, an entitlement or a fee.
    return reply(selected.template,page.rows,opaque=0)
