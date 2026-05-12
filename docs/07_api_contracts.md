# API 合约

## 1. 创建世界观
`POST /v1/worlds`

输入：
- world metadata
- world bible
- creator controls
- event atoms

输出：
- world_id

## 2. 创建会话
`POST /v1/sessions`

输入：
- world_id
- initial_state
- player profile

输出：
- session_id
- current_state

## 3. 推进一步
`POST /v1/sessions/{session_id}/step`

输入：
- player_input
- optional overrides
- optional candidate events

输出：
- chosen_event
- updated_state
- scored_candidates
- critic_trace
- rendered_scene

## 4. route 预览
`POST /v1/routes/preview`

输入：
- state
- depth
- beam_width

输出：
- top_routes
- score_breakdown
- promise outlook

## 5. 回放
`GET /v1/sessions/{session_id}/replay`

输出：
- full timeline
- event trace
- state snapshots

## 6. 评测
`POST /v1/evaluations/run`

输入：
- world_id
- test pack

输出：
- consistency score
- diversity score
- fidelity score
- unresolved promises

## 7. Author `.nosbook` 平台导入
`POST /v1/author/nosbooks/import`

输入：
- Header 使用 `Authorization: Bearer <token>`
- Body 是 `.nosbook` JSON envelope
- `schema_version` 必须是 `nosbook/v1`
- 必填：`work / chapters / branch_map / choice_history / quality_summary`

输出：
- `schema_version = nosbook_import_result/v1`
- `import_id`
- `work_id`
- `status = private_draft`
- `chapter_count`
- `warnings`
- `world_version_link_status = linked | source_only`

规则：
- 无 author token 返回 `401`，`detail.code = nosbook_import_auth_required`
- 导入只创建作者私有草稿，不进入审核或公开发布
- active route chapters 写入 `author_work_chapters`
- `branch_map / choice_history / quality_summary / cover` 作为导入元数据保存
- 源 `world_version_id` 存在时返回 `linked`；不存在时返回 `source_only`，仍允许读取预览但平台续写能力受限
- 同一账号重复上传同一 checksum 必须返回已有私有草稿，避免 agent 重试生成重复作品
