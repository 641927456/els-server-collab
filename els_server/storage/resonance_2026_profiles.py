"""Persistent complete local resonance projection; never zero an existing profile.

Explicit new-profile policy: one unexpanded page, one point per account level,
no invested points and zero opaque fields for a new local no-bonus profile.
These are local initial values, not recovered retail constructor defaults.
Existing pages need explicit verified opaque/earned-level metadata imported;
unknown old state is rejected instead of silently reconstructed or erased.
"""
from dataclasses import replace
import hashlib,json
from els_server.storage.resonance_2026_pages import ResonancePages,CharacterResonancePages,ResonancePage
from els_server.storage.resonance_2026_progress import AccountResonance
from els_server.protocol.resonance_2026_state import ResonanceCharacterState

NEW_PROFILE_POLICY='local-one-page-no-bonus-v1'


class ResonanceProfiles:
    def __init__(self,db,curve,original_definition,*,new_profile_policy):
        if new_profile_policy!=NEW_PROFILE_POLICY:raise ValueError('Explicit reviewed local new-profile policy required')
        self.db=db;self.pages=ResonancePages(db,original_definition);self.accounts=AccountResonance(db,curve)
        self.policy_sha=hashlib.sha256((new_profile_policy+':'+hashlib.sha256(original_definition).hexdigest()).encode()).hexdigest()

    def initialize(self):
        if not self.db.in_transaction:raise ValueError('Caller-owned profile initialization required')
        self.pages.initialize();self.accounts.initialize()
        self.db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_profile_metadata(
            character INTEGER PRIMARY KEY,account INTEGER NOT NULL,earned_level INTEGER NOT NULL,
            opaque_json TEXT NOT NULL,policy_sha256 TEXT NOT NULL)''')

    def _metadata(self,account,character):
        row=self.db.execute('SELECT account,earned_level,opaque_json,policy_sha256 FROM resonance2026_profile_metadata WHERE character=?',(character,)).fetchone()
        if row is None:return None
        if row[0]!=account or row[3]!=self.policy_sha or type(row[1]) is not int or not 1<=row[1]<=999:raise ValueError('Profile metadata differs from account/policy')
        opaque=json.loads(row[2])
        if type(opaque) is not list or len(opaque)!=5:raise ValueError('Complete opaque profile metadata required')
        return row[1],tuple(opaque)

    def _state(self,progress,pages,opaque):
        grouped={0:[],1:[],2:[]};points=dict(pages.selected().points)
        for stat in self.pages.rules.stats:grouped[stat.tab].append((stat.stat_id,points.get(stat.stat_id,0)))
        state=ResonanceCharacterState(progress.level,progress.cumulative_experience,pages.selected().available_points,pages.enabled,
            tuple((k,tuple(sorted(v))) for k,v in sorted(grouped.items())),*opaque,pages.selected_page,len(pages.pages))
        state.notice() # Check every packed scalar and all explicit groups now.
        return state

    def register_existing(self,*,account,character,earned_level,opaque):
        """Explicit import of complete old metadata; cannot replace another import."""
        if not self.db.in_transaction:raise ValueError('Caller-owned profile import required')
        self.pages.owner(account,character);pages=self.pages.read(account,character);progress=self.accounts._read(account)
        if pages is None or progress is None or self._metadata(account,character) is not None:raise ValueError('Only known existing unimported profile may be registered')
        if type(earned_level) is not int or not 1<=earned_level<=progress.level or type(opaque) is not tuple or len(opaque)!=5:raise ValueError('Verified earned-level and complete opaque tuple required')
        self._state(progress,pages,opaque)
        self.db.execute('INSERT INTO resonance2026_profile_metadata VALUES (?,?,?,?,?)',(character,account,earned_level,json.dumps(opaque,separators=(',',':')),self.policy_sha))

    def synchronize(self,*,account,character):
        if not self.db.in_transaction:raise ValueError('Caller-owned profile synchronization required')
        self.pages.owner(account,character);progress=self.accounts._read(account)
        if progress is None:raise ValueError('No authoritative account resonance')
        pages=self.pages.read(account,character);metadata=self._metadata(account,character)
        if pages is None:
            if metadata is not None:raise ValueError('Metadata has lost its original character pages')
            points=tuple((r.stat_id,0) for r in self.pages.rules.stats)
            pages=self.pages.provision(account=account,character=character,operation='local-profile:'+self.policy_sha,
                enabled=True,selected_page=1,pages=(ResonancePage(1,progress.level,points),))
            self.db.execute('INSERT INTO resonance2026_profile_metadata VALUES (?,?,?,?,?)',(character,account,progress.level,'[0,0,0,0,0]',self.policy_sha))
            metadata=(progress.level,(0,0,0,0,0))
        elif metadata is None:raise ValueError('Existing profile opaque metadata requires explicit import')
        earned,opaque=metadata
        if progress.level<earned:raise ValueError('Account level moved below granted profile points')
        if progress.level>earned:
            delta=progress.level-earned
            def change(old,revision):
                if old is None:raise ValueError('Lost existing profile')
                return CharacterResonancePages(revision,old.enabled,old.selected_page,tuple(ResonancePage(p.page_id,p.available_points+delta,p.points) for p in old.pages))
            pages=self.pages.mutate(account=account,character=character,operation=f'level-sync:{earned}:{progress.level}',expected_revision=pages.revision,
                kind='account-level-credit',inputs=[earned,progress.level],change=change)
            self.db.execute('UPDATE resonance2026_profile_metadata SET earned_level=? WHERE character=? AND account=?',(progress.level,character,account))
        return self._state(progress,pages,opaque)

    def synchronize_account(self,*,account):
        if not self.db.in_transaction:raise ValueError('Caller-owned account/profile synchronization required')
        characters=[c for c, in self.db.execute('SELECT uid FROM character_owners WHERE account_id=? ORDER BY uid',(account,))]
        return {c:self.synchronize(account=account,character=c) for c in characters}
