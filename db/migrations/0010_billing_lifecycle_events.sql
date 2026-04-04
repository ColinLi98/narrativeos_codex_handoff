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
