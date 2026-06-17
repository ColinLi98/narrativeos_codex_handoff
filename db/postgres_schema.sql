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

create table if not exists author_comment_threads (
  thread_id text primary key,
  world_version_id text not null references world_versions(world_version_id),
  revision_id text,
  anchor_type text not null,
  anchor_key text not null,
  status text not null default 'open',
  severity text not null default 'normal',
  assignee_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_author_comment_threads_world_version_id on author_comment_threads(world_version_id);
create index if not exists idx_author_comment_threads_revision_id on author_comment_threads(revision_id);
create index if not exists idx_author_comment_threads_assignee_id on author_comment_threads(assignee_id);

create table if not exists author_comment_messages (
  message_id text primary key,
  thread_id text not null references author_comment_threads(thread_id),
  actor_id text not null,
  actor_role text not null,
  body text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_author_comment_messages_thread_id on author_comment_messages(thread_id);

create table if not exists author_approval_records (
  approval_id text primary key,
  world_version_id text not null references world_versions(world_version_id),
  revision_id text,
  status text not null,
  reviewer_id text not null,
  reason text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_author_approval_records_world_version_id on author_approval_records(world_version_id);
create index if not exists idx_author_approval_records_revision_id on author_approval_records(revision_id);

create table if not exists author_notifications (
  notification_id text primary key,
  world_version_id text not null references world_versions(world_version_id),
  thread_id text references author_comment_threads(thread_id),
  approval_id text references author_approval_records(approval_id),
  recipient_id text not null,
  recipient_role text not null default 'reviewer',
  notification_type text not null,
  status text not null default 'unread',
  actor_id text,
  actor_role text,
  title text not null,
  body text not null,
  anchor_type text,
  anchor_key text,
  metadata_json jsonb,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_author_notifications_world_version_id on author_notifications(world_version_id);
create index if not exists idx_author_notifications_thread_id on author_notifications(thread_id);
create index if not exists idx_author_notifications_approval_id on author_notifications(approval_id);
create index if not exists idx_author_notifications_recipient_id on author_notifications(recipient_id);
create index if not exists idx_author_notifications_status on author_notifications(status);

create table if not exists author_thread_watchers (
  watcher_record_id text primary key,
  thread_id text not null references author_comment_threads(thread_id),
  watcher_id text not null,
  added_by text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_author_thread_watchers_thread_id on author_thread_watchers(thread_id);
create index if not exists idx_author_thread_watchers_watcher_id on author_thread_watchers(watcher_id);

create table if not exists author_draft_watchers (
  watcher_record_id text primary key,
  world_version_id text not null references world_versions(world_version_id),
  watcher_id text not null,
  added_by text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_author_draft_watchers_world_version_id on author_draft_watchers(world_version_id);
create index if not exists idx_author_draft_watchers_watcher_id on author_draft_watchers(watcher_id);

create table if not exists author_notification_preferences (
  preference_id text primary key,
  actor_id text not null,
  notification_type text not null,
  in_app_enabled text not null default 'true',
  async_mirror_enabled text not null default 'true',
  async_sink_name text,
  delivery_target text,
  updated_at timestamptz not null default now()
);

create index if not exists idx_author_notification_preferences_actor_id on author_notification_preferences(actor_id);
create index if not exists idx_author_notification_preferences_notification_type on author_notification_preferences(notification_type);

create table if not exists auth_identities (
  actor_id text primary key,
  account_id text,
  actor_role text not null,
  display_name text,
  password_hash text not null,
  password_salt text not null,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_auth_identities_account_id on auth_identities(account_id);

create table if not exists auth_tokens (
  token_id text primary key,
  actor_id text not null references auth_identities(actor_id),
  account_id text,
  actor_role text not null,
  token_hash text not null,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  expires_at timestamptz,
  last_used_at timestamptz
);

create index if not exists idx_auth_tokens_actor_id on auth_tokens(actor_id);
create index if not exists idx_auth_tokens_account_id on auth_tokens(account_id);
create index if not exists idx_auth_tokens_token_hash on auth_tokens(token_hash);

create table if not exists billing_checkout_sessions (
  checkout_session_id text primary key,
  account_id text not null,
  tier_id text not null,
  provider text not null,
  provider_ref text,
  subscription_id text,
  status text not null default 'created',
  checkout_url text,
  idempotency_key text not null,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_billing_checkout_sessions_account_id on billing_checkout_sessions(account_id);
create index if not exists idx_billing_checkout_sessions_provider_ref on billing_checkout_sessions(provider_ref);
create index if not exists idx_billing_checkout_sessions_idempotency_key on billing_checkout_sessions(idempotency_key);

create table if not exists billing_lifecycle_events (
  event_id text primary key,
  event_type text not null,
  provider text not null,
  provider_event_id text not null,
  account_id text,
  subscription_id text,
  checkout_session_id text,
  status text not null default 'received',
  payload_json jsonb,
  processing_result jsonb,
  occurred_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists idx_billing_lifecycle_events_provider_event_id on billing_lifecycle_events(provider_event_id);
create index if not exists idx_billing_lifecycle_events_account_id on billing_lifecycle_events(account_id);
create index if not exists idx_billing_lifecycle_events_subscription_id on billing_lifecycle_events(subscription_id);
create index if not exists idx_billing_lifecycle_events_checkout_session_id on billing_lifecycle_events(checkout_session_id);

create table if not exists billing_retry_attempts (
  retry_attempt_id text primary key,
  account_id text,
  subscription_id text,
  checkout_session_id text,
  source_event_id text,
  status text not null default 'planned',
  retry_reason text,
  attempt_count integer not null default 1,
  next_retry_at timestamptz,
  payload_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_billing_retry_attempts_account_id on billing_retry_attempts(account_id);
create index if not exists idx_billing_retry_attempts_subscription_id on billing_retry_attempts(subscription_id);
create index if not exists idx_billing_retry_attempts_checkout_session_id on billing_retry_attempts(checkout_session_id);
create index if not exists idx_billing_retry_attempts_source_event_id on billing_retry_attempts(source_event_id);

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
