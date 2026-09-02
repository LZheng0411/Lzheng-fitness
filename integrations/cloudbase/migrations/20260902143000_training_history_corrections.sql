-- Additive history-correction support for completed training sessions.
-- The original plan snapshot is never modified. Every correction stores a
-- server-built before snapshot and remains owner-only through PostgreSQL RLS.

alter table public.training_sessions
  add column if not exists last_corrected_at timestamptz,
  add column if not exists correction_count integer not null default 0,
  add column if not exists review_sync_status text not null default 'current';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'training_sessions_review_sync_status_check'
  ) then
    alter table public.training_sessions
      add constraint training_sessions_review_sync_status_check
      check (review_sync_status in ('current', 'needs_review'));
  end if;
end $$;

create table if not exists public.training_session_revisions (
  id uuid primary key default gen_random_uuid(),
  owner_id text not null default auth.uid(),
  session_id uuid not null references public.training_sessions(id) on delete cascade,
  revision_number integer not null,
  correction_reason text,
  source text not null default 'manual_correction',
  full_snapshot jsonb not null,
  created_at timestamptz not null default now(),
  unique (session_id, revision_number),
  check (source in ('manual_correction', 'restore_checkpoint'))
);

create index if not exists training_session_revisions_owner_session_idx
  on public.training_session_revisions(owner_id, session_id, revision_number desc);

alter table public.training_session_revisions enable row level security;
alter table public.training_session_revisions force row level security;

drop policy if exists training_session_revisions_owner_all on public.training_session_revisions;
create policy training_session_revisions_owner_all
  on public.training_session_revisions
  for all
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

create or replace function public.training_session_snapshot(p_session_id uuid)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select jsonb_build_object(
    'schema', 'lzheng_training_session_snapshot_v1',
    'captured_at', now(),
    'session', to_jsonb(s),
    'exercises', coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'exercise', to_jsonb(e),
          'sets', coalesce((
            select jsonb_agg(to_jsonb(ts) order by ts.set_number)
            from public.training_sets ts
            where ts.exercise_id = e.id and ts.owner_id = auth.uid()
          ), '[]'::jsonb)
        ) order by e.sort_order
      )
      from public.training_exercises e
      where e.session_id = s.id and e.owner_id = auth.uid()
    ), '[]'::jsonb)
  )
  from public.training_sessions s
  where s.id = p_session_id and s.owner_id = auth.uid();
$$;

