"""Preserve the native ordinary/ice distinction for verified fashion readers."""
from els_server.game_data import client_data


def native_groups(rows):
    client=client_data()
    result=[]
    for row in rows:
        item=client.item(row['template'])
        group=row['group']
        if group in (7,27) and item['flags4']&1:
            group=27 if item['flags8']&256 else 7
        result.append(dict(row,group=group))
    return result
