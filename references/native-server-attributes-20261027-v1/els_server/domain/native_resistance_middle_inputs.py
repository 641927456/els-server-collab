"""8623B0's distinct title, pet and Artifact resistance sources in order.

Title options use882230/882380. The pet socket/aura and Artifact group/potential
branches call865660 directly, after their own presence/phase gates. Neither
collection/world options nor the ordinary collector's combined vector belong
here. Live pet presence is an independent lifecycle input, not a SQL default.
"""
from dataclasses import dataclass
from els_server.domain import native_resistance_option as options
from els_server.domain.native_rank_coefficient import coefficient
from els_server.domain.native_pve_rank_coefficient import factor


@dataclass(frozen=True)
class MiddleSources:
    title_options:tuple
    pet_options:tuple
    artifact_options:tuple


def _validate(sources,mode):
    if type(sources)is not MiddleSources or type(mode)is not int or mode not in(0,1):
        raise ValueError('Complete typed resistance middle sources and mode required')
    for group in(sources.title_options,sources.pet_options,sources.artifact_options):
        if (type(group)is not tuple or len(group)>16384
                or any(type(identity)is not int or not 0<=identity<2**31 for identity in group)):
            raise ValueError('Canonical ordered resistance source option IDs required')


def from_auxiliary(auxiliary, *, mode, pet_runtime_ready):
    if type(pet_runtime_ready)is not bool:
        raise ValueError('Explicit current owned pet runtime readiness required')
    source=auxiliary['option_sources']
    if (type(source)is not tuple or len(source)!=4
            or any(type(row)is not tuple or len(row)!=2 for row in source)
            or tuple(row[0]for row in source)!=('title','pet','artifact','collection')):
        raise ValueError('Complete same-snapshot auxiliary sources required')
    result=MiddleSources(*(row[1]for row in source[:3]));_validate(result,mode)
    if mode==0 and result.pet_options and not pet_runtime_ready:
        raise ValueError('Nonempty pet resistance source awaits owned runtime presence')
    return result


def merge(current,definitions,sources, *, mode,rank,pve_context):
    _validate(sources,mode)
    callbacks=[];rank_factor=coefficient(rank)
    for filtered,group in((True,sources.title_options),
            (False,sources.pet_options if mode==0 else()),(False,sources.artifact_options)):
        for identity in group:
            definition=definitions.get(identity)
            if definition is None or filtered and not options.eligible(definition,mode=mode):continue
            current=options.merge(current,definition,rank_factor=rank_factor,
                pve_rank_factor=factor(definition,**pve_context),weight=1.)
            callbacks.append((identity,1.))
    return dict(values=current,callbacks=tuple(callbacks))
