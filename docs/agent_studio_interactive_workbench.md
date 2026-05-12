# Agent Studio Interactive Workbench

Agent Studio is the default Author-side creation surface for local co-directed fiction work. It keeps the existing Author advanced tools available, but moves the first-run path into a product workflow:

1. Set story goal, genre, length, reader experience, remix permission, and cover intent.
2. Create a local author work and generate the first chapter.
3. Read chapters in the Studio reader.
4. Choose a route card or write a director intent.
5. Create branches, switch the export main route, validate, preview, and export `.nosbook`.

## Boundaries

- The generation kernel remains unchanged.
- Choice semantics are generic product tags layered over existing choices.
- Reader-visible Studio copy uses product language. Internal issue codes remain in Ops/Eval diagnostics.
- Branches use AuthorWork branch family APIs and are displayed as route names such as `主线` and `路线 A：...`.

## Layout Contract

- Studio mode compacts the shared Author chrome so the workbench appears close to the first viewport and does not compete with the chapter.
- Wide desktop uses a reading-first two-column workbench:沉浸阅读器 / 导演台, with作品导航和路线地图 as a compact strip below the reader.
- On wide desktop, the director panel stays sticky while the user scrolls through choices and the route strip.
- Medium desktop stacks as reader, director, then route/navigation so the chapter remains the primary surface.
- Mobile stacks as reader, director, then route/navigation so the chapter remains the primary surface.
- The chapter body scrolls inside the reading page, and mobile choice cards use a bounded scroll area so director controls remain reachable.

## Interfaces

- Existing `reader_view.choices: string[]` remains compatible.
- Optional `reader_view.choice_impacts[]` adds risk, emotion, pacing, relationship, mystery, expected effect, and director-intent prefill.
- Route selections are persisted through `route_choices.payload_json`.
- Author works export via:

```http
GET /v1/author/works/{work_id}/export?format=nosbook&route=active
```

The response is a JSON envelope with `schema_version: nosbook/v1` and content type `application/vnd.narrativeos.nosbook+json`.

## Export Envelope

The `.nosbook` export contains:

- `work`
- `export_route`
- `chapters`
- `branch_map`
- `choice_history`
- `quality_summary`
- `cover`

`route=active` exports only the active/main route chapters by default.

## Codex Upload Workflow

Agent Studio now supports an agent-operated platform upload loop without adding a Studio UI upload button. The default upload result is an Author private draft; it does not submit for review or publish.

Platform API:

```http
POST /v1/author/nosbooks/import
Authorization: Bearer <token>
Content-Type: application/vnd.narrativeos.nosbook+json
```

The request body is the existing `.nosbook` JSON envelope. The importer requires `schema_version: nosbook/v1` plus `work`, `chapters`, `branch_map`, `choice_history`, and `quality_summary`. Success returns `schema_version: nosbook_import_result/v1`, `work_id`, `status: private_draft`, chapter count, warnings, and `world_version_link_status`.

Codex-style local upload:

```bash
export NARRATIVEOS_PLATFORM_URL="https://your-platform.example"
export NARRATIVEOS_PLATFORM_TOKEN="<author bearer token>"
python scripts/upload_nosbook.py --file path/to/work.nosbook
```

One-command local Studio bridge:

```bash
export NARRATIVEOS_LOCAL_STUDIO_URL="http://127.0.0.1:8000"
export NARRATIVEOS_LOCAL_STUDIO_TOKEN="<local author bearer token>"
export NARRATIVEOS_PLATFORM_URL="https://your-platform.example"
export NARRATIVEOS_PLATFORM_TOKEN="<platform author bearer token>"
python scripts/upload_nosbook.py --local-work-id work_xxx
```

The CLI prints machine-readable JSON and exits non-zero on failure. It does not print or persist the token. If the source `world_version_id` exists on the platform, the import result is `world_version_link_status: linked`; otherwise it is `source_only`, which is still readable as a private draft but may not support platform continuation until the source world is installed.

Recommended agent flow:

1. Start the local Studio with `bash scripts/run_agent_studio_local.sh`.
2. Create or continue the work locally.
3. Set `NARRATIVEOS_LOCAL_STUDIO_TOKEN`, `NARRATIVEOS_PLATFORM_URL`, and `NARRATIVEOS_PLATFORM_TOKEN`.
4. Run `python scripts/upload_nosbook.py --local-work-id work_xxx`.
5. Optionally keep using `--file path/to/work.nosbook` when the agent already has an exported file.
6. Use the returned `work_id` to verify the imported private draft with `GET /v1/author/works/{work_id}`.

## Local Launch

Use the Studio-specific local launcher for author creation sessions:

```bash
bash scripts/run_agent_studio_local.sh
```

The launcher reuses `scripts/run_backend_local.sh`, waits for `/health`, and opens:

```text
http://127.0.0.1:8000/app?product=author&workspace=studio&debug=1
```

Set `AGENT_STUDIO_OPEN_BROWSER=0` to keep the browser closed while still starting the local backend.

## Browser Smoke

Run the focused rendered smoke when changing Studio startup, generation, branch, or export behavior:

```bash
CI_HEADLESS=1 bash scripts/run_agent_studio_smoke.sh
```

The smoke drives the real Author-side UI through startup, first chapter generation, director continuation, branch creation, and `.nosbook` export. It writes:

- `artifacts/agent_studio_smoke_result.json`
- `artifacts/agent_studio_smoke_failure_snapshot.json`
- `artifacts/agent_studio_smoke_failure.png`
- `artifacts/agent_studio_smoke_desktop.png`
- `artifacts/agent_studio_smoke_mobile.png`
- `artifacts/agent_studio_smoke_visual_review.md`

The result must report `schema_version: agent_studio_smoke/v1`, exported `nosbook/v1`, branch map count, choice history count, quality summary keys, screenshot file paths, mobile overflow width, desktop sticky director status, mobile choice bounded-scroll status, visual review checklist counters, generation wait copy, and `visible_q_code: false`.

Rendered QA now captures the Studio workbench at `1440x1000` after the first chapter and at `390x844` after branch/export. The verifier checks that the reader body, director panel, branch map, and quality labels are visible, that the desktop director panel remains sticky after scrolling to choices/routes, that mobile choice cards stay in a bounded scroll area, that mobile has no horizontal overflow, and that visible Studio text does not expose internal quality codes.

`agent_studio_smoke_visual_review.md` is a human-triage aid for the generated screenshots. Objective rows mirror smoke assertions and subjective rows are marked `manual_review`, so reviewers can inspect balance, clipping, reachability, and reader focus without adding fragile automated gates.

When a PR changes Agent Studio layout CSS, especially `.agent-studio-*` selectors in `src/narrativeos/web/styles.css`, reviewers must paste the two `manual_review` rows into a PR comment after inspecting the screenshots:

```md
| desktop | Three-column workbench review | manual_review | artifacts/agent_studio_smoke_desktop.png | accepted |
| mobile | Stacked workbench review | manual_review | artifacts/agent_studio_smoke_mobile.png | accepted |
```

Use `needs follow-up` instead of `accepted` for any visible overlap, clipped text, unreachable controls, or loss of reader prominence. This is a human review convention, not an automated image comparison gate.

The two required row identifiers are:

- `desktop / Three-column workbench review / manual_review`
- `mobile / Stacked workbench review / manual_review`

Expected long-generation product copy:

- startup: `第一章生成中` / `正在建立作品设定、人物冲突和章节正文，可能需要一两分钟。`
- continuation: `续写中` / `正在沿导演意图推进下一章，完成后会自动跳到新章节。`
- branch: `新路线创建中` / `正在从当前章节保存分支。`
