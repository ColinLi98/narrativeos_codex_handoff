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
