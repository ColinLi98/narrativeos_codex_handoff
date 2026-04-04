create table if not exists author_draft_watchers (
  watcher_record_id text primary key,
  world_version_id text not null references world_versions(world_version_id),
  watcher_id text not null,
  added_by text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_author_draft_watchers_world_version_id on author_draft_watchers(world_version_id);
create index if not exists idx_author_draft_watchers_watcher_id on author_draft_watchers(watcher_id);
