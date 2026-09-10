"""Update only an installed workbench knowledge projection; no network actions."""
import argparse,datetime,hashlib,json,os,re
from pathlib import Path

PATTERN=re.compile(r'(<script id="knowledge-library-data" type="application/json">)(.*?)(</script>)',re.S)
def digest(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--html',required=True);p.add_argument('--data',required=True);p.add_argument('--backup-dir',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 target=Path(a.html).absolute();datafile=Path(a.data).absolute();backup=Path(a.backup_dir).absolute()
 for path in [target,datafile,backup]:
  for part in [path,*path.parents]:
   if part.exists() and (part.is_symlink() or getattr(part,'is_junction',lambda:False)()):raise ValueError('Reparse path refused')
 if backup==target.parent or target.parent in backup.parents:raise ValueError('Backup must be outside project root')
 records=json.loads(datafile.read_text(encoding='utf-8-sig'));seen=set()
 if not isinstance(records,list):raise ValueError('Knowledge must be an array')
 for row in records:
  if not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k].strip() for k in ['id','title','summary','body','author','topic','date']):raise ValueError('Incomplete knowledge item')
  if row['id'] in seen:raise ValueError('Duplicate id')
  seen.add(row['id'])
  for source in row.get('sources',[]):
   from urllib.parse import urlparse
   parsed=urlparse(source.get('url',''))
   if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Source must be a public HTTPS URL')
  if len(row['body'])>150000:raise ValueError('Entry too large')
 before=target.read_bytes();html=before.decode('utf-8-sig');matches=list(PATTERN.finditer(html))
 if len(matches)!=1:raise ValueError('Exactly one installed knowledge data block required')
 match=matches[0];payload=json.dumps(records,ensure_ascii=False).replace('<','\\u003c')
 updated=html[:match.start(2)]+payload+html[match.end(2):]
 assert PATTERN.sub('',html)==PATTERN.sub('',updated)
 receipt={'items':len(records),'applied':a.apply,'before_sha256':digest(before),'data_sha256':digest(payload.encode()),'outside_knowledge_unchanged':True,'deployed':False}
 if a.apply:
  backup.mkdir(parents=True,exist_ok=True);stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
  (backup/(stamp+'-before.html')).write_bytes(before)
  if target.read_bytes()!=before:raise ValueError('Concurrent edit detected')
  temporary=target.with_name('.knowledge-write-'+stamp+'.tmp')
  try:
   temporary.write_bytes(updated.encode('utf-8'));os.replace(temporary,target)
  finally:
   if temporary.exists():temporary.unlink()
  assert json.loads(PATTERN.search(target.read_text(encoding='utf-8')).group(2))==records
  receipt['after_sha256']=digest(target.read_bytes())
  (backup/(stamp+'-receipt.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 print(json.dumps(receipt))
if __name__=='__main__':main()
