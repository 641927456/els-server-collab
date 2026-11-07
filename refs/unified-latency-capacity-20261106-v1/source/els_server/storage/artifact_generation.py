"""New Artifact instances begin unidentified; Mirror effects draw once at identify."""
def initialize(db,owner,item):
 from els_server.domain.artifact_progression import catalog
 from els_server.domain.local_artifact_rules import generation,generated_spirit,spirit_group
 if str(item['template']) in generation()['generated']:
  from els_server.storage.equipment_options import replace as options
  item['option_groups']={str(spirit_group(item['template'])):[generated_spirit(item['template'])]}
  options(db,owner,item['uid'],{},item['option_groups']);return
 if item['template'] not in catalog()['equipment']:return
 from els_server.storage.equipment_identification import replace
 replace(db,owner,item['uid'],True,False);item['identified']=False
