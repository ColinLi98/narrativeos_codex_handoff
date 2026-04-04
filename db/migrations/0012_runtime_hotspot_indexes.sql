create index if not exists idx_sessions_world_version_updated_at on sessions(world_version_id, updated_at);
create index if not exists idx_sessions_reader_updated_at on sessions(reader_id, updated_at);
create index if not exists idx_sessions_status_updated_at on sessions(status, updated_at);

create index if not exists idx_chapters_session_chapter_index on chapters(session_id, chapter_index);
create index if not exists idx_chapters_world_version_created_at on chapters(world_version_id, created_at);

create index if not exists idx_review_records_asset_type_status_updated_at on review_records(asset_type, status, updated_at);
create index if not exists idx_review_records_asset_type_asset_id_updated_at on review_records(asset_type, asset_id, updated_at);
create index if not exists idx_review_records_reviewer_updated_at on review_records(reviewer_id, updated_at);

create table if not exists subscriptions (
  subscription_id text primary key,
  account_id text not null,
  tier_id text not null,
  provider text not null,
  provider_ref text,
  status text not null default 'trialing',
  period_start timestamptz,
  period_end timestamptz,
  cancel_at_period_end text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_subscriptions_account_status_updated_at on subscriptions(account_id, status, updated_at);

create index if not exists idx_usage_meters_account_created_at on usage_meters(account_id, created_at);
create index if not exists idx_usage_meters_session_created_at on usage_meters(session_id, created_at);
create index if not exists idx_usage_meters_world_version_created_at on usage_meters(world_version_id, created_at);

create index if not exists idx_analytics_events_event_name_occurred_at on analytics_events(event_name, occurred_at);
create index if not exists idx_analytics_events_session_occurred_at on analytics_events(session_id, occurred_at);
create index if not exists idx_analytics_events_world_version_occurred_at on analytics_events(world_version_id, occurred_at);
