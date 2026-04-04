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
