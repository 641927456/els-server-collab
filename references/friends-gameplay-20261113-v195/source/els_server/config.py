"""Strict deployment configuration; paths resolve relative to the TOML file."""
from dataclasses import dataclass, field
from pathlib import Path
import math
import tomllib
import ipaddress


DEFAULT_CHANNEL_NAME = '本地测试'


@dataclass(frozen=True)
class ServerConfig:
    host: str = '127.0.0.1'
    port: int = 19400
    profile: str = 'integrated_dx11'
    state_file: Path = Path('state/integrated.sqlite3')
    log_dir: Path = Path('logs/server')
    max_connections: int = 16
    economy_workers: int = 2
    idle_timeout: float = 300.0
    frame_timeout: float = 15.0
    write_timeout: float = 10.0
    egress_mbps: float = 0.0
    shutdown_timeout: float = 15.0
    log_max_bytes: int = 5_242_880
    log_backups: int = 4
    attribute_enchant_enabled: bool = False
    normal_equipment_moves_enabled: bool = False
    equipment_repair_enabled: bool = False
    mode: str = 'friends'
    accounts_file: Path = Path('state/accounts.sqlite3')
    tls_cert: Path = Path('config/server-cert.pem')
    tls_key: Path = Path('config/server-key.pem')
    client_probe_port: int = 19401
    authentication_timeout: float = 8.0
    registration_enabled: bool = False
    max_registered_accounts: int = 64
    # Development gate until native peer transport and two-client play pass.
    friends_coop_enabled: bool = False
    channel_name: str = DEFAULT_CHANNEL_NAME
    anti_cheat_enabled: bool = True
    anti_cheat_min_clear_seconds: dict[int, int] = field(default_factory=dict)
    anti_cheat_max_solo_damage_per_second: dict[int, int] = field(default_factory=dict)
    anti_cheat_sentry_min_interval_ms: int = 0

    def __post_init__(self):
        if type(self.anti_cheat_enabled) is not bool:
            raise ValueError('Invalid anti_cheat_enabled')
        if type(self.anti_cheat_sentry_min_interval_ms) is not int or not 0 <= self.anti_cheat_sentry_min_interval_ms <= 10_000:
            raise ValueError('Invalid anti_cheat_sentry_min_interval_ms')
        for name, bound in (('anti_cheat_min_clear_seconds', 2**31),
                            ('anti_cheat_max_solo_damage_per_second', 2**63)):
            limits = getattr(self, name)
            if (type(limits) is not dict or any(
                    type(map_id) is not int or not 1 <= map_id < 2**31
                    or type(value) is not int or not 1 <= value < bound
                    for map_id, value in limits.items())):
                raise ValueError('Invalid ' + name)
        if (not isinstance(self.channel_name, str) or not self.channel_name.strip()
                or len(self.channel_name.encode('utf-16le')) > 48
                or any(ord(c) < 32 or ord(c) == 127 for c in self.channel_name)):
            raise ValueError('频道名称需要 1–24 个字符，不能包含控制字符')
        if self.mode != 'friends':raise ValueError('Use the unified authenticated server; choose its bind IP with host')
        if type(self.registration_enabled) is not bool or self.registration_enabled and self.mode!='friends':raise ValueError('Registration requires friends mode')
        if type(self.max_registered_accounts) is not int or not 2<=self.max_registered_accounts<=256:raise ValueError('Registration capacity')
        if type(self.friends_coop_enabled) is not bool or self.friends_coop_enabled and self.mode!='friends':raise ValueError('Cooperative dungeons require friends mode')
        if not isinstance(self.host,str) or ipaddress.ip_address(self.host).version!=4:raise ValueError('Expected an IPv4 bind address')
        if self.mode=='friends' and (self.profile!='integrated_dx11' or any(not isinstance(getattr(self,n),Path) for n in ('accounts_file','tls_cert','tls_key'))):raise ValueError('Friends mode requires persistent profile, account registry and TLS certificate/key')
        if self.accounts_file is not None and self.accounts_file==self.state_file:raise ValueError('Account registry must be separate from game save')
        if self.profile not in ('bootstrap', 'integrated_dx11'):raise ValueError('Unknown feature profile')
        if type(self.attribute_enchant_enabled) is not bool or self.attribute_enchant_enabled and self.profile!='integrated_dx11':raise ValueError('Invalid attribute enchant profile')
        if type(self.normal_equipment_moves_enabled) is not bool or self.normal_equipment_moves_enabled and self.profile!='integrated_dx11':raise ValueError('Invalid normal equipment move profile')
        if type(self.equipment_repair_enabled) is not bool or self.equipment_repair_enabled and self.profile!='integrated_dx11':raise ValueError('Invalid repair profile')
        for name, low, high in [('port',0,65535),('max_connections',1,384),('economy_workers',1,4),
                                ('log_max_bytes',4096,100_000_000),('log_backups',1,20),('client_probe_port',1,65535)]:
            value=getattr(self,name)
            if type(value) is not int or not low<=value<=high:raise ValueError('Invalid '+name)
        if(type(self.egress_mbps)not in(int,float)or not math.isfinite(self.egress_mbps)or self.egress_mbps<0 or not math.isfinite(self.egress_mbps*125000)):raise ValueError('Invalid egress_mbps')
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
            default=cls.__dataclass_fields__[name].default
            value=values.get(name,str(default) if default is not None else None)
            if value is None:continue
            if not isinstance(value,str) or not value.strip():raise ValueError('Invalid '+name)
            values[name]=(path.parent/value).resolve()
        for name in ('anti_cheat_min_clear_seconds', 'anti_cheat_max_solo_damage_per_second'):
            if name not in values:
                continue
            limits = values[name]
            if type(limits) is not dict or any(
                    not key.isascii() or not key.isdecimal() or key.startswith('0') or len(key) > 10
                    for key in limits):
                raise ValueError('Expected canonical map IDs in ' + name)
            values[name] = {int(key): value for key, value in limits.items()}
        return cls(**values)

    def session_options(self):
        if self.profile=='bootstrap':return dict(client_build='dx11_260923',channel_name=self.channel_name)
        return dict(client_build='dx11_260923',channel_name=self.channel_name,
                    enter_town=True,enter_dungeon=True,
                    npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                    reward_test=True,item_test=True,drop_probe=True,drop_test=True,
                    boss_gauge_test=True,shop_test=True,ice_test=True,
                    attribute_enchant_enabled=self.attribute_enchant_enabled,
                    normal_equipment_moves_enabled=self.normal_equipment_moves_enabled,
                    equipment_repair_enabled=self.equipment_repair_enabled)
