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
