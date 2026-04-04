create table if not exists author_thread_watchers (
  watcher_record_id text primary key,
  thread_id text not null references author_comment_threads(thread_id),
  watcher_id text not null,
  added_by text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_author_thread_watchers_thread_id on author_thread_watchers(thread_id);
create index if not exists idx_author_thread_watchers_watcher_id on author_thread_watchers(watcher_id);
