alter table if exists author_works add column if not exists branch_id text;
alter table if exists author_works add column if not exists root_work_id text;
alter table if exists author_works add column if not exists parent_work_id text;
alter table if exists author_works add column if not exists branch_name text;
alter table if exists author_works add column if not exists branch_kind text;
alter table if exists author_works add column if not exists branch_origin_label text;
alter table if exists author_works add column if not exists fork_after_chapter_index integer default 0;
alter table if exists author_works add column if not exists is_active_line integer default 0;

update author_works
set root_work_id = work_id
where root_work_id is null;

update author_works
set branch_id = work_id
where branch_id is null;

update author_works
set branch_name = '主线'
where branch_name is null;

update author_works
set branch_kind = 'mainline'
where branch_kind is null;

update author_works
set fork_after_chapter_index = 0
where fork_after_chapter_index is null;

update author_works
set is_active_line = 1
where is_active_line is null;

create index if not exists idx_author_works_root_work_updated_at on author_works(root_work_id, updated_at);
