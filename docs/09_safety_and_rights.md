# 安全与权利边界（工程实现视角）

## 内容来源分桶
- public_domain
- original
- licensed
- unlicensed_fanfic (不得进入商业化池)

## 工程层要支持的检查
- source_type
- monetization_allowed
- rating ceiling
- forbidden topics / motifs
- shareability flags

## 分级不是一句话
系统需要区分：
- free tier
- paid tier
- creator tier

并在 event atom 与 renderer 两层都做检查。

## 分享内容
对外分享内容建议保留：
- ai_generated_label
- world_id
- route_id
- rating
- source_type
