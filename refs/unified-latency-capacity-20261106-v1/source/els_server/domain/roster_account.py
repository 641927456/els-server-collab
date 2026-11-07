"""Authenticated account before the player has created or selected a character."""
from pathlib import Path
from els_server.domain.local_session import LocalAccount,SessionOrderError
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState


class RosterAccount(LocalAccount):
    def __init__(self,path,account_id,account_name,*,characters=None):
        super().__init__(None,account_id,account_name)
        self.path=Path(path)
        self.uid=None
        self.characters=self._reuse_characters(characters,self.path) if characters is not None else Characters(self.path,account_id)

    def character(self):return None
    def enable_characters(self):return self.characters
    # Session feature initialization must not allocate a dummy character save.
    # Persistent gameplay stores belong to a selected, owned character only.
    def enable_rewards(self):return None
    def enable_inventory(self):return None
    def get_reward_balances(self):raise SessionOrderError('No character selected')
    def get_inventory_snapshot(self):raise SessionOrderError('No character selected')

    def for_character(self,uid):
        self.characters.identity(uid)
        if uid not in self.character_accounts:
            account=LocalAccount(LocalState(self.path,uid),self.account_id,self.account_name)
            account.root=self;account.characters=self.characters
            account.enable_inventory();self.character_accounts[uid]=account
        return self.character_accounts[uid]
