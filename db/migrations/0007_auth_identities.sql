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
