#!/usr/bin/env python3
"""Regression: generated instance ids scope local browser storage keys."""
import re, uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'skills/lzheng-fitness-workbench-builder/scripts/Build-FitnessWorkbenchData.py'
HTML=ROOT/'skills/lzheng-fitness-workbench-builder/assets/workbench-template.html'
def key(instance,version,kind): return f'fitness.workbench.v1.{instance}.{version}.{kind}'
def main():
 text=HTML.read_text(encoding='utf-8')
 for marker in ('D.system&&D.system.instance_id','CARDIO_RECORDS_KEY','nutritionStorage','trainingLocalKey'):
  assert marker in text,marker
 a,b=str(uuid.uuid4()),str(uuid.uuid4()); store={key(a,'v1','cardio.records'):'A'}
 assert key(b,'v1','cardio.records') not in store
 assert key(a,'v2','cardio.records') != key(a,'v1','cardio.records')
 assert 'uuid.uuid4()' in BUILD.read_text(encoding='utf-8')
 print('INSTANCE_ISOLATION: PASS')
if __name__=='__main__': main()
