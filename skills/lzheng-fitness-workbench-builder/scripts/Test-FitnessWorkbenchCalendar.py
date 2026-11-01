#!/usr/bin/env python3
"""Calendar boundaries and independently carried prescriptions; anonymous fixtures."""
import copy
import datetime as dt
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('builder', Path(__file__).with_name('Build-FitnessWorkbenchData.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
plan = {'plan': {'week_policy': 'monday_sunday', 'calendar_anchor': '2026-07-27', 'frequency': 4}, 'schedule': [], 'cycles': []}
for i in range(7):
    plan['schedule'].append({'day': (dt.date(2026, 9, 7) + dt.timedelta(days=i)).isoformat(), 'theme': '未排期'})
plan['schedule'][1].update(day_key='腿A', label='W7', prescription_week=7, exercises=[{'name':'杠铃深蹲', 'sets':'50kg 2×3', 'target':'示例，非处方'}])
plan['schedule'].append({'day':'日期待定', 'day_key':'上肢A', 'label':'W7 沿用W6', 'prescription_week':6, 'carryover':True, 'schedule_status':'awaiting_date', 'exercises':[{'name':'杠铃卧推', 'sets':'30kg 3×5', 'target':'原示例处方'}]})
today = dt.date(2026,9,8)
days, timeline = b.build_days(plan,7,'2026-07-27')
data = {'calendar_week':b.calendar_window(plan,today), 'meta':{'current_week':7},'days':days,'timeline':timeline}
assert not b.validate_calendar_schedule(data,plan,today)
assert b.current_week_from_schedule(plan,'2026-07-27',dt.date(2026,9,6)) == 6
assert b.current_week_from_schedule(plan,'2026-07-27',dt.date(2026,9,7)) == 7
assert b.current_week_from_schedule(plan,'2026-07-27',dt.date(2026,9,14)) == 8
assert days['上肢A']['date'] is None and days['上肢A']['prescription_week'] == 6
bad=copy.deepcopy(data);bad['days']['上肢A']['exercises'][0]['d']='35kg 3×5'
assert b.validate_calendar_schedule(bad,plan,today), 'carried load must not advance from calendar week'
bad_plan=copy.deepcopy(plan);bad_plan['schedule'][0]['day']='2026-09-01'
assert b.validate_calendar_schedule(data,bad_plan,today), 'reject four sessions spanning two weeks'
assert b.parse_schedule_date('2027-01-04','2026-07-27') == '2027-01-04'
assert b.calendar_window(plan,dt.date(2027,1,3))['end'] == '2027-01-03'
print('FITNESS_WORKBENCH_CALENDAR: PASS')

# A valid historical week is preserved, while the current week remains unplanned.
later = dt.date(2026,9,21)
original = copy.deepcopy(plan)
projected = b.project_calendar_timeline(plan, timeline, later)
late_data = {'calendar_week':b.calendar_window(plan,later), 'meta':{'current_week':9},
             'days':days, 'timeline':projected}
assert not b.validate_calendar_schedule(late_data,plan,later)
assert plan == original and days['腿A']['date'] == '2026-09-08'
assert len(projected) == 7 and all(x['type'] == 'unplanned' for x in projected)
assert days['上肢A']['prescription_week'] == 6
for change in ('duplicate', 'cross_week', 'missing'):
    invalid=copy.deepcopy(plan)
    if change == 'duplicate': invalid['schedule'][0]['day']='2026-09-08'
    elif change == 'cross_week': invalid['schedule'][0]['day']='2026-09-01'
    else: invalid['schedule'].pop(0)
    assert b.validate_calendar_schedule(late_data,invalid,later), change
bad=copy.deepcopy(late_data);bad['timeline'][0]['type']='recovery'
assert b.validate_calendar_schedule(bad,plan,later), 'unplanned must not become rest'
bad=copy.deepcopy(late_data);bad['days']['腿A']['date']='2026-09-22'
assert b.validate_calendar_schedule(bad,plan,later), 'no automatic reschedule'
assert b.project_calendar_timeline(plan,timeline,today) == timeline
print('FITNESS_WORKBENCH_EXPIRED_CALENDAR: PASS')
