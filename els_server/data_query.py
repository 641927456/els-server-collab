"""Read-only data inspection: python -m els_server.data_query --help."""
import argparse
import json
from els_server.game_data import client_data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=('summary','item','skill','level','character','dungeon','resource','npc','result-code','equipment-requirements','repair-quote','enchant-summary','enchant-effect','enchant-scroll','enchant-material','enchant-cost','enchant-quote','profession-summary','profession-settings','profession','crafting-summary','recipe','crafting-requirements'))
    parser.add_argument('identity',nargs='?')
    parser.add_argument('--level',type=int,default=1)
    parser.add_argument('--quantity',type=int,default=1,help='Batch size for read-only crafting requirements')
    parser.add_argument('--durability',type=int,help='Explicit current endurance for read-only repair quotation')
    parser.add_argument('--unit-class',type=int,help='Native class ID for equipment requirement inspection')
    parser.add_argument('--transcendence',action='store_true')
    parser.add_argument('--npc',action='store_true',help='Exact NPC variant of an enchant effect')
    parser.add_argument('--source-index',type=int,help='Material equipment-level index (1..100); enchant-material identity is the cost tier')
    parser.add_argument('--target-element',type=int,choices=range(1,8),help='Native attribute type 1..6, or random 7')
    parser.add_argument('--grade',choices=('LOW','NORMAL','RARE','ELITE','UNIQUE','LEGEND'))
    parser.add_argument('--enchant-slots',type=int,nargs=4,default=[0,0,0,0],help='Four existing native element slot IDs for a read-only cost quote')
    args=parser.parse_args();data=client_data()
    if args.kind=='summary':result={k:data.manifest[k] for k in ('client_sha256','catalog_sha256','counts','limits')}
    elif args.kind=='enchant-summary':
        from els_server.enchant_data import enchant_data
        result=enchant_data().manifest
    elif args.kind=='crafting-summary':
        from els_server.manufacture_data import manufacture_data
        result=manufacture_data().manifest
    elif args.kind in ('profession-summary','profession-settings'):
        from els_server.profession_data import profession_data
        catalog=profession_data()
        result=catalog.manifest if args.kind=='profession-summary' else catalog.settings()
    elif args.kind=='resource':result=data.resource(args.identity)
    else:
        if args.identity is None:parser.error('identity is required')
        identity=int(args.identity)
        if args.kind=='result-code':
            from els_server.result_messages import result_messages
            result=dict(code=identity,text=result_messages().text(identity),scope='Native message lookup; not a success/failure classification')
        elif args.kind=='equipment-requirements':
            from els_server.domain.equipment_requirements import inspect_requirements
            from els_server.domain.equipment_eligibility import inspect_eligibility
            if args.unit_class is None:parser.error('equipment-requirements requires --unit-class')
            result=inspect_requirements(identity,args.unit_class)
            result['eligibility']=inspect_eligibility(identity,args.unit_class,args.level)
        elif args.kind=='repair-quote':
            from els_server.domain.equipment_repair import template_quote
            if args.durability is None:parser.error('repair-quote requires --durability')
            result=template_quote(identity,args.durability)
        elif args.kind=='profession':
            from els_server.profession_data import profession_data
            result=profession_data().template(identity)
        elif args.kind=='recipe':
            from els_server.manufacture_data import manufacture_data
            result=manufacture_data().recipe(identity)
        elif args.kind=='crafting-requirements':
            from els_server.domain.manufacture_requirements import requirements
            result=requirements(identity,args.quantity)
        elif args.kind=='item':
            result=data.item(identity);result['record_hex']=result.pop('record').hex()
        elif args.kind.startswith('enchant-'):
            from els_server.enchant_data import enchant_data
            catalog=enchant_data()
            if args.kind=='enchant-quote':
                from els_server.domain.enchant_rules import attribute_quote
                if args.target_element is None:parser.error('enchant-quote requires --target-element')
                result=attribute_quote(identity,args.enchant_slots,args.target_element)
            elif args.kind=='enchant-cost':
                from els_server.domain.enchant_rules import normal_item_quote
                result=normal_item_quote(identity,args.enchant_slots)
            elif args.kind=='enchant-effect':result=catalog.effect(identity,npc=args.npc)
            elif args.kind=='enchant-scroll':result=catalog.scroll(identity)
            else:
                if args.source_index is None or args.grade is None:parser.error('enchant-material requires --source-index and --grade')
                result=dict(enchant_type=identity,source_index=args.source_index,grade=args.grade,
                            material_quantity=catalog.material_quantity(identity,args.source_index,args.grade),transaction_implemented=False)
        elif args.kind=='skill':result=data.skill(identity)
        elif args.kind=='npc':result=data.npc(identity)
        elif args.kind=='level':result=data.level_progress(identity)
        elif args.kind=='dungeon':
            from els_server.domain.reward_rules import drop_reference
            result=dict(definition=data.dungeon(identity),drops=drop_reference(identity))
        else:
            from els_server.domain.skill_rules import learned_skills,equippable_skills
            from els_server.domain.character_stats import combat_breakdown
            character=dict(unit_class=identity,level=args.level,transcendence=args.transcendence)
            result=dict(definition=data.unit(identity),learned=learned_skills(character),equippable=equippable_skills(character),
                        attributes=combat_breakdown(character))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
