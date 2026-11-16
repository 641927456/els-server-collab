"""Original Ironwall aiming actors owned by the participating rider.

The native riding user creates its own aiming target. This authority does
not include the turret, enemy summons, or another participant's target.
"""
GRAPH='1e010c5a23db8aaf3acc9bbbb7a7db93d705c7e3fc995cbc817ce01842711877'
SOURCES={
    0:(8921,{
        8908:('DEVILDOM5_IRONWALL_STAGE0_TURRET.lua','8f85e7cb9b66134f6a987d9080f5bf1a1eeac83f1603d50dde2fae570279dec3'),
    }),
    1:(8922,{
        8909:('DEVILDOM5_IRONWALL_STAGE1_TURRET.lua','16f6db0369debf115328cad184d9295d36935426936aa0b1088b3ed52b8762fd'),
        8942:('DEVILDOM5_IRONWALL_STAGE1_TURRET2.lua','cfb359efa804a352c76870b29d2c01de0abb6b4eb6c70e5f5047579fe265334e'),
    }),
}

def templates(run):
    if run.identity!=35110 or run.part!=0 or run.graph['source_sha256']!=GRAPH:
        return frozenset()
    source=SOURCES.get(run.stage)
    if source is None:return frozenset()
    target,turrets=source
    if target not in run.graph['stages'][str(run.stage)]['allowed_summons']:
        return frozenset()
    from els_server.game_data import client_data
    for npc in run.current['npcs']:
        row=turrets.get(npc['template'])
        if row is None or npc.get('dynamic') or npc['key']in run.defeated:continue
        script,digest=row
        if (client_data().npc(npc['template'])['script']==script
                and run.catalog.manifest['source_sha256'].get(script)==digest):
            return frozenset((target,))
    return frozenset()
