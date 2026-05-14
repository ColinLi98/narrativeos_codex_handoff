// Ops render sections extracted from app.js to keep render/update responsibilities isolated.

var OpsRenderRuntime = (() => {
  const dom = OpsDOM;
  const { api, clearNode, createListCard, formatTimestamp, formatPercent, parseMaybeJson, localizeDisplayText } = UIShared;
  const { gatingStatusLabel } = ReaderAccessors;
  const {
    reviewStatusLabel,
    opsStatusLabel,
    opsProviderLabel,
    opsTrackLabel,
    opsScopeLabel,
    opsActionModeLabel,
    opsIssueCodeLabel,
    opsIssueCodeList,
    opsWorldLabel,
    opsWorldList,
    opsTrackList,
    opsPreferredCandidateLabel,
    opsBooleanLabel,
    opsNumericValue,
    opsLatencyValue,
    opsCostValue,
    opsRolloutSummary,
    opsTargetLabel,
    opsFieldLine,
    opsPairsLine,
    summarizeChecklistEvidence,
    applySupportPrefill,
    applyGovernanceCasePrefill,
    openLearnedWorldDetail,
    openLearnedIssueDetail,
    selectReviewBacklogItem
  } = OpsShared;
  const {
    OPS_REFRESH_SCOPE_ALL,
    normalizeOpsRefreshScopes,
    syncOpsNavigationContext,
    refreshOpsReleaseFlow,
    refreshOpsReleaseWorkspace,
    refreshOpsSurface
  } = OpsRefreshRuntime;

function summarizeReviewTimelineEntry(item) {
  const note = item.note_payload || {};
  const targetVersion = item.target_world_version_id || item.published_world_version_id || item.world_version_id || item.asset_id || "-";
  const packSummary = (item.top_failing_pack_ids || []).join(" / ") || "-";
  const gateSummary = (item.publish_gate_errors || []).join(" / ") || "-";
  const riskSummary = (item.risk_summary?.publish_gate_errors || []).join(" / ") || "-";
  return (
    `${opsFieldLine("状态", reviewStatusLabel(item.status))} · ${targetVersion}\n` +
    `${formatTimestamp(item.updated_at)} · ${opsFieldLine("审阅人", item.reviewer_id || "-")} · ${opsFieldLine("风险等级", item.risk_rating || "-")}\n` +
    `${opsFieldLine("最近判断", opsStatusLabel(item.latest_decision || "-"))} · ${opsFieldLine("跨包通过率", item.cross_pack_pass_rate !== undefined && item.cross_pack_pass_rate !== null ? Number(item.cross_pack_pass_rate).toFixed(3) : "-")}\n` +
    `${opsFieldLine("薄弱世界", (item.top_failing_pack_ids || []).map((worldId) => opsWorldLabel(worldId)).join(" / ") || "-")}\n` +
    `${opsFieldLine("发布门禁", gateSummary)}\n` +
    `${opsFieldLine("回滚目标", item.target_world_version_id || "-")} · ${opsFieldLine("上一版本", item.previous_world_version_id || "-")}\n` +
    `${opsFieldLine("访问原因", item.entitlement_reason || note.entitlement_reason || "-")} · ${opsFieldLine("风险门禁", riskSummary)}`
  );
}

function summarizeReviewHubItem(item) {
  if (item.source_type === "quality_review_case") {
    const traceSummary = item.source_payload?.trace_summary || {};
    return (
      `${opsFieldLine("队列", item.queue || "-")} · ${opsFieldLine("状态", opsStatusLabel(item.status || "-"))} · ${opsFieldLine("严重度", item.severity || "-")}\n` +
      `${opsFieldLine("负责人", item.owner_id || "-")} · ${opsFieldLine("Surface", traceSummary.source_surface || "-")} · ${opsFieldLine("Trace", traceSummary.trace_id || "-")}\n` +
      `${opsFieldLine("账户", item.account_id || "-")} · ${opsFieldLine("世界", opsWorldLabel(item.world_id || "-"))}\n` +
      `${opsFieldLine("原因", opsIssueCodeList(traceSummary.reason_codes || []))}\n` +
      `${opsFieldLine("建议动作", item.recommended_action || "-")}`
    );
  }
  return (
    `${opsFieldLine("队列", item.queue || "-")} · ${opsFieldLine("状态", opsStatusLabel(item.status || "-"))} · ${opsFieldLine("严重度", item.severity || "-")}\n` +
    `${opsFieldLine("负责人", item.owner_id || "-")} · ${opsFieldLine("审阅人", item.reviewer_id || "-")} · ${opsFieldLine("SLA", item.sla_bucket || "-")}\n` +
    `${opsFieldLine("账户", item.account_id || "-")} · ${opsFieldLine("世界", opsWorldLabel(item.world_id || "-"))}\n` +
    `${item.summary || "-"}\n` +
    `${opsFieldLine("建议动作", item.recommended_action || "-")}`
  );
}

function summarizeReviewHubSummary(summary) {
  return opsSections(
    opsSection("总体", [
      opsFieldLine("总数", summary.total_count ?? 0),
      opsFieldLine("待处理", summary.actionable_count ?? 0),
      opsFieldLine("未分派", summary.unassigned_count ?? 0),
      opsFieldLine("阻塞", summary.blocked_count ?? 0),
      opsFieldLine("即将超时", summary.due_soon_count ?? 0),
      opsFieldLine("已超时", summary.overdue_count ?? 0),
    ]),
    opsSection("队列分布", [
      opsPairsLine("队列", summary.queue_counts || {}),
      opsPairsLine("状态", summary.status_counts || {}, opsStatusLabel),
      opsPairsLine("严重度", summary.severity_counts || {}),
    ])
  );
}

function formatSignedDelta(value) {
  const numeric = Number(value || 0);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(3)}`;
}

function summarizeRollbackEntry(item) {
  return (
    `${reviewStatusLabel(item.status)} · ${formatTimestamp(item.updated_at)}\n` +
    `${opsFieldLine("回滚目标", item.rollback_target_world_version_id || "-")} · ${opsFieldLine("上一版本", item.rollback_previous_world_version_id || "-")}\n` +
    `${opsFieldLine("审阅人", item.reviewer_id || "-")} · ${opsFieldLine("原因", item.rollback_reason || "-")}\n` +
    `${opsFieldLine("门禁", ((item.rollback_gate_errors || []).join(" / ")) || "-")}`
  );
}

function summarizeQualityTrendEntry(item) {
  const delta = item.delta_vs_previous || {};
  return (
    `${item.world_version_id}\n` +
    `${opsFieldLine("状态", opsStatusLabel(item.status))} · ${opsFieldLine("最近判断", opsStatusLabel(item.latest_decision || "-"))} · ${opsFieldLine("更新时间", formatTimestamp(item.updated_at))}\n` +
    `${opsFieldLine("通过率", `${formatPercent(item.pass_rate)} (${formatSignedDelta(delta.pass_rate)})`)} · ${opsFieldLine("重写率", `${formatPercent(item.rewrite_rate)} (${formatSignedDelta(delta.rewrite_rate)})`)}\n` +
    `${opsFieldLine("阻塞率", `${formatPercent(item.block_rate)} (${formatSignedDelta(delta.block_rate)})`)} · ${opsFieldLine("跨包通过率", `${Number(item.cross_pack_pass_rate || 0).toFixed(3)} (${formatSignedDelta(delta.cross_pack_pass_rate)})`)}\n` +
    `${opsFieldLine("是否回退", opsBooleanLabel(item.regression_detected))} · ${opsFieldLine("门禁", (item.publish_gate_errors || []).join(" / ") || "-")}\n` +
    `${opsFieldLine("薄弱世界", (item.top_failing_pack_ids || []).map((worldId) => opsWorldLabel(worldId)).join(" / ") || "-")}`
  );
}

function summarizeReleaseBlocker(item) {
  return (
    `${item.label || item.key}\n` +
    `${opsFieldLine("原因", item.reason || "-")} · ${opsFieldLine("负责人", item.owner || "-")} · ${opsFieldLine("严重度", item.severity || "-")}\n` +
    `${opsFieldLine("下一步", item.next_action || "-")} · ${opsFieldLine("证据", summarizeChecklistEvidence(item.evidence))}`
  );
}

function opsSection(title, lines = []) {
  const visibleLines = (lines || []).filter((item) => String(item || "").trim());
  if (!visibleLines.length) return "";
  return `${title}：\n${visibleLines.join("\n")}`;
}

function opsSections(...sections) {
  return sections.filter((item) => String(item || "").trim()).join("\n\n");
}

function opsList(items, formatter = (item) => item, empty = "-") {
  if (!Array.isArray(items) || !items.length) return empty;
  return items.map((item, index) => formatter(item, index)).join("\n");
}

function opsParagraphList(items, formatter = (item) => item, empty = "-") {
  if (!Array.isArray(items) || !items.length) return empty;
  return items.map((item, index) => formatter(item, index)).join("\n\n");
}

function renderLocalizedCardHtml(title, score, body, footer = "") {
  return `
    <div class="list-card-head">
      <h3>${localizeDisplayText(title)}</h3>
      <span class="list-card-score">${localizeDisplayText(score || "")}</span>
    </div>
    <p class="list-card-body">${localizeDisplayText(body || "")}</p>
    ${footer}
  `;
}

function opsStatusPairList(pairs) {
  return opsPairsLine("状态分布", pairs || {}, opsStatusLabel);
}

function opsProviderPairList(label, pairs) {
  return opsPairsLine(label, pairs || {}, opsProviderLabel);
}

function opsStageMetricParagraph(track, item) {
  return opsSections(
    opsSection(`${opsTrackLabel(track)} · ${opsStatusLabel(item.rollout_status || "-")}`, [
      opsFieldLine("回执数", item.receipt_count ?? 0),
      opsFieldLine("事故率", opsNumericValue(item.incident_rate, 3)),
      opsFieldLine("回退率", opsNumericValue(item.fallback_rate, 3)),
      opsFieldLine("后端错误率", opsNumericValue(item.backend_error_rate, 3)),
      opsFieldLine("总成本", opsCostValue(item.total_estimated_cost, 3)),
      opsFieldLine("平均成本", opsCostValue(item.avg_estimated_cost, 3)),
      opsFieldLine("运行时延迟", opsLatencyValue(item.runtime_latency?.avg_latency_ms)),
      opsFieldLine("运行时 P95", opsLatencyValue(item.runtime_latency?.p95_latency_ms)),
      opsFieldLine("轨道延迟", opsLatencyValue(item.track_latency?.avg_latency_ms)),
      opsFieldLine("命中分桶次数", item.canary_match_count ?? 0),
    ])
  );
}

function opsProviderMetricParagraph(item) {
  return opsSections(
    opsSection(opsProviderLabel(item.provider || "-"), [
      opsFieldLine("回执数", item.receipt_count ?? 0),
      opsFieldLine("事故数", item.incident_count ?? 0),
      opsFieldLine("候选选中", item.selected_as_candidate_count ?? 0),
      opsFieldLine("渲染选中", item.selected_as_renderer_count ?? 0),
      opsFieldLine("回退率", opsNumericValue(item.fallback_rate, 3)),
      opsFieldLine("预算拦截率", opsNumericValue(item.budget_block_rate, 3)),
      opsFieldLine("后端错误率", opsNumericValue(item.backend_error_rate, 3)),
      opsFieldLine("缓存命中率", opsNumericValue(item.cache_hit_rate, 3)),
      opsFieldLine("运行时延迟", opsLatencyValue(item.avg_runtime_latency_ms)),
      opsFieldLine("运行时 P95", opsLatencyValue(item.p95_runtime_latency_ms)),
      opsFieldLine("候选延迟", opsLatencyValue(item.avg_candidate_latency_ms)),
      opsFieldLine("渲染延迟", opsLatencyValue(item.avg_renderer_latency_ms)),
      opsFieldLine("总成本", opsCostValue(item.total_estimated_cost, 3)),
      opsFieldLine("平均成本", opsCostValue(item.avg_estimated_cost, 3)),
      opsFieldLine("候选请求成本", opsCostValue(item.candidate_estimated_request_cost, 4)),
      opsFieldLine("渲染请求成本", opsCostValue(item.renderer_estimated_request_cost, 4)),
      opsFieldLine("平均输出字符", opsNumericValue(item.avg_output_chars, 1)),
    ])
  );
}

function opsCostTrendParagraph(item) {
  return opsSections(
    opsSection(item.bucket || "-", [
      opsFieldLine("总成本", opsCostValue(item.total_estimated_cost, 3)),
      opsFieldLine("回执数", item.receipt_count ?? 0),
      opsFieldLine("事故数", item.incident_count ?? 0),
    ])
  );
}

function opsLatencyTrendParagraph(item) {
  return opsSections(
    opsSection(item.bucket || "-", [
      opsFieldLine("运行时延迟", opsLatencyValue(item.runtime?.avg_latency_ms)),
      opsFieldLine("候选延迟", opsLatencyValue(item.candidate?.avg_latency_ms)),
      opsFieldLine("渲染延迟", opsLatencyValue(item.renderer?.avg_latency_ms)),
    ])
  );
}

function opsPromotionBody(promotion, metricLabel, metricValue) {
  return opsSections(
    opsSection("总体判断", [
      opsFieldLine("轨道", opsTrackLabel(promotion.track || "-")),
      opsFieldLine("范围", opsScopeLabel(promotion.scope || "-")),
      opsFieldLine("建议结论", opsStatusLabel(promotion.recommendation_status || promotion.status || "-")),
      opsFieldLine("审批状态", opsStatusLabel(promotion.approval_status || "pending")),
      opsFieldLine("需要重新确认", opsBooleanLabel(promotion.reconfirm_required)),
      opsFieldLine("下一步", promotion.recommended_action || "-"),
    ]),
    opsSection("最近审批", [
      opsFieldLine("状态", opsStatusLabel(promotion.latest_approval_record?.status || "-")),
      opsFieldLine("审阅人", promotion.latest_approval_record?.reviewer_id || "-"),
      opsFieldLine("更新时间", promotion.latest_approval_record?.updated_at || "-"),
      opsFieldLine("原因", promotion.latest_approval_record?.reason || "-"),
    ]),
    opsSection("阻塞与提示", [
      opsFieldLine("阻塞项", (promotion.blockers || []).join(" / ") || "-"),
      opsFieldLine("提示项", (promotion.advisories || []).join(" / ") || "-"),
    ]),
    opsSection("证据包", [
      opsFieldLine(metricLabel, metricValue),
      opsFieldLine("训练/验证/测试", `${promotion.evidence?.train_count ?? 0} / ${promotion.evidence?.val_count ?? 0} / ${promotion.evidence?.test_count ?? 0}`),
      opsFieldLine("偏好候选", opsPreferredCandidateLabel(promotion.evidence?.preferred_shadow_candidate)),
      opsFieldLine("审阅待补样", promotion.evidence?.review_backlog_count ?? 0),
      opsFieldLine("配对覆盖待补样", promotion.evidence?.pair_backlog_count ?? 0),
      opsFieldLine("世界分歧数", promotion.evidence?.disagreement_world_count ?? 0),
      opsFieldLine("问题分歧数", promotion.evidence?.disagreement_issue_count ?? 0),
    ]),
    opsSection("检查清单", [
      opsList(promotion.checklist || [], (item) => `${item.ok ? "已通过" : "未通过"} · ${item.key} · ${item.reason || "-"}`),
    ])
  );
}


function renderOpsNavigationSection() {
    clearNode(dom.opsNavigationSummary);
    clearNode(dom.opsNavigationTargets);
    clearNode(dom.opsNavigationActions);
    if (!opsState.opsNavigationModel) {
      clearNode(dom.opsNavigationSummary, "这里会显示统一上下文、升级状态与推荐路径。");
      clearNode(dom.opsNavigationTargets, "这里会显示关联对象与导航入口。");
      clearNode(dom.opsNavigationActions, "这里会显示跨面板后续动作。");
    } else {
      const model = opsState.opsNavigationModel;
      const context = model.active_context || {};
      const escalation = model.escalation_summary || {};
      const warnings = model.context_warnings || [];
      const staleRefs = Object.values(model.linked_context?.stale_refs || {});
      dom.opsNavigationSummary.appendChild(
        createListCard({
          title: "运营导航模型",
          score: opsStatusLabel(escalation.status || "-"),
          body:
            `${opsFieldLine("账户", context.account_id || "-")} · ${opsFieldLine("世界", opsWorldLabel(context.world_id || "-"))} · ${opsFieldLine("世界版本", context.world_version_id || "-")}\n` +
            `${opsFieldLine("个案", context.case_id || "-")} · ${opsFieldLine("告警", context.alert_id || "-")}\n` +
            `${opsFieldLine("推荐目标", escalation.recommended_target || "-")}\n` +
            `${opsFieldLine("推荐原因", escalation.recommended_reason || "-")}\n` +
            `${opsFieldLine("升级路径", (escalation.escalation_path || []).join(" → ") || "-")}\n` +
            `${opsFieldLine("上下文处理", (model.context_resolution || []).join(" / ") || "-")}${
              warnings.length
                ? `\n${opsFieldLine("告警", warnings.join(" / "))}`
                : ""
            }${
              staleRefs.length
                ? `\n${opsFieldLine("失效引用", staleRefs.map((item) => `${item.ref_id} · ${opsStatusLabel(item.status)}`).join(" / "))}`
                : ""
            }`
        })
      );
      if (!(model.navigation_targets || []).length) {
        clearNode(dom.opsNavigationTargets, "这里会显示关联对象与导航入口。");
      } else {
        const targetCard = createListCard({
          title: "关联目标",
          score: `${(model.navigation_targets || []).length} 个目标`,
          body: (model.navigation_targets || []).map((item) => `${item.label} · ${item.kind}${item.active ? " · 当前目标" : ""}`).join("\n"),
        });
        const actions = document.createElement("div");
        actions.className = "composer-actions";
        (model.navigation_targets || []).forEach((item) => {
          const button = document.createElement("button");
          button.className = item.target_id === escalation.recommended_target ? "primary-action" : "ghost-action";
          button.textContent = item.label;
          button.addEventListener("click", async () => {
            try {
              await OpsActionsRuntime.runOpsNavigationTarget(item);
            } catch (error) {
              alert(`打开 navigation target 失败：${error.message}`);
            }
          });
          actions.appendChild(button);
        });
        dom.opsNavigationTargets.appendChild(targetCard);
        dom.opsNavigationTargets.appendChild(actions);
      }
      if (!(model.follow_up_actions || []).length) {
        clearNode(dom.opsNavigationActions, "这里会显示跨面板后续动作。");
      } else {
        const followUpCard = createListCard({
          title: "后续动作",
          score: `${(model.follow_up_actions || []).length} 个动作`,
          body: (model.follow_up_actions || []).map((item) => `${item.label} · ${item.source_surface || "-"}\n${item.reason || "-"}`).join("\n\n"),
        });
        const actions = document.createElement("div");
        actions.className = "composer-actions";
        (model.follow_up_actions || []).forEach((item) => {
          const button = document.createElement("button");
          button.className = item.mode === "execute" ? "primary-action" : "ghost-action";
          button.textContent = item.label;
          button.addEventListener("click", async () => {
            try {
              await OpsActionsRuntime.runOpsNavigationFollowUpAction(item);
            } catch (error) {
              alert(`执行 follow-up action 失败：${error.message}`);
            }
          });
          actions.appendChild(button);
        });
        dom.opsNavigationActions.appendChild(followUpCard);
        dom.opsNavigationActions.appendChild(actions);
      }
    }
}

function renderOpsReviewReleaseSection() {
  clearNode(dom.opsReviewQueue);
  const reviewHub = opsState.opsReviewHub || {};
  const reviewItems = reviewHub.items || [];
  const triage = reviewHub.triage || {};
  if (!reviewItems.length) {
    clearNode(dom.opsReviewQueue, "暂时没有统一审阅项。");
  } else {
    dom.opsReviewQueue.appendChild(
      createListCard({
        title: "统一审阅台",
        score: `${reviewItems.length} items`,
        body: summarizeReviewHubSummary(reviewHub.summary || {}),
      })
    );
    reviewItems.forEach((item) => {
      const notePayload = parseMaybeJson(item.notes);
      const card = document.createElement("article");
      card.className = "list-card";
      if (item.review_item_id === opsState.opsSelectedReviewItemId) {
        card.classList.add("is-active");
      }
      const body = summarizeReviewHubItem(item);
      card.innerHTML = renderLocalizedCardHtml(
        item.headline || item.review_item_id,
        `${item.queue || "-"} · ${item.status || "-"}`,
        body,
        `<div class="composer-actions">
          <button class="ghost-action review-open">查看详情</button>
          <button class="ghost-action review-assign">分给我</button>
          <button class="ghost-action review-in-review">进入审阅</button>
          <button class="primary-action review-primary">${item.queue === "content_release" ? "批准" : "解决"}</button>
        </div>`
      );
      card.querySelector(".review-open").addEventListener("click", async () => {
        await OpsActionsRuntime.loadSelectedOpsReviewItem(item.review_item_id);
        OpsRenderRuntime.renderOpsSurface();
      });
      card.querySelector(".review-assign").addEventListener("click", async () => {
        await OpsActionsRuntime.runOpsReviewHubAction(item, "assign_to_me");
      });
      card.querySelector(".review-in-review").addEventListener("click", async () => {
        await OpsActionsRuntime.runOpsReviewHubAction(item, "mark_in_review");
      });
      card.querySelector(".review-primary").addEventListener("click", async () => {
        await OpsActionsRuntime.runOpsReviewHubAction(item, item.queue === "content_release" ? "approve" : "resolve");
      });
      dom.opsReviewQueue.appendChild(card);
    });
  }
  clearNode(dom.opsWorldStatus);
  clearNode(dom.opsReleaseWorkspaceSummary);
  clearNode(dom.opsReleaseWorkspaceActions);
  clearNode(dom.opsReleaseWorkspaceTimeline);
  clearNode(dom.opsReleaseWorkspaceDetails);
  if (!opsState.opsWorldStatuses.length) {
    clearNode(dom.opsWorldStatus, "选择或刷新后，这里会显示当前审阅项详情。");
    clearNode(dom.opsReleaseWorkspaceSummary, "这里会显示当前世界的发布摘要。");
    clearNode(dom.opsReleaseWorkspaceActions, "这里会显示当前世界的快捷动作。");
    clearNode(dom.opsReleaseWorkspaceTimeline, "这里会显示当前世界的运营时间线。");
    clearNode(dom.opsReleaseWorkspaceDetails, "这里会显示发布阻塞项、版本矩阵与回滚工作台。");
  } else {
    const selectedReviewItem = opsState.opsSelectedReviewItemDetail?.review_item || null;
    if (selectedReviewItem) {
      const selectedWork = opsState.opsSelectedReviewWorkDetail?.work || null;
      const selectedQualityPayload =
        selectedReviewItem.source_type === "quality_review_case"
          ? (opsState.opsSelectedReviewItemDetail?.review_item?.source_payload || {})
          : {};
      const selectedQualityCase = selectedQualityPayload.review_case || {};
      const selectedQualityEvent = selectedQualityPayload.quality_event || {};
      const selectedQualityScore = selectedQualityPayload.content_quality_score || {};
      const selectedQualityTrace = selectedQualityPayload.trace_summary || {};
      const selectedQualityTraceDetail = opsState.opsQualityTraceDetail || null;
      const selectedChapter = selectedWork?.chapters?.length ? selectedWork.chapters[selectedWork.chapters.length - 1] : null;
      const workDiagnostics = selectedWork?.diagnostics_summary || selectedWork?.diagnostics_summary_json || {};
      const workEvaluation = workDiagnostics.evaluation_summary || {};
      const selectedChapterDiagnostics = selectedChapter?.latest_diagnostic_summary || {};
      const selectedChapterIssueCodes =
        selectedChapterDiagnostics.issue_codes ||
        (selectedChapter?.diagnostic_summary_json?.issues || [])
          .map((item) => item?.issue_code)
          .filter(Boolean);
      const detailCard = createListCard({
        title: selectedReviewItem.headline || selectedReviewItem.review_item_id,
        score: `${selectedReviewItem.queue || "-"} · ${opsStatusLabel(selectedReviewItem.status || "-")}`,
        body: opsSections(
          opsSection("当前审阅项", [
            opsFieldLine("来源", `${selectedReviewItem.source_type || "-"} / ${selectedReviewItem.source_id || "-"}`),
            opsFieldLine("负责人", selectedReviewItem.owner_id || "-"),
            opsFieldLine("审阅人", selectedReviewItem.reviewer_id || "-"),
            opsFieldLine("严重度", selectedReviewItem.severity || "-"),
            opsFieldLine("SLA", selectedReviewItem.sla_bucket || "-"),
            opsFieldLine("建议动作", selectedReviewItem.recommended_action || "-"),
          ]),
          opsSection("上下文", [
            opsFieldLine("账户", selectedReviewItem.account_id || "-"),
            opsFieldLine("世界", opsWorldLabel(selectedReviewItem.world_id || "-")),
            opsFieldLine("世界版本", selectedReviewItem.world_version_id || "-"),
            opsFieldLine("关联对象", (selectedReviewItem.linked_entities || []).map((entity) => `${entity.kind}:${entity.id}`).join(" / ") || "-"),
          ]),
          opsSection("摘要", [
            selectedReviewItem.summary || "-",
          ]),
          selectedReviewItem.source_type === "quality_review_case" ? opsSection("质量案例", [
            opsFieldLine("Case 状态", opsStatusLabel(selectedQualityCase.status || "-")),
            opsFieldLine("Owner", selectedQualityCase.owner_id || "-"),
            opsFieldLine("Surface", selectedQualityEvent.source_surface || selectedQualityCase.source_surface || "-"),
            opsFieldLine("Trace", selectedQualityTrace.trace_id || selectedQualityEvent.trace_id || "-"),
            opsFieldLine("原因", opsIssueCodeList(selectedQualityCase.reason_codes || selectedQualityScore.reason_codes || [])),
            opsFieldLine("总分", selectedQualityScore.overall_score !== undefined && selectedQualityScore.overall_score !== null ? Number(selectedQualityScore.overall_score).toFixed(2) : "-"),
            opsFieldLine("Veto", selectedQualityScore.veto === undefined ? "-" : opsBooleanLabel(selectedQualityScore.veto)),
            opsFieldLine("证据", (selectedQualityCase.evidence_refs || []).map((item) => `${item.kind || "evidence"}:${item.ref_id || "-"}`).join(" / ") || "-"),
            opsFieldLine("来源引用", Object.entries(selectedQualityCase.source_ref || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"),
          ]) : "",
          selectedReviewItem.source_type === "quality_review_case" && selectedQualityTraceDetail ? opsSection("Trace Drilldown", [
            opsFieldLine("Trace", selectedQualityTraceDetail.trace_id || "-"),
            opsFieldLine("事件状态", opsStatusLabel(selectedQualityTraceDetail.event?.status || "-")),
            opsFieldLine("入口", selectedQualityTraceDetail.event?.source_surface || "-"),
            opsFieldLine("账户", selectedQualityTraceDetail.linked_context?.account_id || "-"),
            opsFieldLine("世界版本", selectedQualityTraceDetail.linked_context?.world_version_id || "-"),
            opsFieldLine("反馈数", selectedQualityTraceDetail.feedback_summary?.feedback_item_count ?? 0),
            opsFieldLine("重试信号", selectedQualityTraceDetail.feedback_summary?.retry_signal_count ?? 0),
            `反馈时间线：\n${(selectedQualityTraceDetail.feedback_items || []).map((item) => `${item.feedback_type || "-"} · ${item.signal || "-"} · ${formatTimestamp(item.created_at)}\n${Object.entries(item.payload || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`).join("\n\n") || "-"}`,
          ]) : "",
          selectedWork ? opsSection("作品稿", [
            opsFieldLine("作品编号", selectedWork.work_id || "-"),
            opsFieldLine("作品状态", selectedWork.status || "-"),
            opsFieldLine("章节进度", `${selectedWork.chapter_count || 0}/${selectedWork.target_chapter_count || 0}`),
            opsFieldLine("最新修订", selectedWork.latest_revision?.revision_type || "-"),
            opsFieldLine("最新诊断", workDiagnostics.latest_decision || "-"),
          ]) : "",
          selectedWork ? opsSection("章节列表", [
            (selectedWork.chapters || [])
              .map((chapter) => `第 ${chapter.chapter_index} 章 · ${chapter.chapter_title}\n${chapter.status || "-"} / ${chapter.source_type || "-"}`)
              .join("\n\n") || "-",
          ]) : "",
          selectedWork ? opsSection("正文预览", [
            selectedChapter
              ? `第 ${selectedChapter.chapter_index} 章 · ${selectedChapter.chapter_title}\n${selectedChapter.body || "-"}`
              : "-",
          ]) : "",
          selectedWork ? opsSection("诊断证据", [
            `latest ${workDiagnostics.latest_decision || "-"}\n` +
              `pass ${formatPercent(workEvaluation.pass_rate)}\n` +
              `rewrite ${formatPercent(workEvaluation.rewrite_rate)}\n` +
              `block ${formatPercent(workEvaluation.block_rate)}\n` +
              `chapter ${(selectedChapterIssueCodes || []).join(" / ") || "-"}`,
          ]) : "",
          opsSection("源负载", [
            localizeDisplayText(JSON.stringify((opsState.opsSelectedReviewItemDetail?.review_item?.source_payload || opsState.opsSelectedReviewItemDetail?.source_payload || {}), null, 2)),
          ])
        ),
      });
      const actions = document.createElement("div");
      actions.className = "composer-actions";
      (selectedReviewItem.allowed_actions || []).slice(0, 8).forEach((actionId) => {
        const button = document.createElement("button");
        button.className = ["approve", "resolve"].includes(actionId) ? "primary-action" : "ghost-action";
        button.textContent = {
          assign_to_me: "分给我",
          mark_triaged: "标记已分诊",
          mark_in_review: "进入审阅",
          approve: "批准",
          needs_changes: "要求修改",
          block: "阻塞",
          resolve: "解决",
          dismiss: "驳回",
          open_release_workspace: "打开发布台",
          open_account_workspace: "打开账户台",
          open_governance_case: "打开治理个案",
          open_investigation: "打开排查",
          escalate_to_governance: "升级到治理",
        }[actionId] || actionId;
        button.addEventListener("click", async () => {
          await OpsActionsRuntime.runOpsReviewHubAction(selectedReviewItem, actionId);
        });
        actions.appendChild(button);
      });
      dom.opsWorldStatus.appendChild(detailCard);
      dom.opsWorldStatus.appendChild(actions);
      const triageCard = createListCard({
        title: "跨域分诊",
        score: `${(triage.unassigned || []).length} unassigned`,
        body: opsSections(
          opsSection("未分派", [opsList(triage.unassigned || [], (item) => `${item.headline} · ${item.queue} · ${item.severity}`)]),
          opsSection("阻塞", [opsList(triage.blocked || [], (item) => `${item.headline} · ${item.queue} · ${item.status}`)]),
          opsSection("即将超时", [opsList(triage.due_soon || [], (item) => `${item.headline} · ${item.sla_bucket} · due ${item.due_at || "-"}`)]),
        ),
      });
      dom.opsWorldStatus.appendChild(triageCard);
    } else {
      clearNode(dom.opsWorldStatus, "选择一个统一审阅项后，这里会显示详情、动作和跨域分诊摘要。");
    }
    opsState.opsWorldStatuses.forEach((status) => {
      const card = document.createElement("article");
      card.className = "list-card";
      if (status.world_id === opsState.selectedOpsWorldId) {
        card.classList.add("is-active");
      }
      const rollbackTarget = status.versions.find((item) => item.world_version_id !== status.published_version);
      const checklistSummary = status.publish_checklist_summary || {};
      const checklistDrilldown = (status.publish_checklist || [])
        .map((item) => `${item.ok ? "✓" : "×"} ${item.label} · ${item.reason || "-"}\n负责人 ${item.owner || "-"} · 严重度 ${item.severity || "-"} · 下一步 ${item.next_action || "-"}\n证据 ${summarizeChecklistEvidence(item.evidence)}`)
        .join("\n\n") || "暂无 checklist";
      const reviewDrilldown = (status.recent_reviews_drilldown || [])
        .map((item) => summarizeReviewTimelineEntry(item))
        .join("\n\n") || "暂无 recent reviews";
      const worldStatusBody =
        `${status.versions.map((item) => `${item.world_version_id} · ${item.status}`).join("\n")}\n\n` +
        `发布清单摘要：\n可发布 ${checklistSummary.publish_ready ? "是" : "否"} · 阻塞 ${checklistSummary.blocked_count ?? 0}/${checklistSummary.total ?? 0}\n负责人 ${(checklistSummary.owners || []).join(" / ") || "-"}\n下一步 ${(checklistSummary.next_actions || []).join(" / ") || "-"}\n\n` +
        `Author 长线口径：\n入口 ${(status.author_longform_capability || {}).entry_mode || "-"} · 目标 ${(status.author_longform_capability || {}).requested_target_band || "-"} · claim ${(status.author_longform_capability || {}).claim_safe_band || "-"}\nOps ready band ${(status.author_claim_alignment || {}).ops_release_ready_band || "-"} · alignment ${((status.author_claim_alignment || {}).aligned ? "yes" : "no")}\n\n` +
        `发布清单明细：\n${checklistDrilldown}\n\n` +
        `风险摘要：\n可发布 ${status.risk_summary?.publish_ready ? "是" : "否"}\n门禁 ${((status.risk_summary?.publish_gate_errors) || []).join(" / ") || "-"}\n最近回滚 ${status.risk_summary?.latest_rollback_target || "-"} · ${status.risk_summary?.latest_rollback_reason || "-"}\n权益告警 ${((status.risk_summary?.entitlement_alerts) || []).map((item) => `${item.event_name}:${item.reason || "-"}`).join(" / ") || "-"}\n\n` +
        `学习层影子评估：\n状态 ${status.learned_shadow_summary?.status || "-"} · 一致率 ${status.learned_shadow_summary?.agreement_rate !== null && status.learned_shadow_summary?.agreement_rate !== undefined ? Number(status.learned_shadow_summary.agreement_rate).toFixed(3) : "-"}\n问题 ${(status.learned_shadow_summary?.top_mismatch_issue_codes || []).slice(0, 3).map((item) => item.issue_code || item.key).join(" / ") || "-"}\n下一步 ${status.learned_shadow_summary?.recommended_next_action || "-"}\n\n` +
        `学习层影子重排：\n状态 ${status.learned_reranker_shadow_summary?.status || "-"} · 准确率 ${status.learned_reranker_shadow_summary?.per_world_accuracy?.[status.world_id] !== undefined ? Number(status.learned_reranker_shadow_summary.per_world_accuracy[status.world_id]).toFixed(3) : "-"}\n下一步 ${status.learned_reranker_shadow_summary?.recommended_next_action || "-"}\n\n` +
        `最近审核明细：\n${reviewDrilldown}` +
        `${(status.recent_entitlement_events || []).length ? `\n\n最近权益事件：\n${status.recent_entitlement_events.slice(0, 5).map((item) => `${item.event_name} · ${item.reason || "-"} · ${formatTimestamp(item.occurred_at)}`).join("\n")}` : ""}`;
      card.innerHTML = renderLocalizedCardHtml(
        status.world_id,
        status.published_version || "未发布",
        worldStatusBody,
        rollbackTarget ? `<div class="composer-actions"><button class="ghost-action rollback-world">回滚到 ${rollbackTarget.world_version_id}</button></div>` : ""
      );
      if (rollbackTarget) {
        card.querySelector(".rollback-world").addEventListener("click", async () => {
          await api(`/v1/ops/worlds/${status.world_id}/rollback`, {
            method: "POST",
            body: JSON.stringify({ target_world_version_id: rollbackTarget.world_version_id }),
          });
          await refreshOpsReleaseFlow();
        });
      }
      card.addEventListener("click", async () => {
        opsState.selectedOpsWorldId = status.world_id;
        syncOpsNavigationContext({ world_id: status.world_id }, { preserveExisting: true });
        if (dom.opsReleaseWorldId) {
          dom.opsReleaseWorldId.value = status.world_id;
        }
        await refreshOpsReleaseWorkspace();
        renderOpsSurface();
      });
      dom.opsWorldStatus.appendChild(card);
    });
  }

  if (!opsState.opsReleaseWorkspace) {
    clearNode(dom.opsReleaseWorkspaceSummary, "这里会显示当前世界的发布摘要。");
    clearNode(dom.opsReleaseWorkspaceActions, "这里会显示当前世界的快捷动作。");
    clearNode(dom.opsReleaseWorkspaceTimeline, "这里会显示当前世界的运营时间线。");
    clearNode(dom.opsReleaseWorkspaceDetails, "这里会显示发布阻塞项、版本矩阵与回滚工作台。");
  } else {
    const release = opsState.opsReleaseWorkspace;
    const summary = release.release_summary || {};
    const blockers = release.publish_blockers || {};
    const phaseAGate = blockers.phase_a_quality_gate || {};
    const qualityProjection = release.quality_projection_summary || {};
    const rollback = release.rollback_workspace || {};
    const investigation = release.investigation_summary || {};
      dom.opsReleaseWorkspaceSummary.appendChild(
      createListCard({
        title: `发布台 · ${opsWorldLabel(release.world_id)}`,
        score: opsStatusLabel(summary.health_status || "-"),
        body:
          `${opsFieldLine("已发布版本", summary.published_version || "-")} · ${opsFieldLine("当前选中版本", summary.selected_world_version_id || "-")}\n` +
          `${opsFieldLine("是否可发布", opsBooleanLabel(summary.publish_ready))} · ${opsFieldLine("阻塞项", summary.blocked_checklist_count ?? 0)}\n` +
          `${opsFieldLine("Author 入口", summary.author_entry_mode || "-")} · ${opsFieldLine("目标 band", summary.author_requested_target_band || "-")}\n` +
          `${opsFieldLine("Author claim", summary.author_claim_safe_band || "-")} · ${opsFieldLine("Ops ready band", summary.ops_release_ready_band || "-")}\n` +
          `${opsFieldLine("Claim alignment", opsBooleanLabel(summary.author_claim_alignment))}\n` +
          `${opsFieldLine("质量案例", summary.quality_open_case_count ?? 0)} · ${opsFieldLine("blocked 事件", summary.quality_blocked_event_count ?? 0)} · ${opsFieldLine("review_required 事件", summary.quality_review_required_event_count ?? 0)}\n` +
          `${opsFieldLine("最新质量 Trace", summary.quality_latest_trace_id || "-")}\n` +
          `${opsFieldLine("策略包批量验证", summary.strategy_bundle_batch_validation_status || "-")} · ${opsFieldLine("验证原因", summary.strategy_bundle_batch_validation_reason || "-")}\n` +
          `${opsFieldLine("策略包趋势", summary.strategy_bundle_batch_validation_trend_status || "-")} · ${opsFieldLine("趋势原因", summary.strategy_bundle_batch_validation_trend_reason || "-")}\n` +
          `${opsFieldLine("是否建议淘汰", summary.strategy_bundle_batch_validation_retire_recommended ? "yes" : "no")}\n` +
          `${opsFieldLine("storybook 标题趋势", summary.reader_storybook_title_homogenization_trend_status || "-")} · ${opsFieldLine("promoted pairs", summary.reader_storybook_title_homogenization_promoted_pair_count ?? 0)}\n` +
          `${opsFieldLine("近期回滚次数", summary.recent_rollback_count ?? 0)} · ${opsFieldLine("最近回滚目标", summary.latest_rollback_target || "-")}\n` +
          `${opsFieldLine("建议动作", summary.recommended_action || "-")}\n` +
          `${opsPairsLine("审阅人分布", release.review_ownership_summary?.reviewer_counts || {})}\n` +
          `${opsFieldLine("清单负责人", (release.review_ownership_summary?.checklist_owners || []).join(" / ") || "-")}\n` +
          `${opsFieldLine("建议排查路径", (investigation.recommended_paths || []).map((item) => item.path_id).join(" / ") || "-")}`
      })
    );
    if (!(release.action_pack || []).length) {
      clearNode(dom.opsReleaseWorkspaceActions, "这里会显示当前世界的快捷动作。");
    } else {
      const actionCard = createListCard({
        title: "发布动作",
        score: `${(release.action_pack || []).length} actions`,
        body: (release.action_pack || []).map((item) => `${item.label} · ${opsActionModeLabel(item.mode)}\n${item.reason || "-"}`).join("\n\n"),
      });
      const actions = document.createElement("div");
      actions.className = "composer-actions";
      (release.action_pack || []).forEach((item) => {
        const button = document.createElement("button");
        button.className = item.mode === "execute" ? "primary-action" : "ghost-action";
        button.textContent = item.label;
        button.addEventListener("click", async () => {
          try {
            await OpsActionsRuntime.runOpsReleaseWorkspaceAction(item);
          } catch (error) {
            alert(`执行 release action 失败：${error.message}`);
          }
        });
        actions.appendChild(button);
      });
      dom.opsReleaseWorkspaceActions.appendChild(actionCard);
      dom.opsReleaseWorkspaceActions.appendChild(actions);
    }
    if (!(release.operator_timeline || []).length) {
      clearNode(dom.opsReleaseWorkspaceTimeline, "这里会显示当前世界的运营时间线。");
    } else {
      (release.operator_timeline || []).forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.headline || item.entry_id}</h3>
            <span class="list-card-score">${item.category || "-"}</span>
          </div>
          <p class="list-card-body">${formatTimestamp(item.occurred_at)}\n${item.summary || "-"}\nnext ${(item.next_actions || []).join(" / ") || "-"}</p>
        `;
        dom.opsReleaseWorkspaceTimeline.appendChild(card);
      });
    }
      const detailBody = [
        `publish blockers:\n${(blockers.items || []).map((item) => summarizeReleaseBlocker(item)).join("\n\n") || "-"}`,
        `author longform capability:\nentry ${(release.release_evidence_bundle?.author_longform_capability || {}).entry_mode || "-"} · requested ${(release.release_evidence_bundle?.author_longform_capability || {}).requested_target_band || "-"} · claim ${(release.release_evidence_bundle?.author_longform_capability || {}).claim_safe_band || "-"}\nstatus ${((release.release_evidence_bundle?.author_longform_capability || {}).longform_readiness || {}).status || "-"}\nblockers ${(((release.release_evidence_bundle?.author_longform_capability || {}).longform_readiness || {}).blockers || []).map((item) => item.message || item.key).join(" / ") || "-"}\nstructure ${((release.release_evidence_bundle?.author_longform_capability || {}).structure_counts || {}).character_count ?? 0} 角色 / ${((release.release_evidence_bundle?.author_longform_capability || {}).structure_counts || {}).scene_blueprint_count ?? 0} 场景 / ${((release.release_evidence_bundle?.author_longform_capability || {}).structure_counts || {}).location_count ?? 0} 地点`,
        `author claim alignment:\nclaim ${(release.release_evidence_bundle?.author_claim_alignment || {}).claim_safe_band || "-"} · ops ready ${(release.release_evidence_bundle?.author_claim_alignment || {}).ops_release_ready_band || "-"}\nalignment ${((release.release_evidence_bundle?.author_claim_alignment || {}).aligned ? "yes" : "no")} · reason ${(release.release_evidence_bundle?.author_claim_alignment || {}).reason || "-"}`,
        `strategy bundle batch validation:\nstrategy ${(release.release_evidence_bundle?.strategy_bundle_batch_validation_summary || {}).strategy_bundle_label || "-"} ${(release.release_evidence_bundle?.strategy_bundle_batch_validation_summary || {}).strategy_bundle_id ? `(${(release.release_evidence_bundle?.strategy_bundle_batch_validation_summary || {}).strategy_bundle_id})` : ""}\nstatus ${summary.strategy_bundle_batch_validation_status || "-"} · decision reason ${summary.strategy_bundle_batch_validation_reason || "-"}\nvalidated worlds ${(release.release_evidence_bundle?.strategy_bundle_batch_validation_summary || {}).validated_world_count ?? 0} · effectiveness ${Number((release.release_evidence_bundle?.strategy_bundle_batch_validation_summary || {}).effectiveness_rate || 0).toFixed(3)}\ncompatible worlds ${((release.release_evidence_bundle?.strategy_bundle_batch_validation_summary || {}).compatible_world_ids || []).join(" / ") || "-"}\nadaptation ${((release.release_evidence_bundle?.strategy_bundle_batch_validation_summary || {}).top_adaptation_targets || []).map((item) => `${item.kind}:${item.name}=${item.count}`).join(" / ") || "-"}`,
        `strategy bundle history:\ntrend ${(release.release_evidence_bundle?.strategy_bundle_batch_validation_history_summary || {}).trend_status || "-"} · reason ${(release.release_evidence_bundle?.strategy_bundle_batch_validation_history_summary || {}).trend_reason || "-"}\nlatest ${(release.release_evidence_bundle?.strategy_bundle_batch_validation_history_summary || {}).latest_decision || "-"} · effectiveness ${Number((release.release_evidence_bundle?.strategy_bundle_batch_validation_history_summary || {}).latest_effectiveness_rate || 0).toFixed(3)} · delta ${Number((release.release_evidence_bundle?.strategy_bundle_batch_validation_history_summary || {}).delta_effectiveness_rate || 0).toFixed(3)}\nretire recommended ${((release.release_evidence_bundle?.strategy_bundle_batch_validation_history_summary || {}).retire_recommended ? "yes" : "no")}\nrecent runs ${((release.release_evidence_bundle?.strategy_bundle_batch_validation_history || {}).entries || []).map((item) => `${item.generated_at || "-"}:${item.decision || "-"}:${Number(item.effectiveness_rate || 0).toFixed(3)}`).join(" / ") || "-"}`,
        `reader storybook title trend:\ntrend ${(release.release_evidence_bundle?.reader_storybook_title_homogenization_history_summary || {}).trend_status || "-"} · reason ${(release.release_evidence_bundle?.reader_storybook_title_homogenization_history_summary || {}).trend_reason || "-"}\nlatest ${(release.release_evidence_bundle?.reader_storybook_title_homogenization_history_summary || {}).latest_generated_at || "-"} · promoted ${(release.release_evidence_bundle?.reader_storybook_title_homogenization_history_summary || {}).promoted_pair_count ?? 0}\npairs ${((release.release_evidence_bundle?.reader_storybook_title_homogenization_promoted_pairs || []).map((item) => `${item.non_jade_world_id}->${item.jade_world_id}@${item.consecutive_warning_count}`).join(" / ")) || "-"}`,
        `版本矩阵：\n${(release.version_matrix || []).map((item) => `${item.world_version_id}\n${item.status} · 最近判断 ${item.latest_decision || "-"} · 是否可发布 ${item.publish_ready ? "是" : "否"}\n跨包 ${Number(item.cross_pack_pass_rate || 0).toFixed(3)} · 阻塞 ${formatPercent(item.block_rate)} · 是否回退 ${item.regression_detected ? "是" : "否"}\n薄弱世界 ${(item.top_failing_pack_ids || []).join(" / ") || "-"}\n门禁 ${(item.publish_gate_errors || []).join(" / ") || "-"}\n更新时间 ${formatTimestamp(item.updated_at)}`).join("\n\n") || "-"}`,
        `回滚工作台：\n最近回滚 ${rollback.latest_rollback?.rollback_target_world_version_id || "-"} · ${rollback.latest_rollback?.rollback_reason || "-"}\n候选版本 ${(rollback.rollback_candidates || []).map((item) => `${item.world_version_id}:${item.status}`).join(" / ") || "-"}\n摘要数量 ${(rollback.summary || {}).total_entries ?? 0} · 最近原因 ${(rollback.summary || {}).latest_reason || "-"}`,
      ].join("\n\n");
      const detailCard = createListCard({
        title: "发布详情",
        score: `${(blockers.items || []).length} blockers`,
        body: detailBody,
      });
      if (opsState.selectedOpsReleaseBlockerKey && opsState.selectedOpsReleaseBlockerKey !== "phase_a_quality_gate") {
        detailCard.dataset.releaseBlockerKey = opsState.selectedOpsReleaseBlockerKey;
      }
      dom.opsReleaseWorkspaceDetails.appendChild(detailCard);
    if (phaseAGate.available) {
      const summaryCard = createListCard({
        title: "Phase A Quality Gate",
        score: `${(phaseAGate.failed_check_items || []).length} failed`,
        body:
          `${opsFieldLine("配置版本", phaseAGate.config_version || "-")}\n` +
          `${opsFieldLine("失败项", (phaseAGate.failed_check_items || []).map((item) => item.check_key).join(" / ") || "-")}`
      });
      summaryCard.dataset.releaseBlockerKey = "phase_a_quality_gate";
      dom.opsReleaseWorkspaceDetails.appendChild(summaryCard);
      if ((qualityProjection.events || []).length) {
        const qualityCard = createListCard({
          title: "质量投影",
          score: `${qualityProjection.summary?.open_review_case_count ?? 0} open`,
          body:
            `${opsFieldLine("事件数", qualityProjection.summary?.event_count ?? 0)} · ${opsFieldLine("案例数", qualityProjection.summary?.review_case_count ?? 0)}\n` +
            `${opsFieldLine("blocked", qualityProjection.summary?.blocked_event_count ?? 0)} · ${opsFieldLine("review_required", qualityProjection.summary?.review_required_event_count ?? 0)}\n` +
            `最近 Trace：\n${(qualityProjection.events || []).slice(0, 3).map((item) => `${item.trace_id || "-"} · ${opsStatusLabel(item.status || "-")} · ${opsIssueCodeList(item.reason_codes || [])}`).join("\n") || "-"}`
        });
        dom.opsReleaseWorkspaceDetails.appendChild(qualityCard);
      }
      (phaseAGate.failed_check_items || []).forEach((item) => {
        const card = createListCard({
          title: item.label || item.check_key,
          score: "blocked",
          body:
            `${opsFieldLine("原因", item.reason || "-")}\n` +
            `${opsFieldLine("阈值", item.threshold !== undefined && item.threshold !== null ? item.threshold : "-")}\n` +
            `${opsFieldLine("实际值", Array.isArray(item.actual) ? JSON.stringify(item.actual) : (item.actual !== undefined && item.actual !== null ? item.actual : "-"))}\n` +
            `${opsFieldLine("涉及 worlds", (item.evaluated_world_ids || []).map((worldId) => opsWorldLabel(worldId)).join(" / ") || "-")}`
        });
        card.dataset.releaseBlockerKey = "phase_a_quality_gate";
        card.dataset.releaseBlockerCheckKey = item.check_key || "";
        if (
          opsState.selectedOpsReleaseBlockerKey === "phase_a_quality_gate"
          && opsState.selectedOpsReleaseBlockerCheckKey
          && opsState.selectedOpsReleaseBlockerCheckKey === item.check_key
        ) {
          card.classList.add("is-highlighted");
        }
        dom.opsReleaseWorkspaceDetails.appendChild(card);
      });
    }
  }

  clearNode(dom.opsReviewHistory);
  if (!opsState.opsWorldHistories.length) {
    clearNode(dom.opsReviewHistory, "这里会显示世界版本的审核、发布和回滚记录。");
  } else {
    opsState.opsWorldHistories.forEach((history) => {
      const card = document.createElement("article");
      card.className = "list-card";
      const summary = history.review_summary || {};
      const rollbackSummary = history.rollback_summary || {};
      const timelineBody = (history.review_timeline || []).slice(0, 8).map((item) => summarizeReviewTimelineEntry(item)).join("\n\n") || "暂无审核记录";
      const rollbackBody = (history.rollback_drilldown || []).slice(0, 5).map((item) => summarizeRollbackEntry(item)).join("\n\n") || "暂无 rollback 记录";
      const reviewHistoryBody =
        `摘要：\n状态 ${Object.entries(summary.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n审阅人 ${Object.entries(summary.reviewer_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n最近发布 ${summary.latest_published_world_version_id || "-"}\n最近阻塞 ${summary.latest_blocked_world_version_id || "-"}\n最近回滚 ${summary.latest_rollback_target_world_version_id || "-"}\n\n` +
        `回滚摘要：\n数量 ${rollbackSummary.total_entries ?? 0}\n目标 ${Object.entries(rollbackSummary.target_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n审阅人 ${Object.entries(rollbackSummary.reviewer_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n最近原因 ${rollbackSummary.latest_reason || "-"}\n\n` +
        `审核时间线：\n${timelineBody}\n\n回滚明细：\n${rollbackBody}`;
      card.innerHTML = renderLocalizedCardHtml(history.world_id, `${summary.total_entries ?? (history.review_history || []).length} 条`, reviewHistoryBody);
      dom.opsReviewHistory.appendChild(card);
    });
  }

  clearNode(dom.opsQualityTrend);
  if (!opsState.opsWorldHistories.length) {
    clearNode(dom.opsQualityTrend, "这里会显示每个世界版本的通过、重写、阻塞与跨包走势。");
  } else {
    opsState.opsWorldHistories.forEach((history) => {
      const card = document.createElement("article");
      card.className = "list-card";
      const summary = history.quality_trend_summary || {};
      const qualityBody =
        `摘要：\n最近版本 ${summary.latest_world_version_id || "-"}\n最强版本 ${summary.strongest_world_version_id || "-"}\n最弱版本 ${summary.weakest_world_version_id || "-"}\n回退版本 ${(summary.regression_version_ids || []).join(" / ") || "-"}\n阻塞版本 ${(summary.blocked_version_ids || []).join(" / ") || "-"}\n改善版本 ${(summary.improving_version_ids || []).join(" / ") || "-"}\n最近变化 通过率 ${formatSignedDelta(summary.latest_delta?.pass_rate)} · 阻塞率 ${formatSignedDelta(summary.latest_delta?.block_rate)} · 跨包 ${formatSignedDelta(summary.latest_delta?.cross_pack_pass_rate)}\n\n趋势明细：\n${(history.quality_trend || []).map((item) => summarizeQualityTrendEntry(item)).join("\n\n") || "暂无版本级质量趋势。"}`;
      card.innerHTML = renderLocalizedCardHtml(history.world_id, `${(history.quality_trend || []).length} 条`, qualityBody);
      dom.opsQualityTrend.appendChild(card);
    });
  }
}

