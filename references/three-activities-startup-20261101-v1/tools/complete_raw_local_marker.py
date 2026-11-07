from delivery_common import *
pointer=read(R/'releases/local/current.json');assert pointer['release']=='local-three-activities-startup-ui-20261101-v1'
root=R/pointer['path'];assert sha(root/'local-business-manifest.json')==pointer['manifest_sha256'];assert not(root/'release-snapshot.json').exists()
save(W/'raw-local-support/selector-initial-failure.json',dict(ok=False,actual_launcher=60,error='Local release is incomplete',cause='New raw LOCAL installation omitted the standard generated release-snapshot.json marker',server_or_database_changes=False))
save(root/'release-snapshot.json',dict(release=pointer['release'],channel='local',local_business_manifest_sha256=pointer['manifest_sha256'],player_database_restore=False))
print('Completed the standard generated LOCAL marker; all frozen runtime bytes unchanged')
