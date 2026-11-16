"""Resolve guild-war announcement names for send and preview."""
from els_server.storage.read_scope import snapshot_connection


def guild_names(path, guilds):
    if (not isinstance(guilds, list) or not 1 <= len(guilds) <= 10
            or any(type(uid) is not int or not 1 <= uid < 2**63 for uid in guilds)
            or len(set(guilds)) != len(guilds)):
        raise ValueError('请输入按实际名次排列的 1–10 个公会编号')
    with snapshot_connection(path) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_guilds'").fetchone() is None:
            raise ValueError('本服暂无公会记录')
        keys = ','.join('?' for _ in guilds)
        names = dict(db.execute(f'SELECT id,name FROM native_guilds WHERE id IN ({keys})', guilds))
    if len(names) != len(guilds):
        raise ValueError('名次清单包含不存在的公会')
    return [names[uid] for uid in guilds]
