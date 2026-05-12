create table if not exists grounding_checks (
  grounding_check_id text primary key,
  trace_id text,
  status text not null,
  confidence numeric not null default 0,
  source_surface text not null,
  world_version_id text,
  session_id text,
  chapter_id text,
  evidence_refs_json jsonb not null,
  unsupported_claims_json jsonb not null,
  reason_codes_json jsonb not null,
  summary text not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_grounding_checks_trace_created_at on grounding_checks(trace_id, created_at);
create index if not exists idx_grounding_checks_status_created_at on grounding_checks(status, created_at);
create index if not exists idx_grounding_checks_world_created_at on grounding_checks(world_version_id, created_at);
create index if not exists idx_grounding_checks_session_created_at on grounding_checks(session_id, created_at);
