#!/usr/bin/env python3
"""Intake and load calibration remain independent; non-personal fixtures."""
import copy
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('builder',Path(__file__).with_name('Build-FitnessWorkbenchData.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
plan={'plan':{'title':'Training Plan','athlete':'Test Athlete','goal':'general_fitness','frequency':3},'cycles':[],
      'schedule':[{'day':'10-05','theme':'Session A','day_key':'Session A','exercises':[
          {'name':'Cable raise','priority':'key','sets':'3×12；重量现场校准','load_status':'calibration_required'}]}]}
baseline={'source_version':'v01'}
state=b.build_onboarding(plan,baseline,[])
assert state['completed'] and state['mode']=='needs_calibration'
assert state['calibration_required'] and state['missing']==[]
for field in ('athlete','goal','frequency'):
    missing=copy.deepcopy(plan);missing['plan'].pop(field)
    state=b.build_onboarding(missing,baseline,[])
    assert state['completed'] and state['missing'] and '待填写' in state['message'],field
assert b.build_onboarding(plan,{},[])['completed']
demo=copy.deepcopy(plan);demo['plan']['title']='匿名示例';demo['plan']['record_nature']='example'
assert not b.build_onboarding(demo,baseline,[])['completed']
alias=copy.deepcopy(plan);alias['plan']['title']='匿名使用者的个人计划，原页待建档'
assert b.build_onboarding(alias,baseline,[])['completed']
assert b.build_onboarding(alias,baseline,[])['profile']['athlete']=='Test Athlete'
empty=copy.deepcopy(plan);empty['schedule']=[]
assert '训练计划待填写' in b.build_onboarding(empty,baseline,[])['message']
ready=copy.deepcopy(plan);ready['schedule'][0]['exercises'][0]['load_status']='verified'
state=b.build_onboarding(ready,baseline,[])
assert state['completed'] and state['mode']=='ready' and not state['calibration_required']
days,_=b.build_days(plan,1,'2026-10-05')
exercise=days['Session A']['exercises'][0]
assert exercise['w'] is None and exercise['load_status']=='calibration_required'
assert exercise['d']=='3×12；重量现场校准'
print('FITNESS_WORKBENCH_ONBOARDING: PASS')
