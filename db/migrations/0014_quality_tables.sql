create table if not exists quality_policies (
  policy_id text primary key,
  version text not null,
  scenario_id text not null,
  risk_tier text not null,
  mode text not null,
  rule_ids_json jsonb not null,
  policy_payload_json jsonb not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_quality_policies_scenario_risk_updated_at on quality_policies(scenario_id, risk_tier, updated_at);
create index if not exists idx_quality_policies_mode_updated_at on quality_policies(mode, updated_at);

create table if not exists quality_events (
  event_id text primary key,
  trace_id text not null,
  event_type text not null,
  source_surface text not null,
  status text,
  world_version_id text,
  session_id text,
  source_ref_json jsonb not null,
  payload_json jsonb not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_quality_events_trace_created_at on quality_events(trace_id, created_at);
create index if not exists idx_quality_events_surface_status_created_at on quality_events(source_surface, status, created_at);
create index if not exists idx_quality_events_world_created_at on quality_events(world_version_id, created_at);
create index if not exists idx_quality_events_session_created_at on quality_events(session_id, created_at);

create table if not exists content_quality_scores (
  score_id text primary key,
  trace_id text,
  source_surface text not null,
  status text,
  world_version_id text,
  session_id text,
  chapter_id text,
  rubric_version text not null,
  overall_score numeric not null default 0,
  veto boolean not null default false,
  dimension_scores_json jsonb not null,
  reason_codes_json jsonb not null,
  evidence_refs_json jsonb not null,
  score_payload_json jsonb not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_content_quality_scores_trace_created_at on content_quality_scores(trace_id, created_at);
create index if not exists idx_content_quality_scores_status_created_at on content_quality_scores(status, created_at);
create index if not exists idx_content_quality_scores_world_created_at on content_quality_scores(world_version_id, created_at);
create index if not exists idx_content_quality_scores_session_created_at on content_quality_scores(session_id, created_at);

create table if not exists review_cases (
  case_id text primary key,
  trace_id text,
  case_type text not null,
  status text not null,
  owner_id text,
  source_surface text,
  world_version_id text,
  session_id text,
  score_id text,
  source_ref_json jsonb not null,
  reason_codes_json jsonb not null,
  evidence_refs_json jsonb not null,
  case_payload_json jsonb not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_review_cases_status_updated_at on review_cases(status, updated_at);
create index if not exists idx_review_cases_trace_updated_at on review_cases(trace_id, updated_at);
create index if not exists idx_review_cases_world_status_updated_at on review_cases(world_version_id, status, updated_at);
create index if not exists idx_review_cases_session_status_updated_at on review_cases(session_id, status, updated_at);
