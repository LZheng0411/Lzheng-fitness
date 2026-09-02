-- Local nutrition archive and lightweight subjective check-ins.
-- This migration is additive and preserves existing nutrition records.

create table if not exists public.nutrition_subjective_checkins (
  id uuid primary key default gen_random_uuid(),
  owner_id text not null default auth.uid(),
  recorded_on date not null default current_date,
  meal_id uuid references public.nutrition_meals(id) on delete set null,
  checkin_scope text not null default 'day' check (checkin_scope in ('meal', 'training', 'day')),
  hunger_level integer check (hunger_level between 0 and 5),
  fullness_level integer check (fullness_level between 0 and 5),
  energy_level integer check (energy_level between 0 and 5),
  digestion_level integer check (digestion_level between 0 and 5),
  training_performance_level integer check (training_performance_level between 0 and 5),
  note text check (note is null or char_length(btrim(note)) between 1 and 1000),
  captured_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    hunger_level is not null or fullness_level is not null or energy_level is not null
    or digestion_level is not null or training_performance_level is not null or note is not null
  ),
  check (checkin_scope <> 'meal' or meal_id is not null),
  check (checkin_scope = 'meal' or meal_id is null)
);

create index if not exists nutrition_subjective_checkins_owner_date_idx
  on public.nutrition_subjective_checkins (owner_id, recorded_on desc, captured_at desc);

alter table public.nutrition_subjective_checkins enable row level security;
alter table public.nutrition_subjective_checkins force row level security;
grant select, insert, update, delete on table public.nutrition_subjective_checkins to authenticated;

drop policy if exists nutrition_subjective_checkins_select_own on public.nutrition_subjective_checkins;
drop policy if exists nutrition_subjective_checkins_insert_own on public.nutrition_subjective_checkins;
drop policy if exists nutrition_subjective_checkins_update_own on public.nutrition_subjective_checkins;
drop policy if exists nutrition_subjective_checkins_delete_own on public.nutrition_subjective_checkins;

create policy nutrition_subjective_checkins_select_own on public.nutrition_subjective_checkins
  for select to authenticated using (owner_id = auth.uid());
create policy nutrition_subjective_checkins_insert_own on public.nutrition_subjective_checkins
  for insert to authenticated with check (
    owner_id = auth.uid()
    and (
      meal_id is null
      or exists (
        select 1 from public.nutrition_meals meal
        where meal.id = nutrition_subjective_checkins.meal_id
          and meal.owner_id = auth.uid()
      )
    )
  );
create policy nutrition_subjective_checkins_update_own on public.nutrition_subjective_checkins
  for update to authenticated using (owner_id = auth.uid()) with check (
    owner_id = auth.uid()
    and (
      meal_id is null
      or exists (
        select 1 from public.nutrition_meals meal
        where meal.id = nutrition_subjective_checkins.meal_id
          and meal.owner_id = auth.uid()
      )
    )
  );
create policy nutrition_subjective_checkins_delete_own on public.nutrition_subjective_checkins
  for delete to authenticated using (owner_id = auth.uid());

-- A foreign key alone does not prove that the selected meal belongs to the
-- current user. Keep cross-account meal references impossible even if an ID
-- is guessed or supplied by a stale client.
create or replace function public.assert_nutrition_subjective_checkin_meal_owner()
returns trigger
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  if new.meal_id is not null and not exists (
    select 1 from public.nutrition_meals
    where id = new.meal_id and owner_id = auth.uid()
  ) then
    raise exception 'nutrition_checkin_meal_not_owned';
  end if;
  return new;
end;
$$;

drop trigger if exists nutrition_subjective_checkins_meal_owner on public.nutrition_subjective_checkins;
create trigger nutrition_subjective_checkins_meal_owner
before insert or update of meal_id on public.nutrition_subjective_checkins
for each row execute function public.assert_nutrition_subjective_checkin_meal_owner();

drop trigger if exists nutrition_subjective_checkins_updated_at on public.nutrition_subjective_checkins;
create trigger nutrition_subjective_checkins_updated_at
before update on public.nutrition_subjective_checkins
for each row execute function public.set_updated_at();

alter table public.nutrition_agent_jobs
  drop constraint if exists nutrition_agent_jobs_job_type_check;
alter table public.nutrition_agent_jobs
  add constraint nutrition_agent_jobs_job_type_check
    check (job_type in ('meal_analysis', 'meal_consumption_analysis', 'weekly_review', 'local_archive'));

create unique index if not exists nutrition_agent_jobs_active_local_archive_idx
  on public.nutrition_agent_jobs (owner_id, job_type)
  where job_type = 'local_archive' and status in ('queued', 'processing');

-- The browser can create one owner-only archive request. The local Windows
-- Agent later consumes it; there is no trigger, schedule, or polling here.
create or replace function public.queue_nutrition_local_archive(
  p_job_id uuid,
  p_requested_for date default current_date
)
returns uuid
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_owner_id text := auth.uid();
begin
  if v_owner_id is null or v_owner_id = '' then
    raise exception 'authentication_required';
  end if;
  if exists (
    select 1 from public.nutrition_agent_jobs
    where owner_id = v_owner_id
      and job_type = 'local_archive'
      and status in ('queued', 'processing')
  ) then
    raise exception 'nutrition_local_archive_already_active';
  end if;
  insert into public.nutrition_agent_jobs (
    id, owner_id, job_type, requested_for, status, input_snapshot
  ) values (
    p_job_id, v_owner_id, 'local_archive', coalesce(p_requested_for, current_date), 'queued',
    jsonb_build_object('archive_schema', 1, 'requested_from', 'fitness_workbench', 'mode', 'incremental')
  );
  return p_job_id;
end;
$$;

grant execute on function public.queue_nutrition_local_archive(uuid, date) to authenticated;
