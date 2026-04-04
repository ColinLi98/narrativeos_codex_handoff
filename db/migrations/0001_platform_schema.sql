-- NarrativeOS platform schema (minimum viable)

create table if not exists worlds (
  world_id text primary key,
  latest_version text,
  title text not null,
  status text not null default 'draft',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists world_versions (
  world_version_id text primary key,
  world_id text not null references worlds(world_id),
  version text not null,
  author_id text not null,
  status text not null default 'draft',
  risk_rating text,
  manifest_json jsonb not null,
  worldpack_json jsonb not null,
  validation_report_json jsonb,
  simulation_report_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists sessions (
  session_id text primary key,
  reader_id text,
  world_version_id text not null references world_versions(world_version_id),
  status text not null default 'active',
  chapter_index int not null default 0,
  story_phase text,
  narrative_state_json jsonb not null,
  entitlements_snapshot_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists chapters (
  chapter_id text primary key,
  session_id text not null references sessions(session_id),
  world_version_id text not null references world_versions(world_version_id),
  chapter_index int not null,
  plan_json jsonb,
  rendered_body text,
  choices_json jsonb,
  cost_estimate numeric,
  review_flags_json jsonb,
  created_at timestamptz not null default now()
);

create table if not exists route_choices (
  choice_event_id bigserial primary key,
  session_id text not null references sessions(session_id),
  chapter_id text not null references chapters(chapter_id),
  choice_id text not null,
  selected_at timestamptz not null default now(),
  payload_json jsonb
);

create table if not exists entitlements (
  entitlement_id text primary key,
  account_id text,
  reader_id text not null,
  world_id text,
  entitlement_type text not null,
  wallet_type text,
  tier_id text,
  status text not null default 'active',
  balance numeric,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists usage_meters (
  meter_id text primary key,
  account_id text,
  reader_id text,
  session_id text,
  chapter_id text,
  world_version_id text,
  action_type text not null,
  usage_units numeric not null,
  estimated_cost numeric,
  wallet_type text,
  subscription_tier text,
  provider text,
  model_policy_version text,
  created_at timestamptz not null default now()
);

create table if not exists review_records (
  review_id text primary key,
  asset_type text not null,
  asset_id text not null,
  status text not null,
  reviewer_id text,
  risk_rating text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists analytics_events (
  event_id bigserial primary key,
  event_name text not null,
  reader_id text,
  session_id text,
  world_version_id text,
  payload_json jsonb,
  occurred_at timestamptz not null default now()
);
