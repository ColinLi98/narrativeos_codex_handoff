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
