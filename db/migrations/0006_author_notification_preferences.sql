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