create or replace function public.correct_training_session_sets(
  p_session_id uuid,
  p_changes jsonb,
  p_reason text default '修正训练时的误填数据'
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_owner_id text := auth.uid();
  v_snapshot jsonb;
  v_revision integer;
  v_change jsonb;
  v_set_id uuid;
  v_updated integer := 0;
begin
  if v_owner_id is null then raise exception 'AUTH_REQUIRED'; end if;
  if jsonb_typeof(p_changes) <> 'array' or jsonb_array_length(p_changes) = 0 then
    raise exception 'NO_CHANGES';
  end if;

  perform 1 from public.training_sessions
  where id = p_session_id and owner_id = v_owner_id and status = 'completed'
  for update;
  if not found then raise exception 'COMPLETED_SESSION_NOT_FOUND'; end if;

  v_snapshot := public.training_session_snapshot(p_session_id);
  if v_snapshot is null then raise exception 'SNAPSHOT_FAILED'; end if;

  select coalesce(max(revision_number), 0) + 1 into v_revision
  from public.training_session_revisions
  where session_id = p_session_id and owner_id = v_owner_id;

  insert into public.training_session_revisions(
    owner_id, session_id, revision_number, correction_reason, source, full_snapshot
  ) values (
    v_owner_id, p_session_id, v_revision, nullif(trim(p_reason), ''),
    'manual_correction', v_snapshot
  );

  for v_change in select value from jsonb_array_elements(p_changes)
  loop
    begin
      v_set_id := (v_change->>'set_id')::uuid;
    exception when others then
      raise exception 'INVALID_SET_ID';
    end;

    if not exists (
      select 1
      from public.training_sets ts
      join public.training_exercises e on e.id = ts.exercise_id
      where ts.id = v_set_id
        and ts.owner_id = v_owner_id
        and e.owner_id = v_owner_id
        and e.session_id = p_session_id
    ) then
      raise exception 'SET_NOT_IN_SESSION';
    end if;

    if (v_change ? 'weight') and (v_change->>'weight') is not null
       and ((v_change->>'weight')::numeric < 0 or (v_change->>'weight')::numeric > 1000) then
      raise exception 'INVALID_WEIGHT';
    end if;
    if (v_change ? 'reps') and (v_change->>'reps') is not null
       and ((v_change->>'reps')::integer < 0 or (v_change->>'reps')::integer > 100) then
      raise exception 'INVALID_REPS';
    end if;
    if (v_change ? 'rpe') and (v_change->>'rpe') is not null
       and ((v_change->>'rpe')::numeric < 0 or (v_change->>'rpe')::numeric > 10) then
      raise exception 'INVALID_RPE';
    end if;

    update public.training_sets
    set weight = case when v_change ? 'weight' then nullif(v_change->>'weight', '')::numeric else weight end,
        reps = case when v_change ? 'reps' then nullif(v_change->>'reps', '')::integer else reps end,
        rpe = case when v_change ? 'rpe' then nullif(v_change->>'rpe', '')::numeric else rpe end,
        updated_at = now()
    where id = v_set_id and owner_id = v_owner_id;
    v_updated := v_updated + 1;
  end loop;

  update public.training_sessions
  set last_corrected_at = now(),
      correction_count = correction_count + 1,
      review_sync_status = 'needs_review',
      client_revision = client_revision + 1,
      updated_at = now()
  where id = p_session_id and owner_id = v_owner_id;

  return jsonb_build_object(
    'session_id', p_session_id,
    'revision_number', v_revision,
    'updated_sets', v_updated,
    'review_sync_status', 'needs_review'
  );
end;
$$;

create or replace function public.restore_training_session_revision(p_revision_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_owner_id text := auth.uid();
  v_revision public.training_session_revisions%rowtype;
  v_current jsonb;
  v_next integer;
  v_exercise jsonb;
  v_set jsonb;
  v_restored integer := 0;
begin
  if v_owner_id is null then raise exception 'AUTH_REQUIRED'; end if;
  select * into v_revision
  from public.training_session_revisions
  where id = p_revision_id and owner_id = v_owner_id;
  if not found then raise exception 'REVISION_NOT_FOUND'; end if;

  perform 1 from public.training_sessions
  where id = v_revision.session_id and owner_id = v_owner_id and status = 'completed'
  for update;
  if not found then raise exception 'COMPLETED_SESSION_NOT_FOUND'; end if;

  v_current := public.training_session_snapshot(v_revision.session_id);
  select coalesce(max(revision_number), 0) + 1 into v_next
  from public.training_session_revisions
  where session_id = v_revision.session_id and owner_id = v_owner_id;
  insert into public.training_session_revisions(
    owner_id, session_id, revision_number, correction_reason, source, full_snapshot
  ) values (
    v_owner_id, v_revision.session_id, v_next,
    '恢复旧版本前的自动快照', 'restore_checkpoint', v_current
  );

  for v_exercise in select value from jsonb_array_elements(v_revision.full_snapshot->'exercises')
  loop
    for v_set in select value from jsonb_array_elements(v_exercise->'sets')
    loop
      update public.training_sets
      set weight = nullif(v_set->>'weight', '')::numeric,
          reps = nullif(v_set->>'reps', '')::integer,
          rpe = nullif(v_set->>'rpe', '')::numeric,
          rir = nullif(v_set->>'rir', '')::numeric,
          is_completed = coalesce((v_set->>'is_completed')::boolean, false),
          note = v_set->>'note',
          updated_at = now()
      where id = (v_set->>'id')::uuid and owner_id = v_owner_id;
      if found then v_restored := v_restored + 1; end if;
    end loop;
  end loop;

  update public.training_sessions
  set last_corrected_at = now(),
      correction_count = correction_count + 1,
      review_sync_status = 'needs_review',
      client_revision = client_revision + 1,
      updated_at = now()
  where id = v_revision.session_id and owner_id = v_owner_id;

  return jsonb_build_object(
    'session_id', v_revision.session_id,
    'restored_revision', v_revision.revision_number,
    'checkpoint_revision', v_next,
    'restored_sets', v_restored,
    'review_sync_status', 'needs_review'
  );
end;
$$;

grant select, insert on public.training_session_revisions to authenticated;
grant execute on function public.training_session_snapshot(uuid) to authenticated;
grant execute on function public.correct_training_session_sets(uuid, jsonb, text) to authenticated;
grant execute on function public.restore_training_session_revision(uuid) to authenticated;
