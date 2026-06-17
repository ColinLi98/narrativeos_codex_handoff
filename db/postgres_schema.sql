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

alter table if exists author_works add column if not exists branch_id text;
alter table if exists author_works add column if not exists root_work_id text;
alter table if exists author_works add column if not exists parent_work_id text;
alter table if exists author_works add column if not exists branch_name text;
alter table if exists author_works add column if not exists branch_kind text;
alter table if exists author_works add column if not exists branch_origin_label text;
alter table if exists author_works add column if not exists fork_after_chapter_index integer default 0;
alter table if exists author_works add column if not exists is_active_line integer default 0;

update author_works
set root_work_id = work_id
where root_work_id is null;

update author_works
set branch_id = work_id
where branch_id is null;

update author_works
set branch_name = '主线'
where branch_name is null;

update author_works
set branch_kind = 'mainline'
where branch_kind is null;

update author_works
set fork_after_chapter_index = 0
where fork_after_chapter_index is null;

update author_works
set is_active_line = 1
where is_active_line is null;

create index if not exists idx_author_works_root_work_updated_at on author_works(root_work_id, updated_at);

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

create table if not exists plans (
  plan_id text primary key,
  display_name text not null,
  subscription_tier text not null,
  monthly_price_usd numeric not null default 0,
  status text not null default 'active',
  seat_limit integer not null default 0,
  workspace_limit integer not null default 0,
  campaign_limit integer not null default 0,
  plan_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_plans_status_updated_at on plans(status, updated_at);

create table if not exists customer_accounts (
  customer_account_id text primary key,
  account_id text not null unique,
  display_name text,
  status text not null default 'trial',
  plan_id text not null,
  seat_limit integer not null default 0,
  workspace_limit integer not null default 0,
  campaign_limit integer not null default 0,
  seat_count integer not null default 0,
  workspace_count integer not null default 0,
  campaign_count integer not null default 0,
  renewal_due_at timestamptz,
  metadata_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_customer_accounts_status_updated_at on customer_accounts(status, updated_at);
create index if not exists idx_customer_accounts_plan_status_updated_at on customer_accounts(plan_id, status, updated_at);
create index if not exists idx_customer_accounts_renewal_due_at on customer_accounts(renewal_due_at);

create table if not exists billing_profiles (
  billing_profile_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  provider text not null,
  provider_customer_ref text,
  invoice_email text,
  legal_name text,
  billing_country text,
  tax_status text,
  status text not null default 'active',
  profile_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_billing_profiles_customer_updated_at on billing_profiles(customer_account_id, updated_at);
create index if not exists idx_billing_profiles_account_updated_at on billing_profiles(account_id, updated_at);
create index if not exists idx_billing_profiles_provider_status_updated_at on billing_profiles(provider, status, updated_at);

create table if not exists usage_ledgers (
  usage_ledger_id text primary key,
  account_id text not null,
  customer_account_id text,
  plan_id text,
  status text not null default 'open',
  billing_period_start timestamptz not null,
  billing_period_end timestamptz not null,
  presented_count integer not null default 0,
  handoff_count integer not null default 0,
  conversion_count integer not null default 0,
  subtotal_amount_usd numeric not null default 0,
  disputed_amount_usd numeric not null default 0,
  credited_amount_usd numeric not null default 0,
  reversed_amount_usd numeric not null default 0,
  ledger_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_usage_ledgers_account_period_updated_at on usage_ledgers(account_id, billing_period_start, updated_at);
create index if not exists idx_usage_ledgers_customer_period_updated_at on usage_ledgers(customer_account_id, billing_period_start, updated_at);
create index if not exists idx_usage_ledgers_status_updated_at on usage_ledgers(status, updated_at);

create table if not exists billable_events (
  billable_event_id text primary key,
  usage_ledger_id text,
  account_id text not null,
  customer_account_id text,
  plan_id text,
  billable_metric text not null,
  status text not null default 'recorded',
  trace_id text,
  quality_event_id text,
  runtime_receipt_event_id text,
  feedback_item_id text,
  source_surface text,
  world_version_id text,
  session_id text,
  quantity numeric not null default 1,
  unit_price_usd numeric not null default 0,
  amount_usd numeric not null default 0,
  reason_codes_json jsonb not null default '[]',
  event_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_billable_events_account_created_at on billable_events(account_id, created_at);
create index if not exists idx_billable_events_customer_created_at on billable_events(customer_account_id, created_at);
create index if not exists idx_billable_events_trace_created_at on billable_events(trace_id, created_at);
create index if not exists idx_billable_events_metric_status_created_at on billable_events(billable_metric, status, created_at);

create table if not exists invoice_previews (
  invoice_preview_id text primary key,
  usage_ledger_id text,
  account_id text not null,
  customer_account_id text,
  plan_id text,
  status text not null default 'draft',
  billing_period_start timestamptz not null,
  billing_period_end timestamptz not null,
  subtotal_amount_usd numeric not null default 0,
  credits_applied_usd numeric not null default 0,
  disputed_amount_usd numeric not null default 0,
  credited_amount_usd numeric not null default 0,
  reversed_amount_usd numeric not null default 0,
  total_due_usd numeric not null default 0,
  line_items_json jsonb not null default '[]',
  summary_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_invoice_previews_account_period_updated_at on invoice_previews(account_id, billing_period_start, updated_at);
create index if not exists idx_invoice_previews_customer_period_updated_at on invoice_previews(customer_account_id, billing_period_start, updated_at);

create table if not exists credit_balances (
  credit_balance_id text primary key,
  account_id text not null,
  customer_account_id text,
  balance_type text not null,
  amount_usd numeric not null default 0,
  source_ref_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_credit_balances_account_updated_at on credit_balances(account_id, updated_at);
create index if not exists idx_credit_balances_customer_updated_at on credit_balances(customer_account_id, updated_at);
create index if not exists idx_credit_balances_type_updated_at on credit_balances(balance_type, updated_at);

create table if not exists overage_flags (
  overage_flag_id text primary key,
  account_id text not null,
  customer_account_id text,
  plan_id text,
  metric_type text not null,
  status text not null default 'active',
  observed_units numeric not null default 0,
  included_units numeric not null default 0,
  overage_units numeric not null default 0,
  flag_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_overage_flags_account_status_updated_at on overage_flags(account_id, status, updated_at);
create index if not exists idx_overage_flags_metric_status_updated_at on overage_flags(metric_type, status, updated_at);

create table if not exists campaigns (
  campaign_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  title text not null,
  target_icp_vertical text not null,
  cta_text text not null,
  disclosure_text text not null,
  activation_status text not null default 'draft',
  selected_channels_json jsonb not null default '[]',
  selected_partner_refs_json jsonb not null default '[]',
  primary_review_case_id text,
  latest_submission_id text,
  campaign_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_campaigns_account_status_updated_at on campaigns(account_id, activation_status, updated_at);
create index if not exists idx_campaigns_customer_status_updated_at on campaigns(customer_account_id, activation_status, updated_at);

create table if not exists campaign_proof_bundles (
  proof_bundle_id text primary key,
  campaign_id text not null,
  bundle_label text not null default 'default',
  proof_points_json jsonb not null default '[]',
  source_urls_json jsonb not null default '[]',
  artifact_refs_json jsonb not null default '[]',
  bundle_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_campaign_proof_bundles_campaign_updated_at on campaign_proof_bundles(campaign_id, updated_at);

create table if not exists campaign_channel_targets (
  channel_target_id text primary key,
  campaign_id text not null,
  channel_name text not null,
  partner_ref text,
  priority integer not null default 0,
  readiness_status text not null default 'selected',
  target_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_campaign_channel_targets_campaign_priority_updated_at on campaign_channel_targets(campaign_id, priority, updated_at);

create table if not exists campaign_review_submissions (
  submission_id text primary key,
  campaign_id text not null,
  review_case_id text,
  status text not null default 'submitted',
  submitted_by text not null,
  reviewer_id text,
  decision_note text,
  submitted_at timestamptz not null default CURRENT_TIMESTAMP,
  decided_at timestamptz,
  submission_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_campaign_review_submissions_campaign_updated_at on campaign_review_submissions(campaign_id, updated_at);
create index if not exists idx_campaign_review_submissions_review_case_updated_at on campaign_review_submissions(review_case_id, updated_at);
create index if not exists idx_campaign_review_submissions_status_updated_at on campaign_review_submissions(status, updated_at);

create table if not exists partners (
  partner_id text primary key,
  name text not null,
  lifecycle_status text not null default 'discovered',
  sla_status text not null default 'unknown',
  receipt_capability text not null default 'unknown',
  disclosure_readiness text not null default 'unknown',
  billing_readiness text not null default 'unknown',
  allowlisted_channels_json jsonb not null default '[]',
  primary_endpoint_url text,
  endpoint_health_status text not null default 'unknown',
  partner_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_partners_lifecycle_updated_at on partners(lifecycle_status, updated_at);
create index if not exists idx_partners_endpoint_health_updated_at on partners(endpoint_health_status, updated_at);

create table if not exists partner_capabilities (
  partner_capability_id text primary key,
  partner_id text not null,
  capability_type text not null,
  status text not null default 'unknown',
  capability_value text,
  capability_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_partner_capabilities_partner_updated_at on partner_capabilities(partner_id, updated_at);
create index if not exists idx_partner_capabilities_type_status_updated_at on partner_capabilities(capability_type, status, updated_at);

create table if not exists partner_health_checks (
  health_check_id text primary key,
  partner_id text not null,
  endpoint_url text,
  status text not null default 'unknown',
  status_code integer,
  response_time_ms numeric,
  checked_at timestamptz not null default CURRENT_TIMESTAMP,
  health_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_partner_health_checks_partner_checked_at on partner_health_checks(partner_id, checked_at);
create index if not exists idx_partner_health_checks_status_checked_at on partner_health_checks(status, checked_at);

create table if not exists disputes (
  dispute_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  campaign_id text,
  invoice_preview_id text,
  billable_event_id text,
  quality_event_id text,
  trace_id text,
  dispute_reason_code text not null,
  note text,
  status text not null default 'open',
  requested_amount_usd numeric not null default 0,
  resolved_amount_usd numeric not null default 0,
  requested_by text not null,
  reviewer_id text,
  resolution_note text,
  dispute_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_disputes_account_status_updated_at on disputes(account_id, status, updated_at);
create index if not exists idx_disputes_customer_status_updated_at on disputes(customer_account_id, status, updated_at);
create index if not exists idx_disputes_billable_event_updated_at on disputes(billable_event_id, updated_at);

create table if not exists refund_requests (
  refund_request_id text primary key,
  dispute_id text,
  customer_account_id text not null,
  account_id text not null,
  invoice_preview_id text,
  billable_event_id text,
  trace_id text,
  status text not null default 'requested',
  requested_amount_usd numeric not null default 0,
  approved_amount_usd numeric not null default 0,
  requested_by text not null,
  reviewer_id text,
  refund_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_refund_requests_account_status_updated_at on refund_requests(account_id, status, updated_at);
create index if not exists idx_refund_requests_dispute_updated_at on refund_requests(dispute_id, updated_at);

create table if not exists settlement_runs (
  settlement_run_id text primary key,
  customer_account_id text,
  account_id text,
  billing_period_start timestamptz,
  billing_period_end timestamptz,
  status text not null default 'draft',
  subtotal_amount_usd numeric not null default 0,
  disputed_amount_usd numeric not null default 0,
  credited_amount_usd numeric not null default 0,
  reversed_amount_usd numeric not null default 0,
  refunded_amount_usd numeric not null default 0,
  net_amount_usd numeric not null default 0,
  run_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_settlement_runs_account_updated_at on settlement_runs(account_id, updated_at);
create index if not exists idx_settlement_runs_status_updated_at on settlement_runs(status, updated_at);

create table if not exists settlement_items (
  settlement_item_id text primary key,
  settlement_run_id text not null,
  billable_event_id text,
  invoice_preview_id text,
  dispute_id text,
  refund_request_id text,
  status text not null default 'approved',
  amount_usd numeric not null default 0,
  item_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_settlement_items_run_status_created_at on settlement_items(settlement_run_id, status, created_at);

create table if not exists support_cases (
  support_case_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  campaign_id text,
  invoice_preview_id text,
  billable_event_id text,
  quality_event_id text,
  trace_id text,
  case_type text not null default 'general',
  subject text not null,
  description text not null,
  status text not null default 'open',
  priority text not null default 'medium',
  requested_by text not null,
  owner_id text,
  resolution_note text,
  support_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_support_cases_account_status_updated_at on support_cases(account_id, status, updated_at);
create index if not exists idx_support_cases_owner_status_updated_at on support_cases(owner_id, status, updated_at);

create table if not exists manual_adjustments (
  adjustment_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  dispute_id text,
  refund_request_id text,
  invoice_preview_id text,
  billable_event_id text,
  adjustment_type text not null,
  amount_usd numeric not null default 0,
  status text not null default 'applied',
  requested_by text not null,
  reviewer_id text,
  adjustment_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_manual_adjustments_account_status_updated_at on manual_adjustments(account_id, status, updated_at);
create index if not exists idx_manual_adjustments_dispute_updated_at on manual_adjustments(dispute_id, updated_at);

create table if not exists audit_logs (
  audit_log_id text primary key,
  actor_id text not null,
  actor_role text not null,
  account_id text,
  customer_account_id text,
  object_type text not null,
  object_id text not null,
  action_type text not null,
  source_surface text not null,
  customer_visible_payload_json jsonb not null default '{}',
  internal_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_audit_logs_account_created_at on audit_logs(account_id, created_at);
create index if not exists idx_audit_logs_customer_created_at on audit_logs(customer_account_id, created_at);
create index if not exists idx_audit_logs_actor_created_at on audit_logs(actor_id, created_at);
create index if not exists idx_audit_logs_action_created_at on audit_logs(action_type, created_at);

create table if not exists customer_audit_exports (
  audit_export_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  requested_by text not null,
  period_start timestamptz,
  period_end timestamptz,
  export_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_customer_audit_exports_account_created_at on customer_audit_exports(account_id, created_at);
create index if not exists idx_customer_audit_exports_customer_created_at on customer_audit_exports(customer_account_id, created_at);

create table if not exists data_retention_policies (
  retention_policy_id text primary key,
  scope text not null,
  retention_days integer not null default 30,
  deletion_mode text not null default 'manual_request',
  status text not null default 'active',
  policy_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_data_retention_policies_scope_status_updated_at on data_retention_policies(scope, status, updated_at);

create table if not exists data_deletion_requests (
  deletion_request_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  requested_by text not null,
  scope text not null,
  status text not null default 'requested',
  requested_payload_json jsonb not null default '{}',
  affected_object_counts_json jsonb not null default '{}',
  resolution_note text,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_data_deletion_requests_account_status_updated_at on data_deletion_requests(account_id, status, updated_at);
create index if not exists idx_data_deletion_requests_customer_status_updated_at on data_deletion_requests(customer_account_id, status, updated_at);

create table if not exists invoice_issuances (
  invoice_id text primary key,
  invoice_preview_id text not null,
  customer_account_id text not null,
  account_id text not null,
  provider text not null,
  provider_invoice_ref text,
  provider_customer_ref text,
  status text not null default 'draft',
  currency text not null default 'USD',
  subtotal_amount_usd numeric not null default 0,
  total_due_usd numeric not null default 0,
  hosted_invoice_url text,
  invoice_pdf_url text,
  issued_at timestamptz,
  paid_at timestamptz,
  voided_at timestamptz,
  invoice_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_invoice_issuances_account_status_updated_at on invoice_issuances(account_id, status, updated_at);
create index if not exists idx_invoice_issuances_customer_status_updated_at on invoice_issuances(customer_account_id, status, updated_at);
create index if not exists idx_invoice_issuances_provider_ref_updated_at on invoice_issuances(provider_invoice_ref, updated_at);

create table if not exists payment_transactions (
  payment_transaction_id text primary key,
  invoice_id text,
  customer_account_id text,
  account_id text not null,
  provider text not null,
  provider_transaction_ref text,
  transaction_type text not null default 'payment',
  status text not null default 'pending',
  amount_usd numeric not null default 0,
  currency text not null default 'USD',
  trace_id text,
  transaction_payload_json jsonb not null default '{}',
  occurred_at timestamptz not null default CURRENT_TIMESTAMP,
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_payment_transactions_account_occurred_at on payment_transactions(account_id, occurred_at);
create index if not exists idx_payment_transactions_invoice_occurred_at on payment_transactions(invoice_id, occurred_at);
create index if not exists idx_payment_transactions_provider_ref_occurred_at on payment_transactions(provider_transaction_ref, occurred_at);

create table if not exists provider_webhook_events (
  provider_webhook_event_id text primary key,
  provider text not null,
  provider_event_id text not null,
  event_type text not null,
  status text not null default 'received',
  invoice_id text,
  account_id text,
  payload_json jsonb not null default '{}',
  processing_result_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  processed_at timestamptz
);

create index if not exists idx_provider_webhook_events_provider_created_at on provider_webhook_events(provider, created_at);
create index if not exists idx_provider_webhook_events_provider_event_created_at on provider_webhook_events(provider_event_id, created_at);
create index if not exists idx_provider_webhook_events_status_created_at on provider_webhook_events(status, created_at);

create table if not exists credit_notes (
  credit_note_id text primary key,
  invoice_id text not null,
  customer_account_id text,
  account_id text not null,
  provider text not null,
  provider_credit_note_ref text,
  status text not null default 'issued',
  amount_usd numeric not null default 0,
  reason text,
  credit_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_credit_notes_invoice_created_at on credit_notes(invoice_id, created_at);
create index if not exists idx_credit_notes_provider_ref_created_at on credit_notes(provider_credit_note_ref, created_at);

create table if not exists payment_retry_attempts (
  payment_retry_attempt_id text primary key,
  invoice_id text,
  customer_account_id text,
  account_id text not null,
  provider text not null,
  status text not null default 'planned',
  retry_reason text,
  attempt_count integer not null default 1,
  next_retry_at timestamptz,
  retry_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_payment_retry_attempts_invoice_updated_at on payment_retry_attempts(invoice_id, updated_at);
create index if not exists idx_payment_retry_attempts_account_updated_at on payment_retry_attempts(account_id, updated_at);

create table if not exists dunning_events (
  dunning_event_id text primary key,
  invoice_id text,
  customer_account_id text,
  account_id text not null,
  status text not null default 'scheduled',
  step text not null,
  event_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_dunning_events_invoice_created_at on dunning_events(invoice_id, created_at);
create index if not exists idx_dunning_events_account_created_at on dunning_events(account_id, created_at);

create table if not exists renewal_trackers (
  renewal_tracker_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  status text not null default 'stable',
  renewal_due_at timestamptz,
  tracker_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_renewal_trackers_account_status_updated_at on renewal_trackers(account_id, status, updated_at);

create table if not exists dunning_runs (
  dunning_run_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  invoice_id text,
  status text not null default 'open',
  current_step text not null default 'initial_notice',
  dunning_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_dunning_runs_account_status_updated_at on dunning_runs(account_id, status, updated_at);

create table if not exists pilot_conversion_tracks (
  pilot_conversion_track_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  status text not null default 'watch',
  track_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_pilot_conversion_tracks_account_status_updated_at on pilot_conversion_tracks(account_id, status, updated_at);

create table if not exists expansion_candidates (
  expansion_candidate_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  status text not null default 'watch',
  trigger_type text not null,
  candidate_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_expansion_candidates_account_status_updated_at on expansion_candidates(account_id, status, updated_at);

create table if not exists churn_risk_flags (
  churn_risk_flag_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  status text not null default 'watch',
  risk_level text not null default 'medium',
  flag_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_churn_risk_flags_account_status_updated_at on churn_risk_flags(account_id, status, updated_at);

create table if not exists production_signoffs (
  signoff_id text primary key,
  launch_label text not null,
  status text not null default 'draft',
  source_go_live_checklist_id text,
  source_manual_signoff_bundle_id text,
  rollup_summary_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_signoffs_status_updated_at on production_signoffs(status, updated_at);
create index if not exists idx_production_signoffs_launch_label_updated_at on production_signoffs(launch_label, updated_at);

create table if not exists production_signoff_items (
  signoff_item_id text primary key,
  signoff_id text not null,
  item_code text not null,
  category text not null,
  label text not null,
  owner_role text not null,
  owner_actor_id text,
  due_at timestamptz,
  status text not null default 'pending',
  decision_note text,
  approved_at timestamptz,
  evidence_count integer not null default 0,
  item_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_signoff_items_signoff_status_due_at on production_signoff_items(signoff_id, status, due_at);
create index if not exists idx_production_signoff_items_owner_status_due_at on production_signoff_items(owner_role, status, due_at);
create index if not exists idx_production_signoff_items_code_status_updated_at on production_signoff_items(item_code, status, updated_at);

create table if not exists production_signoff_evidence (
  evidence_id text primary key,
  signoff_id text not null,
  signoff_item_id text not null,
  evidence_type text not null,
  source_ref_json jsonb not null default '{}',
  summary text,
  customer_safe boolean not null default false,
  payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_signoff_evidence_item_created_at on production_signoff_evidence(signoff_item_id, created_at);
create index if not exists idx_production_signoff_evidence_signoff_created_at on production_signoff_evidence(signoff_id, created_at);

create table if not exists production_cutover_windows (
  cutover_window_id text primary key,
  signoff_id text not null,
  launch_wave text not null,
  target_environment text not null,
  starts_at timestamptz,
  ends_at timestamptz,
  rollback_owner_role text,
  status text not null default 'planned',
  cutover_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_cutover_windows_signoff_status_starts_at on production_cutover_windows(signoff_id, status, starts_at);
create index if not exists idx_production_cutover_windows_env_status_starts_at on production_cutover_windows(target_environment, status, starts_at);

create table if not exists production_customer_acceptance_records (
  acceptance_record_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  signoff_id text,
  launch_wave text not null,
  status text not null default 'draft',
  readiness_summary_json jsonb not null default '{}',
  acceptance_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_customer_acceptance_account_status_updated_at on production_customer_acceptance_records(account_id, status, updated_at);
create index if not exists idx_production_customer_acceptance_wave_status_updated_at on production_customer_acceptance_records(launch_wave, status, updated_at);

create table if not exists go_live_ready_accounts (
  go_live_ready_account_id text primary key,
  customer_account_id text not null,
  account_id text not null,
  acceptance_record_id text not null,
  launch_wave text not null,
  status text not null default 'candidate',
  readiness_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_go_live_ready_accounts_wave_status_updated_at on go_live_ready_accounts(launch_wave, status, updated_at);
create index if not exists idx_go_live_ready_accounts_account_status_updated_at on go_live_ready_accounts(account_id, status, updated_at);

create table if not exists launch_wave_statuses (
  launch_wave_status_id text primary key,
  launch_wave text not null,
  status text not null default 'planned',
  target_environment text not null default 'production',
  wave_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_launch_wave_statuses_wave_status_updated_at on launch_wave_statuses(launch_wave, status, updated_at);

create table if not exists production_preflight_runs (
  preflight_run_id text primary key,
  signoff_id text,
  launch_wave text not null,
  target_environment text not null default 'production',
  status text not null default 'running',
  go_no_go text not null default 'manual_review',
  hard_fail_count integer not null default 0,
  soft_fail_count integer not null default 0,
  run_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_preflight_runs_signoff_status_updated_at on production_preflight_runs(signoff_id, status, updated_at);
create index if not exists idx_production_preflight_runs_wave_status_updated_at on production_preflight_runs(launch_wave, status, updated_at);

create table if not exists production_preflight_checks (
  preflight_check_id text primary key,
  preflight_run_id text not null,
  check_key text not null,
  linked_signoff_item_code text,
  owner_role text not null,
  status text not null default 'passed',
  summary text,
  evidence_ref text,
  payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_preflight_checks_run_status_created_at on production_preflight_checks(preflight_run_id, status, created_at);
create index if not exists idx_production_preflight_checks_linked_item_status_created_at on production_preflight_checks(linked_signoff_item_code, status, created_at);

create table if not exists first_7_day_outcomes (
  first_7_day_outcome_id text primary key,
  account_id text not null,
  customer_account_id text,
  launch_wave text not null,
  launch_anchor_at timestamptz,
  outcome_payload_json jsonb not null default '{}',
  generated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_first_7_day_outcomes_account_generated_at on first_7_day_outcomes(account_id, generated_at);
create index if not exists idx_first_7_day_outcomes_wave_generated_at on first_7_day_outcomes(launch_wave, generated_at);

create table if not exists first_30_day_value_summaries (
  first_30_day_value_summary_id text primary key,
  account_id text not null,
  customer_account_id text,
  launch_wave text not null,
  launch_anchor_at timestamptz,
  provisional boolean not null default true,
  summary_payload_json jsonb not null default '{}',
  generated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_first_30_day_value_summaries_account_generated_at on first_30_day_value_summaries(account_id, generated_at);
create index if not exists idx_first_30_day_value_summaries_wave_generated_at on first_30_day_value_summaries(launch_wave, generated_at);

create table if not exists pilot_to_paid_readiness_scores (
  pilot_to_paid_readiness_score_id text primary key,
  account_id text not null,
  customer_account_id text,
  launch_wave text not null,
  launch_anchor_at timestamptz,
  score double precision not null default 0,
  band text not null default 'watch',
  score_payload_json jsonb not null default '{}',
  generated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_pilot_to_paid_readiness_scores_account_generated_at on pilot_to_paid_readiness_scores(account_id, generated_at);
create index if not exists idx_pilot_to_paid_readiness_scores_wave_generated_at on pilot_to_paid_readiness_scores(launch_wave, generated_at);

create table if not exists customer_success_snapshots (
  customer_success_snapshot_id text primary key,
  account_id text not null,
  customer_account_id text,
  launch_wave text not null,
  launch_anchor_at timestamptz,
  snapshot_payload_json jsonb not null default '{}',
  generated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_customer_success_snapshots_account_generated_at on customer_success_snapshots(account_id, generated_at);
create index if not exists idx_customer_success_snapshots_wave_generated_at on customer_success_snapshots(launch_wave, generated_at);

create table if not exists production_launch_events (
  launch_event_id text primary key,
  launch_wave text not null,
  account_id text,
  event_category text not null,
  event_type text not null,
  phase text not null,
  severity text not null default 'info',
  related_object_type text,
  related_object_id text,
  occurred_at timestamptz not null default CURRENT_TIMESTAMP,
  event_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_launch_events_wave_phase_occurred_at on production_launch_events(launch_wave, phase, occurred_at);
create index if not exists idx_production_launch_events_account_severity_occurred_at on production_launch_events(account_id, severity, occurred_at);

create table if not exists production_postmortem_records (
  postmortem_record_id text primary key,
  launch_wave text not null,
  account_id text,
  status text not null default 'draft',
  summary_json jsonb not null default '{}',
  generated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_production_postmortem_records_wave_status_generated_at on production_postmortem_records(launch_wave, status, generated_at);
create index if not exists idx_production_postmortem_records_account_status_generated_at on production_postmortem_records(account_id, status, generated_at);

create table if not exists go_live_day_runs (
  go_live_day_run_id text primary key,
  signoff_id text,
  launch_wave text not null,
  account_id text,
  status text not null default 'running',
  activation_state_before text,
  activation_state_after text,
  report_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_go_live_day_runs_wave_status_updated_at on go_live_day_runs(launch_wave, status, updated_at);

create table if not exists go_live_day_checkpoints (
  go_live_day_checkpoint_id text primary key,
  go_live_day_run_id text not null,
  checkpoint_key text not null,
  status text not null default 'passed',
  summary text,
  evidence_ref text,
  rollback_recommendation text,
  checkpoint_payload_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_go_live_day_checkpoints_run_created_at on go_live_day_checkpoints(go_live_day_run_id, created_at);
create index if not exists idx_go_live_day_checkpoints_key_status_created_at on go_live_day_checkpoints(checkpoint_key, status, created_at);

create table if not exists launch_week_guard_runs (
  launch_week_guard_run_id text primary key,
  launch_wave text not null,
  account_id text,
  status text not null default 'not_ready',
  replication_readiness text not null default 'not_ready',
  summary_json jsonb not null default '{}',
  generated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_launch_week_guard_runs_wave_status_generated_at on launch_week_guard_runs(launch_wave, status, generated_at);

create table if not exists first_customer_success_packs (
  first_customer_success_pack_id text primary key,
  launch_wave text not null,
  account_id text,
  status text not null default 'not_ready',
  pack_payload_json jsonb not null default '{}',
  generated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_first_customer_success_packs_wave_status_generated_at on first_customer_success_packs(launch_wave, status, generated_at);

create table if not exists auth_identity_profiles (
  actor_id text primary key references auth_identities(actor_id),
  account_id text,
  email_address text,
  email_verified text not null default 'false',
  verification_required text not null default 'false',
  verification_sent_at timestamptz,
  verified_at timestamptz,
  password_reset_sent_at timestamptz,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_auth_identity_profiles_account_id on auth_identity_profiles(account_id);
create index if not exists idx_auth_identity_profiles_email_address on auth_identity_profiles(email_address);

create table if not exists auth_flow_tokens (
  flow_token_id text primary key,
  actor_id text not null references auth_identities(actor_id),
  account_id text,
  flow_type text not null,
  token_hash text not null,
  status text not null default 'active',
  payload_json jsonb,
  expires_at timestamptz,
  consumed_at timestamptz,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_auth_flow_tokens_actor_id on auth_flow_tokens(actor_id);
create index if not exists idx_auth_flow_tokens_account_id on auth_flow_tokens(account_id);
create index if not exists idx_auth_flow_tokens_flow_type on auth_flow_tokens(flow_type);
create index if not exists idx_auth_flow_tokens_token_hash on auth_flow_tokens(token_hash);

create table if not exists auth_delivery_attempts (
  attempt_id text primary key,
  actor_id text,
  account_id text,
  flow_type text not null,
  provider text not null,
  email_mode text not null,
  sender_email text,
  recipient_email text not null,
  status text not null,
  provider_message_id text,
  error_code text,
  error_reason text,
  retryable text not null default 'false',
  metadata_json jsonb,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_auth_delivery_attempts_actor_flow_created_at on auth_delivery_attempts(actor_id, flow_type, created_at);
create index if not exists idx_auth_delivery_attempts_recipient_created_at on auth_delivery_attempts(recipient_email, created_at);
create index if not exists idx_auth_delivery_attempts_status_created_at on auth_delivery_attempts(status, created_at);
create index if not exists idx_auth_delivery_attempts_provider_message_id on auth_delivery_attempts(provider_message_id);
create index if not exists idx_auth_delivery_attempts_error_code on auth_delivery_attempts(error_code);

create table if not exists showcase_work_likes (
  showcase_like_id text primary key,
  world_id text not null,
  world_version_id text not null,
  account_id text not null,
  actor_id text,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create unique index if not exists uq_showcase_work_likes_world_account on showcase_work_likes(world_id, account_id);
create index if not exists idx_showcase_work_likes_world_created_at on showcase_work_likes(world_id, created_at);
create index if not exists idx_showcase_work_likes_account_created_at on showcase_work_likes(account_id, created_at);

create table if not exists showcase_work_comments (
  showcase_comment_id text primary key,
  world_id text not null,
  world_version_id text not null,
  account_id text not null,
  actor_id text,
  author_name text not null,
  content text not null,
  status text not null default 'published',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_showcase_work_comments_world_status_created_at on showcase_work_comments(world_id, status, created_at);
create index if not exists idx_showcase_work_comments_account_created_at on showcase_work_comments(account_id, created_at);

create table if not exists showcase_work_tips (
  showcase_tip_id text primary key,
  world_id text not null,
  world_version_id text not null,
  account_id text not null,
  actor_id text,
  amount integer not null default 0,
  wallet_type text not null default 'story_credits',
  balance_after double precision not null default 0,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_showcase_work_tips_world_created_at on showcase_work_tips(world_id, created_at);
create index if not exists idx_showcase_work_tips_account_created_at on showcase_work_tips(account_id, created_at);

create table if not exists story_session_bookmarks (
  bookmark_id text primary key,
  session_id text not null,
  account_id text not null,
  node_id text not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create unique index if not exists uq_story_session_bookmarks_session_account_node on story_session_bookmarks(session_id, account_id, node_id);
create index if not exists idx_story_session_bookmarks_session_created_at on story_session_bookmarks(session_id, created_at);
create index if not exists idx_story_session_bookmarks_account_created_at on story_session_bookmarks(account_id, created_at);

create table if not exists story_session_share_tokens (
  share_token text primary key,
  session_id text not null,
  account_id text not null,
  node_id text not null,
  sharer_name text not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create unique index if not exists uq_story_session_share_tokens_session_account_node on story_session_share_tokens(session_id, account_id, node_id);
create index if not exists idx_story_session_share_tokens_token_created_at on story_session_share_tokens(share_token, created_at);
create index if not exists idx_story_session_share_tokens_session_created_at on story_session_share_tokens(session_id, created_at);
create index if not exists idx_story_session_share_tokens_account_created_at on story_session_share_tokens(account_id, created_at);

drop index if exists uq_story_session_share_tokens_session_account_node;

alter table story_session_share_tokens
  add column if not exists status text not null default 'active';

alter table story_session_share_tokens
  add column if not exists expires_at timestamptz;

alter table story_session_share_tokens
  add column if not exists revoked_at timestamptz;

create index if not exists idx_story_session_share_tokens_session_account_node_status
  on story_session_share_tokens(session_id, account_id, node_id, status);

alter table auth_identity_profiles
  add column if not exists avatar_url text;

alter table auth_identity_profiles
  add column if not exists ui_preferences_json jsonb;

alter table auth_identity_profiles
  add column if not exists deactivated_at timestamptz;

alter table auth_identity_profiles
  add column if not exists deactivated_by text;

alter table auth_identity_profiles
  add column if not exists deactivation_reason text;

alter table auth_identity_profiles
  add column if not exists pending_email_address text;

alter table auth_identity_profiles
  add column if not exists pending_email_change_requested_at timestamptz;

alter table auth_identity_profiles
  add column if not exists email_change_last_sent_at timestamptz;

create index if not exists idx_auth_identity_profiles_pending_email_address
  on auth_identity_profiles(pending_email_address);

alter table billing_checkout_sessions
  add column if not exists checkout_kind text not null default 'subscription';

alter table billing_checkout_sessions
  add column if not exists package_id text;

alter table billing_checkout_sessions
  add column if not exists fulfilled_at timestamptz;

create table if not exists soul_profile_preferences (
  actor_id text primary key,
  account_id text,
  genres_json jsonb not null default '[]',
  styles_json jsonb not null default '[]',
  privacy_mode text not null default 'followers',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_soul_profile_preferences_account_updated_at on soul_profile_preferences(account_id, updated_at);

create table if not exists library_work_favorites (
  favorite_id text primary key,
  account_id text not null,
  work_id text not null,
  work_kind text not null,
  title_snapshot text,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create unique index if not exists uq_library_work_favorites_account_work on library_work_favorites(account_id, work_id);
create index if not exists idx_library_work_favorites_account_created_at on library_work_favorites(account_id, created_at);
create index if not exists idx_library_work_favorites_work_created_at on library_work_favorites(work_id, created_at);

create table if not exists library_follows (
  follow_id text primary key,
  account_id text not null,
  target_type text not null,
  target_id text not null,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create unique index if not exists uq_library_follows_account_target on library_follows(account_id, target_type, target_id);
create index if not exists idx_library_follows_account_created_at on library_follows(account_id, created_at);
create index if not exists idx_library_follows_target_created_at on library_follows(target_type, target_id, created_at);

create table if not exists showcase_work_views (
  showcase_view_id text primary key,
  world_id text not null,
  world_version_id text not null,
  account_id text,
  viewer_key text not null,
  event_type text not null default 'view',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create unique index if not exists uq_showcase_work_views_world_viewer_event on showcase_work_views(world_id, viewer_key, event_type);
create index if not exists idx_showcase_work_views_world_event_created_at on showcase_work_views(world_id, event_type, created_at);
create index if not exists idx_showcase_work_views_account_event_created_at on showcase_work_views(account_id, event_type, created_at);

create table if not exists author_project_graphs (
  project_id text primary key,
  world_version_id text not null unique,
  account_id text not null,
  engine text not null default 'balanced',
  enabled_rule_ids_json jsonb not null default '[]',
  nodes_json jsonb not null default '[]',
  connections_json jsonb not null default '[]',
  metadata_json jsonb not null default '{}',
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create index if not exists idx_author_project_graphs_account_updated_at on author_project_graphs(account_id, updated_at);
create index if not exists idx_author_project_graphs_world_version_updated_at on author_project_graphs(world_version_id, updated_at);

create table if not exists ops_configs (
  ops_config_id text primary key,
  config_type text not null,
  scope_key text,
  status text not null default 'active',
  config_payload_json jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_ops_configs_type_scope_updated_at on ops_configs(config_type, scope_key, updated_at);
create index if not exists idx_ops_configs_status_updated_at on ops_configs(status, updated_at);

insert into ops_configs (
  ops_config_id,
  config_type,
  scope_key,
  status,
  config_payload_json,
  created_at,
  updated_at
)
select
  'governance_capacity_override::' || risk_tier as ops_config_id,
  'governance_capacity_override' as config_type,
  risk_tier as scope_key,
  case when mode = 'active' then 'active' else 'disabled' end as status,
  policy_payload_json as config_payload_json,
  created_at,
  updated_at
from quality_policies
where scenario_id = 'governance_capacity_override'
on conflict (ops_config_id) do update
set
  status = excluded.status,
  config_payload_json = excluded.config_payload_json,
  updated_at = excluded.updated_at;

create table if not exists library_stats_cubes (
  library_stats_cube_id text primary key,
  account_id text not null,
  snapshot_payload_json jsonb not null default '{}',
  source_updated_at timestamptz not null default CURRENT_TIMESTAMP,
  created_at timestamptz not null default CURRENT_TIMESTAMP,
  updated_at timestamptz not null default CURRENT_TIMESTAMP
);

create unique index if not exists uq_library_stats_cubes_account on library_stats_cubes(account_id);
create index if not exists idx_library_stats_cubes_account_updated_at on library_stats_cubes(account_id, updated_at);
create index if not exists idx_library_stats_cubes_source_updated_at on library_stats_cubes(source_updated_at);

alter table library_stats_cubes
  add column if not exists semantic_version text not null default 'library_stats_semantic/v2';

alter table library_stats_cubes
  add column if not exists source_breakdown_json jsonb not null default '{}';

alter table library_stats_cubes
  add column if not exists invalidated_at timestamptz;

alter table library_stats_cubes
  add column if not exists last_invalidated_event_name text;

alter table library_stats_cubes
  add column if not exists last_invalidated_event_at timestamptz;

create index if not exists idx_library_stats_cubes_invalidated_at on library_stats_cubes(invalidated_at);

create table if not exists generated_media_assets (
  asset_id text primary key,
  asset_kind text not null,
  owner_scope text not null,
  owner_id text not null,
  world_id text,
  world_version_id text,
  session_id text,
  chapter_index integer,
  reader_id text,
  storage_bucket text,
  storage_key text,
  mime_type text,
  width integer,
  height integer,
  visibility text not null default 'private',
  generation_status text not null default 'queued',
  model_name text,
  prompt_version text,
  source_fingerprint text,
  prompt_trace_json json,
  error text,
  created_at text not null,
  updated_at text not null
);

create index if not exists idx_generated_media_assets_owner_kind_status_updated_at
on generated_media_assets (owner_scope, owner_id, asset_kind, generation_status, updated_at);

create index if not exists idx_generated_media_assets_world_kind_status_updated_at
on generated_media_assets (world_version_id, asset_kind, generation_status, updated_at);

create index if not exists idx_generated_media_assets_owner_fingerprint
on generated_media_assets (owner_scope, owner_id, asset_kind, source_fingerprint);
