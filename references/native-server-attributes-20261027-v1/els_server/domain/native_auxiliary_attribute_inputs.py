"""Same-snapshot title/pet/Artifact/collection inputs for collector integration.

This supplies these four original source groups only. Worn/set, active buffs,
named/preset and other collector sources remain separate explicit producers.
"""
from els_server.domain.native_title_attribute_inputs import inputs as title_inputs
from els_server.domain.native_pet_attribute_inputs import option_ids as pet_options
from els_server.domain.native_artifact_attribute_inputs import option_ids as artifact_options
from els_server.domain.native_collection_attribute_inputs import option_ids as collection_options

def build(snapshot, *, mode, at):
    if type(mode)is not int or mode not in(0,1)or type(at)is not int or not 0<=at<2**40:
        raise ValueError('Explicit native mode and source validity time required')
    character=snapshot['character'];companions=snapshot['companions'];owner=snapshot['owner']
    if character['uid']!=owner:raise ValueError('Auxiliary attribute owner differs')
    title=character['title'];title_source=character['title_source']
    if title_source['title']!=title:raise ValueError('Current title source differs')
    deadlines=[]
    if title:
        from els_server.domain.titles import eligible
        if not eligible(character,title):raise ValueError('Current title qualification differs')
        owned=next((v for v in title_source['owned']if v['title']==title),None)
        if owned is None:raise ValueError('Current title ownership missing')
        end=owned['expires_at']
        if end:
            if at>=end:raise ValueError('Current title source expired; capture again')
            deadlines.append(end)
    selected=companions['active_pet'];pet=None
    if selected:
        pet=next((v for v in companions['pets']if v['uid']==selected),None)
        if pet is None or pet['owner']!=owner or pet['kind']!='pet':raise ValueError('Current pet source ownership differs')
        from els_server.storage.boosting_2026_limited_pet import require_current
        require_current(pet,at=at)
        if pet.get('expires_at'):deadlines.append(pet['expires_at'])
    artifact=character['artifact']
    if artifact is None:
        if character['master']:raise ValueError('Current Master character lacks Artifact')
        artifact_ids=()
    else:
        from els_server.domain.artifact_progression import require_artifact
        artifact=require_artifact(character)
        artifact_ids=artifact_options(artifact['template'],artifact['evolution'],tuple(artifact['potentials']))
    title_value=title_inputs(title)
    # Original888CA0/896870 pass the same PvP byte through8889F0 argument4
    # and8A2900 argument5. 8A30B0 reloads it before the pet source branch.
    sources=(('title',title_value['options']),('pet',pet_options(pet,excluded=bool(mode))),
             ('artifact',artifact_ids),('collection',collection_options(character.get('el_search_collection'))))
    return dict(title_direct=title_value['direct'],option_sources=sources,
                valid_before=min(deadlines)if deadlines else None)
