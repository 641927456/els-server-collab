"""Atomic native613 category refund with one existing ordinary scroll."""
import hashlib,json
from els_server.protocol.resonance_2026_scroll import scroll_request
from els_server.storage.resonance_2026_resets import ResetOperations,canonical
from els_server.storage.resonance_2026_pages import CharacterResonancePages,ResonancePage
from els_server.storage.item_actor import require_active_character

class ScrollOperations(ResetOperations):
    def edit(self,*,account,character,operation,expected_revision,payload,kind):
        if not self.db.in_transaction:raise ValueError('Caller-owned scroll transaction required')
        with self.profiles.pages.transaction():
            return self._scroll(account,character,operation,expected_revision,payload,kind)

    def _scroll(self,account,character,operation,expected_revision,payload,kind):
        if kind!=0x613:raise ValueError('Category scroll route')
        category,page=scroll_request(payload)
        profiles=self.profiles;pages=profiles.pages
        pages.owner(account,character);require_active_character(self.db,character)
        metadata=profiles._metadata(account,character)
        if metadata is None or metadata[1]!=(0,0,0,0,0):
            raise ValueError('Unknown temporary category refund policy')
        digest=hashlib.sha256(canonical([account,character,kind,payload.hex(),self.items.digest]).encode()).hexdigest()
        previous=self.db.execute('SELECT account,request_sha256,page_sha256,page_revision,positions_json FROM resonance2026_reset_receipts WHERE character=? AND operation=?',(character,operation)).fetchone()
        if previous is not None:
            receipt=self.db.execute('SELECT request_sha256,revision FROM resonance2026_page_receipts WHERE character=? AND operation=?',(character,operation)).fetchone()
            current=pages.read(account,character)
            if previous[:2]!=(account,digest) or receipt!=previous[2:4] or current is None or current.revision<previous[3]:
                raise ValueError('Category scroll receipt conflicts or lost state')
            return self._reply(account,character,0x614,tuple(tuple(p)for p in json.loads(previous[4])))
        if self.db.execute('SELECT 1 FROM resonance2026_page_receipts WHERE character=? AND operation=?',(character,operation)).fetchone():
            raise ValueError('Page operation exists without matching scroll receipt')
        used={}
        def change(current,revision):
            if current is None or not current.enabled or page!=current.selected_page:
                raise ValueError('Stale or unopened category scroll page')
            selected=current.selected();rules=pages.rules
            refund=sum(value for stat,value in selected.points if rules.stat(stat).tab==category)
            # The UI-only empty-category policy is not yet recovered. This
            # finite positive-refund route refuses it without spending a scroll.
            if refund<=0:raise ValueError('Empty-category scroll policy is not verified')
            prior=self.items.groups['scroll'][:self.items.groups['scroll'].index(163564)]
            for template in prior:
                if self.db.execute('SELECT 1 FROM inventory_items WHERE owner=? AND template=? AND count>0 LIMIT 1',(character,template)).fetchone():
                    raise ValueError('Earlier native scroll variant is outside verified admission')
            updated=tuple((stat,0 if rules.stat(stat).tab==category else value)for stat,value in selected.points)
            checked=rules.add(current=updated,additions=(),available_points=selected.available_points+refund,bonus_points=())
            used['positions'],used['consumed']=self._consume(character,'scroll',1)
            edited=tuple(ResonancePage(p.page_id,checked.remaining_points,checked.points)if p.page_id==page else p for p in current.pages)
            return CharacterResonancePages(revision,current.enabled,current.selected_page,edited)
        pages.mutate(account=account,character=character,operation=operation,expected_revision=expected_revision,
            kind='category-scroll',inputs=[kind,payload.hex(),self.items.digest],change=change)
        page_sha,revision=self.db.execute('SELECT request_sha256,revision FROM resonance2026_page_receipts WHERE character=? AND operation=?',(character,operation)).fetchone()
        self.db.execute('INSERT INTO resonance2026_reset_receipts VALUES(?,?,?,?,?,?,?,?)',
            (character,operation,account,digest,page_sha,revision,canonical(used['positions']),canonical(used['consumed'])))
        return self._reply(account,character,0x614,used['positions'])
