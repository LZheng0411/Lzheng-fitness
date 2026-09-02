#!/usr/bin/env python3
"""Static public CloudBase contract gate with deliberate negative fixtures."""
import re, shutil, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MIGRATIONS=ROOT/'integrations/cloudbase/migrations'
REQUIRED={'training_sessions':['week_number','current_exercise_index','completed_at','correction_count','review_sync_status'],'training_exercises':['exercise_key','planned_name','actual_weight_text','problem_note'],'training_sets':['weight','reps','rpe','is_completed'],'training_session_revisions':['full_snapshot','revision_number'],'cardio_sessions':['performed_time','pool_length_m','avg_heart_rate','problem_note'],'nutrition_meals':['consumed_estimate','confirmed_nutrition','consumption_status'],'nutrition_meal_photos':['meal_id','object_key'],'nutrition_profiles':['current_target'],'nutrition_daily_targets':['target_date','calories'],'nutrition_body_metrics':['measured_on'],'nutrition_weekly_reviews':['decision_status'],'nutrition_subjective_checkins':['checkin_scope','hunger_level','digestion_level'],'nutrition_agent_jobs':['job_type','reference_id']}
RPCs=(
    'queue_nutrition_meal_consumption',
    'queue_nutrition_local_archive',
    'correct_training_session_sets',
    'restore_training_session_revision',
)
def check(text):
    for table,cols in REQUIRED.items():
        if not re.search(r'(?:create|alter) table public\.'+re.escape(table)+r'\b',text): raise AssertionError('missing table '+table)
        for col in cols:
            if not re.search(r'\b'+re.escape(col)+r'\b',text): raise AssertionError('missing column '+table+'.'+col)
    for rpc in RPCs:
        if 'function public.'+rpc not in text: raise AssertionError('missing RPC '+rpc)
    if 'enable row level security' not in text or 'owner_only' not in text: raise AssertionError('missing owner RLS')
def main():
    files=sorted(MIGRATIONS.glob('*.sql'))
    if len(files)<3: raise AssertionError('expected ordered additive migrations')
    text='\n'.join(path.read_text(encoding='utf-8') for path in files);check(text)
    for token in ('current_exercise_index','function public.queue_nutrition_local_archive','function public.correct_training_session_sets'):
        broken=text.replace(token,'removed_contract_token')
        try: check(broken)
        except AssertionError: continue
        raise AssertionError('negative fixture passed: '+token)
    print('CLOUDBASE_MIGRATION_CONTRACT: PASS')
if __name__=='__main__': main()