function renderOpsRuntimeSection() {
  clearNode(dom.opsSchemaLifecycle);
  clearNode(dom.opsDataIntegrity);
  if (!opsState.opsSchemaLifecycle) {
    clearNode(dom.opsSchemaLifecycle, "这里会显示当前数据库后端、待执行迁移状态和结构漂移摘要。");
    clearNode(dom.opsDataIntegrity, "这里会显示热点索引覆盖、会话漂移、孤儿分支选择与修复待办。");
  } else {
    const lifecycle = opsState.opsSchemaLifecycle;
    dom.opsSchemaLifecycle.appendChild(
      createListCard({
        title: "数据库结构生命周期",
        score: opsStatusLabel(lifecycle.status || "-"),
        body: opsSections(
          opsSection("基础信息", [
            opsFieldLine("后端", lifecycle.backend || "-"),
            opsFieldLine("最新可用版本", lifecycle.latest_available_version || "-"),
            opsFieldLine("最新已应用版本", lifecycle.latest_applied_version || "-"),
            opsFieldLine("待应用版本", (lifecycle.pending_versions || []).join(" / ") || "-"),
          ]),
          opsSection("一致性", [
            opsFieldLine("结构是否与迁移一致", opsBooleanLabel(lifecycle.schema_matches_migrations)),
            opsFieldLine("Alembic 状态", opsStatusLabel(lifecycle.alembic?.status || "-")),
            opsFieldLine("当前 Alembic 版本", lifecycle.alembic?.current_revision || "-"),
            opsFieldLine("目标 Alembic 版本", lifecycle.alembic?.head_revision || "-"),
          ]),
          opsSection("指纹", [
            opsFieldLine("数据库结构指纹", (lifecycle.schema_sql_fingerprint || "-").slice(0, 12)),
            opsFieldLine("迁移指纹", (lifecycle.migrations_fingerprint || "-").slice(0, 12)),
          ])
        )
      })
    );
  }
  if (!opsState.opsDataIntegrity) {
    clearNode(dom.opsDataIntegrity, "这里会显示热点索引覆盖、会话漂移、孤儿分支选择与修复待办。");
  } else {
    const integrity = opsState.opsDataIntegrity;
    const repairResult = opsState.opsDataIntegrityRepair;
    dom.opsDataIntegrity.appendChild(
      createListCard({
        title: "数据一致性与修复",
        score: opsStatusLabel(integrity.status || "-"),
        body: opsSections(
          opsSection("总体状态", [
            opsFieldLine("后端", integrity.backend || "-"),
            opsFieldLine("数据库结构状态", opsStatusLabel(integrity.schema_lifecycle?.status || "-")),
            opsFieldLine("热点索引覆盖", `${integrity.hotspot_index_summary?.covered_count ?? 0}/${integrity.hotspot_index_summary?.expected_count ?? 0}`),
            opsFieldLine("缺失索引", integrity.hotspot_index_summary?.missing_count ?? 0),
          ]),
          opsSection("并发与漂移", [
            opsFieldLine("会话指针漂移", integrity.concurrency_summary?.session_pointer_drift_count ?? 0),
            opsFieldLine("孤儿选项", integrity.concurrency_summary?.orphan_route_choice_count ?? 0),
            opsFieldLine("重复生效中的订阅", integrity.concurrency_summary?.duplicate_active_subscription_count ?? 0),
            opsFieldLine("告警", (integrity.warnings || []).join(" / ") || "-"),
          ]),
          opsSection("安全修复动作", [
            opsList(integrity.repair_actions || [], (item) => `${item.action} · ${item.target_count} · ${item.reason || "-"}`),
          ]),
          opsSection("人工处理待办", [
            opsList(integrity.manual_backlog || [], (item) => `${item.action} · ${item.target_count} · ${item.reason || "-"}`),
          ]),
          repairResult ? opsSection("最近一次修复", [
            opsFieldLine("模式", repairResult.apply ? "正式应用" : "仅演练"),
            opsFieldLine("是否有变更", opsBooleanLabel(repairResult.changed)),
            opsFieldLine("动作结果", (repairResult.action_results || []).map((item) => `${item.action}:${item.applied_count ?? 0}/${item.planned_count ?? 0}`).join(" / ") || "-"),
          ]) : ""
        )
      })
    );
  }

  clearNode(dom.opsDeploymentRunbook);
  clearNode(dom.opsIncidentPlaybook);
  clearNode(dom.opsDeploymentHealthGate);
  clearNode(dom.opsPreflightVerification);
  if (!opsState.opsDeploymentRunbook) {
    clearNode(dom.opsDeploymentHealthGate, "这里会显示发布健康门和总体放行状态。");
    clearNode(dom.opsPreflightVerification, "这里会显示发布前校验包与推荐验证命令。");
    clearNode(dom.opsDeploymentRunbook, "这里会显示发布运行手册与最近备份。");
    clearNode(dom.opsIncidentPlaybook, "这里会显示事故处置手册与建议恢复步骤。");
  } else {
    const healthGate = opsState.opsDeploymentHealthGate || {};
    dom.opsDeploymentHealthGate.appendChild(
      createListCard({
        title: "发布健康门",
        score: opsStatusLabel(healthGate.status || "-"),
        body: opsSections(
          opsSection("总体判断", [
            opsFieldLine("建议动作", healthGate.recommended_action || "-"),
            opsFieldLine("检查项", ((healthGate.checks || []).map((item) => `${item.key}:${opsStatusLabel(item.status)}`).join(" / ")) || "-"),
          ]),
          opsSection("结构与事故", [
            opsFieldLine("数据库结构状态", opsStatusLabel(healthGate.schema_lifecycle?.status || "-")),
            opsFieldLine("事故数", healthGate.incident_snapshot?.incident_count ?? 0),
            opsPairsLine("通道分布", healthGate.incident_snapshot?.by_provider || {}, opsProviderLabel),
          ])
        )
      })
    );

    const preflight = opsState.opsPreflightVerification || {};
    dom.opsPreflightVerification.appendChild(
      createListCard({
        title: "发布前校验包",
        score: opsStatusLabel(preflight.verification_summary?.gate_status || "-"),
        body: opsSections(
          opsSection("总体判断", [
            opsFieldLine("建议动作", preflight.verification_summary?.recommended_action || "-"),
            opsFieldLine("数据库结构状态", opsStatusLabel(preflight.verification_summary?.schema_status || "-")),
            opsFieldLine("事故数", preflight.verification_summary?.incident_count ?? 0),
          ]),
          opsSection("恢复验证步骤", [
            opsList(preflight.restore_verification_steps || []),
          ]),
          opsSection("建议命令", [
            opsList(preflight.verification_commands || []),
          ])
        )
      })
    );

    const runbook = opsState.opsDeploymentRunbook;
    dom.opsDeploymentRunbook.appendChild(
      createListCard({
        title: "发布运行手册",
        score: opsStatusLabel(runbook.schema_lifecycle?.status || runbook.backend || "-"),
        body: opsSections(
          opsSection("基础信息", [
            opsFieldLine("后端", runbook.backend || "-"),
            opsFieldLine("数据库地址", runbook.database_url || "-"),
            opsFieldLine("预检查结果", ((runbook.preflight_checks || []).map((item) => `${item.key}:${item.ok ? "通过" : item.reason}`).join(" / ")) || "-"),
          ]),
          opsSection("发布步骤", [opsList(runbook.deploy_steps || [])]),
          opsSection("回滚步骤", [opsList(runbook.rollback_steps || [])]),
          opsSection("恢复验证步骤", [opsList(runbook.restore_verification_steps || [])]),
          opsSection("恢复提示", [opsList(runbook.restore_decision_hints || [])]),
          opsSection("最近恢复请求", [
            opsParagraphList(runbook.recent_restore_requests || [], (item) =>
              `${item.request_id} · ${opsStatusLabel(item.approval_status || item.latest_status || "-")}\n` +
              `${opsFieldLine("发起人", item.requested_by || "-")} · ${opsFieldLine("批准人", item.approved_by || "-")} · ${opsFieldLine("执行人", item.executed_by || "-")}\n` +
              `${opsFieldLine("审批有效期", item.approval_expires_at || "-")}\n` +
              `${opsFieldLine("备份格式", item.backup_format || "-")} · ${opsFieldLine("目标数据库", item.target_database_identity || "-")}\n` +
              `${opsFieldLine("原因", item.reason || "-")}\n` +
              `${opsFieldLine("任务", item.executed_job_id || "-")} · ${opsFieldLine("产物", item.artifact_path || "-")}`
            ),
          ]),
          opsSection("最近恢复任务", [
            opsParagraphList(runbook.recent_restore_jobs || [], (item) =>
              `${item.job_id} · ${opsStatusLabel(item.status || "-")}\n` +
              `${opsFieldLine("请求 ID", item.payload?.request_id || "-")} · ${opsFieldLine("产物", (item.result_summary || {}).result_json || (item.result_summary || {}).artifact_dir || "-")}`
            ),
          ]),
          opsSection("最近恢复演练", [
            opsParagraphList(runbook.recent_recovery_drills || [], (item) =>
              `${item.drill_id || "-"} · ${opsStatusLabel(item.status || "-")}\n` +
              `${opsFieldLine("备份路径", item.backup_path || "-")}\n` +
              `${opsFieldLine("产物", item.artifact_path || "-")}`
            ),
          ]),
          opsSection("最近备份", [
            opsParagraphList(runbook.recent_backups || [], (item) =>
              `${item.backup_id} · ${opsStatusLabel(item.status || "-")}\n` +
              `${opsFieldLine("备份路径", item.backup_path || "-")} · ${opsFieldLine("创建时间", item.created_at || "-")}`
            ),
          ])
        )
      })
    );
    if (!dom.opsRestorePath?.value && runbook.recent_backups?.[0]?.backup_path && dom.opsRestorePath) {
      dom.opsRestorePath.value = runbook.recent_backups[0].backup_path;
    }
    if (!dom.opsRestoreRequestId?.value && runbook.recent_restore_requests?.[0]?.request_id && dom.opsRestoreRequestId) {
      dom.opsRestoreRequestId.value = runbook.recent_restore_requests[0].request_id;
    }
  }

  if (!opsState.opsIncidentPlaybook) {
    clearNode(dom.opsIncidentPlaybook, "这里会显示事故处置手册与建议恢复步骤。");
  } else {
    const playbook = opsState.opsIncidentPlaybook;
    dom.opsIncidentPlaybook.appendChild(
      createListCard({
        title: "事故处置手册",
        score: `${playbook.incident_snapshot?.incident_count ?? 0} 起事故`,
        body:
          `数据库结构 ${playbook.deployment_runbook?.schema_lifecycle?.status || "-"}\n` +
          `恢复提示 ${(playbook.deployment_runbook?.restore_decision_hints || []).join(" / ") || "-"}\n` +
          `分诊步骤：\n${(playbook.triage_steps || []).join("\n") || "-"}\n\n` +
          `恢复步骤：\n${(playbook.recovery_steps || []).join("\n") || "-"}\n\n` +
          `恢复校验：\n${(playbook.restore_verification_steps || []).join("\n") || "-"}\n\n` +
          `决策矩阵：\n${(playbook.decision_matrix || []).map((item) => `${item.preferred_action} · ${item.when ? "立即执行" : "待命观察"}\n${item.scenario}\n检查项 ${(item.inspect || []).join(" / ") || "-"}`).join("\n\n") || "-"}`
      })
    );
  }

  clearNode(dom.opsRuntimeIncidentSnapshot);
  clearNode(dom.opsRuntimeReceipts);
  clearNode(dom.opsProviderRouting);
  clearNode(dom.opsProviderRollout);
  clearNode(dom.opsProviderRuntimeMetrics);
  clearNode(dom.opsStoryBootstrapWorldSummary);
  clearNode(dom.opsStoryBootstrapWorldDetail);
  if (!opsState.opsRuntimeIncidentSnapshot) {
    clearNode(dom.opsRuntimeIncidentSnapshot, "这里会显示运行时事故快照、通道回退、预算拦截与缓存命中概况。");
    clearNode(dom.opsRuntimeReceipts, "这里会显示最近的运行回执。");
    clearNode(dom.opsProviderRouting, "这里会显示通道路由策略，以及候选链路和渲染链路的当前路由配置。");
    clearNode(dom.opsProviderRollout, "这里会显示候选链路和渲染链路的灰度、全量启用与回滚控制。");
    clearNode(dom.opsProviderRuntimeMetrics, "这里会显示通道运行指标、灰度阶段对比与成本趋势。");
    clearNode(dom.opsStoryBootstrapWorldSummary, "这里会显示 Story bootstrap 首轮质量门碰撞摘要。");
    clearNode(dom.opsStoryBootstrapWorldDetail, "这里会显示选中 world 的 Story bootstrap 重试明细。");
  } else {
    const snapshot = opsState.opsRuntimeIncidentSnapshot;
    const qualitySummary = opsState.opsQualitySummary || {};
    const commercialization = opsState.opsCommercializationSummary || {};
    dom.opsRuntimeIncidentSnapshot.appendChild(
      createListCard({
        title: "运行时事故快照",
        score: `${snapshot.incident_count ?? 0} 起事故`,
        body:
          `健康状态 ${snapshot.health_status || "-"} · 数据库结构 ${snapshot.schema_lifecycle_status || "-"}\n` +
          `回执数 ${snapshot.receipt_count ?? 0} · 缓存命中率 ${snapshot.cache_hit_rate !== null && snapshot.cache_hit_rate !== undefined ? Number(snapshot.cache_hit_rate).toFixed(3) : "-"} · 总成本 ${Number(snapshot.total_estimated_cost || 0).toFixed(3)}\n` +
          `运行时延迟 ${snapshot.latency_summary?.runtime?.avg_latency_ms !== null && snapshot.latency_summary?.runtime?.avg_latency_ms !== undefined ? Number(snapshot.latency_summary.runtime.avg_latency_ms).toFixed(1) : "-"}ms / P95 ${snapshot.latency_summary?.runtime?.p95_latency_ms !== null && snapshot.latency_summary?.runtime?.p95_latency_ms !== undefined ? Number(snapshot.latency_summary.runtime.p95_latency_ms).toFixed(1) : "-"}ms\n` +
          `候选链路 ${snapshot.latency_summary?.candidate?.avg_latency_ms !== null && snapshot.latency_summary?.candidate?.avg_latency_ms !== undefined ? Number(snapshot.latency_summary.candidate.avg_latency_ms).toFixed(1) : "-"}ms · 渲染链路 ${snapshot.latency_summary?.renderer?.avg_latency_ms !== null && snapshot.latency_summary?.renderer?.avg_latency_ms !== undefined ? Number(snapshot.latency_summary.renderer.avg_latency_ms).toFixed(1) : "-"}ms\n` +
          `事故类型 ${Object.entries(snapshot.by_incident_type || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `通道分布 ${Object.entries(snapshot.by_provider || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `入口分布 ${Object.entries(snapshot.by_surface || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n\n` +
          `最近事故：\n${(snapshot.latest_incidents || []).map((item) => `${item.action} · ${item.response_status} · ${(item.incident_flags || []).join("/") || "-"}\n${item.selected_provider || item.provider || "-"} · ${item.session_id || "-"} · ${item.world_version_id || "-"}\n延迟 ${item.runtime_latency_ms !== null && item.runtime_latency_ms !== undefined ? Number(item.runtime_latency_ms).toFixed(1) : "-"}ms`).join("\n\n") || "-"}`
      })
    );
    if (qualitySummary.summary) {
      dom.opsRuntimeIncidentSnapshot.appendChild(
        createListCard({
          title: "Canonical 质量摘要",
          score: `${qualitySummary.summary.open_review_case_count ?? 0} open`,
          body:
            `${opsFieldLine("事件数", qualitySummary.summary.event_count ?? 0)} · ${opsFieldLine("案例数", qualitySummary.summary.review_case_count ?? 0)}\n` +
            `${opsFieldLine("blocked", qualitySummary.summary.blocked_event_count ?? 0)} · ${opsFieldLine("review_required", qualitySummary.summary.review_required_event_count ?? 0)}\n` +
            `${opsFieldLine("反馈项", qualitySummary.summary.feedback_item_count ?? 0)} · ${opsFieldLine("重试信号", qualitySummary.summary.retry_signal_count ?? 0)}\n` +
            `${opsPairsLine("状态", qualitySummary.summary.by_status || {}, opsStatusLabel)}\n` +
            `${opsPairsLine("入口", qualitySummary.summary.by_source_surface || {})}`
        })
      );
    }

    if (!opsState.opsRuntimeReceipts.length) {
      clearNode(dom.opsRuntimeReceipts, "这里会显示最近的运行回执。");
    } else {
      opsState.opsRuntimeReceipts.forEach((item) => {
        const card = createListCard({
          title: item.action || "运行时回执",
          score: item.response_status || "-",
          body: opsSections(
            opsSection("基础信息", [
              opsFieldLine("发生时间", formatTimestamp(item.occurred_at)),
              opsFieldLine("入口", item.surface || "-"),
              opsFieldLine("通道", opsProviderLabel(item.selected_provider || item.provider || "-")),
              opsFieldLine("事件标记", (item.incident_flags || []).join(" / ") || "-"),
            ]),
            opsSection("灰度与策略", [
              opsFieldLine("候选链路", opsRolloutSummary(item.candidate_rollout_status, item.candidate_canary_match)),
              opsFieldLine("渲染链路", opsRolloutSummary(item.renderer_rollout_status, item.renderer_canary_match)),
            ]),
            opsSection("缓存与预算", [
              opsFieldLine("缓存命中", item.cache_hit === null || item.cache_hit === undefined ? "-" : opsBooleanLabel(item.cache_hit)),
              opsFieldLine("预算拦截", opsBooleanLabel(item.budget_blocked)),
              opsFieldLine("是否回退", opsBooleanLabel(item.fallback_used)),
            ]),
            opsSection("性能与成本", [
              opsFieldLine("运行时延迟", opsLatencyValue(item.runtime_latency_ms)),
              opsFieldLine("候选延迟", opsLatencyValue(item.candidate_latency_ms)),
              opsFieldLine("渲染延迟", opsLatencyValue(item.renderer_latency_ms)),
              opsFieldLine("尝试次数", `${item.attempt_count ?? 0} / 候选 ${item.candidate_attempt_count ?? 0} / 渲染 ${item.renderer_attempt_count ?? 0}`),
              opsFieldLine("请求成本", `${opsCostValue(item.candidate_estimated_request_cost_usd, 4)} / ${opsCostValue(item.renderer_estimated_request_cost_usd, 4)}`),
              opsFieldLine("总成本", opsCostValue(item.estimated_cost, 3)),
            ]),
            opsSection("输出与错误", [
              opsFieldLine("候选数", `${item.candidate_counts?.raw ?? 0}/${item.candidate_counts?.legal ?? 0}`),
              opsFieldLine("输出字符", item.output_chars ?? 0),
              opsFieldLine("错误", item.backend_error || "-"),
            ])
          )
        });
        dom.opsRuntimeReceipts.appendChild(card);
      });
    }
    (opsState.opsQualityEvents || []).forEach((item) => {
      const card = createListCard({
        title: `质量事件 · ${item.trace_id || item.event_id}`,
        score: opsStatusLabel(item.status || "-"),
        body: opsSections(
          opsSection("基础信息", [
            opsFieldLine("入口", item.source_surface || "-"),
            opsFieldLine("账户", item.account_id || "-"),
            opsFieldLine("世界版本", item.world_version_id || "-"),
            opsFieldLine("会话", item.session_id || "-"),
            opsFieldLine("总分", item.overall_score !== undefined && item.overall_score !== null ? Number(item.overall_score).toFixed(2) : "-"),
          ]),
          opsSection("规则与审阅", [
            opsFieldLine("原因", opsIssueCodeList(item.reason_codes || [])),
            opsFieldLine("Review Case", item.review_case_id || "-"),
            opsFieldLine("创建时间", formatTimestamp(item.created_at)),
          ])
        )
      });
      if (item.trace_id === opsState.opsSelectedQualityTraceId) {
        card.classList.add("is-active");
      }
      card.addEventListener("click", async () => {
        await OpsActionsRuntime.loadOpsQualityTraceDetail(item.trace_id);
        renderOpsSurface(["runtime"]);
      });
      dom.opsRuntimeReceipts.appendChild(card);
    });
    if (opsState.opsQualityTraceDetail) {
      const detail = opsState.opsQualityTraceDetail;
      dom.opsRuntimeReceipts.appendChild(
        createListCard({
          title: `质量 Trace 详情 · ${detail.trace_id || "-"}`,
          score: opsStatusLabel(detail.event?.status || "-"),
          body: opsSections(
            opsSection("事件", [
              opsFieldLine("入口", detail.event?.source_surface || "-"),
              opsFieldLine("账户", detail.linked_context?.account_id || "-"),
              opsFieldLine("世界", opsWorldLabel(detail.linked_context?.world_id || "-")),
              opsFieldLine("世界版本", detail.linked_context?.world_version_id || "-"),
              opsFieldLine("会话", detail.linked_context?.session_id || "-"),
            ]),
            opsSection("评分", [
              opsFieldLine("总分", detail.score?.overall_score !== undefined && detail.score?.overall_score !== null ? Number(detail.score.overall_score).toFixed(2) : "-"),
              opsFieldLine("Veto", detail.score?.veto === undefined ? "-" : opsBooleanLabel(detail.score.veto)),
              opsFieldLine("原因", opsIssueCodeList(detail.score?.reason_codes || detail.review_case?.reason_codes || [])),
            ]),
            opsSection("审阅", [
              opsFieldLine("Case", detail.review_case?.case_id || "-"),
              opsFieldLine("状态", opsStatusLabel(detail.review_case?.status || "-")),
              opsFieldLine("Owner", detail.review_case?.owner_id || "-"),
            ]),
            opsSection("反馈时间线", [
              opsFieldLine("反馈项", detail.feedback_summary?.feedback_item_count ?? 0),
              opsFieldLine("重试信号", detail.feedback_summary?.retry_signal_count ?? 0),
              (detail.feedback_items || []).map((item) => `${item.feedback_type || "-"} · ${item.signal || "-"} · ${formatTimestamp(item.created_at)}\n${Object.entries(item.payload || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`).join("\n\n") || "-",
            ])
          )
        })
      );
    }
    if (commercialization.pilot_vs_paid) {
      dom.opsRuntimeIncidentSnapshot.appendChild(
        createListCard({
          title: "Commercialization Snapshot",
          score: `${commercialization.pilot_vs_paid.pilot_account_count ?? 0}/${commercialization.pilot_vs_paid.paid_account_count ?? 0}`,
          body:
            `pilot ${commercialization.pilot_vs_paid.pilot_account_count ?? 0} · paid ${commercialization.pilot_vs_paid.paid_account_count ?? 0}\n` +
            `renewal_due ${(commercialization.renewal_due_accounts || {}).count ?? 0} · churn_risk ${(commercialization.churn_risk_accounts || {}).count ?? 0}\n` +
            `dunning ${(commercialization.dunning_runs || {}).count ?? 0} · pilot_ready ${(commercialization.pilot_conversion || {}).ready_count ?? 0} · expansion ${(commercialization.expansion_candidates || {}).recommended_count ?? 0}\n` +
            `support backlog ${(commercialization.support_backlog || {}).count ?? 0} · dispute backlog ${(commercialization.dispute_backlog || {}).count ?? 0}`,
        })
      );
    }
    if (commercialization.launch_week_alert_pack?.summary) {
      const pack = commercialization.launch_week_alert_pack;
      dom.opsRuntimeIncidentSnapshot.appendChild(
        createListCard({
          title: "Launch Week Alert Pack",
          score: `${pack.summary.alert_count ?? 0} alerts`,
          body:
            `severity ${(pack.summary.by_severity && Object.entries(pack.summary.by_severity).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\n` +
            `owners ${(pack.summary.by_owner_role && Object.entries(pack.summary.by_owner_role).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\n` +
            `${(pack.alerts || []).map((item) => `${item.alert_key} · ${item.severity} · ${item.owner_role}\ncount ${item.count ?? 0}\n${item.summary}\nrefs ${(item.drilldown_refs || []).map((ref) => `${ref.kind}:${ref.id}`).join(" / ") || "-"}`).join("\n\n") || "-"}`
        })
      );
    }
  }

  if (!opsState.opsProviderRouting) {
    clearNode(dom.opsProviderRouting, "这里会显示通道路由策略，以及候选链路和渲染链路的当前路由配置。");
  } else {
    const policy = opsState.opsProviderRouting;
    dom.opsProviderRouting.appendChild(
      createListCard({
        title: "通道路由策略",
        score: `${policy.candidate?.backend_present ? "候选链路已启用" : "候选链路已关闭"} · ${policy.renderer?.backend_present ? "渲染链路已启用" : "渲染链路已关闭"}`,
        body:
          `候选链路通道 ${(policy.candidate?.provider_order || []).join(" / ") || "-"}\n` +
          `候选链路重试 ${policy.candidate?.retry_policy?.max_attempts ?? "-"} · 缓存 ${policy.candidate?.cache_policy?.enabled ? `启用:${policy.candidate?.cache_policy?.max_entries}` : "关闭"} · 预算 ${policy.candidate?.budget_policy?.max_prompt_chars ?? "-"}/${policy.candidate?.budget_policy?.max_estimated_cost_usd ?? "-"}\n` +
          `候选链路回退 ${(policy.candidate?.fallback_chain || []).join(" -> ") || "-"}\n\n` +
          `渲染链路通道 ${(policy.renderer?.provider_order || []).join(" / ") || "-"}\n` +
          `渲染链路重试 ${policy.renderer?.retry_policy?.max_attempts ?? "-"} · 缓存 ${policy.renderer?.cache_policy?.enabled ? `启用:${policy.renderer?.cache_policy?.max_entries}` : "关闭"} · 预算 ${policy.renderer?.budget_policy?.max_prompt_chars ?? "-"}/${policy.renderer?.budget_policy?.max_estimated_cost_usd ?? "-"}\n` +
          `渲染链路回退 ${(policy.renderer?.fallback_chain || []).join(" -> ") || "-"}`
      })
    );
  }

  if (!opsState.opsProviderRollout) {
    clearNode(dom.opsProviderRollout, "这里会显示候选链路和渲染链路的灰度、全量启用与回滚控制。");
  } else {
    const rollout = opsState.opsProviderRollout;
    const candidate = rollout.tracks?.candidate || {};
    const renderer = rollout.tracks?.renderer || {};
    dom.opsProviderRollout.appendChild(
      createListCard({
        title: "通道灰度摘要",
        score: rollout.recommended_next_action || "-",
        body:
          `全量启用 ${(rollout.active_tracks || []).join(" / ") || "-"} · 灰度中 ${(rollout.canary_tracks || []).join(" / ") || "-"} · 已回滚 ${(rollout.rolled_back_tracks || []).join(" / ") || "-"}\n` +
          `候选链路 ${candidate.rollout_status || "-"} · 分桶 ${candidate.bucket_percentage ?? 0}% · 白名单 ${(candidate.world_allowlist || []).join(" / ") || "-"}\n` +
          `渲染链路 ${renderer.rollout_status || "-"} · 分桶 ${renderer.bucket_percentage ?? 0}% · 白名单 ${(renderer.world_allowlist || []).join(" / ") || "-"}`
      })
    );
  }

    if (!opsState.opsProviderRuntimeMetrics) {
      clearNode(dom.opsProviderRuntimeMetrics, "这里会显示通道运行指标与成本趋势看板。");
    } else {
      const metrics = opsState.opsProviderRuntimeMetrics;
    const rolloutStageCard = createListCard({
      title: "灰度阶段对比",
      score: "影子 / 灰度 / 全量",
      body: opsSections(
        opsSection("候选链路", [
          opsParagraphList(metrics.rollout_stage_summary?.candidate || [], (item) => opsStageMetricParagraph("candidate", item)),
        ]),
        opsSection("渲染链路", [
          opsParagraphList(metrics.rollout_stage_summary?.renderer || [], (item) => opsStageMetricParagraph("renderer", item)),
        ])
      )
    });
    dom.opsProviderRuntimeMetrics.appendChild(rolloutStageCard);
    dom.opsProviderRuntimeMetrics.appendChild(
      createListCard({
        title: "通道运行指标",
        score: `${metrics.receipt_count ?? 0} 条回执`,
        body: opsSections(
          opsSection("总览", [
            opsFieldLine("总成本", opsCostValue(metrics.total_estimated_cost, 3)),
            opsFieldLine("运行时延迟", opsLatencyValue(metrics.latency_summary?.runtime?.avg_latency_ms)),
            opsFieldLine("运行时 P95", opsLatencyValue(metrics.latency_summary?.runtime?.p95_latency_ms)),
            opsFieldLine("候选延迟", opsLatencyValue(metrics.latency_summary?.candidate?.avg_latency_ms)),
            opsFieldLine("渲染延迟", opsLatencyValue(metrics.latency_summary?.renderer?.avg_latency_ms)),
            opsPairsLine("入口分布", metrics.surface_summary || {}),
            opsPairsLine("动作分布", metrics.action_summary || {}),
          ]),
          opsSection("通道明细", [
            opsParagraphList(metrics.provider_summary || [], (item) => opsProviderMetricParagraph(item)),
          ]),
          opsSection("成本趋势", [
            opsParagraphList(metrics.cost_trend || [], (item) => opsCostTrendParagraph(item)),
          ]),
          opsSection("延迟趋势", [
            opsParagraphList(metrics.latency_trend || [], (item) => opsLatencyTrendParagraph(item)),
          ])
        )
        })
      );
    }

    if (!(opsState.opsStoryBootstrapWorldSummary || []).length) {
      clearNode(dom.opsStoryBootstrapWorldSummary, "这里会显示 Story bootstrap 首轮质量门碰撞摘要。");
    } else {
      const bootstrapWorlds = opsState.opsStoryBootstrapWorldSummary || [];
      const attemptedCount = bootstrapWorlds.reduce((sum, item) => sum + Number(item.attemptedCount || 0), 0);
      const firstFailed = bootstrapWorlds.reduce((sum, item) => sum + Number(item.firstAttemptQualityGuardFailedCount || 0), 0);
      const finalFailed = bootstrapWorlds.reduce((sum, item) => sum + Number(item.finalQualityGuardFailedCount || 0), 0);
      dom.opsStoryBootstrapWorldSummary.appendChild(
        createListCard({
          title: "Story Bootstrap 质量门碰撞摘要",
          score: `${bootstrapWorlds.length} 个 worlds`,
          body:
            `${opsFieldLine("总尝试", attemptedCount)} · ${opsFieldLine("首轮失败", firstFailed)} · ${opsFieldLine("最终失败", finalFailed)}\n` +
            `${opsFieldLine("首轮失败率", formatPercent(firstFailed / Math.max(1, attemptedCount)))} · ${opsFieldLine("最终失败率", formatPercent(finalFailed / Math.max(1, attemptedCount)))}\n` +
            `${opsFieldLine("当前 drill-down", opsWorldLabel(opsState.selectedOpsWorldId || bootstrapWorlds[0]?.worldId || "-"))}`
        })
      );
      bootstrapWorlds.forEach((item) => {
        const card = createListCard({
          title: `Bootstrap · ${opsWorldLabel(item.worldId)}`,
          score: `${Number(item.qualityGuardCollisionDelta || 0).toFixed(3)} Δ`,
          body:
            `${opsFieldLine("总尝试", item.attemptedCount ?? 0)} · ${opsFieldLine("首轮失败", item.firstAttemptQualityGuardFailedCount ?? 0)} · ${opsFieldLine("最终失败", item.finalQualityGuardFailedCount ?? 0)}\n` +
            `${opsFieldLine("首轮失败率", formatPercent(item.firstAttemptQualityGuardFailedRate || 0))} · ${opsFieldLine("最终失败率", formatPercent(item.finalQualityGuardFailedRate || 0))}\n` +
            `${opsFieldLine("重试恢复率", formatPercent(item.retriedRecoveryRate || 0))} · ${opsFieldLine("碰撞降幅", Number(item.qualityGuardCollisionDelta || 0).toFixed(3))}`
        });
        if (item.worldId === opsState.selectedOpsWorldId) {
          card.classList.add("is-active");
        }
        card.addEventListener("click", async () => {
          opsState.selectedOpsWorldId = item.worldId;
          syncOpsNavigationContext({ world_id: item.worldId }, { preserveExisting: true });
          await refreshOpsSurface({ scopes: ["runtime", "navigation"] });
        });
        dom.opsStoryBootstrapWorldSummary.appendChild(card);
      });
    }

    if (!opsState.opsStoryBootstrapWorldDetail?.world) {
      clearNode(dom.opsStoryBootstrapWorldDetail, "这里会显示选中 world 的 Story bootstrap 重试明细。");
    } else {
      const detail = opsState.opsStoryBootstrapWorldDetail;
      dom.opsStoryBootstrapWorldDetail.appendChild(
        createListCard({
          title: `Bootstrap Drill-Down · ${opsWorldLabel(detail.world.worldId)}`,
          score: `${detail.rows?.length ?? 0} 条`,
          body:
            `${opsFieldLine("总尝试", detail.world.attemptedCount ?? 0)} · ${opsFieldLine("首轮失败率", formatPercent(detail.world.firstAttemptQualityGuardFailedRate || 0))} · ${opsFieldLine("最终失败率", formatPercent(detail.world.finalQualityGuardFailedRate || 0))}\n` +
            `${opsFieldLine("重试恢复率", formatPercent(detail.world.retriedRecoveryRate || 0))} · ${opsFieldLine("碰撞降幅", Number(detail.world.qualityGuardCollisionDelta || 0).toFixed(3))}\n\n` +
            `最近结果：\n${(detail.rows || []).map((item) =>
              `${item.sessionId || "-"} · ${item.worldVersionId || "-"}\n` +
              `attempts ${item.attemptCount ?? 0} · first ${item.firstAttemptResultStatus || "-"} · final ${item.finalResultStatus || "-"}\n` +
              `recovered ${item.recoveredAfterRetry ? "yes" : "no"} · intent ${item.bootstrapIntent || "-"} · ${formatTimestamp(item.occurredAt)}`
            ).join("\n\n") || "-"}`
        })
      );
    }

  clearNode(dom.opsMeterList);
  if (!opsState.opsMeters.length) {
    clearNode(dom.opsMeterList, "继续阅读发生后，这里会出现 meter 记录。");
  } else {
    opsState.opsMeters.forEach((meter) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${meter.action_type}</h3>
          <span class="list-card-score">${Number(meter.estimated_cost || 0).toFixed(3)}</span>
        </div>
        <p class="list-card-body">${meter.world_version_id || "-"}\n${meter.session_id || "-"}\nunits ${Number(meter.usage_units || 0).toFixed(3)} · wallet ${meter.wallet_type || "-"}\ntier ${meter.subscription_tier || "-"} · rule ${meter.model_policy_version || "-"}</p>
      `;
      dom.opsMeterList.appendChild(card);
    });
  }
}

function renderOpsJobsSection() {
  clearNode(dom.opsAsyncJobSummary);
  clearNode(dom.opsAsyncJobBootReconcile);
  clearNode(dom.opsAsyncJobIncidents);
  clearNode(dom.opsAsyncJobArtifactRetention);
  clearNode(dom.opsAsyncJobOperatorHistory);
  clearNode(dom.opsAsyncJobHandoffBundle);
  clearNode(dom.opsAsyncJobAdapterValidation);
  clearNode(dom.opsAsyncJobAdapterHealthProbe);
  clearNode(dom.opsAsyncJobNotificationReceipts);
  clearNode(dom.opsAsyncNotificationRetryQueue);
  clearNode(dom.opsAsyncNotificationDeadLetterQueue);
  clearNode(dom.opsAsyncRetryOutcomeDashboard);
  clearNode(dom.opsAsyncJobs);
  if (!opsState.opsAsyncJobSummary) {
    clearNode(dom.opsAsyncJobSummary, "这里会显示长任务队列摘要。");
    clearNode(dom.opsAsyncJobBootReconcile, "这里会显示启动时异步对账器的处理结果。");
    clearNode(dom.opsAsyncJobIncidents, "这里会显示失败、排队中和长时间运行任务的事故恢复摘要。");
    clearNode(dom.opsAsyncJobArtifactRetention, "这里会显示异步任务产物保留与保留状态。");
    clearNode(dom.opsAsyncJobOperatorHistory, "这里会显示运营操作历史。");
    clearNode(dom.opsAsyncJobHandoffBundle, "这里会显示异步任务交接包与确认摘要。");
    clearNode(dom.opsAsyncJobAdapterValidation, "这里会显示异步适配器配置校验结果。");
    clearNode(dom.opsAsyncJobAdapterHealthProbe, "这里会显示异步适配器健康探测结果。");
    clearNode(dom.opsAsyncJobNotificationReceipts, "这里会显示通知送达回执。");
    clearNode(dom.opsAsyncNotificationRetryQueue, "这里会显示通知重试队列。");
    clearNode(dom.opsAsyncNotificationDeadLetterQueue, "这里会显示通知死信队列。");
    clearNode(dom.opsAsyncRetryOutcomeDashboard, "这里会显示重试结果看板。");
    clearNode(dom.opsAsyncJobs, "这里会显示学习层训练和运行时备份相关的异步工作流状态。");
  } else {
    const summary = opsState.opsAsyncJobSummary;
    dom.opsAsyncJobSummary.appendChild(
      createListCard({
        title: "异步任务摘要",
        score: `${summary.job_count ?? 0} 个任务`,
        body: opsSections(
          opsSection("总体分布", [
            opsPairsLine("状态分布", summary.by_status || {}, opsStatusLabel),
            opsPairsLine("任务类型分布", summary.by_type || {}),
            opsFieldLine("支持的任务类型", (summary.supported_job_types || []).join(" / ") || "-"),
            opsPairsLine("租约状态", summary.by_lease_status || {}, opsStatusLabel),
          ]),
          opsSection("最近完成", [
            opsFieldLine("任务 ID", summary.latest_finished_job?.job_id || "-"),
            opsFieldLine("状态", opsStatusLabel(summary.latest_finished_job?.status || "-")),
          ])
        )
      })
    );
    const boot = opsState.opsAsyncJobBootReconcile || {};
    dom.opsAsyncJobBootReconcile.appendChild(
      createListCard({
        title: "启动时异步对账器",
        score: `${boot.reconciled_count ?? 0} 个已对账`,
        body: opsSections(
          opsSection("基本信息", [
            opsFieldLine("发起人", boot.requested_by || "-"),
            opsFieldLine("建议动作", boot.recommended_action || "-"),
          ]),
          opsSection("已处理任务", [
            opsFieldLine("任务列表", (boot.reconciled_jobs || []).map((item) => `${item.job_id}:${item.last_recovery_action || "-"}`).join(" / ") || "-"),
          ])
        )
      })
    );
    const incidents = opsState.opsAsyncJobIncidents || {};
    dom.opsAsyncJobIncidents.appendChild(
      createListCard({
        title: "异步任务事故恢复",
        score: opsStatusLabel(incidents.status || "-"),
        body: opsSections(
          opsSection("总体判断", [
            opsFieldLine("建议动作", incidents.recommended_action || "-"),
            opsFieldLine("失败任务", incidents.failed_count ?? 0),
            opsFieldLine("排队中任务", incidents.queued_count ?? 0),
            opsFieldLine("长时间运行任务", incidents.stale_running_count ?? 0),
            opsFieldLine("租约过期任务", incidents.expired_lease_count ?? 0),
            opsFieldLine("可恢复任务", incidents.recoverable_count ?? 0),
          ]),
          opsSection("任务类型分布", [
            opsPairsLine("类型", incidents.by_type || {}),
          ]),
          opsSection("重点任务", [
            opsFieldLine("失败任务列表", (incidents.failed_jobs || []).map((item) => item.job_id).join(" / ") || "-"),
            opsFieldLine("长时间运行任务列表", (incidents.stale_running_jobs || []).map((item) => item.job_id).join(" / ") || "-"),
          ])
        )
      })
    );
    const retention = opsState.opsAsyncJobArtifactRetention || {};
    const remoteShipping = opsState.opsAsyncJobRemoteShipping || {};
    dom.opsAsyncJobArtifactRetention.appendChild(
      createListCard({
        title: "异步任务产物保留",
        score: `${retention.jobs_with_artifacts ?? 0} 个任务`,
        body: opsSections(
          opsSection("总体情况", [
            opsFieldLine("产物总数", retention.total_artifact_count ?? 0),
            opsFieldLine("总字节数", retention.total_bytes ?? 0),
            opsFieldLine("默认远端适配器", remoteShipping.registry?.default_adapter || "-"),
            opsFieldLine("可用远端适配器", (remoteShipping.registry?.available_adapters || []).join(" / ") || "-"),
          ]),
          opsSection("保留状态", [
            opsPairsLine("产物状态", retention.by_status || {}, opsStatusLabel),
            opsFieldLine("即将过期", retention.expiring_soon_count ?? 0),
            opsFieldLine("已过期", retention.expired_count ?? 0),
            opsFieldLine("缺失", retention.missing_count ?? 0),
            opsPairsLine("远端状态", remoteShipping.by_status || {}, opsStatusLabel),
          ]),
          opsSection("任务列表", [
            opsFieldLine("任务", (retention.artifact_jobs || []).map((item) => `${item.job_id}:${opsStatusLabel(item.artifact_status)}`).join(" / ") || "-"),
          ])
        )
      })
    );
    const operatorHistory = opsState.opsAsyncJobOperatorHistory || {};
    dom.opsAsyncJobOperatorHistory.appendChild(
      createListCard({
        title: "运营操作历史",
        score: `${operatorHistory.entry_count ?? 0} 条记录`,
        body: opsSections(
          opsSection("分布", [
            opsPairsLine("操作人", operatorHistory.by_operator || {}),
            opsPairsLine("动作", operatorHistory.by_action || {}),
          ]),
          opsSection("最近记录", [
            opsFieldLine("最近操作", (operatorHistory.latest_entries || []).map((item) => `${item.operator_id || "-"}:${item.action}@${item.job_id}`).join(" / ") || "-"),
          ])
        )
      })
    );
    const handoff = opsState.opsAsyncJobHandoffBundle || {};
    const bundle = handoff.handoff_bundle || handoff;
    const handoffSla = opsState.opsAsyncJobHandoffSla || {};
    dom.opsAsyncJobHandoffBundle.appendChild(
      createListCard({
        title: "异步任务交接包",
        score: `${bundle.acknowledgement_summary?.pending_count ?? 0} 条待确认`,
        body:
          `推荐动作 ${bundle.recommended_next_action || "-"}\n` +
          `通知接收端 ${(bundle.notification_sinks?.default_sink || "-")} · ${(bundle.notification_sinks?.available_sinks || []).join(" / ") || "-"}\n` +
          `需要确认 ${bundle.acknowledgement_summary?.required_count ?? 0} · 待确认 ${bundle.acknowledgement_summary?.pending_count ?? 0} · 已确认 ${bundle.acknowledgement_summary?.acknowledged_count ?? 0}\n` +
          `超时 ${handoffSla.overdue_count ?? 0} · 待处理 ${handoffSla.pending_count ?? 0}\n` +
          `任务 ${(bundle.jobs_requiring_handoff || []).map((item) => `${item.job_id}:${item.acknowledgement_status}/${item.handoff_sla_status || "-"}/${item.remote_shipping_status || "-"}`).join(" / ") || "-"}\n` +
          `导出 ${handoff.export_path || "-"} · 通知 ${handoff.notification_receipt?.sink_name || "-"}`
      })
    );
    const adapterValidation = opsState.opsAsyncJobAdapterValidation || {};
    dom.opsAsyncJobAdapterValidation.appendChild(
      createListCard({
        title: "异步适配器配置校验",
        score: adapterValidation.valid ? "配置正常" : "配置异常",
        body:
          `远端 ${adapterValidation.remote_shipping?.valid ? "正常" : "异常"} · 默认 ${(adapterValidation.remote_shipping?.config_source?.resolved_default_adapter || "-")}\n` +
          `接收端 ${adapterValidation.notification_sinks?.valid ? "正常" : "异常"} · 默认 ${(adapterValidation.notification_sinks?.config_source?.resolved_default_sink || "-")}\n` +
          `远端检查 ${(adapterValidation.remote_shipping?.checks || []).map((item) => `${item.adapter_name}:${item.valid ? "正常" : (item.issues || []).join("/")}`).join(" / ") || "-"}\n` +
          `接收端检查 ${(adapterValidation.notification_sinks?.checks || []).map((item) => `${item.sink_name}:${item.valid ? "正常" : (item.issues || []).join("/")}`).join(" / ") || "-"}`
      })
    );
    const adapterProbe = opsState.opsAsyncJobAdapterHealthProbe || {};
    dom.opsAsyncJobAdapterHealthProbe.appendChild(
      createListCard({
        title: "异步适配器健康探测",
        score: adapterProbe.status || "-",
        body:
          `远端默认 ${(adapterProbe.remote_shipping?.default_probe?.status || "-")} · ${(adapterProbe.remote_shipping?.default_adapter || "-")}\n` +
          `接收端默认 ${(adapterProbe.notification_sinks?.default_probe?.status || "-")} · ${(adapterProbe.notification_sinks?.default_sink || "-")}\n` +
          `远端探测 ${Object.entries(adapterProbe.remote_shipping?.probes || {}).map(([key, value]) => `${key}=${value.status}`).join(" / ") || "-"}\n` +
          `接收端探测 ${Object.entries(adapterProbe.notification_sinks?.probes || {}).map(([key, value]) => `${key}=${value.status}`).join(" / ") || "-"}`
      })
    );
    const notificationReceipts = opsState.opsAsyncJobNotificationReceipts || {};
    dom.opsAsyncJobNotificationReceipts.appendChild(
      createListCard({
        title: "通知送达回执",
        score: `${notificationReceipts.receipt_count ?? 0} 条回执`,
        body:
          `接收端 ${Object.entries(notificationReceipts.by_sink || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `事件 ${Object.entries(notificationReceipts.by_event_type || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `状态 ${Object.entries(notificationReceipts.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `最近回执 ${(notificationReceipts.latest_receipts || []).map((item) => `#${item.event_id || "-"}:${item.sink_name || "-"}:${item.event_type || "-"}:${item.target_exists ? "存在" : "缺失"}`).join(" / ") || "-"}`
      })
    );
    const retryQueue = opsState.opsAsyncNotificationRetryQueue || {};
    const retryPolicies = opsState.opsAsyncRetryPolicies || {};
    dom.opsAsyncNotificationRetryQueue.appendChild(
      createListCard({
        title: "通知重试队列",
        score: `${retryQueue.retry_count ?? 0} 次重试`,
        body:
          `默认策略 ${retryPolicies.default_policy_id || "-"}\n` +
          `可用策略 ${(retryPolicies.available_policy_ids || []).join(" / ") || "-"}\n` +
          `状态 ${Object.entries(retryQueue.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `最近重试 ${(retryQueue.retries || []).map((item) => `${item.retry_id || "-"}:${item.status || "-"}:${item.source_event_type || "-"}:${item.process_count || 0}:${item.failure_classification?.failure_class || "-"}/${item.retry_decision || "-"}`).join(" / ") || "-"}`
      })
    );
    const deadLetters = opsState.opsAsyncNotificationDeadLetterQueue || {};
    dom.opsAsyncNotificationDeadLetterQueue.appendChild(
      createListCard({
        title: "通知死信队列",
        score: `${deadLetters.dead_letter_count ?? 0} 条死信`,
        body:
          `status ${Object.entries(deadLetters.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `failure ${Object.entries(deadLetters.by_failure_class || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `最近死信 ${(deadLetters.dead_letters || []).map((item) => `${item.dead_letter_id || "-"}:${item.failure_classification?.failure_class || "-"}`).join(" / ") || "-"}`
      })
    );
    const retryOutcome = opsState.opsAsyncRetryOutcomeDashboard || {};
    dom.opsAsyncRetryOutcomeDashboard.appendChild(
      createListCard({
        title: "重试结果看板",
        score: `${retryOutcome.retry_count ?? 0} 次重试`,
        body:
          `成功 ${(retryOutcome.successful_retry_count ?? 0)} · 计划内 ${(retryOutcome.planned_retry_count ?? 0)} · 最终失败 ${(retryOutcome.terminal_failure_count ?? 0)} · 成功率 ${retryOutcome.success_rate ?? "-"}\n` +
          `状态 ${Object.entries(retryOutcome.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `决策 ${Object.entries(retryOutcome.by_retry_decision || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `失败类型 ${Object.entries(retryOutcome.by_failure_class || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`
      })
    );
    if (!opsState.opsAsyncJobs.length) {
      clearNode(dom.opsAsyncJobs, "这里会显示学习层训练和运行时备份相关的异步工作流状态。");
    } else {
      opsState.opsAsyncJobs.forEach((job) => {
        const card = createListCard({
          title: `${job.job_type || "job"} · ${job.job_id || "-"}`,
          score: job.status || "-",
          body:
              `requested by ${job.requested_by || "-"}\n` +
              `queued ${formatTimestamp(job.created_at)} · started ${job.started_at ? formatTimestamp(job.started_at) : "-"} · finished ${job.finished_at ? formatTimestamp(job.finished_at) : "-"}\n` +
              `duration ${job.duration_seconds ?? "-"}s\n` +
              `lease ${job.lease_status || "-"} · owner ${job.lease_owner || "-"} · expires ${job.lease_expires_at ? formatTimestamp(job.lease_expires_at) : "-"}\n` +
              `heartbeat ${job.heartbeat_at ? formatTimestamp(job.heartbeat_at) : "-"} · count ${job.heartbeat_count ?? 0}\n` +
              `retention ${job.artifact_retention_days ?? "-"}d · until ${job.artifact_retention_until ? formatTimestamp(job.artifact_retention_until) : "-"}\n` +
              `remote ${job.remote_shipping_status || "not_shipped"} · ${job.remote_shipped_at ? formatTimestamp(job.remote_shipped_at) : "-"}\n` +
              `sla ${job.handoff_sla_status || "-"} · due ${job.handoff_sla_due_at ? formatTimestamp(job.handoff_sla_due_at) : "-"}\n` +
              `ack ${job.acknowledged_by || "-"} · ${job.acknowledged_at ? formatTimestamp(job.acknowledged_at) : "-"}\n` +
              `steps ${(job.workflow?.steps || []).map((item) => `${item.label}:${item.status}`).join(" / ") || "-"}\n` +
              `payload ${job.job_type === "learned_training" ? `tracks ${(job.payload?.tracks || []).join(" / ") || "-"}` : `label ${job.payload?.label || "-"}${job.result_summary?.backup_path ? ` · path ${job.result_summary.backup_path}` : ""}`}\n` +
              `result ${job.job_type === "learned_training" ? `ok ${(job.result_summary?.tracks_succeeded || []).join(" / ") || "-"} · failed ${(job.result_summary?.tracks_failed || []).join(" / ") || "-"}` : job.result_summary?.status || "-"}\n` +
            `recovery ${(job.recovery_history || []).map((item) => `${item.action}@${item.occurred_at}`).join(" / ") || "-"}\n` +
            `error ${job.error || "-"}`
        });
        card.addEventListener("click", () => {
          if (dom.opsAsyncJobId) {
            dom.opsAsyncJobId.value = job.job_id || "";
          }
          if (dom.opsAsyncJobNote) {
            dom.opsAsyncJobNote.value = job.acknowledgement_note || "";
          }
        });
        dom.opsAsyncJobs.appendChild(card);
      });
    }
  }
}

function renderOpsAccountSection() {
  clearNode(dom.opsSubscriptionAudit);
  clearNode(dom.opsAccountWorkspaceSummary);
  clearNode(dom.opsAccountWorkspaceActions);
  clearNode(dom.opsAccountWorkspaceTimeline);
  if (!opsState.opsSubscriptionAudit) {
    clearNode(dom.opsSubscriptionAudit, "这里会显示当前账户的订阅与钱包情况。");
  } else {
    const audit = opsState.opsSubscriptionAudit;
    const card = document.createElement("article");
    card.className = "list-card";
    const subscriptions = (audit.subscriptions || []).map((item) => `${item.tier_id} · ${item.status} · ${item.provider}\n周期结束 ${item.period_end || "-"}\n到期取消 ${item.cancel_at_period_end ? "是" : "否"}\n下一步 ${item.next_action || "-"}\n原因 ${item.lifecycle_reason || "-"}`).join("\n\n") || "暂无";
    const entitlements = (audit.entitlements || []).map((item) => `${item.entitlement_id}\n${item.entitlement_type} · ${item.wallet_type || item.tier_id || "-"} · ${item.status}\n余额 ${item.balance ?? "-"} · 原因 ${item.reason || "-"}`).join("\n\n") || "暂无";
    const wallets = Object.entries(audit.wallets || {})
      .map(([walletType, value]) => `${walletType}=${Number(value.balance || 0).toFixed(0)} · ${opsStatusLabel(value.status || "-")}`)
      .join("\n") || "暂无";
    const events = (audit.events || [])
      .map((item) => `${item.event_name} · ${formatTimestamp(item.occurred_at)}\n${Object.entries(item.payload_json || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`)
      .join("\n\n") || "暂无";
    const matrix = audit.entitlement_matrix || {};
    const matrixSummary = [
      `配置版本 ${audit.config_version || "-"}`,
      `阅读继续 -> ${(matrix.reader?.continue_story?.required_tier || "-")} / ${(matrix.reader?.continue_story?.wallet_type || "-")}`,
      `创作起稿 -> ${(matrix.author?.draft_from_brief?.required_tier || "-")} / ${(matrix.author?.draft_from_brief?.wallet_type || "-")}`,
      `创作模拟 -> ${(matrix.author?.simulate?.required_tier || "-")} / ${(matrix.author?.simulate?.wallet_type || "-")}`,
    ].join("\n");
    const auditSummary = [
      `权益数量 ${audit.audit_summary?.entitlement_count ?? 0}`,
      `状态 ${Object.entries(audit.audit_summary?.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `类型 ${Object.entries(audit.audit_summary?.entitlement_type_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `最近时间 ${audit.audit_summary?.latest_event_at || "-"}`,
      `生命周期事件 ${audit.lifecycle_history_summary?.event_count ?? 0} · 重试 ${audit.lifecycle_history_summary?.retry_attempt_count ?? 0}`,
    ].join("\n");
    const checkoutSessions = (audit.recent_checkout_sessions || []).map((item) => `${item.checkout_session_id} · ${item.status} · ${item.tier_id}\n过期时间 ${item.expires_at || "-"} · 订阅 ${item.subscription_id || "-"}`).join("\n\n") || "暂无";
    card.innerHTML = renderLocalizedCardHtml(
      audit.account_id,
      `${(audit.subscriptions || []).length} 条订阅`,
      `订阅：\n${subscriptions}\n\n钱包：\n${wallets}\n\n权益：\n${entitlements}\n\n支付会话：\n${checkoutSessions}\n\n审计摘要：\n${auditSummary}\n\n权益矩阵：\n${matrixSummary}\n\n事件：\n${events}`
    );
    dom.opsSubscriptionAudit.appendChild(card);
  }

  clearNode(dom.opsSubscriptionTimeline);
  if (!opsState.opsSubscriptionAudit?.audit_timeline?.length) {
    clearNode(dom.opsSubscriptionTimeline, "这里会显示权益授予、撤销与生命周期的审计时间线。");
  } else {
    opsState.opsSubscriptionAudit.audit_timeline.forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = renderLocalizedCardHtml(
        item.event_name,
        item.status || "-",
        `${formatTimestamp(item.occurred_at)}\n权益 ${item.entitlement_id || "-"}\n订阅 ${item.subscription_id || "-"}\n钱包 ${item.wallet_type || "-"} · 档位 ${item.tier_id || "-"}\n原因 ${item.reason || "-"} · 余额 ${item.balance ?? "-"}`
      );
      if (item.entitlement_id && dom.opsEntitlementId) {
        card.addEventListener("click", () => {
          dom.opsEntitlementId.value = item.entitlement_id;
        });
      }
      dom.opsSubscriptionTimeline.appendChild(card);
    });
    (opsState.opsSubscriptionAudit?.lifecycle_history_summary?.latest_events || []).forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = renderLocalizedCardHtml(
        item.event_type || "-",
        item.status || "-",
        `${formatTimestamp(item.occurred_at)}\n通道 ${item.provider || "-"}\n订阅 ${item.subscription_id || "-"}\n支付会话 ${item.checkout_session_id || "-"}\n通道事件 ${item.provider_event_id || "-"}\n处理时间 ${item.processed_at || "-"}`
      );
      if (item.event_id && dom.opsBillingEventId) {
        card.addEventListener("click", () => {
          dom.opsBillingEventId.value = item.event_id;
        });
      }
      dom.opsSubscriptionTimeline.appendChild(card);
    });
    (opsState.opsSubscriptionAudit?.lifecycle_history_summary?.latest_retry_attempts || []).forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = renderLocalizedCardHtml(
        item.retry_attempt_id,
        item.status || "-",
        `${formatTimestamp(item.updated_at)}\n订阅 ${item.subscription_id || "-"}\n原因 ${item.retry_reason || "-"}\n次数 ${item.attempt_count || 0}\n下次时间 ${item.next_retry_at || "-"}`
      );
      dom.opsSubscriptionTimeline.appendChild(card);
    });
  }

  clearNode(dom.opsAccountDetail);
  clearNode(dom.opsAccountActivity);
  clearNode(dom.opsSupportSummary);
  clearNode(dom.opsSupportIssues);
  clearNode(dom.opsAlertSummary);
  clearNode(dom.opsAlertFeed);
  clearNode(dom.opsAlertDetail);
  clearNode(dom.opsGovernanceSummary);
  clearNode(dom.opsGovernanceCases);
  clearNode(dom.opsGovernanceDetail);
  clearNode(dom.opsGovernanceExport);
  clearNode(dom.opsAccountAuditSummary);
  clearNode(dom.opsAccountAuditTrail);
  if (!opsState.opsAccountDetail) {
    clearNode(dom.opsAccountWorkspaceSummary, "这里会显示当前账户的运营摘要。");
    clearNode(dom.opsAccountWorkspaceActions, "这里会显示当前账户的快捷动作与推荐处置顺序。");
    clearNode(dom.opsAccountWorkspaceTimeline, "这里会显示账户级运营时间线。");
    clearNode(dom.opsAccountDetail, "这里会显示当前账户的订阅、钱包、权限与最近活动。");
    clearNode(dom.opsAccountActivity, "这里会显示当前账户最近的会话、草稿和计量记录。");
    clearNode(dom.opsSupportSummary, "这里会显示当前账户的客服摘要与推荐动作。");
    clearNode(dom.opsSupportIssues, "这里会显示当前账户的客服问题定位结果。");
    clearNode(dom.opsAlertSummary, "这里会显示当前告警流的统计摘要。");
    clearNode(dom.opsAlertFeed, "这里会显示主动告警列表。");
    clearNode(dom.opsAlertDetail, "这里会显示选中告警的标准处置包、运行手册和排查引用。");
    clearNode(dom.opsGovernanceSummary, "这里会显示当前账户的权益、治理与滥用个案摘要。");
    clearNode(dom.opsGovernanceCases, "这里会显示当前账户关联的治理个案列表。");
    clearNode(dom.opsGovernanceDetail, "这里会显示选中治理个案的深度详情。");
    clearNode(dom.opsGovernanceExport, "这里会显示治理审计导出摘要。");
    clearNode(dom.opsAccountAuditSummary, "这里会显示当前账户的完整审计摘要。");
    clearNode(dom.opsAccountAuditTrail, "这里会显示当前账户的完整审计轨迹。");
  } else {
    const detail = opsState.opsAccountDetail;
    const workspace = opsState.opsAccountWorkspace || {};
    const governance = opsState.opsGovernanceSnapshot || {};
    const subscription = detail.subscription || {};
    const wallets = Object.entries(detail.wallets || {})
      .map(([walletType, value]) => `${walletType}=${Number(value.balance || 0).toFixed(0)} · ${value.status || "-"}`)
      .join("\n") || "暂无";
    const authorActions = detail.author_access?.actions || {};
    const gatingSummary = [
      `brief ${gatingStatusLabel(authorActions.draft_from_brief)} · ${authorActions.draft_from_brief?.wallet_type || "-"}`,
      `simulate ${gatingStatusLabel(authorActions.simulate)} · ${authorActions.simulate?.wallet_type || "-"}`,
      `save ${gatingStatusLabel(authorActions.save_draft)} · ${authorActions.save_draft?.wallet_type || "-"}`,
      `submit ${gatingStatusLabel(authorActions.submit_draft)} · ${authorActions.submit_draft?.wallet_type || "-"}`,
    ].join("\n");
    const workspaceSummary = workspace.workspace_summary || {};
    const walletPosture = workspace.wallet_posture || {};
    const entitlementPosture = workspace.entitlement_posture || {};
    if (!workspace.generated_at) {
      clearNode(dom.opsAccountWorkspaceSummary, "这里会显示当前账户的运营摘要。");
      clearNode(dom.opsAccountWorkspaceActions, "这里会显示当前账户的快捷动作与推荐处置顺序。");
      clearNode(dom.opsAccountWorkspaceTimeline, "这里会显示账户级运营时间线。");
    } else {
    dom.opsAccountWorkspaceSummary.appendChild(
        createListCard({
          title: `运营摘要 · ${workspace.account_id || detail.account_id}`,
          score: opsStatusLabel(workspaceSummary.health_status || "-"),
          body:
            `${opsFieldLine("订阅状态", opsStatusLabel(workspaceSummary.subscription_status || "-"))} · ${opsFieldLine("会员方案", workspaceSummary.tier_id || "-")}\n` +
            `${opsFieldLine("告警数", workspaceSummary.actionable_alert_count ?? 0)} · ${opsFieldLine("客服问题", workspaceSummary.support_issue_count ?? 0)} · ${opsFieldLine("治理个案", workspaceSummary.open_governance_case_count ?? 0)} · ${opsFieldLine("限制", workspaceSummary.active_restriction_count ?? 0)}\n` +
            `${opsFieldLine("推荐路径", workspaceSummary.recommended_path || "-")}\n` +
            `${opsFieldLine("阅读面", `${opsStatusLabel(workspaceSummary.surface_statuses?.reader?.status || "-")} · ${workspaceSummary.surface_statuses?.reader?.reason || "-"}`)}\n` +
            `${opsFieldLine("创作面", `${opsStatusLabel(workspaceSummary.surface_statuses?.author?.status || "-")} · ${workspaceSummary.surface_statuses?.author?.reason || "-"}`)}\n\n` +
            `钱包情况：\n${(walletPosture.wallets || []).map((item) => `${item.wallet_type}=${Number(item.balance || 0).toFixed(0)} · ${opsStatusLabel(item.status || "-")}${item.anomaly ? " · 异常" : ""}`).join("\n") || "-"}\n\n` +
            `${opsFieldLine("权益总数", entitlementPosture.total_entitlements ?? 0)} · ${opsFieldLine("可撤销项", (entitlementPosture.revoke_candidates || []).length)}\n` +
            `${opsPairsLine("权益状态分布", entitlementPosture.status_counts || {}, opsStatusLabel)}\n\n` +
            `阻塞项：\n${(workspace.top_blockers || []).map((item) => `${item.headline} · ${item.severity}\n${item.summary}`).join("\n\n") || "-"}`
        })
      );
      if (!(workspace.action_pack || []).length) {
        clearNode(dom.opsAccountWorkspaceActions, "这里会显示当前账户的快捷动作与推荐处置顺序。");
      } else {
      const actionCard = createListCard({
        title: "快捷动作",
        score: `${(workspace.action_pack || []).length} 个动作`,
        body: (workspace.action_pack || []).map((item) => `${item.label} · ${opsActionModeLabel(item.mode)}\n${item.reason || "-"}`).join("\n\n"),
      });
        const actions = document.createElement("div");
        actions.className = "composer-actions";
        (workspace.action_pack || []).forEach((item) => {
          const button = document.createElement("button");
          button.className = item.mode === "execute" ? "primary-action" : "ghost-action";
          button.textContent = item.label;
          button.addEventListener("click", async () => {
            try {
              await OpsActionsRuntime.runOpsWorkspaceAction(item);
            } catch (error) {
              alert(`执行 workspace action 失败：${error.message}`);
            }
          });
          actions.appendChild(button);
        });
        dom.opsAccountWorkspaceActions.appendChild(actionCard);
        dom.opsAccountWorkspaceActions.appendChild(actions);
      }
      if (!(workspace.operator_timeline || []).length) {
        clearNode(dom.opsAccountWorkspaceTimeline, "这里会显示账户级运营时间线。");
      } else {
        (workspace.operator_timeline || []).forEach((item) => {
          const card = document.createElement("article");
          card.className = "list-card";
          card.innerHTML = renderLocalizedCardHtml(
            item.headline || item.entry_id,
            item.category || "-",
            `${formatTimestamp(item.occurred_at)}\n${item.summary || "-"}\n下一步 ${(item.next_actions || []).join(" / ") || "-"}`
          );
          dom.opsAccountWorkspaceTimeline.appendChild(card);
        });
      }
    }
    dom.opsAccountDetail.appendChild(
      createListCard({
        title: `账户详情 · ${detail.account_id}`,
        score: opsStatusLabel(subscription.status || "no-subscription"),
        body: opsSections(
          opsSection("订阅情况", [
            opsFieldLine("当前方案", `${subscription.tier_id || "-"} · ${subscription.display_name || "-"}`),
            opsFieldLine("通道", opsProviderLabel(subscription.provider || "-")),
            opsFieldLine("下一步", subscription.next_action || "-"),
            opsFieldLine("原因", subscription.lifecycle_reason || "-"),
            opsFieldLine("周期结束", subscription.period_end || "-"),
            opsFieldLine("是否可续费", opsBooleanLabel(subscription.renewable)),
          ]),
          opsSection("支付与账单", [
            opsFieldLine("最近支付会话", detail.checkout_session?.checkout_session_id || "-"),
            opsFieldLine("支付状态", opsStatusLabel(detail.checkout_session?.status || "-")),
            opsFieldLine("账单事件数", detail.lifecycle_history_summary?.event_count ?? 0),
            opsFieldLine("重试次数", detail.lifecycle_history_summary?.retry_attempt_count ?? 0),
          ]),
          opsSection("钱包情况", [wallets]),
          opsSection("创作权限", [gatingSummary]),
          opsSection("最近活动摘要", [
            opsFieldLine("计量记录", detail.activity_summary?.recent_meter_count ?? 0),
            opsFieldLine("事件数", detail.activity_summary?.recent_event_count ?? 0),
            opsFieldLine("会话数", detail.activity_summary?.recent_session_count ?? 0),
            opsFieldLine("草稿数", detail.activity_summary?.recent_draft_count ?? 0),
          ])
        )
      })
    );

    dom.opsAccountActivity.appendChild(
      createListCard({
        title: "最近会话 / 草稿 / 计量",
        score: `${(detail.recent_sessions || []).length + (detail.recent_drafts || []).length}`,
        body: opsSections(
          opsSection("最近会话", [
            opsParagraphList(detail.recent_sessions || [], (item) =>
              `${item.session_id} · ${opsWorldLabel(item.world_id)}\n` +
              `${opsFieldLine("当前回合", item.current_turn_index)} · ${opsFieldLine("最近章节", item.last_chapter_title || item.last_event_title || "-")}\n` +
              `${opsFieldLine("访问层级", item.access_tier || "-")} · ${opsFieldLine("原因", item.reason || "-")}`
            ),
          ]),
          opsSection("最近草稿", [
            opsParagraphList(detail.recent_drafts || [], (item) =>
              `${item.world_version_id} · ${opsStatusLabel(item.status)}\n` +
              `${item.title || opsWorldLabel(item.world_id)} · ${opsFieldLine("风险等级", item.risk_rating || "-")}`
            ),
          ]),
          opsSection("最近计量", [
            opsParagraphList(detail.recent_meters || [], (item) =>
              `${item.action_type} · ${opsFieldLine("点数", Number(item.usage_units || 0).toFixed(3))} · ${opsFieldLine("钱包", item.wallet_type || "-")}\n` +
              `${opsFieldLine("世界版本", item.world_version_id || "-")} · ${opsFieldLine("会话", item.session_id || "-")}`
            ),
          ])
        )
      })
    );

    const supportSummary = detail.support_summary || {};
    const supportTooling = detail.support_tooling || {};
    dom.opsSupportSummary.appendChild(
      createListCard({
        title: `客服摘要 · ${detail.account_id}`,
        score: `${supportSummary.open_issue_count ?? 0} 个问题`,
        body: opsSections(
          opsSection("总体情况", [
            opsFieldLine("主要问题类型", supportSummary.primary_issue_type || "-"),
            opsFieldLine("高优先级问题", supportSummary.high_priority_issue_count ?? 0),
            opsFieldLine("近期付费受阻", supportSummary.recent_payment_required_count ?? 0),
            opsFieldLine("近期发起支付", supportSummary.recent_checkout_started_count ?? 0),
            opsFieldLine("最近问题时间", supportSummary.latest_issue_at || "-"),
          ]),
          opsSection("分布", [
            opsPairsLine("问题类型", supportSummary.issue_type_counts || {}),
            opsPairsLine("严重度", supportSummary.severity_counts || {}),
          ]),
          opsSection("推荐动作", [
            opsList(supportTooling.recommended_actions || [], (item) => `${item.label} · ${localizeDisplayText(item.action_type || "-")}`),
          ])
        )
      })
    );

    if (!detail.support_issues?.length) {
      clearNode(dom.opsSupportIssues, "这里会显示当前账户的客服问题定位结果。");
    } else {
      detail.support_issues.forEach((issue) => {
        const card = document.createElement("article");
        card.className = "list-card";
        const actionsMarkup = (issue.suggested_operator_actions || [])
          .map((action, index) => `<button class="ghost-action support-prefill" data-issue-index="${issue.issue_id}" data-action-index="${index}">${action.label}</button>`)
          .join("") + `<button class="ghost-action support-escalate">升级治理个案</button>`;
        const linkedCases = (governance.support_issue_refs || []).find((item) => item.issue_id === issue.issue_id)?.linked_cases || [];
        card.innerHTML = renderLocalizedCardHtml(
          issue.title,
          issue.severity || "-",
          `${issue.summary || "-"}\n原因 ${issue.reason || "-"} · 发现时间 ${issue.detected_at || "-"}\n触达面 ${(issue.surfaces || []).join(" / ") || "-"}\n关联个案 ${linkedCases.map((item) => `${item.case_id}:${item.status}`).join(" / ") || "-"}\n关联对象 ${Object.entries(issue.related_objects || {}).map(([key, value]) => `${key}=${Array.isArray(value) ? value.join(",") : value}`).join(" / ") || "-"}\n证据 ${Object.entries(issue.evidence || {}).map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`).join(" / ") || "-"}`,
          `<div class="composer-actions">${actionsMarkup}</div>`
        );
        card.querySelectorAll(".support-prefill").forEach((button) => {
          button.addEventListener("click", () => {
            const actionIndex = Number(button.getAttribute("data-action-index") || 0);
            const action = (issue.suggested_operator_actions || [])[actionIndex];
            applySupportPrefill(action?.prefill || {});
          });
        });
        card.querySelector(".support-escalate")?.addEventListener("click", () => escalateSupportIssue(issue));
        dom.opsSupportIssues.appendChild(card);
      });
    }

    const alertFeed = opsState.opsAlertsFeed || {};
    if (!alertFeed.alerts?.length) {
      clearNode(dom.opsAlertSummary, "这里会显示当前告警流的统计摘要。");
      clearNode(dom.opsAlertFeed, "这里会显示主动告警列表。");
      clearNode(dom.opsAlertDetail, "这里会显示选中告警的标准处置包、运行手册和排查引用。");
    } else {
      const alertSummary = alertFeed.summary || {};
    dom.opsAlertSummary.appendChild(
        createListCard({
          title: "告警摘要",
          score: `${alertSummary.actionable_alert_count ?? 0} 条待处理`,
          body:
            `${opsFieldLine("最新告警时间", alertSummary.latest_detected_at ? formatTimestamp(alertSummary.latest_detected_at) : "-")}\n` +
            `${opsPairsLine("分类分布", alertSummary.by_category || {})}\n` +
            `${opsPairsLine("严重度分布", alertSummary.by_severity || {})}\n` +
            `${opsPairsLine("状态分布", alertSummary.by_status || {}, opsStatusLabel)}`
        })
      );
      alertFeed.alerts.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        if (item.alert_id === opsState.selectedOpsAlertId) {
          card.classList.add("is-active");
        }
        card.innerHTML = renderLocalizedCardHtml(
          item.title || item.alert_id,
          `${item.severity || "-"} · ${opsStatusLabel(item.status || "-")}`,
          `${formatTimestamp(item.detected_at)}\n${item.category || "-"} · ${item.source_type || "-"}\n账户 ${item.account_id || "全局"}\n${item.summary || "-"}\n下一步 ${(item.recommended_actions || []).join(" / ") || "-"}`
        );
        card.addEventListener("click", async () => {
          opsState.selectedOpsAlertId = item.alert_id;
          const accountId = currentOpsAlertFilters().accountId || item.account_id || "";
          syncOpsNavigationContext({ account_id: accountId, alert_id: item.alert_id }, { preserveExisting: true });
          opsState.opsAlertDetail = await api(
            `/v1/ops/alerts/${encodeURIComponent(item.alert_id)}${
              accountId ? `?account_id=${encodeURIComponent(accountId)}` : ""
            }`
          );
          renderOpsSurface();
        });
        dom.opsAlertFeed.appendChild(card);
      });
      if (!opsState.opsAlertDetail) {
        clearNode(dom.opsAlertDetail, "这里会显示选中告警的标准处置包、运行手册和排查引用。");
      } else {
        const detailPayload = opsState.opsAlertDetail;
        const alert = detailPayload.alert || {};
        const runbook = detailPayload.runbook || {};
        const responseBundle = detailPayload.standard_response_bundle || {};
        const investigation = detailPayload.investigation_bundle?.filters || alert.investigation_ref || {};
        const supportActions = (responseBundle.recommended_actions || [])
          .concat((responseBundle.support_issue?.suggested_operator_actions || []).map((item) => item.action_type))
          .filter(Boolean);
        dom.opsAlertDetail.appendChild(
          createListCard({
            title: `告警详情 · ${alert.alert_id || "-"}`,
            score: `${opsStatusLabel(alert.status || "-")} · ${alert.severity || "-"}`,
            body:
              `${opsFieldLine("账户", alert.account_id || "全局")} · ${opsFieldLine("分类", alert.category || "-")} · ${opsFieldLine("来源", alert.source_type || "-")}\n` +
              `${opsFieldLine("发现时间", alert.detected_at ? formatTimestamp(alert.detected_at) : "-")}\n` +
              `${opsFieldLine("摘要", alert.summary || "-")}\n` +
              `${opsFieldLine("关联引用", (alert.source_refs || []).map((item) => `${item.label || item.kind}:${item.ref_id || "-"}`).join(" / ") || "-")}\n` +
              `${opsFieldLine("推荐动作", (alert.recommended_actions || []).join(" / ") || "-")}\n` +
              `${opsFieldLine("标准路径", (alert.standard_operating_path || []).join(" → ") || "-")}\n` +
              `${opsFieldLine("当前处理人", alert.state?.reviewer_id || "-")} · ${opsFieldLine("备注", alert.state?.note || "-")}\n\n` +
              `排查引用：\n${opsFieldLine("账户", investigation.account_id || "-")} · ${opsFieldLine("世界版本", investigation.world_version_id || "-")} · ${opsFieldLine("治理个案", investigation.case_id || "-")}\n\n` +
              `运行手册：\n${opsFieldLine("分诊步骤", (runbook.triage_steps || []).join(" / ") || "-")}\n${opsFieldLine("恢复步骤", (runbook.recovery_steps || []).join(" / ") || "-")}\n\n` +
              `标准响应：\n${supportActions.join(" / ") || (responseBundle.recommended_next_actions || []).join(" / ") || (runbook.standard_actions || []).join(" / ") || "-"}`
          })
        );
      }
    }

    const governanceSummary = governance.governance_summary || {};
    const restrictionSummary = governance.restriction_summary || {};
    dom.opsGovernanceSummary.appendChild(
      createListCard({
        title: `治理摘要 · ${detail.account_id}`,
        score: `${governanceSummary.open_case_count ?? 0} 个待处理`,
        body:
          `${opsFieldLine("个案总数", governanceSummary.total_cases ?? 0)} · ${opsFieldLine("已升级", governanceSummary.escalated_case_count ?? 0)}\n` +
          `${opsFieldLine("生效中的限制", restrictionSummary.active_restriction_count ?? 0)}\n` +
          `${opsFieldLine("逾期个案", governanceSummary.overdue_case_count ?? 0)}\n` +
          `${opsPairsLine("状态分布", governanceSummary.status_counts || {}, opsStatusLabel)}\n` +
          `个案类型 ${Object.entries(governanceSummary.case_type_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `严重度 ${Object.entries(governanceSummary.severity_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `队列 ${Object.entries(governanceSummary.queue_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `负责人 ${Object.entries(governanceSummary.owner_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `最近个案 ${governanceSummary.latest_case_id || "-"} · ${governanceSummary.latest_case_at || "-"}\n\n` +
          `推荐入口：\n${(governance.recommended_case_prefills || []).map((item) => item.label).join("\n") || "-"}`
      })
    );
    if (governance.recommended_case_prefills?.length) {
      const actions = document.createElement("div");
      actions.className = "composer-actions";
      governance.recommended_case_prefills.forEach((item, index) => {
        const button = document.createElement("button");
        button.className = "ghost-action";
        button.textContent = item.label;
        button.addEventListener("click", () => applyGovernanceCasePrefill(item.prefill || {}));
        actions.appendChild(button);
      });
      dom.opsGovernanceSummary.appendChild(actions);
    }

    if (!governance.governance_cases?.length) {
      clearNode(dom.opsGovernanceCases, "这里会显示当前账户关联的治理个案列表。");
    } else {
      governance.governance_cases.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        const restriction = item.restriction || {};
        const workflow = item.workflow_summary || {};
        card.innerHTML = renderLocalizedCardHtml(
          item.summary || item.case_id,
          opsStatusLabel(item.status || "-"),
          `${item.case_id}\n${item.case_type || "-"} · ${item.queue || "-"} · ${item.severity || "-"}\n目标 ${item.target_type || "-"}:${item.target_id || "-"}\n负责人 ${workflow.owner_id || item.owner_id || "-"} · 到期 ${item.due_at || workflow.due_at || "-"} · 是否逾期 ${workflow.is_overdue ? "是" : "否"}\n审阅人 ${item.reviewer_id || "-"} · 更新时间 ${item.updated_at || "-"}\n策略 ${(workflow.policy_labels || item.policy_labels || []).join(" / ") || "-"} · 处置结论 ${workflow.disposition || item.disposition || "-"}\n证据数 ${workflow.evidence_count ?? (item.evidence_refs || []).length ?? 0} · 客服问题 ${(item.support_issue_ids || []).join(" / ") || "-"}\n限制 ${restriction.restriction_id || "-"} · ${restriction.restriction_type || "-"} · ${opsStatusLabel(restriction.status || "-")}\n处理说明 ${item.resolution_notes || "-"}\n状态流转 ${(item.status_transitions || []).map((entry) => `${opsStatusLabel(entry.status || "-")}@${entry.changed_at}`).join(" / ") || "-"}`
        );
        card.addEventListener("click", () => {
          applyGovernanceCasePrefill({
            case_id: item.case_id,
            case_type: item.case_type,
            target_type: item.target_type,
            target_id: item.target_id,
            severity: item.severity,
            reviewer_id: item.reviewer_id,
            owner_id: workflow.owner_id || item.owner_id,
            summary: item.summary,
            description: item.resolution_notes || item.description,
            status: item.status,
            account_id: item.account_id || detail.account_id,
            due_at: workflow.due_at || item.due_at,
            disposition: workflow.disposition || item.disposition,
            policy_labels: workflow.policy_labels || item.policy_labels || [],
          });
          syncOpsNavigationContext(
            {
              account_id: item.account_id || detail.account_id,
              case_id: item.case_id,
              world_id: item.world_id || undefined,
              world_version_id: item.world_version_id || undefined,
            },
            { preserveExisting: true }
          );
          openGovernanceCaseDetail(item.case_id);
        });
        dom.opsGovernanceCases.appendChild(card);
      });
    }

    if (!opsState.opsGovernanceDetail) {
      clearNode(dom.opsGovernanceDetail, "这里会显示选中治理个案的深度详情。");
    } else {
      const item = opsState.opsGovernanceDetail;
      const restriction = item.restriction || {};
      const workflow = item.workflow_summary || {};
      const permissions = item.permission_summary || {};
        dom.opsGovernanceDetail.appendChild(
        createListCard({
          title: `治理详情 · ${item.case_id}`,
          score: opsStatusLabel(item.status || "-"),
          body:
            `${opsFieldLine("个案类型", item.case_type || "-")} · ${opsFieldLine("队列", item.queue || "-")} · ${opsFieldLine("严重度", item.severity || "-")}\n` +
            `${opsFieldLine("目标", `${item.target_type || "-"}:${item.target_id || "-"}`)} · ${opsFieldLine("审阅人", item.reviewer_id || "-")}\n` +
            `${opsFieldLine("负责人", workflow.owner_id || item.owner_id || "-")} · ${opsFieldLine("到期时间", workflow.due_at || item.due_at || "-")} · ${opsFieldLine("是否逾期", opsBooleanLabel(workflow.is_overdue))}\n` +
            `${opsFieldLine("关联客服问题", (item.support_issue_ids || []).join(" / ") || "-")}\n` +
            `${opsFieldLine("限制", `${restriction.restriction_id || "-"} · ${restriction.restriction_type || "-"} · ${opsStatusLabel(restriction.status || "-")}`)}\n` +
            `${opsFieldLine("策略标签", (workflow.policy_labels || item.policy_labels || []).join(" / ") || "-")} · ${opsFieldLine("处置结论", workflow.disposition || item.disposition || "-")}\n` +
            `${opsFieldLine("可用流转", (workflow.transition_options || []).join(" / ") || "-")}\n` +
            `${opsFieldLine("权限", `认领 ${opsBooleanLabel(permissions.can_claim)} / 分派 ${opsBooleanLabel(permissions.can_assign)} / 证据 ${opsBooleanLabel(permissions.can_add_evidence)} / 流转 ${opsBooleanLabel(permissions.can_transition)} / 释放限制 ${opsBooleanLabel(permissions.can_release_restriction)}`)}\n` +
            `${opsFieldLine("摘要", item.summary || "-")}\n${opsFieldLine("处理说明", item.resolution_notes || "-")}\n\n` +
            `流程清单：\n${(item.workflow_checklist || []).map((entry) => `${entry.key} · ${opsStatusLabel(entry.status)}\n${entry.label}${entry.note ? ` · ${entry.note}` : ""}`).join("\n\n") || "-"}\n\n` +
            `证据：\n${(item.evidence_refs || []).map((entry) => `${entry.title || entry.kind} · ${entry.kind}\n${entry.ref_id || "-"} · ${entry.preview || "-"}`).join("\n\n") || "-"}\n\n` +
            `下一步动作：\n${(item.recommended_next_actions || []).join("\n") || "-"}\n\n` +
            `状态流转：\n${(item.status_transitions || []).map((entry) => `${opsStatusLabel(entry.status)} · ${entry.reviewer_id || "-"} · ${entry.changed_at}\n${entry.notes || "-"}`).join("\n\n") || "-"}\n\n` +
            `关联客服问题：\n${(item.linked_support_issues || []).map((issue) => `${issue.issue_id} · ${issue.issue_type} · ${issue.severity}\n${issue.title || "-"}\n${issue.summary || "-"}`).join("\n\n") || "-"}\n\n` +
            `审计事件：\n${(item.audit_events || []).map((event) => `${event.action} · ${opsStatusLabel(event.status || "-")} · ${formatTimestamp(event.occurred_at)}\n${event.reason || "-"} · ${event.object_type || "-"}:${event.object_id || "-"}`).join("\n\n") || "-"}`
        })
      );
    }

    const governanceExport = opsState.opsGovernanceExport || {};
    if (!governanceExport.cases?.length && !governanceExport.restrictions?.length) {
      clearNode(dom.opsGovernanceExport, "这里会显示治理审计导出摘要。");
    } else {
      dom.opsGovernanceExport.appendChild(
        createListCard({
          title: `治理审计导出 · ${detail.account_id}`,
          score: `${governanceExport.governance_summary?.total_cases ?? 0} 个个案`,
          body: opsSections(
            opsSection("生成信息", [
              opsFieldLine("导出时间", governanceExport.export_generated_at || "-"),
              opsFieldLine("个案总数", governanceExport.governance_summary?.total_cases ?? 0),
              opsFieldLine("限制总数", governanceExport.restriction_summary?.total_restrictions ?? (governanceExport.restrictions || []).length),
            ]),
            opsSection("个案状态", [
              opsPairsLine("状态分布", governanceExport.governance_summary?.status_counts || {}, opsStatusLabel),
            ]),
            opsSection("限制分布", [
              opsPairsLine("限制状态", governanceExport.restriction_summary?.status_counts || {}, opsStatusLabel),
              opsPairsLine("限制类型", governanceExport.restriction_summary?.type_counts || {}),
            ]),
            opsSection("个案明细", [
              opsParagraphList(governanceExport.cases || [], (item) => opsSections(
                opsSection(`${item.case_id || "-"} · ${opsStatusLabel(item.status || "-")}`, [
                  opsFieldLine("个案类型", item.case_type || "-"),
                  opsFieldLine("队列", item.queue || "-"),
                  opsFieldLine("严重度", item.severity || "-"),
                  opsFieldLine("目标", opsTargetLabel(item.target_type, item.target_id)),
                  opsFieldLine("审阅人", item.reviewer_id || "-"),
                ])
              )),
            ]),
            opsSection("限制明细", [
              opsParagraphList(governanceExport.restrictions || [], (item) => opsSections(
                opsSection(`${item.restriction_id || "-"} · ${opsStatusLabel(item.status || "-")}`, [
                  opsFieldLine("限制类型", item.restriction_type || "-"),
                  opsFieldLine("关联个案", item.case_id || "-"),
                  opsFieldLine("目标", opsTargetLabel(item.target_type, item.target_id)),
                ])
              )),
            ])
          )
        })
      );
    }

    const auditBreakdown = detail.audit_breakdown || {};
    const auditSummary = [
      `总数 ${auditBreakdown.total_entries ?? 0}`,
      `最近时间 ${auditBreakdown.latest_at || "-"}`,
      `分类 ${Object.entries(auditBreakdown.by_category || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `触达面 ${Object.entries(auditBreakdown.by_surface || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `来源 ${Object.entries(auditBreakdown.sources || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `高频动作 ${((auditBreakdown.top_actions || []).map((item) => `${item.action}=${item.count}`).join(" / ")) || "-"}`,
      `游标 ${detail.timeline_cursor?.returned ?? 0}/${detail.timeline_cursor?.limit ?? 0} · 还有更多 ${detail.timeline_cursor?.has_more ? "是" : "否"}`,
    ].join("\n");
    dom.opsAccountAuditSummary.appendChild(
      createListCard({
        title: "审计拆解",
        score: `${auditBreakdown.total_entries ?? 0} 条记录`,
        body: auditSummary,
      })
    );

    if (!detail.audit_trail?.length) {
      clearNode(dom.opsAccountAuditTrail, "这里会显示当前账户的完整审计轨迹。");
    } else {
      detail.audit_trail.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = renderLocalizedCardHtml(
          item.action || "-",
          item.category || "-",
          `${formatTimestamp(item.occurred_at)}\n${item.surface || "-"} · ${item.source_type || "-"}\n操作人 ${item.actor_id || "-"} → ${item.object_type || "-"} ${item.object_id || "-"}\n状态 ${opsStatusLabel(item.status || "-")} · 原因 ${item.reason || "-"}\n钱包 ${item.wallet_type || "-"} · 档位 ${item.tier_id || "-"} · 点数 ${item.usage_units ?? "-"}\n世界 ${item.world_version_id || item.world_id || "-"} · 会话 ${item.session_id || "-"}`
        );
        if (item.object_type === "entitlement" && item.object_id && dom.opsEntitlementId) {
          card.addEventListener("click", () => {
            dom.opsEntitlementId.value = item.object_id;
          });
        }
        dom.opsAccountAuditTrail.appendChild(card);
      });
    }
  }
}

function renderOpsInvestigationSection() {
  clearNode(dom.opsInvestigationSummary);
  clearNode(dom.opsInvestigationTimeline);
  clearNode(dom.opsInvestigationEvidence);
  if (!opsState.opsInvestigationBundle) {
    clearNode(dom.opsInvestigationSummary, "这里会显示排查摘要与推荐排查路径。");
    clearNode(dom.opsInvestigationTimeline, "这里会显示统一排查时间线。");
    clearNode(dom.opsInvestigationEvidence, "这里会显示证据索引。");
  } else {
    const bundle = opsState.opsInvestigationBundle;
    const summary = bundle.investigation_summary || {};
    const filters = bundle.filters || {};
    const linked = bundle.linked_entities || {};
    const authorCapability = bundle.author_longform_capability || {};
    const authorAlignment = bundle.author_claim_alignment || {};
    const recommended = (bundle.recommended_paths || [])
      .map((item, index) => `${index + 1}. ${item.path_id} · score ${item.score ?? 0}\n${item.reason || "-"}`)
      .join("\n\n") || "-";
    dom.opsInvestigationSummary.appendChild(
      createListCard({
        title: `排查摘要 · ${filters.account_id || linked.account_id || "-"}`,
        score: `${summary.trace_count ?? 0} 条轨迹`,
        body:
          `生成时间 ${formatTimestamp(bundle.generated_at)}\n` +
          `筛选条件 账户 ${filters.account_id || "-"} · 世界 ${filters.world_version_id || "-"} · 个案 ${filters.case_id || "-"} · 数量上限 ${filters.limit || "-"}\n` +
          `关联订阅 ${linked.subscription_id || "-"} · 支付会话 ${linked.checkout_session_id || "-"}\n` +
          `治理个案 ${(linked.governance_case_ids || []).join(" / ") || "-"}\n` +
          `世界版本 ${(linked.world_version_ids || []).join(" / ") || "-"}\n` +
          `客服问题 ${(linked.support_issue_ids || []).join(" / ") || "-"}\n\n` +
          `长线口径：\n` +
          `入口 ${authorCapability.entry_mode || "-"} · 目标 ${authorCapability.requested_target_band || "-"} · claim ${authorCapability.claim_safe_band || "-"}\n` +
          `Ops ready band ${authorAlignment.ops_release_ready_band || "-"} · alignment ${authorAlignment.aligned === undefined ? "-" : (authorAlignment.aligned ? "yes" : "no")}\n` +
          `Readiness ${((authorCapability.longform_readiness || {}).status) || "-"} · blockers ${(((authorCapability.longform_readiness || {}).blockers) || []).map((item) => item.message || item.key).join(" / ") || "-"}\n\n` +
          `摘要：\n` +
          `最近时间 ${summary.latest_at ? formatTimestamp(summary.latest_at) : "-"}\n` +
          `分类 ${Object.entries(summary.category_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `严重度 ${Object.entries(summary.severity_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `限制 ${summary.active_restriction_count ?? 0} · 客服问题 ${summary.open_support_issue_count ?? 0} · 账单事件 ${summary.billing_event_count ?? 0} · 重试 ${summary.billing_retry_attempt_count ?? 0}\n\n` +
          `推荐路径：\n${recommended}`
      })
    );

    if (!bundle.trace_timeline?.length) {
      clearNode(dom.opsInvestigationTimeline, "这里会显示统一排查时间线。");
    } else {
      bundle.trace_timeline.forEach((item) => {
        const card = createListCard({
          title: item.headline || item.trace_id,
          score: `${item.category || "-"} · ${item.severity || "-"}`,
          body: opsSections(
            opsSection("时间与来源", [
              opsFieldLine("发生时间", formatTimestamp(item.occurred_at)),
              opsFieldLine("来源", item.source_type || "-"),
              opsFieldLine("状态", opsStatusLabel(item.status || "-")),
            ]),
            opsSection("摘要", [
              item.summary || "-",
            ]),
            opsSection("上下文", [
              opsFieldLine("账户", item.account_id || "-"),
              opsFieldLine("世界版本", item.world_version_id || "-"),
              opsFieldLine("治理个案", item.case_id || "-"),
              opsFieldLine("会话", item.session_id || "-"),
              opsFieldLine("对象", opsTargetLabel(item.object_type, item.object_id)),
              opsFieldLine("关联轨迹", (item.related_trace_ids || []).join(" / ") || "-"),
            ]),
            opsSection("下一步", [
              opsList(item.next_actions || []),
            ]),
            opsSection("证据引用", [
              opsList(item.evidence_refs || [], (ref) => `${ref.label || ref.kind || "证据"} · ${ref.ref_id || "-"}`),
            ])
          )
        });
        card.addEventListener("click", () => {
          if (item.case_id && dom.opsGovernanceCaseId) {
            dom.opsGovernanceCaseId.value = item.case_id;
          }
          if (item.world_version_id && dom.opsInvestigationWorldVersionId) {
            dom.opsInvestigationWorldVersionId.value = item.world_version_id;
          }
          if (item.account_id && dom.opsInvestigationAccountId) {
            dom.opsInvestigationAccountId.value = item.account_id;
          }
          if (item.source_type === "billing_lifecycle_event" && item.object_id && dom.opsBillingEventId) {
            dom.opsBillingEventId.value = item.object_id;
          }
        });
        dom.opsInvestigationTimeline.appendChild(card);
      });
    }

    if (!bundle.evidence_index?.length) {
      clearNode(dom.opsInvestigationEvidence, "这里会显示证据索引。");
    } else {
      bundle.evidence_index.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.title || item.evidence_id}</h3>
            <span class="list-card-score">${item.source_type || "-"}</span>
          </div>
          <p class="list-card-body">${item.preview || "-"}\n来源 ${item.source_id || "-"}\n关联对象 ${item.linked_object_type || "-"}:${item.linked_object_id || "-"}</p>
        `;
        dom.opsInvestigationEvidence.appendChild(card);
      });
    }
  }
}

function renderOpsLearnedSection() {
  clearNode(dom.opsEvalMetrics);
  if (!opsState.opsEvalMetrics) {
    clearNode(dom.opsEvalMetrics, "这里会显示通过、重写、阻塞、核心问题与质量趋势。");
  } else {
    const metric = opsState.opsEvalMetrics;
    const qualitySummary = opsState.opsQualitySummary || {};
    const commercialization = opsState.opsCommercializationSummary || {};
    const continuationSummary = metric.continuation_signal_summary || {};
    const topCorrelations = (metric.quality_signal_correlations || []).slice(0, 3);
    const worldDetails = (metric.continuation_world_details || []).slice(0, 3);
    const versionDetails = (metric.continuation_version_details || []).slice(0, 4);
    const accumulation = metric.continuation_sample_accumulation || {};
    const calibration = metric.q03_q09_calibration || {};
    const q03Calibration = calibration.q03 || {};
    const q09Calibration = calibration.q09 || {};
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>当前质量概览</h3>
        <span class="list-card-score">通过 ${(Number(metric.pass_rate || 0) * 100).toFixed(0)}%</span>
      </div>
      <p class="list-card-body">重写 ${(Number(metric.rewrite_rate || 0) * 100).toFixed(0)}% · 阻塞 ${(Number(metric.block_rate || 0) * 100).toFixed(0)}%\n继续相关性 ${Number(metric.online_continuation_correlation || 0).toFixed(2)}\n样本 ${continuationSummary.sample_count ?? 0} · 正样本 ${continuationSummary.positive_count ?? 0} · 负样本 ${continuationSummary.negative_count ?? 0}\n最高相关性 ${(topCorrelations || []).map((item) => `${item.metric}=${Number(item.correlation || 0).toFixed(2)}`).join(" / ") || "-"}</p>
    `;
    dom.opsEvalMetrics.appendChild(card);

    const drilldownCard = document.createElement("article");
    drilldownCard.className = "list-card";
    drilldownCard.innerHTML = `
      <div class="list-card-head">
        <h3>继续阅读钻取</h3>
        <span class="list-card-score">${worldDetails.length} 个世界</span>
      </div>
      <p class="list-card-body">世界：\n${worldDetails.map((item) => `${item.world_id} · 相关性 ${Number(item.online_continuation_correlation || 0).toFixed(2)} · 样本 ${item.sample_count ?? 0} · 缺口 ${item.sample_gap ?? 0}\n继续率 ${(Number(item.continuation_rate || 0) * 100).toFixed(0)}% · 建议动作 ${item.recommended_action || "-"}`).join("\n\n") || "-"}\n\n版本：\n${versionDetails.map((item) => `${item.world_version_id} · 相关性 ${Number(item.online_continuation_correlation || 0).toFixed(2)} · 样本 ${item.sample_count ?? 0} · 缺口 ${item.sample_gap ?? 0}`).join("\n") || "-"}</p>
    `;
    dom.opsEvalMetrics.appendChild(drilldownCard);

    const accumulationCard = document.createElement("article");
    accumulationCard.className = "list-card";
    accumulationCard.innerHTML = `
      <div class="list-card-head">
        <h3>样本积累</h3>
        <span class="list-card-score">${accumulation.worlds_below_target_count ?? 0} 个世界待补样</span>
      </div>
      <p class="list-card-body">目标 / 世界 ${accumulation.target_sample_count_per_world ?? 0} · 目标 / 版本 ${accumulation.target_sample_count_per_version ?? 0}\n负样本目标 ${accumulation.target_negative_samples ?? 0}\n未达标世界 ${accumulation.worlds_below_target_count ?? 0} · 未达标版本 ${accumulation.versions_below_target_count ?? 0}\n\n优先世界：\n${(accumulation.prioritized_worlds || []).map((item) => `${item.world_id} · 样本 ${item.sample_count ?? 0} · 负样本 ${item.negative_count ?? 0} · 缺口 ${item.sample_gap ?? 0} · ${item.recommended_action || "-"}`).join("\n") || "-"}\n\n优先版本：\n${(accumulation.prioritized_versions || []).map((item) => `${item.world_version_id} · 样本 ${item.sample_count ?? 0} · 负样本 ${item.negative_count ?? 0} · 缺口 ${item.sample_gap ?? 0}`).join("\n") || "-"}</p>
    `;
    dom.opsEvalMetrics.appendChild(accumulationCard);

    const calibrationCard = document.createElement("article");
    calibrationCard.className = "list-card";
    calibrationCard.innerHTML = `
      <div class="list-card-head">
        <h3>Q03 / Q09 校准</h3>
        <span class="list-card-score">${calibration.coverage_status || "-"}</span>
      </div>
      <p class="list-card-body">样本 ${calibration.sample_count ?? 0} · 缺口 ${calibration.sample_gap ?? 0}\nQ03: ${q03Calibration.primary_metric || "-"} = ${q03Calibration.primary_correlation !== null && q03Calibration.primary_correlation !== undefined ? Number(q03Calibration.primary_correlation).toFixed(2) : "-"} · ${q03Calibration.recommendation || "-"}\nQ09: ${q09Calibration.primary_metric || "-"} = ${q09Calibration.primary_correlation !== null && q09Calibration.primary_correlation !== undefined ? Number(q09Calibration.primary_correlation).toFixed(2) : "-"} · ${q09Calibration.recommendation || "-"}</p>
    `;
    dom.opsEvalMetrics.appendChild(calibrationCard);

    const issuesCard = document.createElement("article");
    issuesCard.className = "list-card";
    issuesCard.innerHTML = `
      <div class="list-card-head">
        <h3>核心问题</h3>
        <span class="list-card-score">${(metric.top_issue_categories || []).length} 类</span>
      </div>
      <p class="list-card-body">${(metric.top_issue_categories || []).map((item) => `${item.issue_code} · ${item.count} · ${item.owning_module}\n修复建议：${item.fix_hint}`).join("\n\n") || "暂无 issue 聚合"}</p>
    `;
    dom.opsEvalMetrics.appendChild(issuesCard);

    const trendCard = document.createElement("article");
    trendCard.className = "list-card";
    trendCard.innerHTML = `
      <div class="list-card-head">
        <h3>世界包趋势</h3>
        <span class="list-card-score">${(metric.per_world_pack_quality_trend || []).length} 条</span>
      </div>
      <p class="list-card-body">${(metric.per_world_pack_quality_trend || []).map((item) => `${item.world_version_id} · avg ${Number(item.avg_score || 0).toFixed(3)}`).join("\n") || "暂无趋势数据"}</p>
    `;
    dom.opsEvalMetrics.appendChild(trendCard);

    const actionCard = document.createElement("article");
    actionCard.className = "list-card";
    actionCard.innerHTML = `
      <div class="list-card-head">
        <h3>建议修复顺序</h3>
        <span class="list-card-score">${(metric.next_actions || []).length} 项</span>
      </div>
      <p class="list-card-body">${(metric.next_actions || []).map((item, index) => `${index + 1}. ${item.issue_code} -> ${item.owning_module}\n${item.fix_hint}`).join("\n\n") || "当前没有额外修复建议。"}</p>
    `;
    dom.opsEvalMetrics.appendChild(actionCard);

    const learnedCard = document.createElement("article");
    learnedCard.className = "list-card";
    learnedCard.innerHTML = `
      <div class="list-card-head">
        <h3>学习层影子评估</h3>
        <span class="list-card-score">${metric.learned_shadow_summary?.status || "未就绪"}</span>
      </div>
      <p class="list-card-body">是否可用 ${metric.learned_shadow_summary?.available ? "是" : "否"}\n一致率 ${metric.learned_shadow_summary?.agreement_rate !== null && metric.learned_shadow_summary?.agreement_rate !== undefined ? Number(metric.learned_shadow_summary.agreement_rate).toFixed(3) : "-"}\n训练 ${metric.learned_shadow_summary?.train_count ?? 0} · 验证 ${metric.learned_shadow_summary?.val_count ?? 0} · 测试 ${metric.learned_shadow_summary?.test_count ?? 0}\n告警 ${(metric.learned_shadow_summary?.warnings || []).join(" / ") || "-"}\n下一步 ${metric.learned_shadow_summary?.recommended_next_action || "-"}\n\n世界分歧：\n${(metric.learned_shadow_summary?.top_mismatch_worlds || []).map((item) => `${item.world_id}=${Number(item.value ?? item.count ?? 0).toFixed(3)}`).join("\n") || "-"}\n\n问题分歧：\n${(metric.learned_shadow_summary?.top_mismatch_issue_codes || []).map((item) => `${item.issue_code || item.key}=${Number(item.value ?? item.count ?? 0).toFixed(3)}`).join("\n") || "-"}</p>
    `;
    dom.opsEvalMetrics.appendChild(learnedCard);

    const rerankerCard = document.createElement("article");
    rerankerCard.className = "list-card";
    rerankerCard.innerHTML = `
      <div class="list-card-head">
        <h3>学习层影子重排</h3>
        <span class="list-card-score">${metric.learned_reranker_shadow_summary?.status || "未就绪"}</span>
      </div>
      <p class="list-card-body">是否可用 ${metric.learned_reranker_shadow_summary?.available ? "是" : "否"}\n训练 ${metric.learned_reranker_shadow_summary?.train_count ?? 0} · 验证 ${metric.learned_reranker_shadow_summary?.val_count ?? 0} · 测试 ${metric.learned_reranker_shadow_summary?.test_count ?? 0}\n告警 ${(metric.learned_reranker_shadow_summary?.warnings || []).join(" / ") || "-"}\n下一步 ${metric.learned_reranker_shadow_summary?.recommended_next_action || "-"}\n\n世界准确率：\n${Object.entries(metric.learned_reranker_shadow_summary?.per_world_accuracy || {}).map(([worldId, value]) => `${worldId}=${Number(value).toFixed(3)}`).join("\n") || "-"}\n\n问题错误率：\n${Object.entries(metric.learned_reranker_shadow_summary?.per_issue_code_error_rate || {}).map(([issueCode, value]) => `${issueCode}=${Number(value).toFixed(3)}`).join("\n") || "-"}\n\n低覆盖世界：\n${(metric.learned_reranker_shadow_summary?.low_pair_coverage_worlds || []).map((item) => `${item.world_id}=${item.count}`).join("\n") || "-"}</p>
    `;
    dom.opsEvalMetrics.appendChild(rerankerCard);

    if (qualitySummary.summary) {
      const canonicalCard = document.createElement("article");
      canonicalCard.className = "list-card";
      canonicalCard.innerHTML = `
        <div class="list-card-head">
          <h3>Canonical 质量摘要</h3>
          <span class="list-card-score">${qualitySummary.summary.open_review_case_count ?? 0} open</span>
        </div>
        <p class="list-card-body">事件 ${qualitySummary.summary.event_count ?? 0} · 案例 ${qualitySummary.summary.review_case_count ?? 0}\nblocked ${qualitySummary.summary.blocked_event_count ?? 0} · review_required ${qualitySummary.summary.review_required_event_count ?? 0}\n反馈 ${qualitySummary.summary.feedback_item_count ?? 0} · 重试 ${qualitySummary.summary.retry_signal_count ?? 0}\n原因 ${(qualitySummary.summary.top_reason_codes || []).map((item) => `${item.reason_code}=${item.count}`).join(" / ") || "-"}\n反馈类型 ${(qualitySummary.summary.top_feedback_types || []).map((item) => `${item.feedback_type}=${item.count}`).join(" / ") || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(canonicalCard);
    }

    if (qualitySummary.groundedness_summary) {
      const groundingCard = document.createElement("article");
      groundingCard.className = "list-card";
      groundingCard.innerHTML = `
        <div class="list-card-head">
          <h3>Groundedness Summary</h3>
          <span class="list-card-score">${Number(qualitySummary.groundedness_summary.pass_rate || 0).toFixed(3)}</span>
        </div>
        <p class="list-card-body">pass rate ${Number(qualitySummary.groundedness_summary.pass_rate || 0).toFixed(3)}\nweak ${qualitySummary.groundedness_summary.weak_count ?? 0} · failed ${qualitySummary.groundedness_summary.failed_count ?? 0}\nunsupported claims ${qualitySummary.groundedness_summary.unsupported_claim_count ?? 0}</p>
      `;
      dom.opsEvalMetrics.appendChild(groundingCard);
    }

    if (qualitySummary.feedback_summary) {
      const feedbackCard = document.createElement("article");
      feedbackCard.className = "list-card";
      feedbackCard.innerHTML = `
        <div class="list-card-head">
          <h3>Feedback Summary</h3>
          <span class="list-card-score">${qualitySummary.feedback_summary.thumbs_up_count ?? 0}/${qualitySummary.feedback_summary.thumbs_down_count ?? 0}</span>
        </div>
        <p class="list-card-body">thumbs up ${qualitySummary.feedback_summary.thumbs_up_count ?? 0} · thumbs down ${qualitySummary.feedback_summary.thumbs_down_count ?? 0}\nexplicit ${(qualitySummary.feedback_summary.explicit_vs_implicit || {}).explicit ?? 0} · implicit ${(qualitySummary.feedback_summary.explicit_vs_implicit || {}).implicit ?? 0}\nreason codes ${(qualitySummary.feedback_summary.top_reason_codes || []).map((item) => `${item.reason_code}=${item.count}`).join(" / ") || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(feedbackCard);
    }

    if (qualitySummary.review_pressure) {
      const reviewPressureCard = document.createElement("article");
      reviewPressureCard.className = "list-card";
      reviewPressureCard.innerHTML = `
        <div class="list-card-head">
          <h3>Review Pressure</h3>
          <span class="list-card-score">${qualitySummary.review_pressure.unresolved_review_cases ?? 0}</span>
        </div>
        <p class="list-card-body">new ${qualitySummary.review_pressure.new_review_cases ?? 0} · unresolved ${qualitySummary.review_pressure.unresolved_review_cases ?? 0}\nreasons ${(qualitySummary.review_pressure.top_review_reasons || []).map((item) => `${item.reason_code}=${item.count}`).join(" / ") || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(reviewPressureCard);
    }

    if (qualitySummary.quality_trend) {
      const trendCardV1 = document.createElement("article");
      trendCardV1.className = "list-card";
      trendCardV1.innerHTML = `
        <div class="list-card-head">
          <h3>Quality Trend</h3>
          <span class="list-card-score">${(qualitySummary.quality_trend.score_trend || []).length} traces</span>
        </div>
        <p class="list-card-body">score ${(qualitySummary.quality_trend.score_trend || []).map((item) => `${item.trace_id}:${item.overall_score}`).join(" / ") || "-"}\nveto ${(qualitySummary.quality_trend.veto_trend || []).map((item) => `${item.trace_id}:${item.veto ? "yes" : "no"}`).join(" / ") || "-"}\nguard ${(qualitySummary.quality_trend.guard_failed_trend || []).map((item) => `${item.trace_id}:${item.status}`).join(" / ") || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(trendCardV1);
    }

    if (commercialization.invoice_preview_totals) {
      const commercialCard = document.createElement("article");
      commercialCard.className = "list-card";
      commercialCard.innerHTML = `
        <div class="list-card-head">
          <h3>Commercial Ops Summary</h3>
          <span class="list-card-score">${(commercialization.invoice_preview_totals || {}).preview_count ?? 0} previews</span>
        </div>
        <p class="list-card-body">invoice subtotal ${Number((commercialization.invoice_preview_totals || {}).subtotal_amount_usd || 0).toFixed(2)} · due ${Number((commercialization.invoice_preview_totals || {}).total_due_usd || 0).toFixed(2)}\nunpaid ${(commercialization.financial_status_totals || {}).unpaid_count ?? 0} · disputed ${(commercialization.financial_status_totals || {}).disputed_count ?? 0} · credited ${(commercialization.financial_status_totals || {}).credited_count ?? 0}\noverage ${(commercialization.overage_totals || {}).active_flag_count ?? 0} · renewal_due ${(commercialization.renewal_due_accounts || {}).count ?? 0} · churn ${(commercialization.churn_risk_accounts || {}).count ?? 0}\ndunning ${(commercialization.dunning_runs || {}).count ?? 0} · pilot_ready ${(commercialization.pilot_conversion || {}).ready_count ?? 0} · expansion ${(commercialization.expansion_candidates || {}).recommended_count ?? 0}\npartner heatmap lifecycle ${(commercialization.partner_readiness_heatmap || {}).lifecycle_counts ? Object.entries((commercialization.partner_readiness_heatmap || {}).lifecycle_counts).map(([key, value]) => `${key}=${value}`).join(" / ") : "-"}\nsupport ${(commercialization.support_backlog || {}).count ?? 0} · disputes ${(commercialization.dispute_backlog || {}).count ?? 0}</p>
      `;
      dom.opsEvalMetrics.appendChild(commercialCard);
    }

    if (commercialization.production_signoff) {
      const signoff = commercialization.production_signoff || {};
      const detail = opsState.opsProductionSignoffDetail || {};
      const nextDue = signoff.next_due_item || {};
      const cutover = signoff.planned_cutover_window || {};
      const signoffCard = document.createElement("article");
      signoffCard.className = "list-card";
      signoffCard.innerHTML = `
        <div class="list-card-head">
          <h3>Production Signoff</h3>
          <span class="list-card-score">${signoff.status || "-"}</span>
        </div>
        <p class="list-card-body">launch ${(signoff.launch_label || "-")} · signoff ${(signoff.signoff_id || "-")}\npending ${signoff.pending_item_count ?? 0} · approved ${signoff.approved_item_count ?? 0} · rejected ${signoff.rejected_item_count ?? 0}\nnext due ${(nextDue.item_code || "-")} · owner ${(nextDue.owner_role || "-")} · due ${(nextDue.due_at ? formatTimestamp(nextDue.due_at) : "-")}\ncutover ${(cutover.launch_wave || "-")} · ${(cutover.target_environment || "-")} · ${(cutover.status || "-")}\nexport ${(detail.export_refs || {}).record_dir || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(signoffCard);
    }

    if (commercialization.production_signoff_action_board) {
      const board = commercialization.production_signoff_action_board || {};
      const boardCard = document.createElement("article");
      boardCard.className = "list-card";
      boardCard.innerHTML = `
        <div class="list-card-head">
          <h3>Production Signoff Action Board</h3>
          <span class="list-card-score">${board.status || "-"}</span>
        </div>
        <p class="list-card-body">pending ${(board.pending_item_count ?? 0)} · approved ${(board.approved_item_count ?? 0)} · rejected ${(board.rejected_item_count ?? 0)} · overdue ${(board.overdue_count ?? 0)}\nblockers ${(board.blocker_counts && Object.entries(board.blocker_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nnext due ${((board.next_due_item || {}).item_code || "-")} · export ${((board.export_refs || {}).record_dir || "-")}</p>
      `;
      dom.opsEvalMetrics.appendChild(boardCard);
    }

    if (commercialization.production_acceptance) {
      const acceptance = commercialization.production_acceptance || {};
      const acceptanceCard = document.createElement("article");
      acceptanceCard.className = "list-card";
      acceptanceCard.innerHTML = `
        <div class="list-card-head">
          <h3>Production Acceptance</h3>
          <span class="list-card-score">${acceptance.acceptance_record_count ?? 0} records</span>
        </div>
        <p class="list-card-body">go_live_ready ${(acceptance.go_live_ready_count ?? 0)} · blocked ${(acceptance.blocked_go_live_count ?? 0)}\nlaunch waves ${(acceptance.launch_wave_count ?? 0)}</p>
      `;
      dom.opsEvalMetrics.appendChild(acceptanceCard);
    }

    if (commercialization.launch_week_ops_pack) {
      const launchOpsPack = commercialization.launch_week_ops_pack || {};
      const launchOpsCard = document.createElement("article");
      launchOpsCard.className = "list-card";
      launchOpsCard.innerHTML = `
        <div class="list-card-head">
          <h3>Launch Week Ops Pack</h3>
          <span class="list-card-score">${launchOpsPack.document_count ?? 0} docs</span>
        </div>
        <p class="list-card-body">bundle ${(launchOpsPack.bundle_id || "-")}\nunresolved manual signoff ${(launchOpsPack.unresolved_manual_signoff_count ?? 0)} · launch alerts ${(launchOpsPack.launch_week_alert_count ?? 0)} · waves ${(launchOpsPack.launch_wave_count ?? 0)}\nrefs ${((launchOpsPack.refs || {}).doc_refs || []).join(" / ") || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(launchOpsCard);
    }

    if (commercialization.launch_handshake_pack) {
      const handshakePack = commercialization.launch_handshake_pack || {};
      const handshakeCard = document.createElement("article");
      handshakeCard.className = "list-card";
      handshakeCard.innerHTML = `
        <div class="list-card-head">
          <h3>Legal & Human-Ops Handshake Pack</h3>
          <span class="list-card-score">${handshakePack.document_count ?? 0} docs</span>
        </div>
        <p class="list-card-body">bundle ${(handshakePack.bundle_id || "-")}\nunresolved manual signoff ${(handshakePack.unresolved_manual_signoff_count ?? 0)} · org-ready deps ${(handshakePack.org_ready_dependency_count ?? 0)} · contact gaps ${(handshakePack.contact_gap_count ?? 0)}\nlaunch waves ${(handshakePack.launch_wave_count ?? 0)} · launch customers ${(handshakePack.launch_customer_count ?? 0)}\nrefs ${((handshakePack.refs || {}).doc_refs || []).join(" / ") || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(handshakeCard);
    }

    if (commercialization.human_signoff_closure_summary) {
      const closure = commercialization.human_signoff_closure_summary || {};
      const closureCard = document.createElement("article");
      closureCard.className = "list-card";
      closureCard.innerHTML = `
        <div class="list-card-head">
          <h3>Human Signoff Closure</h3>
          <span class="list-card-score">${closure.item_count ?? 0} items</span>
        </div>
        <p class="list-card-body">signoff ${(closure.signoff_id || "-")}\nblockers ${(closure.blocker_counts && Object.entries(closure.blocker_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nowners ${(closure.owner_counts && Object.entries(closure.owner_counts).map(([key, value]) => `${key}=${Object.values(value || {}).reduce((acc, item) => acc + Number(item || 0), 0)}`).join(" / ")) || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(closureCard);
    }

    if (commercialization.launch_command_center_summary) {
      const command = commercialization.launch_command_center_summary || {};
      const commandCard = document.createElement("article");
      commandCard.className = "list-card";
      commandCard.innerHTML = `
        <div class="list-card-head">
          <h3>Launch Week Command Center</h3>
          <span class="list-card-score">${command.watchlist_count ?? 0} customers</span>
        </div>
        <p class="list-card-body">launch waves ${(command.launch_wave_count ?? 0)} · revenue protection alerts ${(command.revenue_protection_alert_count ?? 0)}\nlatest preflight ${command.latest_preflight_by_wave ? Object.entries(command.latest_preflight_by_wave).map(([key, value]) => `${key}:${value.status}/${value.go_no_go}`).join(" / ") : "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(commandCard);
    }

    if (commercialization.wave_activation_summary) {
      const activation = commercialization.wave_activation_summary || {};
      const activationCard = document.createElement("article");
      activationCard.className = "list-card";
      activationCard.innerHTML = `
        <div class="list-card-head">
          <h3>Wave Activation</h3>
          <span class="list-card-score">${activation.wave_count ?? 0} waves</span>
        </div>
        <p class="list-card-body">active ${(activation.active_count ?? 0)} · armed ${(activation.armed_count ?? 0)} · activation_ready ${(activation.activation_ready_count ?? 0)} · blocked ${(activation.blocked_count ?? 0)}</p>
      `;
      dom.opsEvalMetrics.appendChild(activationCard);
    }

    if (commercialization.go_live_day_summary) {
      const goLiveDay = commercialization.go_live_day_summary || {};
      const goLiveDayCard = document.createElement("article");
      goLiveDayCard.className = "list-card";
      goLiveDayCard.innerHTML = `
        <div class="list-card-head">
          <h3>Go-Live Day Runner</h3>
          <span class="list-card-score">${goLiveDay.run_count ?? 0} runs</span>
        </div>
        <p class="list-card-body">latest ${(goLiveDay.latest_run_id || "-")}\nstatus ${(goLiveDay.status_counts && Object.entries(goLiveDay.status_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(goLiveDayCard);
    }

    if (commercialization.customer_success_summary) {
      const success = commercialization.customer_success_summary || {};
      const successCard = document.createElement("article");
      successCard.className = "list-card";
      successCard.innerHTML = `
        <div class="list-card-head">
          <h3>Customer Success Snapshot</h3>
          <span class="list-card-score">${success.account_count ?? 0} accounts</span>
        </div>
        <p class="list-card-body">bands ${(success.band_counts && Object.entries(success.band_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nprovisional_30_day ${(success.provisional_30_day_count ?? 0)} · launch waves ${(success.launch_wave_count ?? 0)}</p>
      `;
      dom.opsEvalMetrics.appendChild(successCard);
    }

    if (commercialization.launch_week_guard_summary) {
      const guard = commercialization.launch_week_guard_summary || {};
      const guardCard = document.createElement("article");
      guardCard.className = "list-card";
      guardCard.innerHTML = `
        <div class="list-card-head">
          <h3>First 7 Days Guard</h3>
          <span class="list-card-score">${guard.run_count ?? 0} runs</span>
        </div>
        <p class="list-card-body">latest ${(guard.latest_run_id || "-")}\nreplication-ready ${(guard.ready_count ?? 0)}</p>
      `;
      dom.opsEvalMetrics.appendChild(guardCard);
    }

    if (commercialization.launch_ledger_summary) {
      const ledger = commercialization.launch_ledger_summary || {};
      const ledgerCard = document.createElement("article");
      ledgerCard.className = "list-card";
      ledgerCard.innerHTML = `
        <div class="list-card-head">
          <h3>Production Launch Ledger</h3>
          <span class="list-card-score">${ledger.event_count ?? 0} events</span>
        </div>
        <p class="list-card-body">severity ${(ledger.severity_counts && Object.entries(ledger.severity_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nphase ${(ledger.phase_counts && Object.entries(ledger.phase_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"} </p>
      `;
      dom.opsEvalMetrics.appendChild(ledgerCard);
    }

    if (commercialization.launch_week_alert_pack?.summary) {
      const pack = commercialization.launch_week_alert_pack;
      const launchCard = document.createElement("article");
      launchCard.className = "list-card";
      launchCard.innerHTML = `
        <div class="list-card-head">
          <h3>Launch Week Alert Pack</h3>
          <span class="list-card-score">${pack.summary.alert_count ?? 0} alerts</span>
        </div>
        <p class="list-card-body">severity ${(pack.summary.by_severity && Object.entries(pack.summary.by_severity).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nowners ${(pack.summary.by_owner_role && Object.entries(pack.summary.by_owner_role).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nalerts ${(pack.alerts || []).map((item) => `${item.alert_key}:${item.count}/${item.owner_role}`).join(" / ") || "-"}\nrefs ${(pack.alerts || []).flatMap((item) => item.drilldown_refs || []).slice(0, 8).map((ref) => `${ref.kind}:${ref.id}`).join(" / ") || "-"}</p>
      `;
      dom.opsEvalMetrics.appendChild(launchCard);
    }
  }

  clearNode(dom.opsCrossPackQuality);
  if (!opsState.opsCrossPackQuality) {
    clearNode(dom.opsCrossPackQuality, "这里会显示跨包通过率、薄弱世界与核心指标变化。");
  } else {
    const benchmark = opsState.opsCrossPackQuality;
    const overviewCard = document.createElement("article");
    overviewCard.className = "list-card";
    overviewCard.innerHTML = `
      <div class="list-card-head">
        <h3>跨包概览</h3>
        <span class="list-card-score">${formatPercent(benchmark.cross_pack_pass_rate)}</span>
      </div>
      <p class="list-card-body">覆盖 ${benchmark.worlds?.length || 0} 个世界包\n通过率变化 ${benchmark.delta_summary?.cross_pack_pass_rate_delta >= 0 ? "+" : ""}${Number(benchmark.delta_summary?.cross_pack_pass_rate_delta || 0).toFixed(3)}</p>
    `;
    dom.opsCrossPackQuality.appendChild(overviewCard);

    const failingCard = document.createElement("article");
    failingCard.className = "list-card";
    failingCard.innerHTML = `
      <div class="list-card-head">
        <h3>薄弱世界</h3>
        <span class="list-card-score">${(benchmark.top_failing_packs || []).length} 个</span>
      </div>
      <p class="list-card-body">${(benchmark.top_failing_packs || []).map((item) => `${item.world_id}\n通过率 ${formatPercent(item.pass_rate)} · 阻塞率 ${formatPercent(item.block_rate)}\n主问题：${(item.top_issue_categories || []).map((issue) => issue.issue_code).join(" / ") || "-"}\n最弱维度：${(item.weakest_dimensions || []).map((dimension) => `${dimension.name}=${Number(dimension.value || 0).toFixed(3)}`).join(" / ") || "-"}\n建议目标：${item.recommended_target || "-"}\n声音 ${Number(item.voice_separation_score || 0).toFixed(2)} · 动作 ${Number(item.emotion_action_specificity || 0).toFixed(2)} · 泄漏 ${Number(item.prose_leak_rate || 0).toFixed(3)}`).join("\n\n") || "暂无跨包薄弱项。"}</p>
    `;
    dom.opsCrossPackQuality.appendChild(failingCard);

    const deltaCard = document.createElement("article");
    deltaCard.className = "list-card";
    deltaCard.innerHTML = `
      <div class="list-card-head">
        <h3>指标变化</h3>
        <span class="list-card-score">${(benchmark.delta_summary?.regressions || []).length} 个回退</span>
      </div>
      <p class="list-card-body">${(benchmark.delta_summary?.regressions || []).map((item) => `${item.world_id}\n${item.metrics.join(" / ")}`).join("\n\n") || "当前没有跨 Pack 指标回退。"}</p>
    `;
    dom.opsCrossPackQuality.appendChild(deltaCard);

    const diagnosisCard = document.createElement("article");
    diagnosisCard.className = "list-card";
    diagnosisCard.innerHTML = `
      <div class="list-card-head">
        <h3>逐包诊断</h3>
        <span class="list-card-score">${(benchmark.worlds || []).length} 个</span>
      </div>
      <p class="list-card-body">${(benchmark.worlds || []).map((item) => `${item.world_id}\n主问题：${item.issue_summary?.dominant_issue || "-"}\n最弱维度：${(item.issue_summary?.weakest_dimensions || []).map((dimension) => `${dimension.name}=${Number(dimension.value || 0).toFixed(3)}`).join(" / ") || "-"}\n建议目标：${item.issue_summary?.recommended_target || "-"}`).join("\n\n") || "暂无诊断数据。"}</p>
    `;
    dom.opsCrossPackQuality.appendChild(diagnosisCard);

    const batchValidation = benchmark.strategy_bundle_batch_validation || {};
    const batchOverviewCard = document.createElement("article");
    batchOverviewCard.className = "list-card";
    batchOverviewCard.innerHTML = `
      <div class="list-card-head">
        <h3>策略包批量验证概览</h3>
        <span class="list-card-score">${batchValidation.available ? (batchValidation.decision || "-") : "未运行"}</span>
      </div>
      <p class="list-card-body">策略包 ${(batchValidation.strategy_bundle_label || "-")}${batchValidation.strategy_bundle_id ? ` (${batchValidation.strategy_bundle_id})` : ""}\n已验证 ${batchValidation.validated_world_count ?? 0} 个 weakest packs · 有效率 ${Number(batchValidation.effectiveness_rate || 0).toFixed(3)}\n兼容世界：${(batchValidation.compatible_world_ids || []).join(" / ") || "-"}\n跳过世界：${(batchValidation.skipped_worlds || []).map((item) => `${item.world_id || "-"}(${item.reason || "-"})`).join(" / ") || (batchValidation.available ? "-" : (batchValidation.decision_reason || "未开启策略包批量验证"))}\n结论：${batchValidation.decision || "-"} · 原因：${batchValidation.decision_reason || "-"}</p>
    `;
    dom.opsCrossPackQuality.appendChild(batchOverviewCard);

    const batchAttributionCard = document.createElement("article");
    batchAttributionCard.className = "list-card";
    batchAttributionCard.innerHTML = `
      <div class="list-card-head">
        <h3>策略包执行归因</h3>
        <span class="list-card-score">${batchValidation.available ? `${batchValidation.validated_world_count || 0} 个` : "无数据"}</span>
      </div>
      <p class="list-card-body">overall status：${Object.entries(batchValidation.aggregated_result_attribution?.overall_status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\nstop decisions：${Object.entries(batchValidation.aggregated_result_attribution?.stop_decision_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\nready for validation：${batchValidation.aggregated_result_attribution?.ready_for_validation_count ?? 0}\n\n逐包结果：\n${(batchValidation.validated_worlds || []).map((item) => `${item.world_id}\n窗口 ${item.window_label || "-"} · issues ${(item.issue_codes || []).join(" / ") || "-"}\n状态 ${item.result_attribution?.overall_status || "-"} · ready ${item.ready_for_validation ? "yes" : "no"} · stop ${item.stop_decision?.decision || "-"}`).join("\n\n") || (batchValidation.available ? "暂无逐包执行结果。" : "未开启策略包批量验证。")}\n\n调整目标：\n${(batchValidation.adaptation_targets || []).map((item) => `${item.kind}:${item.name}=${item.count}`).join("\n") || "-"}</p>
    `;
    dom.opsCrossPackQuality.appendChild(batchAttributionCard);

    const batchHistory = benchmark.strategy_bundle_batch_validation_history || {};
    const batchTrend = benchmark.strategy_bundle_batch_validation_trend || {};
    const batchTrendCard = document.createElement("article");
    batchTrendCard.className = "list-card";
    batchTrendCard.innerHTML = `
      <div class="list-card-head">
        <h3>策略包历史趋势</h3>
        <span class="list-card-score">${batchTrend.trend_status || "insufficient_history"}</span>
      </div>
      <p class="list-card-body">策略包 ${(batchTrend.strategy_bundle_id || batchValidation.strategy_bundle_id || "-")}\n趋势原因 ${batchTrend.trend_reason || "-"}\n最新结论 ${batchTrend.latest_decision || "-"} · 最新有效率 ${Number(batchTrend.latest_effectiveness_rate || 0).toFixed(3)}\n有效率变化 ${Number(batchTrend.delta_effectiveness_rate || 0).toFixed(3)} · 建议淘汰 ${batchTrend.retire_recommended ? "yes" : "no"}\n最近有效 run ${batchTrend.recent_run_count ?? 0}\n\n最近几轮：\n${(batchHistory.entries || []).map((item) => `${item.generated_at || "-"}\n${item.decision || "-"} · effectiveness ${Number(item.effectiveness_rate || 0).toFixed(3)} · worlds ${item.validated_world_count ?? 0}`).join("\n\n") || "暂无已保存的策略包批量验证历史。"}</p>
    `;
    dom.opsCrossPackQuality.appendChild(batchTrendCard);
  }

  clearNode(dom.opsLearnedDashboard);
  clearNode(dom.opsLearnedImpact);
  clearNode(dom.opsLearnedCadence);
  clearNode(dom.opsLearnedAssistedGate);
  clearNode(dom.opsLearnedAssistedRerank);
  clearNode(dom.opsLearnedReviewQuality);
  clearNode(dom.opsLearnedTraining);
  clearNode(dom.opsLearnedEvidence);
  if (!opsState.opsLearnedDashboard) {
    clearNode(dom.opsLearnedDashboard, "这里会显示评估器和重排器的统一学习层摘要。");
    clearNode(dom.opsLearnedImpact, "这里会显示评估器和重排器的学习层影响摘要、留存代理与付费代理。");
    clearNode(dom.opsLearnedCadence, "这里会显示评估器和重排器当前处于补数据、训练、验证、晋升还是全量启用阶段。");
    clearNode(dom.opsLearnedAssistedGate, "这里会显示辅助门控实验的配置、护栏、最近决策与回滚条件。");
    clearNode(dom.opsLearnedAssistedRerank, "这里会显示辅助重排实验的配置、护栏、最近决策与回滚条件。");
    clearNode(dom.opsLearnedReviewQuality, "这里会显示人工审阅覆盖、审阅人分布、样本质量告警与高覆盖补样待办。");
    clearNode(dom.opsLearnedTraining, "这里会显示最近一次学习层训练自动化结果。");
    clearNode(dom.opsLearnedEvidence, "这里会显示评估器和重排器的发布证据包摘要。");
  } else {
    const dashboard = opsState.opsLearnedDashboard;
    const learnedImpact = opsState.opsLearnedImpact || {};
    const learnedCadence = opsState.opsLearnedCadence || {};
    const assistedGate = opsState.opsLearnedAssistedGate || {};
    const assistedRerank = opsState.opsLearnedAssistedRerank || {};
    const overviewCard = document.createElement("article");
    overviewCard.className = "list-card";
    overviewCard.innerHTML = `
      <div class="list-card-head">
        <h3>学习层统一总览</h3>
        <span class="list-card-score">${dashboard.recommended_next_focus || "-"}</span>
      </div>
      <p class="list-card-body">${opsSections(
        opsSection("生成信息", [
          opsFieldLine("生成时间", formatTimestamp(dashboard.generated_at)),
          opsFieldLine("建议关注", dashboard.recommended_next_focus || "-"),
        ]),
        opsSection("共同薄弱项", [
          opsFieldLine("共同薄弱世界", (dashboard.shared_weak_worlds || []).map((worldId) => opsWorldLabel(worldId)).join(" / ") || "-"),
          opsFieldLine("共同薄弱问题", opsIssueCodeList(dashboard.shared_weak_issue_codes || [])),
          opsFieldLine("告警", (dashboard.warnings || []).join(" / ") || "-"),
        ])
      )}</p>
    `;
    dom.opsLearnedDashboard.appendChild(overviewCard);

    if (!learnedImpact.track_summaries?.length) {
      clearNode(dom.opsLearnedImpact, "这里会显示评估器和重排器的学习层影响摘要、留存代理与付费代理。");
    } else {
      const trackCard = document.createElement("article");
      trackCard.className = "list-card";
      trackCard.innerHTML = `
        <div class="list-card-head">
          <h3>轨道影响摘要</h3>
          <span class="list-card-score">${learnedImpact.track_summaries.length} tracks</span>
        </div>
        <p class="list-card-body">${opsParagraphList(learnedImpact.track_summaries || [], (item) =>
          `${opsTrackLabel(item.track)}\n` +
          `${opsFieldLine("影响状态", opsStatusLabel(item.impact_status))} · ${opsFieldLine("证据充分度", item.evidence_sufficiency || "-")}\n` +
          `${opsFieldLine("样本数", item.sample_count ?? 0)} · ${opsFieldLine("覆盖世界", item.world_coverage_count ?? 0)} · ${opsFieldLine("覆盖问题", item.issue_coverage_count ?? 0)}\n` +
          `${opsFieldLine("继续阅读相关性", item.continuation_correlation !== null && item.continuation_correlation !== undefined ? Number(item.continuation_correlation).toFixed(2) : "-")} · ${opsFieldLine("付费相关性", item.monetization_correlation !== null && item.monetization_correlation !== undefined ? Number(item.monetization_correlation).toFixed(2) : "-")}\n` +
          `${opsFieldLine("影子指标", item.shadow_agreement_or_accuracy !== null && item.shadow_agreement_or_accuracy !== undefined ? Number(item.shadow_agreement_or_accuracy).toFixed(2) : "-")} · ${opsFieldLine("建议动作", item.recommended_next_action || "-")}`
        )}</p>
      `;
      dom.opsLearnedImpact.appendChild(trackCard);

      const proxyCard = document.createElement("article");
      proxyCard.className = "list-card";
      proxyCard.innerHTML = `
        <div class="list-card-head">
          <h3>留存 / 付费代理指标</h3>
          <span class="list-card-score">${Number(learnedImpact.retention_proxies?.online_continuation_correlation || 0).toFixed(2)}</span>
        </div>
        <p class="list-card-body">${opsSections(
          opsSection("继续阅读信号", [
            opsFieldLine("样本数", learnedImpact.retention_proxies?.continuation_signal_summary?.sample_count ?? 0),
            opsFieldLine("正样本", learnedImpact.retention_proxies?.continuation_signal_summary?.positive_count ?? 0),
            opsFieldLine("负样本", learnedImpact.retention_proxies?.continuation_signal_summary?.negative_count ?? 0),
          ]),
          opsSection("付费信号", [
            opsFieldLine("发起支付", learnedImpact.monetization_proxies?.checkout_started_count ?? 0),
            opsFieldLine("订阅生效", learnedImpact.monetization_proxies?.subscription_activated_count ?? 0),
            opsFieldLine("出现挡板", learnedImpact.monetization_proxies?.payment_required_count ?? 0),
            opsFieldLine("故事点数消耗", learnedImpact.monetization_proxies?.story_credit_consumed_count ?? 0),
            opsFieldLine("创作点数消耗", learnedImpact.monetization_proxies?.studio_credit_consumed_count ?? 0),
          ]),
          opsSection("质量相关性", [
            opsFieldLine("质量→支付", learnedImpact.monetization_proxies?.quality_to_checkout_correlation !== null && learnedImpact.monetization_proxies?.quality_to_checkout_correlation !== undefined ? Number(learnedImpact.monetization_proxies.quality_to_checkout_correlation).toFixed(2) : "-"),
            opsFieldLine("质量→订阅", learnedImpact.monetization_proxies?.quality_to_subscription_correlation !== null && learnedImpact.monetization_proxies?.quality_to_subscription_correlation !== undefined ? Number(learnedImpact.monetization_proxies.quality_to_subscription_correlation).toFixed(2) : "-"),
            opsFieldLine("质量→挡板", learnedImpact.monetization_proxies?.quality_to_paywall_correlation !== null && learnedImpact.monetization_proxies?.quality_to_paywall_correlation !== undefined ? Number(learnedImpact.monetization_proxies.quality_to_paywall_correlation).toFixed(2) : "-"),
          ])
        )}</p>
      `;
      dom.opsLearnedImpact.appendChild(proxyCard);

      const experiment = learnedImpact.experiment_summaries?.assisted_gate || {};
      const experimentCard = document.createElement("article");
      experimentCard.className = "list-card";
      experimentCard.innerHTML = `
        <div class="list-card-head">
          <h3>辅助门控影响</h3>
          <span class="list-card-score">${experiment.impact_status || "-"}</span>
        </div>
        <p class="list-card-body">${opsSections(
          opsSection("实验状态", [
            opsFieldLine("模式", experiment.mode || "-"),
            opsFieldLine("是否开启", opsBooleanLabel(experiment.enabled)),
            opsFieldLine("证据充分度", experiment.evidence_sufficiency || "-"),
          ]),
          opsSection("覆盖与决策", [
            opsFieldLine("决策数", experiment.decision_count ?? 0),
            opsFieldLine("覆盖世界数", experiment.world_coverage_count ?? 0),
            opsFieldLine("进入分桶", experiment.in_bucket_count ?? 0),
            opsFieldLine("原本会拦截", experiment.would_block_count ?? 0),
            opsFieldLine("辅助拦截", experiment.assisted_block_count ?? 0),
          ]),
          opsSection("影响指标", [
            opsFieldLine("继续阅读相关性", experiment.continuation_correlation !== null && experiment.continuation_correlation !== undefined ? Number(experiment.continuation_correlation).toFixed(2) : "-"),
            opsFieldLine("付费相关性", experiment.monetization_correlation !== null && experiment.monetization_correlation !== undefined ? Number(experiment.monetization_correlation).toFixed(2) : "-"),
            opsFieldLine("拦截→支付", experiment.assisted_block_to_checkout_correlation !== null && experiment.assisted_block_to_checkout_correlation !== undefined ? Number(experiment.assisted_block_to_checkout_correlation).toFixed(2) : "-"),
            opsFieldLine("拦截→订阅", experiment.assisted_block_to_subscription_correlation !== null && experiment.assisted_block_to_subscription_correlation !== undefined ? Number(experiment.assisted_block_to_subscription_correlation).toFixed(2) : "-"),
            opsFieldLine("拦截→挡板", experiment.assisted_block_to_paywall_correlation !== null && experiment.assisted_block_to_paywall_correlation !== undefined ? Number(experiment.assisted_block_to_paywall_correlation).toFixed(2) : "-"),
            opsFieldLine("建议动作", experiment.recommended_next_action || "-"),
          ])
        )}</p>
      `;
      dom.opsLearnedImpact.appendChild(experimentCard);

      const worldCard = document.createElement("article");
      worldCard.className = "list-card";
      worldCard.innerHTML = `
        <div class="list-card-head">
          <h3>World Impact Drill-down</h3>
          <span class="list-card-score">${(learnedImpact.world_impact_details || []).length} worlds</span>
        </div>
        <p class="list-card-body">${(learnedImpact.world_impact_details || []).slice(0, 5).map((item) => `${item.world_id}\ncontinuation ${item.continuation_correlation !== null && item.continuation_correlation !== undefined ? Number(item.continuation_correlation).toFixed(2) : "-"} · samples ${item.continuation_sample_count ?? 0} · gap ${item.continuation_sample_gap ?? 0}\ncheckout ${item.checkout_started_count ?? 0} · activated ${item.subscription_activated_count ?? 0} · paywall ${item.payment_required_count ?? 0}\nassisted decisions ${item.assisted_gate_decision_count ?? 0} · in bucket ${item.assisted_gate_in_bucket_count ?? 0} · assisted block ${item.assisted_gate_assisted_block_count ?? 0}\nevaluator ${item.evaluator_agreement_rate !== null && item.evaluator_agreement_rate !== undefined ? Number(item.evaluator_agreement_rate).toFixed(2) : "-"} · reranker ${item.reranker_accuracy !== null && item.reranker_accuracy !== undefined ? Number(item.reranker_accuracy).toFixed(2) : "-"}\nnext ${item.recommended_next_action || "-"}`).join("\n\n") || "-"}</p>
      `;
      dom.opsLearnedImpact.appendChild(worldCard);

      const issueCard = document.createElement("article");
      issueCard.className = "list-card";
      issueCard.innerHTML = `
        <div class="list-card-head">
          <h3>Issue Impact Drill-down</h3>
          <span class="list-card-score">${(learnedImpact.issue_impact_details || []).length} issues</span>
        </div>
        <p class="list-card-body">${(learnedImpact.issue_impact_details || []).slice(0, 5).map((item) => `${item.issue_code}\naffected worlds ${item.affected_world_count ?? 0} · evaluator samples ${item.evaluator_sample_count ?? 0} · reranker samples ${item.reranker_sample_count ?? 0}\ncontinuation ${item.continuation_correlation !== null && item.continuation_correlation !== undefined ? Number(item.continuation_correlation).toFixed(2) : "-"} · monetization ${item.monetization_correlation !== null && item.monetization_correlation !== undefined ? Number(item.monetization_correlation).toFixed(2) : "-"}\npaywall ${item.payment_required_count ?? 0} · checkout ${item.checkout_started_count ?? 0} · activated ${item.subscription_activated_count ?? 0}\nassisted decisions ${item.assisted_gate_decision_count ?? 0} · assisted block ${item.assisted_gate_assisted_block_count ?? 0}\nnext ${item.recommended_next_action || "-"}`).join("\n\n") || "-"}</p>
      `;
      dom.opsLearnedImpact.appendChild(issueCard);

      const accumulationCard = document.createElement("article");
      accumulationCard.className = "list-card";
      accumulationCard.innerHTML = `
        <div class="list-card-head">
          <h3>Impact Sample Accumulation</h3>
          <span class="list-card-score">${learnedImpact.sample_accumulation?.retention?.worlds_below_target_count ?? 0} retention gaps</span>
        </div>
        <p class="list-card-body">retention target/world ${learnedImpact.sample_accumulation?.retention?.target_sample_count_per_world ?? 0} · worlds below ${learnedImpact.sample_accumulation?.retention?.worlds_below_target_count ?? 0}\nevaluator target/world ${learnedImpact.sample_accumulation?.evaluator?.target_sample_count_per_world ?? 0} · worlds below ${learnedImpact.sample_accumulation?.evaluator?.worlds_below_target_count ?? 0}\nreranker target/world ${learnedImpact.sample_accumulation?.reranker?.target_sample_count_per_world ?? 0} · worlds below ${learnedImpact.sample_accumulation?.reranker?.worlds_below_target_count ?? 0}\n\nwarnings:\n${(learnedImpact.warnings || []).join("\n") || "-"}</p>
      `;
      dom.opsLearnedImpact.appendChild(accumulationCard);
    }

    if (!learnedCadence.track_summaries?.length) {
      clearNode(dom.opsLearnedCadence, "这里会显示评估器和重排器当前处于补数据、训练、验证、晋升还是全量启用阶段。");
    } else {
      const cadenceSummaryCard = document.createElement("article");
      cadenceSummaryCard.className = "list-card";
      cadenceSummaryCard.innerHTML = `
        <div class="list-card-head">
          <h3>Learned Cadence Summary</h3>
          <span class="list-card-score">${learnedCadence.cadence_summary?.recommended_next_action || "-"}</span>
        </div>
        <p class="list-card-body">active ${(learnedCadence.cadence_summary?.active_tracks || []).join(" / ") || "-"}\nready ${(learnedCadence.cadence_summary?.ready_queue || []).join(" / ") || "-"} · attention ${(learnedCadence.cadence_summary?.attention_queue || []).join(" / ") || "-"}\nactivate ${(learnedCadence.cadence_summary?.activation_queue || []).join(" / ") || "-"}\npromotion ${(learnedCadence.cadence_summary?.promotion_queue || []).join(" / ") || "-"}\nvalidate ${(learnedCadence.cadence_summary?.validation_queue || []).join(" / ") || "-"}\ntraining ${(learnedCadence.cadence_summary?.training_queue || []).join(" / ") || "-"}\ncollect ${(learnedCadence.cadence_summary?.collection_queue || []).join(" / ") || "-"}\nrebuild ${(learnedCadence.cadence_summary?.rebuild_queue || []).join(" / ") || "-"}\n\nwarnings:\n${(learnedCadence.warnings || []).join("\n") || "-"}</p>
      `;
      dom.opsLearnedCadence.appendChild(cadenceSummaryCard);

      (learnedCadence.track_summaries || []).forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.track}</h3>
            <span class="list-card-score">${item.cadence_stage || "-"} · ${item.cadence_health || "-"}</span>
          </div>
          <p class="list-card-body">next ${item.recommended_next_action || "-"}\nexamples ${item.relevant_example_count ?? 0} · worlds ${item.world_coverage_count ?? 0} · issues ${item.issue_coverage_count ?? 0}\nlatest sample ${item.latest_sample_at ? formatTimestamp(item.latest_sample_at) : "-"}\nartifact ${item.artifact_state?.artifact_present ? "present" : "missing"} · freshness ${item.freshness?.status || "-"}\ncheckpoint ${item.checkpoint_summary?.split_status || "-"} · train ${item.checkpoint_summary?.train_count ?? 0} / val ${item.checkpoint_summary?.val_count ?? 0} / test ${item.checkpoint_summary?.test_count ?? 0}\nshadow ${item.validation_summary?.shadow_status || "-"} · impact ${item.validation_summary?.impact_status || "-"} · sufficiency ${item.validation_summary?.evidence_sufficiency || "-"}\nshadow metric ${item.validation_summary?.shadow_agreement_or_accuracy !== null && item.validation_summary?.shadow_agreement_or_accuracy !== undefined ? Number(item.validation_summary.shadow_agreement_or_accuracy).toFixed(3) : "-"}\npromotion ${item.promotion_summary?.recommendation_status || "-"} · approval ${item.promotion_summary?.approval_status || "-"} · age ${item.promotion_summary?.hours_since_approval !== null && item.promotion_summary?.hours_since_approval !== undefined ? Number(item.promotion_summary.hours_since_approval).toFixed(1) : "-"}h\nrollout ${item.rollout_summary?.rollout_status || "-"} · safe ${item.rollout_summary?.safe_to_rollout ? "yes" : "no"} · age ${item.rollout_summary?.hours_since_rollout !== null && item.rollout_summary?.hours_since_rollout !== undefined ? Number(item.rollout_summary.hours_since_rollout).toFixed(1) : "-"}h\ntraining run ${(item.latest_training_run?.run_id || "-")} · ${(item.latest_training_run?.status || "never")}\nsource counts ${Object.entries(item.source_sample_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\ncoverage gaps review ${item.coverage_gaps?.review_sample_backlog_count ?? 0} · pair ${item.coverage_gaps?.pair_coverage_backlog_count ?? 0} · disagreement ${item.coverage_gaps?.disagreement_issue_count ?? 0}\nstale ${(item.stale_reasons || []).join(" / ") || "-"}\nrecent events:\n${(item.recent_events || []).map((event) => `${event.event_type} · ${event.status || "-"} · ${event.occurred_at ? formatTimestamp(event.occurred_at) : "-"}\n${event.summary || "-"}`).join("\n\n") || "-"}\n\nwarnings:\n${(item.warnings || []).join("\n") || "-"}</p>
        `;
        dom.opsLearnedCadence.appendChild(card);
      });
    }

    if (!assistedGate.config) {
      clearNode(dom.opsLearnedAssistedGate, "这里会显示辅助门控实验的配置、护栏、最近决策与回滚条件。");
    } else {
      const config = assistedGate.config || {};
      if (dom.opsAssistedGateBucket) {
        dom.opsAssistedGateBucket.value = String(config.config?.bucket_percentage ?? 0);
      }
      if (dom.opsAssistedGateConfidence) {
        dom.opsAssistedGateConfidence.value = String(config.config?.confidence_threshold ?? 0.9);
      }
      if (dom.opsAssistedGateWorldAllowlist) {
        dom.opsAssistedGateWorldAllowlist.value = (config.config?.world_allowlist || []).join(", ");
      }
      const configCard = document.createElement("article");
      configCard.className = "list-card";
      configCard.innerHTML = `
        <div class="list-card-head">
          <h3>Assisted Gate Experiment</h3>
          <span class="list-card-score">${config.config?.enabled ? config.config?.mode || "-" : "disabled"}</span>
        </div>
        <p class="list-card-body">track ${assistedGate.track || "evaluator"}\nrecommended ${assistedGate.recommended_next_action || "-"}\nreviewer ${config.reviewer_id || "-"} · updated ${config.updated_at ? formatTimestamp(config.updated_at) : "-"}\nreason ${config.reason || "-"}\nbucket ${config.config?.bucket_percentage ?? 0}% · threshold ${config.config?.confidence_threshold ?? 0}\nallowlist ${(config.config?.world_allowlist || []).join(" / ") || "-"}\nrollout ${assistedGate.rollout_summary?.rollout_status || "-"} · candidate ${assistedGate.rollout_summary?.candidate_ready ? "yes" : "no"} · approval ${assistedGate.rollout_summary?.latest_approval_status || "-"}\n\nguardrails:\n${(assistedGate.guardrails || []).join("\n") || "-"}\n\nrollback:\n${(assistedGate.rollback_conditions || []).join("\n") || "-"}</p>
      `;
      dom.opsLearnedAssistedGate.appendChild(configCard);

      const counterCard = document.createElement("article");
      counterCard.className = "list-card";
      counterCard.innerHTML = `
        <div class="list-card-head">
          <h3>Experiment Counters</h3>
          <span class="list-card-score">${assistedGate.counters?.assisted_block_count ?? 0} assisted blocks</span>
        </div>
        <p class="list-card-body">decisions ${assistedGate.counters?.decision_count ?? 0}\nshadow ${assistedGate.counters?.shadow_count ?? 0} · skipped ${assistedGate.counters?.skipped_count ?? 0}\nwould block ${assistedGate.counters?.would_block_count ?? 0} · in bucket ${assistedGate.counters?.in_bucket_count ?? 0}\nassisted block ${assistedGate.counters?.assisted_block_count ?? 0}</p>
      `;
      dom.opsLearnedAssistedGate.appendChild(counterCard);

      if ((assistedGate.recent_decisions || []).length) {
        const decisionsCard = document.createElement("article");
        decisionsCard.className = "list-card";
        decisionsCard.innerHTML = `
          <div class="list-card-head">
            <h3>Recent Assisted Decisions</h3>
            <span class="list-card-score">${(assistedGate.recent_decisions || []).length} receipts</span>
          </div>
          <p class="list-card-body">${(assistedGate.recent_decisions || []).slice(0, 6).map((item) => `${item.world_version_id || "-"}\n${item.status || "-"} · ${item.mode || "-"} · ${item.guardrail_status || "-"}\nbucket ${item.bucket_match ? "yes" : "no"} · would_block ${item.would_block ? "yes" : "no"} · action ${item.assisted_action || "-"}\nfinal ${(item.final_gate_errors || []).join(" / ") || "-"}\nupdated ${item.updated_at ? formatTimestamp(item.updated_at) : "-"}`).join("\n\n")}</p>
        `;
        dom.opsLearnedAssistedGate.appendChild(decisionsCard);
      }
    }

    if (!assistedRerank.config) {
      clearNode(dom.opsLearnedAssistedRerank, "这里会显示辅助重排实验的配置、护栏、最近决策与回滚条件。");
    } else {
      const config = assistedRerank.config || {};
      if (dom.opsAssistedRerankBucket) {
        dom.opsAssistedRerankBucket.value = String(config.config?.bucket_percentage ?? 0);
      }
      if (dom.opsAssistedRerankConfidence) {
        dom.opsAssistedRerankConfidence.value = String(config.config?.confidence_threshold ?? 0.65);
      }
      if (dom.opsAssistedRerankCandidateWindow) {
        dom.opsAssistedRerankCandidateWindow.value = String(config.config?.candidate_window ?? 3);
      }
      if (dom.opsAssistedRerankMaxScoreGap) {
        dom.opsAssistedRerankMaxScoreGap.value = String(config.config?.max_score_gap ?? 0.08);
      }
      if (dom.opsAssistedRerankWorldAllowlist) {
        dom.opsAssistedRerankWorldAllowlist.value = (config.config?.world_allowlist || []).join(", ");
      }
      const configCard = document.createElement("article");
      configCard.className = "list-card";
      configCard.innerHTML = `
        <div class="list-card-head">
          <h3>Assisted Rerank Experiment</h3>
          <span class="list-card-score">${config.config?.enabled ? config.config?.mode || "-" : "disabled"}</span>
        </div>
        <p class="list-card-body">track ${assistedRerank.track || "reranker"}\nrecommended ${assistedRerank.recommended_next_action || "-"}\nreviewer ${config.reviewer_id || "-"} · updated ${config.updated_at ? formatTimestamp(config.updated_at) : "-"}\nreason ${config.reason || "-"}\nbucket ${config.config?.bucket_percentage ?? 0}% · threshold ${config.config?.confidence_threshold ?? 0}\nwindow ${config.config?.candidate_window ?? 0} · max gap ${config.config?.max_score_gap ?? 0}\nallowlist ${(config.config?.world_allowlist || []).join(" / ") || "-"}\nrollout ${assistedRerank.rollout_summary?.rollout_status || "-"} · candidate ${assistedRerank.rollout_summary?.candidate_ready ? "yes" : "no"} · approval ${assistedRerank.rollout_summary?.latest_approval_status || "-"}\n\nguardrails:\n${(assistedRerank.guardrails || []).join("\n") || "-"}\n\nrollback:\n${(assistedRerank.rollback_conditions || []).join("\n") || "-"}</p>
      `;
      dom.opsLearnedAssistedRerank.appendChild(configCard);

      const counterCard = document.createElement("article");
      counterCard.className = "list-card";
      counterCard.innerHTML = `
        <div class="list-card-head">
          <h3>Rerank Experiment Counters</h3>
          <span class="list-card-score">${assistedRerank.counters?.assisted_swap_count ?? 0} assisted swaps</span>
        </div>
        <p class="list-card-body">decisions ${assistedRerank.counters?.decision_count ?? 0}\nshadow ${assistedRerank.counters?.shadow_count ?? 0} · skipped ${assistedRerank.counters?.skipped_count ?? 0}\nwould swap ${assistedRerank.counters?.would_swap_count ?? 0} · in bucket ${assistedRerank.counters?.in_bucket_count ?? 0}\nassisted swap ${assistedRerank.counters?.assisted_swap_count ?? 0}</p>
      `;
      dom.opsLearnedAssistedRerank.appendChild(counterCard);

      if ((assistedRerank.recent_decisions || []).length) {
        const decisionsCard = document.createElement("article");
        decisionsCard.className = "list-card";
        decisionsCard.innerHTML = `
          <div class="list-card-head">
            <h3>Recent Assisted Rerank Decisions</h3>
            <span class="list-card-score">${(assistedRerank.recent_decisions || []).length} receipts</span>
          </div>
          <p class="list-card-body">${(assistedRerank.recent_decisions || []).slice(0, 6).map((item) => `${item.world_version_id || "-"}\n${item.status || "-"} · ${item.mode || "-"} · beat ${item.beat_index || "-"}\nbucket ${item.bucket_match ? "yes" : "no"} · would_swap ${item.would_swap ? "yes" : "no"} · action ${item.assisted_action || "-"}\nbaseline ${item.baseline_event_id || "-"} -> selected ${item.selected_event_id || "-"}\nupdated ${item.updated_at ? formatTimestamp(item.updated_at) : "-"}`).join("\n\n")}</p>
        `;
        dom.opsLearnedAssistedRerank.appendChild(decisionsCard);
      }
    }

    if (!opsState.opsLearnedReviewQuality) {
      clearNode(dom.opsLearnedReviewQuality, "这里会显示人工审阅覆盖、审阅人分布、样本质量告警与高覆盖补样待办。");
    } else {
      const reviewQuality = opsState.opsLearnedReviewQuality;
      const qualityCard = document.createElement("article");
      qualityCard.className = "list-card";
      qualityCard.innerHTML = `
        <div class="list-card-head">
          <h3>Human Review Coverage & Quality</h3>
          <span class="list-card-score">${reviewQuality.coverage_summary?.worlds_below_target_count ?? 0} gaps</span>
        </div>
        <p class="list-card-body">samples ${reviewQuality.quality_summary?.sample_count ?? 0} · worlds ${reviewQuality.quality_summary?.world_coverage_count ?? 0} · versions ${reviewQuality.quality_summary?.version_coverage_count ?? 0}\nvalidated refs ${reviewQuality.quality_summary?.validated_reference_rate !== null && reviewQuality.quality_summary?.validated_reference_rate !== undefined ? Number(reviewQuality.quality_summary.validated_reference_rate).toFixed(2) : "-"}\nwarning samples ${reviewQuality.quality_summary?.warning_sample_count ?? 0}\nmissing session ${reviewQuality.quality_summary?.missing_session_context_count ?? 0} · missing issues ${reviewQuality.quality_summary?.missing_linked_issue_codes_count ?? 0} · ref not validated ${reviewQuality.quality_summary?.reference_not_validated_count ?? 0}\ntarget/world ${reviewQuality.coverage_summary?.target_sample_count_per_world ?? 0} · reviewer diversity ${reviewQuality.coverage_summary?.target_reviewer_diversity_per_world ?? 0}\nworld gaps ${reviewQuality.coverage_summary?.worlds_below_target_count ?? 0} · low diversity ${reviewQuality.coverage_summary?.low_diversity_world_count ?? 0} · focus issue gaps ${reviewQuality.coverage_summary?.focus_issue_gap_world_count ?? 0}\nshared weak worlds ${(reviewQuality.coverage_summary?.shared_weak_worlds || []).join(" / ") || "-"}\nwarnings:\n${(reviewQuality.warnings || []).join("\n") || "-"}</p>
      `;
      dom.opsLearnedReviewQuality.appendChild(qualityCard);

      const backlogCard = document.createElement("article");
      backlogCard.className = "list-card";
      backlogCard.innerHTML = `
        <div class="list-card-head">
          <h3>High-coverage Replenishment Backlog</h3>
          <span class="list-card-score">${(reviewQuality.replenishment_backlog || []).length} worlds</span>
        </div>
        <p class="list-card-body">${(reviewQuality.replenishment_backlog || []).slice(0, 5).map((item) => `${item.world_id}\npriority ${item.priority} · action ${item.recommended_action}\ncoverage ${item.human_review_count ?? 0}/${reviewQuality.coverage_summary?.target_sample_count_per_world ?? 0} · gap ${item.coverage_gap ?? 0}\nreviewers ${item.reviewer_diversity_count ?? 0}/${reviewQuality.coverage_summary?.target_reviewer_diversity_per_world ?? 0} · gap ${item.reviewer_diversity_gap ?? 0}\nfocus issue gaps ${(item.focus_issue_gaps || []).join(" / ") || "-"}\nwarning samples ${item.warning_sample_count ?? 0}\ncandidate chapters ${(item.candidate_backlog_chapters || []).join(" / ") || "-"}`).join("\n\n") || "-"}</p>
      `;
      dom.opsLearnedReviewQuality.appendChild(backlogCard);

      const flaggedCard = document.createElement("article");
      flaggedCard.className = "list-card";
      flaggedCard.innerHTML = `
        <div class="list-card-head">
          <h3>Flagged Human Review Samples</h3>
          <span class="list-card-score">${(reviewQuality.flagged_samples || []).length} flagged</span>
        </div>
        <p class="list-card-body">${(reviewQuality.flagged_samples || []).slice(0, 5).map((item) => `${item.sample_id}\n${item.world_id} · ${item.chapter_id} · reviewer ${item.reviewer_id || "-"}\nref ${item.reference_status || "-"} · warnings ${(item.ingestion_warnings || []).join(" / ") || "-"}\nlinked issues ${(item.linked_issue_codes || []).join(" / ") || "-"}\nnotes ${item.freeform_notes || "-"}`).join("\n\n") || "-"}</p>
      `;
      dom.opsLearnedReviewQuality.appendChild(flaggedCard);
    }

    const artifactCard = document.createElement("article");
    artifactCard.className = "list-card";
    artifactCard.innerHTML = `
      <div class="list-card-head">
        <h3>Artifact Status</h3>
        <span class="list-card-score">${dashboard.artifact_status?.evaluator?.available || dashboard.artifact_status?.reranker?.available ? "ready" : "partial"}</span>
      </div>
      <p class="list-card-body">evaluator ${dashboard.artifact_status?.evaluator?.available ? "available" : "missing"} · ${dashboard.artifact_status?.evaluator?.artifact_dir || "-"}\npublished ${dashboard.evaluator_shadow_summary?.published_at ? formatTimestamp(dashboard.evaluator_shadow_summary.published_at) : "-"}\nsource ${dashboard.evaluator_shadow_summary?.source_output_dir || "-"}\nfiles ${(dashboard.evaluator_shadow_summary?.artifact_files || []).join(" / ") || "-"}\n\nreranker ${dashboard.artifact_status?.reranker?.available ? "available" : "missing"} · ${dashboard.artifact_status?.reranker?.artifact_dir || "-"}\npublished ${dashboard.reranker_shadow_summary?.published_at ? formatTimestamp(dashboard.reranker_shadow_summary.published_at) : "-"}\nsource ${dashboard.reranker_shadow_summary?.source_output_dir || "-"}\nfiles ${(dashboard.reranker_shadow_summary?.artifact_files || []).join(" / ") || "-"}</p>
    `;
    dom.opsLearnedDashboard.appendChild(artifactCard);

    const coverageCard = document.createElement("article");
    coverageCard.className = "list-card";
    coverageCard.innerHTML = `
      <div class="list-card-head">
        <h3>Coverage Summary</h3>
        <span class="list-card-score">${((dashboard.coverage_summary?.evaluator_low_coverage_worlds || []).length + (dashboard.coverage_summary?.reranker_low_pair_coverage_worlds || []).length)}</span>
      </div>
      <p class="list-card-body">evaluator low coverage:\n${(dashboard.coverage_summary?.evaluator_low_coverage_worlds || []).map((item) => `${item.world_id}=${item.count}`).join("\n") || "-"}\n\nreranker low coverage:\n${(dashboard.coverage_summary?.reranker_low_pair_coverage_worlds || []).map((item) => `${item.world_id}=${item.count}`).join("\n") || "-"}</p>
    `;
    dom.opsLearnedDashboard.appendChild(coverageCard);

    if (!opsState.opsLearnedTrainingResult) {
      clearNode(dom.opsLearnedTraining, "这里会显示最近一次学习层训练自动化结果。");
    } else {
      const run = opsState.opsLearnedTrainingResult;
      if (run.job) {
        dom.opsLearnedTraining.appendChild(
          createListCard({
            title: "Latest Learned Training Job",
            score: run.job.status || "-",
            body:
              `job ${run.job.job_id || "-"}\n` +
              `requested by ${run.job.requested_by || "-"}\n` +
              `queued ${formatTimestamp(run.job.created_at)} · started ${run.job.started_at ? formatTimestamp(run.job.started_at) : "-"}\n` +
              `tracks ${(run.job.payload?.tracks || []).join(" / ") || "-"}\n` +
              `succeeded ${(run.job.result_summary?.tracks_succeeded || []).join(" / ") || "-"}\n` +
              `failed ${(run.job.result_summary?.tracks_failed || []).join(" / ") || "-"}`
          })
        );
      } else {
        dom.opsLearnedTraining.appendChild(
          createListCard({
            title: "Latest Learned Training Run",
            score: `${(run.summary?.tracks_succeeded || []).length}/${(run.summary?.tracks_requested || []).length}`,
            body:
              `run ${run.summary?.run_id || "-"}\n` +
              `generated ${run.summary?.generated_at || "-"}\n` +
              `succeeded ${(run.summary?.tracks_succeeded || []).join(" / ") || "-"}\n` +
              `failed ${(run.summary?.tracks_failed || []).join(" / ") || "-"}\n` +
              `output ${run.summary?.output_dir || "-"}`
          })
        );
      }
    }

    if (!opsState.opsLearnedEvidence) {
      clearNode(dom.opsLearnedEvidence, "这里会显示评估器和重排器的发布证据包摘要。");
    } else {
      ["evaluator", "reranker"].forEach((track) => {
        const evidence = opsState.opsLearnedEvidence?.[track];
        if (!evidence || !evidence.evidence_pack) return;
        const pack = evidence.evidence_pack;
        const summary = pack.evidence_summary || {};
        const artifactState = pack.artifact_state || {};
        dom.opsLearnedEvidence.appendChild(
          createListCard({
            title: `${track} promotion evidence`,
            score: summary.status || "-",
            body:
              `recommended ${summary.recommended_action || "-"} · approval ${pack.promotion_workflow?.approval_status || "-"}\n` +
              `artifact ${artifactState.available ? "available" : "missing"} · published ${artifactState.published_at || "-"}\n` +
              `warnings ${(artifactState.warnings || []).join(" / ") || "-"}\n` +
              `blockers ${(pack.promotion_summary?.blockers || []).join(" / ") || "-"}\n` +
              `advisories ${(pack.promotion_summary?.advisories || []).join(" / ") || "-"}\n` +
              `evidence ${evidence.evidence_path || "-"}`
          })
        );
      });
    }
  }

  clearNode(dom.opsLearnedCompare);
  if (!opsState.opsLearnedCompare) {
    clearNode(dom.opsLearnedCompare, "这里会显示评估器 / 重排器的影子候选对比。");
  } else {
    const compare = opsState.opsLearnedCompare;
    const compareCard = createListCard({
      title: "影子候选对比",
      score: opsPreferredCandidateLabel(compare.preferred_shadow_candidate),
      body: opsSections(
        opsSection("总体判断", [
          opsFieldLine("偏好候选", opsPreferredCandidateLabel(compare.preferred_shadow_candidate)),
          opsFieldLine("下一步", compare.recommended_next_action || "-"),
          opsFieldLine("可安全发布", opsTrackList(compare.safe_rollout_candidates || [])),
        ]),
        opsSection("评估器", [
          opsFieldLine("状态", opsStatusLabel(compare.evaluator_status || "-")),
          opsFieldLine("一致率", opsNumericValue(compare.evaluator_scorecard?.agreement_rate, 3)),
          opsFieldLine("训练/验证/测试", `${compare.evaluator_scorecard?.train_count || 0} / ${compare.evaluator_scorecard?.val_count || 0} / ${compare.evaluator_scorecard?.test_count || 0}`),
          opsFieldLine("告警", (compare.evaluator_scorecard?.warnings || []).join(" / ") || "-"),
          opsFieldLine("发布准备", compare.rollout_readiness?.evaluator?.candidate_ready ? "可以发布" : "继续观察"),
          opsFieldLine("审批提示", compare.rollout_readiness?.evaluator?.approval_hint || "-"),
        ]),
        opsSection("重排器", [
          opsFieldLine("状态", opsStatusLabel(compare.reranker_status || "-")),
          opsFieldLine("平均准确率", opsNumericValue(compare.reranker_scorecard?.average_world_accuracy, 3)),
          opsFieldLine("训练/验证/测试", `${compare.reranker_scorecard?.train_count || 0} / ${compare.reranker_scorecard?.val_count || 0} / ${compare.reranker_scorecard?.test_count || 0}`),
          opsFieldLine("告警", (compare.reranker_scorecard?.warnings || []).join(" / ") || "-"),
          opsFieldLine("发布准备", compare.rollout_readiness?.reranker?.candidate_ready ? "可以发布" : "继续观察"),
          opsFieldLine("审批提示", compare.rollout_readiness?.reranker?.approval_hint || "-"),
        ]),
        opsSection("分歧情况", [
          opsFieldLine("世界分歧", (compare.disagreement_worlds || []).map((item) => `${opsWorldLabel(item.world_id)}:${item.evaluator_signal}/${item.reranker_signal}`).join(" / ") || "-"),
          opsFieldLine("问题分歧", opsIssueCodeList((compare.disagreement_issue_codes || []).map((item) => item.issue_code || item))),
        ])
      )
    });
    dom.opsLearnedCompare.appendChild(compareCard);
  }

  clearNode(dom.opsLearnedRollout);
  if (!opsState.opsLearnedRollout) {
    clearNode(dom.opsLearnedRollout, "这里会显示学习层灰度摘要、可安全发布候选与回滚观察名单。");
  } else {
    const rollout = opsState.opsLearnedRollout;
    const summaryCard = document.createElement("article");
    summaryCard.className = "list-card";
    summaryCard.innerHTML = `
      <div class="list-card-head">
        <h3>Learned Rollout Summary</h3>
        <span class="list-card-score">${(rollout.active_tracks || []).join(" / ") || "shadow"}</span>
      </div>
      <p class="list-card-body">preferred ${rollout.preferred_shadow_candidate || "neither"}\nnext ${rollout.recommended_next_action || "-"}\nactive ${(rollout.active_tracks || []).join(" / ") || "-"}\nsafe ${(rollout.safe_rollout_candidates || []).join(" / ") || "-"}\nrollback ${(rollout.rollback_watchlist || []).join(" / ") || "-"}</p>
    `;
    dom.opsLearnedRollout.appendChild(summaryCard);

    ["evaluator", "reranker"].forEach((track) => {
      const item = rollout.tracks?.[track];
      if (!item) return;
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${track}</h3>
          <span class="list-card-score">${item.rollout_status || "-"}</span>
        </div>
        <p class="list-card-body">safe ${item.safe_to_rollout ? "yes" : "no"} · candidate ${item.candidate_ready ? "yes" : "no"}\napproval ${item.promotion_workflow?.approval_status || "-"} · recommendation ${item.promotion_workflow?.recommendation_status || "-"}\nnext ${item.recommended_action || "-"}\nlatest rollout ${item.latest_rollout_record?.updated_at || "-"} · ${item.latest_rollout_record?.reason || "-"}</p>
        <div class="composer-actions">
          <button class="ghost-action learned-rollout-activate">Activate</button>
          <button class="ghost-action learned-rollout-rollback">Rollback</button>
        </div>
      `;
      card.querySelector(".learned-rollout-activate")?.addEventListener("click", () => submitLearnedRollout(track, "activate"));
      card.querySelector(".learned-rollout-rollback")?.addEventListener("click", () => submitLearnedRollout(track, "rollback"));
      dom.opsLearnedRollout.appendChild(card);
    });
  }

  clearNode(dom.opsLearnedPromotion);
  if (!opsState.opsLearnedPromotion) {
    clearNode(dom.opsLearnedPromotion, "这里会显示评估器发布门、阻塞项、提示项与检查清单。");
  } else {
    const promotion = opsState.opsLearnedPromotion;
    const card = createListCard({
      title: "评估器发布门",
      score: opsStatusLabel(promotion.approval_status || promotion.recommendation_status || "-"),
      body: opsPromotionBody(
        promotion,
        "一致率",
        opsNumericValue(promotion.evidence?.agreement_rate, 3)
      )
    });
    dom.opsLearnedPromotion.appendChild(card);
  }

  clearNode(dom.opsLearnedRerankerPromotion);
  if (!opsState.opsLearnedRerankerPromotion) {
    clearNode(dom.opsLearnedRerankerPromotion, "这里会显示重排器发布门、阻塞项、提示项与检查清单。");
  } else {
    const promotion = opsState.opsLearnedRerankerPromotion;
    const card = createListCard({
      title: "重排器发布门",
      score: opsStatusLabel(promotion.approval_status || promotion.recommendation_status || "-"),
      body: opsPromotionBody(
        promotion,
        "平均准确率",
        opsNumericValue(promotion.evidence?.average_world_accuracy, 3)
      )
    });
    dom.opsLearnedRerankerPromotion.appendChild(card);
  }

  clearNode(dom.opsLearnedWorlds);
  if (!opsState.opsLearnedDashboard?.world_details?.length) {
    clearNode(dom.opsLearnedWorlds, "这里会显示需要优先关注的薄弱世界。");
  } else {
    opsState.opsLearnedDashboard.world_details.forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.world_id}</h3>
          <span class="list-card-score">${item.recommended_action || "-"}</span>
        </div>
        <p class="list-card-body">eval ${item.evaluator_agreement_rate !== null && item.evaluator_agreement_rate !== undefined ? Number(item.evaluator_agreement_rate).toFixed(3) : "-"}\nreranker ${item.reranker_accuracy !== null && item.reranker_accuracy !== undefined ? Number(item.reranker_accuracy).toFixed(3) : "-"}\nevaluator issues ${(item.evaluator_top_issues || []).join(" / ") || "-"}\nreranker issues ${(item.reranker_top_issues || []).join(" / ") || "-"}</p>
      `;
      card.addEventListener("click", () => openLearnedWorldDetail(item.world_id));
      dom.opsLearnedWorlds.appendChild(card);
    });
  }

  clearNode(dom.opsLearnedIssues);
  if (!opsState.opsLearnedDashboard?.issue_details?.length) {
    clearNode(dom.opsLearnedIssues, "这里会显示需要优先关注的问题代码。");
  } else {
    opsState.opsLearnedDashboard.issue_details.forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.issue_code}</h3>
          <span class="list-card-score">${item.recommended_action || "-"}</span>
        </div>
        <p class="list-card-body">eval ${item.evaluator_error_rate !== null && item.evaluator_error_rate !== undefined ? Number(item.evaluator_error_rate).toFixed(3) : "-"}\nreranker ${item.reranker_error_rate !== null && item.reranker_error_rate !== undefined ? Number(item.reranker_error_rate).toFixed(3) : "-"}\nworlds ${(item.affected_worlds || []).join(" / ") || "-"}</p>
      `;
      card.addEventListener("click", () => openLearnedIssueDetail(item.issue_code));
      dom.opsLearnedIssues.appendChild(card);
    });
  }

  clearNode(dom.opsLearnedDetail);
  if (!opsState.opsLearnedDetail) {
    clearNode(dom.opsLearnedDetail, "点击一个世界或问题后，这里会显示对应的深度详情。");
  } else if (opsState.opsLearnedDetail.world_id) {
    const detail = opsState.opsLearnedDetail;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>World Detail · ${detail.world_id}</h3>
        <span class="list-card-score">${detail.recommended_action || "-"}</span>
      </div>
      <p class="list-card-body">evaluator agreement ${detail.evaluator_agreement_rate !== null && detail.evaluator_agreement_rate !== undefined ? Number(detail.evaluator_agreement_rate).toFixed(3) : "-"}\nreranker accuracy ${detail.reranker_accuracy !== null && detail.reranker_accuracy !== undefined ? Number(detail.reranker_accuracy).toFixed(3) : "-"}\nevaluator coverage ${detail.evaluator_low_coverage ? "low" : "ok"}\nreranker coverage ${detail.reranker_low_coverage ? "low" : "ok"}\nevaluator issues ${(detail.evaluator_top_issues || []).join(" / ") || "-"}\nreranker issues ${(detail.reranker_top_issues || []).join(" / ") || "-"}</p>
    `;
    dom.opsLearnedDetail.appendChild(card);
  } else if (opsState.opsLearnedDetail.issue_code) {
    const detail = opsState.opsLearnedDetail;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>Issue Detail · ${detail.issue_code}</h3>
        <span class="list-card-score">${detail.recommended_action || "-"}</span>
      </div>
      <p class="list-card-body">evaluator error ${detail.evaluator_error_rate !== null && detail.evaluator_error_rate !== undefined ? Number(detail.evaluator_error_rate).toFixed(3) : "-"}\nreranker error ${detail.reranker_error_rate !== null && detail.reranker_error_rate !== undefined ? Number(detail.reranker_error_rate).toFixed(3) : "-"}\naffected worlds ${(detail.affected_worlds || []).join(" / ") || "-"}</p>
    `;
    dom.opsLearnedDetail.appendChild(card);
  }

  clearNode(dom.opsLearnedDataOps);
  if (!opsState.opsLearnedDataOps) {
    clearNode(dom.opsLearnedDataOps, "这里会显示审核待办、配对覆盖待补样与行动队列。");
  } else {
    const summary = opsState.opsLearnedDataOps;
    const card = createListCard({
      title: "学习层数据运营",
      score: summary.recommended_next_action || "-",
      body: opsSections(
        opsSection("总体判断", [
          opsFieldLine("偏好候选", opsPreferredCandidateLabel(summary.preferred_shadow_candidate)),
          opsFieldLine("推荐动作", summary.recommended_next_action || "-"),
        ]),
        opsSection("覆盖缺口", [
          opsFieldLine("审阅待补样", summary.coverage_gaps?.review_sample_backlog_count ?? 0),
          opsFieldLine("配对覆盖待补样", summary.coverage_gaps?.pair_coverage_backlog_count ?? 0),
        ]),
        opsSection("共性薄弱项", [
          opsFieldLine("薄弱世界", opsWorldList(summary.coverage_gaps?.shared_weak_worlds || [])),
          opsFieldLine("薄弱问题", opsIssueCodeList(summary.coverage_gaps?.shared_weak_issue_codes || [])),
        ]),
        opsSection("行动队列", [
          opsParagraphList(summary.action_queue || [], (item) => opsSections(
            opsSection(item.action_type || "待办动作", [
              opsFieldLine("世界", item.world_id ? opsWorldLabel(item.world_id) : "-"),
              opsFieldLine("问题", item.issue_code ? opsIssueCodeLabel(item.issue_code) : "-"),
              opsFieldLine("章节", item.chapter_id || "-"),
              opsFieldLine("建议动作", item.recommended_action || "-"),
            ])
          )),
        ])
      )
    });
    dom.opsLearnedDataOps.appendChild(card);
  }

  clearNode(dom.opsReviewSampleBacklog);
  if (!opsState.opsLearnedDataOps?.review_sample_backlog?.length) {
    clearNode(dom.opsReviewSampleBacklog, "这里会显示优先需要人工补样本的章节。");
  } else {
    opsState.opsLearnedDataOps.review_sample_backlog.forEach((item) => {
      const card = createListCard({
        title: `待补样章节 · ${item.chapter_id}`,
        score: item.recommended_action || item.priority || "-",
        body: opsSections(
          opsSection("章节上下文", [
            opsFieldLine("世界", opsWorldLabel(item.world_id)),
            opsFieldLine("世界版本", item.world_version_id || "-"),
            opsFieldLine("当前结论", item.decision || "-"),
            opsFieldLine("优先级", item.priority || "-"),
          ]),
          opsSection("问题信号", [
            opsFieldLine("问题列表", opsIssueCodeList(item.issue_codes || [])),
            opsFieldLine("世界信号", item.world_compare_signal || "-"),
            opsFieldLine("问题信号", opsIssueCodeList(item.issue_compare_signal || [])),
          ]),
          opsSection("摘要", [
            item.summary || "-",
          ])
        )
      });
      if (opsState.opsReviewCaptureTarget?.chapter_id === item.chapter_id) {
        card.classList.add("is-selected");
      }
      card.addEventListener("click", () => selectReviewBacklogItem(item));
      dom.opsReviewSampleBacklog.appendChild(card);
    });
  }

  clearNode(dom.opsPreferenceSamples);
  if (!(opsState.opsPreferenceSamples || []).length) {
    clearNode(dom.opsPreferenceSamples, "这里会显示最近采集的偏好样本。");
  } else {
    (opsState.opsPreferenceSamples || []).slice(0, 5).forEach((item) => {
      const card = createListCard({
        title: `偏好样本 · ${item.preference_id}`,
        score: item.preference_strength || "-",
        body: opsSections(
          opsSection("对比版本", [
            opsFieldLine("左侧版本", item.left_revision_id || "-"),
            opsFieldLine("右侧版本", item.right_revision_id || "-"),
            opsFieldLine("偏好版本", item.preferred_revision_id || "-"),
          ]),
          opsSection("问题与备注", [
            opsFieldLine("关联问题", opsIssueCodeList(item.linked_issue_codes || [])),
            opsFieldLine("备注", item.freeform_notes || "-"),
          ])
        )
      });
      dom.opsPreferenceSamples.appendChild(card);
    });
  }

  clearNode(dom.opsRankingSamples);
  if (!(opsState.opsRankingSamples || []).length) {
    clearNode(dom.opsRankingSamples, "这里会显示最近采集的排序样本。");
  } else {
    (opsState.opsRankingSamples || []).slice(0, 5).forEach((item) => {
      const card = createListCard({
        title: `排序样本 · ${item.ranking_id}`,
        score: item.top_revision_id || "-",
        body: opsSections(
          opsSection("排序结果", [
            opsFieldLine("排序序列", (item.ranked_revision_ids || []).join(" > ") || "-"),
          ]),
          opsSection("问题与备注", [
            opsFieldLine("关联问题", opsIssueCodeList(item.linked_issue_codes || [])),
            opsFieldLine("备注", item.freeform_notes || "-"),
          ])
        )
      });
      dom.opsRankingSamples.appendChild(card);
    });
  }

  clearNode(dom.opsPairCoverageBacklog);
  if (!opsState.opsLearnedDataOps?.pair_coverage_backlog?.length) {
    clearNode(dom.opsPairCoverageBacklog, "这里会显示需要更多版本对比与人工审阅才能形成有效偏好对的位置。");
  } else {
    opsState.opsLearnedDataOps.pair_coverage_backlog.forEach((item) => {
      const card = createListCard({
        title: `配对覆盖待办 · ${opsWorldLabel(item.world_id)} · ${opsIssueCodeLabel(item.issue_code)}`,
        score: item.recommended_action || "-",
        body: opsSections(
          opsSection("覆盖情况", [
            opsFieldLine("覆盖数", item.coverage_count ?? 0),
            opsFieldLine("最近版本", (item.recent_revision_ids || []).join(" / ") || "-"),
            opsFieldLine("变更片段", (item.changed_sections || []).join(" / ") || "-"),
          ]),
          opsSection("影子建议", [
            opsFieldLine("下一步", item.shadow_context?.recommended_next_action || "-"),
          ])
        )
      });
      dom.opsPairCoverageBacklog.appendChild(card);
    });
  }

  clearNode(dom.opsReviewCaptureContext);
  if (!opsState.opsReviewCaptureTarget) {
    clearNode(dom.opsReviewCaptureContext, "点击审核待办里的章节后，这里会自动填充上下文。");
  } else {
    const target = opsState.opsReviewCaptureTarget;
    const card = createListCard({
      title: `人工审阅上下文 · ${target.chapter_id}`,
      score: target.recommended_action || "-",
      body: opsSections(
        opsSection("章节上下文", [
          opsFieldLine("世界", opsWorldLabel(target.world_id)),
          opsFieldLine("世界版本", target.world_version_id || "-"),
          opsFieldLine("会话", target.session_id || "-"),
          opsFieldLine("问题列表", opsIssueCodeList(target.issue_codes || [])),
        ]),
        opsSection("影子建议", [
          opsFieldLine("偏好候选", opsPreferredCandidateLabel(target.shadow_context?.preferred_shadow_candidate)),
          opsFieldLine("下一步", target.shadow_context?.recommended_next_action || "-"),
        ])
      )
    });
    dom.opsReviewCaptureContext.appendChild(card);
  }

  clearNode(dom.opsLastActionImpact);
  if (!opsState.opsLastActionImpact) {
    clearNode(dom.opsLastActionImpact, "提交一条人工审阅后，这里会显示对审核待办、章节对照和下一步动作的即时影响。");
  } else {
    const impact = opsState.opsLastActionImpact;
    const card = createListCard({
      title: `最近动作影响 · ${impact.chapter_id || "-"}`,
      score: impact.cleared_backlog_target ? "已清除" : "已更新",
      body: opsSections(
        opsSection("上下文", [
          opsFieldLine("世界", impact.world_id ? opsWorldLabel(impact.world_id) : "-"),
          opsFieldLine("世界版本", impact.world_version_id || "-"),
          opsFieldLine("审阅样本", impact.review_sample_id || "-"),
        ]),
        opsSection("变化结果", [
          opsFieldLine("偏好候选", `${opsPreferredCandidateLabel(impact.preferred_shadow_candidate_before)} → ${opsPreferredCandidateLabel(impact.preferred_shadow_candidate_after)}`),
          opsFieldLine("下一步", `${impact.recommended_next_action_before || "-"} → ${impact.recommended_next_action_after || "-"}`),
          opsFieldLine("审阅待补样", `${impact.review_backlog_count_before ?? 0} → ${impact.review_backlog_count_after ?? 0}`),
          opsFieldLine("配对覆盖待补样", `${impact.pair_backlog_count_before ?? 0} → ${impact.pair_backlog_count_after ?? 0}`),
          opsFieldLine("行动队列", `${impact.action_queue_count_before ?? 0} → ${impact.action_queue_count_after ?? 0}`),
          opsFieldLine("是否清除目标", opsBooleanLabel(impact.cleared_backlog_target)),
        ]),
        opsSection("告警变化", [
          opsFieldLine("动作前", (impact.warnings_before || []).join(" / ") || "-"),
          opsFieldLine("动作后", (impact.warnings_after || []).join(" / ") || "-"),
        ])
      )
    });
    dom.opsLastActionImpact.appendChild(card);
  }
}

function renderOpsSurface(scopes = OPS_REFRESH_SCOPE_ALL) {
  const scopeSet = new Set(normalizeOpsRefreshScopes(scopes));
  const renderAll = scopeSet.size === OPS_REFRESH_SCOPE_ALL.length;
  const renderNavigation = renderAll || scopeSet.has("navigation");
  const renderReviewRelease = renderAll || scopeSet.has("review_release");
  const renderRuntime = renderAll || scopeSet.has("runtime");
  const renderJobs = renderAll || scopeSet.has("jobs");
  const renderAccount = renderAll || scopeSet.has("account") || scopeSet.has("alerts");
  const renderInvestigation = renderAll || scopeSet.has("investigation");
  const renderLearned = renderAll || scopeSet.has("learned");

  const reviewHubSummary = opsState.opsReviewHub?.summary || {};
  dom.opsPendingCount.textContent = String(reviewHubSummary.actionable_count ?? opsState.opsReviewQueue.length);
  dom.opsPublishedWorlds.textContent = String(
    opsState.opsWorldStatuses.filter((status) => Boolean(status.published_version)).length
  );
  const totalCost = opsState.opsMeters.reduce((sum, item) => sum + Number(item.estimated_cost || 0), 0);
  dom.opsTotalCost.textContent = `¥${totalCost.toFixed(2)}`;

  if (renderNavigation) {
    renderOpsNavigationSection();
  }
  if (renderReviewRelease) {
    renderOpsReviewReleaseSection();
  }
  if (renderRuntime) {
    renderOpsRuntimeSection();
  }
  if (renderJobs) {
    renderOpsJobsSection();
  }
  if (renderAccount) {
    renderOpsAccountSection();
  }
  if (renderInvestigation) {
    renderOpsInvestigationSection();
  }
  if (renderLearned) {
    renderOpsLearnedSection();
  }
}

  return {
    summarizeReviewTimelineEntry,
    formatSignedDelta,
    summarizeRollbackEntry,
    summarizeQualityTrendEntry,
    summarizeReleaseBlocker,
    renderOpsNavigationSection,
    renderOpsReviewReleaseSection,
    renderOpsRuntimeSection,
    renderOpsJobsSection,
    renderOpsAccountSection,
    renderOpsInvestigationSection,
    renderOpsLearnedSection,
    renderOpsSurface
  };
})();
