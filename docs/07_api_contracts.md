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
