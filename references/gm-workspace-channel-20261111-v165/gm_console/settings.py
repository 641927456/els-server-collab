"""Explicit operating settings; game paths, identities and pinned rules stay private."""
from dataclasses import replace
import hashlib
import json
import os
import re
import tomllib

from els_server.config import ServerConfig


FIELDS = [
    ('channel_name', '游戏频道名称', '游戏内显示', 'text', None, 24),
    ('registration_enabled', '开放账号注册', '账号注册', 'bool', None, None),
    ('max_registered_accounts', '注册账号上限', '账号注册', 'int', 2, 256),
    ('max_connections', '同时连接上限', '连接与性能', 'int', 1, 384),
    ('economy_workers', '经济事务工作线程', '连接与性能', 'int', 1, 4),
    ('idle_timeout', '空闲连接超时（秒）', '连接与性能', 'number', 0, 3600),
    ('frame_timeout', '报文读取超时（秒）', '连接与性能', 'number', 0, 3600),
    ('write_timeout', '报文发送超时（秒）', '连接与性能', 'number', 0, 3600),
    ('authentication_timeout', '身份认证超时（秒）', '连接与性能', 'number', 0, 3600),
    ('shutdown_timeout', '正常停服等待（秒）', '连接与性能', 'number', 0, 3600),
    ('attribute_enchant_enabled', '属性赋予', '现有功能入口', 'bool', None, None),
    ('normal_equipment_moves_enabled', '普通装备穿脱', '现有功能入口', 'bool', None, None),
    ('equipment_repair_enabled', '装备修理', '现有功能入口', 'bool', None, None),
    ('log_max_bytes', '单份日志大小（字节）', '运行日志', 'int', 4096, 100000000),
    ('log_backups', '保留日志份数', '运行日志', 'int', 1, 20),
]
NAMES = {row[0] for row in FIELDS}


def revision(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(service):
    raw = service.config_path.read_bytes()
    config = ServerConfig.load(service.config_path)
    return dict(revision=revision(raw), editable=service.phase == 'stopped' and not service.running()
                and not service.shutting_down and service._ports_drained(),
                fields=[dict(name=name, label=label, group=group, kind=kind, min=low, max=high,
                             value=getattr(config, name)) for name, label, group, kind, low, high in FIELDS],
                readonly=dict(friends_coop_enabled=config.friends_coop_enabled),
                effect='正常关服后保存，下次开服生效；保存前自动备份双库和配置。')


def update(service, value):
    if set(value) != {'operation_id', 'reason', 'expected_revision', 'settings'}:
        raise ValueError('服务配置请求字段无效')
    if service.phase != 'stopped' or service.running() or service.shutting_down or not service._ports_drained():
        raise ValueError('请先正常关服，确认服务已停止后再保存服务参数')
    settings = value['settings']
    if not isinstance(settings, dict) or set(settings) != NAMES:
        raise ValueError('请提交完整的服务运营参数')
    raw = service.config_path.read_bytes()
    if value['expected_revision'] != revision(raw):
        raise ValueError('服务配置已被更新，请重新载入后提交')
    for name, _, _, kind, _, _ in FIELDS:
        if kind == 'bool' and type(settings[name]) is not bool:
            raise ValueError('功能开关必须为布尔值')
    # Reuse the actual deployment validator, including mode/profile restrictions.
    config = ServerConfig.load(service.config_path)
    candidate = replace(config, **settings)
    text = raw.decode('utf8')
    document = tomllib.loads(text)
    for name, new_value in settings.items():
        literal = json.dumps(new_value, ensure_ascii=False, allow_nan=False)
        if name in document['server']:
            pattern = rf'''(?m)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*)(?:"(?:[^"\\\r\n]|\\.)*"|'[^'\r\n]*'|[^"'\r\n#]*?)([ \t]*(?:\#[^\r\n]*)?)(\r?)$'''
            text, count = re.subn(pattern, lambda m: m[1] + literal + m[2] + m[3], text)
            if count != 1:
                raise ValueError('配置键需使用独立单行格式：' + name)
        else:
            text = text.rstrip() + '\n' + name + ' = ' + literal + '\n'
    parsed = tomllib.loads(text)['server']
    if any(parsed[name] != new_value for name, new_value in settings.items()):
        raise ValueError('配置序列化结果不一致')
    backup = service.backup()
    # Do not silently overwrite an external edit made while the backup ran.
    if service.config_path.read_bytes() != raw:
        raise ValueError('备份期间配置发生变化，请重新载入')
    temporary = service.config_path.with_name(service.config_path.name + '.gm.tmp')
    created = False
    try:
        with temporary.open('x', encoding='utf8', newline='') as stream:
            created = True
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(service.config_path)
    finally:
        if created:temporary.unlink(missing_ok=True)
    service.config = candidate
    return dict(revision=revision(service.config_path.read_bytes()), settings=settings,
                backup=backup['directory'], message='服务参数已保存，下次开服生效')
