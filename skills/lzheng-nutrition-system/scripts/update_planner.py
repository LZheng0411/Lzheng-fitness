"""Apply an accepted menu to the planner block without changing training facts."""
import argparse,datetime,json,os,re,hashlib
from pathlib import Path
DATA=re.compile(r'(<script id="workbench-data" type="application/json">)([\s\S]*?)(</script>)')

def validate(value):
 if not isinstance(value,dict) or value.get('schema')!=1:raise ValueError('Expected planner schema 1')
 plan=value.get('current_plan')
 if not plan:return
 if not isinstance(plan.get('version'),str) or not plan['version']:raise ValueError('Missing menu version')
 if not plan.get('target_version') or plan.get('target',{}).get('version')!=plan['target_version']:raise ValueError('Menu and target versions do not match')
 if not plan.get('target',{}).get('method'):raise ValueError('Target method must be explicit')
 if not isinstance(plan.get('meals'),list) or not plan['meals']:raise ValueError('Meals required')
 for meal in plan['meals']:
  if not meal.get('name') or not isinstance(meal.get('foods'),list):raise ValueError('Invalid meal')
  for food in meal['foods']:
   if not food.get('name') or not food.get('portion'):raise ValueError('Food and portion required')
   for v in food.get('macros',{}).values():
    import math
    if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0):raise ValueError('Invalid macro')

def main():
 p=argparse.ArgumentParser();p.add_argument('--html',required=True);p.add_argument('--data',required=True);p.add_argument('--backup-dir',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 target=Path(a.html).absolute();backup=Path(a.backup_dir).absolute()
 for path in [target,backup]:
  for part in [path,*path.parents]:
   if part.exists() and (part.is_symlink() or getattr(part,'is_junction',lambda:False)()):raise ValueError('Use real paths')
 if backup==target.parent or target.parent in backup.parents or backup in target.parents:raise ValueError('Use a separate backup directory')
 value=json.loads(Path(a.data).read_text(encoding='utf-8-sig'));validate(value)
 original=target.read_bytes();html=original.decode('utf-8-sig');matches=list(DATA.finditer(html))
 if len(matches)!=1:raise ValueError('Expected one data block')
 data=json.loads(matches[0][2]);data['nutrition_planner']=value
 updated=DATA.sub(lambda m:m[1]+json.dumps(data,ensure_ascii=False).replace('<','\\u003c')+m[3],html)
 if a.apply:
  backup.mkdir(parents=True,exist_ok=True);stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');(backup/(stamp+'-planner-before.html')).write_bytes(original)
  if target.read_bytes()!=original:raise ValueError('Concurrent edit')
  tmp=target.with_name('.planner-'+stamp+'.tmp');tmp.write_text(updated,encoding='utf-8');os.replace(tmp,target)
 print(json.dumps({'applied':a.apply,'plan_version':(value.get('current_plan') or {}).get('version'),'training_facts_changed':False,'intake_confirmed':False,'deployed':False}))
if __name__=='__main__':main()
