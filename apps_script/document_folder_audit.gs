// Editor-run, read-only inventory. Add to each EXISTING Docs/mail project and
// run auditDocumentFolders. Requires its existing Advanced Drive v3 service.
// Reads only allowlisted settings and folder metadata. No credential values,
// document contents, file moves, property writes or trigger changes.
function auditDocumentFolders() {
  const props=PropertiesService.getScriptProperties();
  const keys=['ROOT_FOLDER_ID','DOCUMENTS_ROOT_FOLDER_ID','GMAIL_DOCUMENTS_FOLDER_ID',
    'DOCUMENTS_INTAKE_FOLDER_ID','DOCUMENTS_FILED_FOLDER_ID'];
  const report={folders:[],checks:[],scope:'Current Apps Script project only; sharing membership and pending imports are not audited.'};
  keys.forEach(function(key) {
    const id=String(props.getProperty(key) || '').trim();
    const entry={setting:key,id:id || null,status:'not_configured'};
    if(id) {
      if(!/^[A-Za-z0-9_-]{10,200}$/.test(id))entry.status='invalid_folder_id';
      else try {
        const m=Drive.Files.get(id,{supportsAllDrives:true,
          fields:'id,name,mimeType,trashed,driveId,parents,capabilities(canAddChildren)'});
        entry.status=m.trashed?'trashed':m.mimeType==='application/vnd.google-apps.folder'?'verified_folder':'not_a_folder';
        entry.name=m.name;entry.shared_drive_id=m.driveId || null;
        entry.location=m.driveId?'Shared Drive':'My Drive';
        entry.can_add_children=!!(m.capabilities || {}).canAddChildren;
        entry.parent_ids=m.parents || [];
      } catch(ignore) {entry.status='unavailable_check_access_and_drive_service';}
    }
    report.folders.push(entry);
  });
  const byKey={};report.folders.forEach(function(f){byKey[f.setting]=f;});
  const gmail=byKey.GMAIL_DOCUMENTS_FOLDER_ID,inbox=byKey.DOCUMENTS_INTAKE_FOLDER_ID,filed=byKey.DOCUMENTS_FILED_FOLDER_ID;
  if(gmail.status==='verified_folder')report.checks.push(gmail.shared_drive_id?
    'Existing Gmail destination is in a Shared Drive: candidate for To Review; check its sharing and import receipts before changing settings.':
    'Existing Gmail destination is in My Drive: candidate for To Review with the updated relay; check office ownership and sharing.');
  if(gmail.id && inbox.id)report.checks.push(gmail.id===inbox.id?'Gmail destination and To Review match.':'Gmail destination and To Review differ; reconcile before switching.');
  if(inbox.status==='verified_folder' && filed.status==='verified_folder')report.checks.push(
    inbox.id!==filed.id && inbox.shared_drive_id===filed.shared_drive_id?
    'To Review and Filed are distinct folders in a compatible Drive location; verify office ownership and sharing.':
    'To Review and Filed must be distinct and both in My Drive or in the same Shared Drive.');
  report.checks.push('Keep travel output and private document-processing folders in their existing roles.');
  console.log(JSON.stringify(report,null,2));
  return report;
}

// Editor-run diagnostic when the audit reports an unavailable folder.
// Intentionally lets Apps Script display the Drive error and authorization prompt.
function diagnoseDocumentFolderAccess() {
  const id=PropertiesService.getScriptProperties().getProperty('DOCUMENTS_ROOT_FOLDER_ID');
  if(!id)throw new Error('DOCUMENTS_ROOT_FOLDER_ID is not configured in this project.');
  const folder=Drive.Files.get(id,{supportsAllDrives:true,fields:'id,name,mimeType'});
  console.log(JSON.stringify(folder));
}

// Run in the Docs/travel project after saving the intake and filed properties.
// Uses the minimal metadata request already verified by the office account.
function verifyDocumentIntakeFolders() {
  const props=PropertiesService.getScriptProperties();
  const keys=['DOCUMENTS_INTAKE_FOLDER_ID','DOCUMENTS_FILED_FOLDER_ID'];
  const ids=keys.map(function(key) {
    const id=String(props.getProperty(key) || '').trim();
    if(!id)throw new Error('Missing property: ' + key);
    return id;
  });
  if(ids[0]===ids[1])throw new Error('Intake and Filed must be different folders.');
  keys.forEach(function(key,index) {
    const folder=Drive.Files.get(ids[index],{supportsAllDrives:true,fields:'id,name,mimeType'});
    if(folder.mimeType!=='application/vnd.google-apps.folder')throw new Error(key + ' does not identify a folder.');
    console.log(key + ': ' + JSON.stringify(folder));
  });
  console.log('Both folders are readable. This check does not verify upload or move permissions.');
}
