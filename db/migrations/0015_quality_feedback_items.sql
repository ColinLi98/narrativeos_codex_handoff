create table if not exists quality_feedback_items (
  feedback_item_id text primary key,
  trace_id text,
  source_event_id text,
  feedback_type text not null,
  signal text not null,
  source_surface text not null,
  account_id text,
  world_version_id text,
  session_id text,
  chapter_id text,
  source_ref_json jsonb not null,
  payload_json jsonb not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_quality_feedback_items_trace_created_at on quality_feedback_items(trace_id, created_at);
create index if not exists idx_quality_feedback_items_account_created_at on quality_feedback_items(account_id, created_at);
create index if not exists idx_quality_feedback_items_session_created_at on quality_feedback_items(session_id, created_at);
create index if not exists idx_quality_feedback_items_type_signal_created_at on quality_feedback_items(feedback_type, signal, created_at);
