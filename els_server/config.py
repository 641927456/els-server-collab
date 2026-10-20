"""Strict deployment configuration; paths resolve relative to the TOML file."""
from dataclasses import dataclass
from pathlib import Path
import math
import tomllib
import ipaddress


@dataclass(frozen=True)
class ServerConfig:
    host: str = '127.0.0.1'
    port: int = 19400
    profile: str = 'integrated_dx11'
    state_file: Path = Path('state/integrated.sqlite3')
    log_dir: Path = Path('logs/server')
    max_connections: int = 16
    idle_timeout: float = 300.0
    frame_timeout: float = 15.0
    write_timeout: float = 10.0
    shutdown_timeout: float = 15.0
    log_max_bytes: int = 5_242_880
    log_backups: int = 4
    attribute_enchant_enabled: bool = False
    normal_equipment_moves_enabled: bool = False
    equipment_repair_enabled: bool = False
    mode: str = 'local'
    accounts_file: Path | None = None
    tls_cert: Path | None = None
    tls_key: Path | None = None
    client_probe_port: int = 19401
    authentication_timeout: float = 8.0
    registration_enabled: bool = False
    max_registered_accounts: int = 64
    # Development gate until native peer transport and two-client play pass.
    friends_coop_enabled: bool = False

    def __post_init__(self):
        if self.mode not in ('local','friends'):raise ValueError('Unknown server mode')
        if type(self.registration_enabled) is not bool or self.registration_enabled and self.mode!='friends':raise ValueError('Registration requires friends mode')
        if type(self.max_registered_accounts) is not int or not 2<=self.max_registered_accounts<=256:raise ValueError('Registration capacity')
        if type(self.friends_coop_enabled) is not bool or self.friends_coop_enabled and self.mode!='friends':raise ValueError('Cooperative dungeons require friends mode')
        if not isinstance(self.host,str) or ipaddress.ip_address(self.host).version!=4:raise ValueError('Expected an IPv4 bind address')
        if self.mode=='local' and self.host != '127.0.0.1':raise ValueError('Local mode only supports loopback binding')
        if self.mode=='friends' and (self.profile!='integrated_dx11' or any(not isinstance(getattr(self,n),Path) for n in ('accounts_file','tls_cert','tls_key'))):raise ValueError('Friends mode requires persistent profile, account registry and TLS certificate/key')
        if self.accounts_file is not None and self.accounts_file==self.state_file:raise ValueError('Account registry must be separate from game save')
        if self.profile not in ('bootstrap', 'integrated_dx11'):raise ValueError('Unknown feature profile')
        if type(self.attribute_enchant_enabled) is not bool or self.attribute_enchant_enabled and self.profile!='integrated_dx11':raise ValueError('Invalid attribute enchant profile')
        if type(self.normal_equipment_moves_enabled) is not bool or self.normal_equipment_moves_enabled and self.profile!='integrated_dx11':raise ValueError('Invalid normal equipment move profile')
        if type(self.equipment_repair_enabled) is not bool or self.equipment_repair_enabled and self.profile!='integrated_dx11':raise ValueError('Invalid repair profile')
        for name, low, high in [('port',0,65535),('max_connections',1,128),
                                ('log_max_bytes',4096,100_000_000),('log_backups',1,20),('client_probe_port',1,65535)]:
            value=getattr(self,name)
            if type(value) is not int or not low<=value<=high:raise ValueError('Invalid '+name)
        for name in ('idle_timeout','frame_timeout','write_timeout','shutdown_timeout','authentication_timeout'):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=3600:
                raise ValueError('Invalid '+name)
        for name in ('state_file','log_dir'):
            if not isinstance(getattr(self,name),Path):raise ValueError('Invalid path: '+name)

    @classmethod
    def load(cls, path):
        path=Path(path).resolve()
        document=tomllib.loads(path.read_text(encoding='utf8'))
        if set(document)!={'server'}:raise ValueError('Configuration requires only a [server] table')
        values=document['server']
        unknown=set(values)-set(cls.__dataclass_fields__)
        if unknown:raise ValueError('Unknown configuration keys: '+', '.join(sorted(unknown)))
        for name in ('state_file','log_dir','accounts_file','tls_cert','tls_key'):
            default=getattr(cls(),name)
            value=values.get(name,str(default) if default is not None else None)
            if value is None:continue
            if not isinstance(value,str) or not value.strip():raise ValueError('Invalid '+name)
            values[name]=(path.parent/value).resolve()
        return cls(**values)

    def session_options(self):
        if self.profile=='bootstrap':return {'client_build':'dx11_260923'}
        return dict(client_build='dx11_260923',enter_town=True,enter_dungeon=True,
                    npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                    reward_test=True,item_test=True,drop_probe=True,drop_test=True,
                    boss_gauge_test=True,shop_test=True,ice_test=True,
                    attribute_enchant_enabled=self.attribute_enchant_enabled,
                    normal_equipment_moves_enabled=self.normal_equipment_moves_enabled,
                    equipment_repair_enabled=self.equipment_repair_enabled)
