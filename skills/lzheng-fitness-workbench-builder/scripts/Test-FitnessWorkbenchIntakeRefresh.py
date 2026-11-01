"""A newly supplied real plan must replace the initial onboarding projection immediately."""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
def run(*args):
    r=subprocess.run([sys.executable,'-B',*map(str,args)],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1'})
    if r.returncode:raise AssertionError(r.stdout+r.stderr)
    return r.stdout
def data(html):
    return json.loads(re.search(r'<script id="workbench-data" type="application/json">(.*?)</script>',html,re.S)[1])

with tempfile.TemporaryDirectory(prefix='fitness-intake-refresh-') as raw:
    root=Path(raw);project=root/'project';backups=root/'backups'
    run(HERE/'Initialize-FitnessWorkbench.py','--target',project,'--brand','TEST')
    formal=project/'健身工作台.html';before=formal.read_text(encoding='utf-8')
    assert data(before)['onboarding']['completed'] is False
    path=next((project/'训练与周期/当前周期').glob('*-v01.json'))
    plan=json.loads(path.read_text(encoding='utf-8'))
    plan['plan'].update(record_nature='user_plan',title='匿名使用者的已提供计划',athlete='测试使用者',goal='general_fitness',frequency=4)
    for day in plan['schedule']:
        for exercise in day.get('exercises',[]):
            exercise['sets']=exercise['sets'].replace('示例 ','')
    unknown=plan['schedule'][0]['exercises'][0]
    unknown.update(sets='3×5；重量现场校准',load_status='calibration_required')
    path.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
    receipt=root/'receipt.json'
    run(HERE/'Refresh-FitnessWorkbench.py','--project',project,'--backup-dir',backups,'--receipt',receipt)
    after=formal.read_text(encoding='utf-8');d=data(after)
    assert d['onboarding']['completed'] and d['onboarding']['mode']=='needs_calibration'
    assert d['onboarding']['profile']['athlete']=='测试使用者'
    assert d['meta']['title']=='匿名使用者的已提供计划'
    assert any(e.get('w') for day in d['days'].values() for e in day['exercises']), 'known loads were masked'
    assert any(e.get('load_status')=='calibration_required' and e['w'] is None for day in d['days'].values() for e in day['exercises'])
    strip=lambda s:re.sub(r'(<script id="workbench-data" type="application/json">).*?(</script>)',r'\1{}\2',s,flags=re.S)
    assert strip(before)==strip(after), 'intake refresh replaced the interface'
    assert json.loads(receipt.read_text(encoding='utf-8'))['claims']['formal_refreshed']
print('FITNESS_WORKBENCH_INTAKE_REFRESH: PASS')
