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
