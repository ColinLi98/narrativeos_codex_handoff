// Ops render sections extracted from app.js to keep render/update responsibilities isolated.

function summarizeReviewTimelineEntry(item) {
  const note = item.note_payload || {};
  const targetVersion = item.target_world_version_id || item.published_world_version_id || item.world_version_id || item.asset_id || "-";
  const packSummary = (item.top_failing_pack_ids || []).join(" / ") || "-";
  const gateSummary = (item.publish_gate_errors || []).join(" / ") || "-";
  const riskSummary = (item.risk_summary?.publish_gate_errors || []).join(" / ") || "-";
  return (
    `${reviewStatusLabel(item.status)} · ${targetVersion}\n` +
    `${formatTimestamp(item.updated_at)} · reviewer ${item.reviewer_id || "-"} · risk ${item.risk_rating || "-"}\n` +
    `decision ${item.latest_decision || "-"} · cross-pack ${item.cross_pack_pass_rate !== undefined && item.cross_pack_pass_rate !== null ? Number(item.cross_pack_pass_rate).toFixed(3) : "-"}\n` +
    `weakest ${packSummary}\n` +
    `gate ${gateSummary}\n` +
    `rollback ${item.target_world_version_id || "-"} · previous ${item.previous_world_version_id || "-"}\n` +
    `reason ${item.entitlement_reason || note.entitlement_reason || "-"} · risk gate ${riskSummary}`
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
    `target ${item.rollback_target_world_version_id || "-"} · previous ${item.rollback_previous_world_version_id || "-"}\n` +
    `reviewer ${item.reviewer_id || "-"} · reason ${item.rollback_reason || "-"}\n` +
    `gate ${((item.rollback_gate_errors || []).join(" / ")) || "-"}`
  );
}

function summarizeQualityTrendEntry(item) {
  const delta = item.delta_vs_previous || {};
  return (
    `${item.world_version_id}\n` +
    `${item.status} · decision ${item.latest_decision || "-"} · updated ${formatTimestamp(item.updated_at)}\n` +
    `pass ${formatPercent(item.pass_rate)} (${formatSignedDelta(delta.pass_rate)}) · rewrite ${formatPercent(item.rewrite_rate)} (${formatSignedDelta(delta.rewrite_rate)})\n` +
    `block ${formatPercent(item.block_rate)} (${formatSignedDelta(delta.block_rate)}) · cross-pack ${Number(item.cross_pack_pass_rate || 0).toFixed(3)} (${formatSignedDelta(delta.cross_pack_pass_rate)})\n` +
    `regression ${item.regression_detected ? "yes" : "no"} · gate ${(item.publish_gate_errors || []).join(" / ") || "-"}\n` +
    `weakest ${(item.top_failing_pack_ids || []).join(" / ") || "-"}`
  );
}

function summarizeReleaseBlocker(item) {
  return (
    `${item.label || item.key}\n` +
    `${item.reason || "-"} · owner ${item.owner || "-"} · severity ${item.severity || "-"}\n` +
    `next ${item.next_action || "-"} · evidence ${summarizeChecklistEvidence(item.evidence)}`
  );
}


function renderOpsNavigationSection() {
    clearNode(els.opsNavigationSummary);
    clearNode(els.opsNavigationTargets);
    clearNode(els.opsNavigationActions);
    if (!appState.opsNavigationModel) {
      clearNode(els.opsNavigationSummary, "这里会显示统一 context、升级状态与推荐路径。");
      clearNode(els.opsNavigationTargets, "这里会显示 linked targets 与导航入口。");
      clearNode(els.opsNavigationActions, "这里会显示跨面板 follow-up actions。");
    } else {
      const model = appState.opsNavigationModel;
      const context = model.active_context || {};
      const escalation = model.escalation_summary || {};
      const warnings = model.context_warnings || [];
      const staleRefs = Object.values(model.linked_context?.stale_refs || {});
      els.opsNavigationSummary.appendChild(
        createListCard({
          title: "Ops Navigation Model",
          score: escalation.status || "-",
          body:
            `account ${context.account_id || "-"} · world ${context.world_id || "-"} · world_version ${context.world_version_id || "-"}\n` +
            `case ${context.case_id || "-"} · alert ${context.alert_id || "-"}\n` +
            `recommended ${escalation.recommended_target || "-"}\n` +
            `reason ${escalation.recommended_reason || "-"}\n` +
            `path ${(escalation.escalation_path || []).join(" -> ") || "-"}\n` +
            `resolution ${(model.context_resolution || []).join(" / ") || "-"}${
              warnings.length
                ? `\nwarning ${warnings.join(" / ")}`
                : ""
            }${
              staleRefs.length
                ? `\nstale refs ${staleRefs.map((item) => `${item.ref_id} · ${item.status}`).join(" / ")}`
                : ""
            }`
        })
      );
      if (!(model.navigation_targets || []).length) {
        clearNode(els.opsNavigationTargets, "这里会显示 linked targets 与导航入口。");
      } else {
        const targetCard = createListCard({
          title: "Linked Targets",
          score: `${(model.navigation_targets || []).length} targets`,
          body: (model.navigation_targets || []).map((item) => `${item.label} · ${item.kind}${item.active ? " · active" : ""}`).join("\n"),
        });
        const actions = document.createElement("div");
        actions.className = "composer-actions";
        (model.navigation_targets || []).forEach((item) => {
          const button = document.createElement("button");
          button.className = item.target_id === escalation.recommended_target ? "primary-action" : "ghost-action";
          button.textContent = item.label;
          button.addEventListener("click", async () => {
            try {
              await runOpsNavigationTarget(item);
            } catch (error) {
              alert(`打开 navigation target 失败：${error.message}`);
            }
          });
          actions.appendChild(button);
        });
        els.opsNavigationTargets.appendChild(targetCard);
        els.opsNavigationTargets.appendChild(actions);
      }
      if (!(model.follow_up_actions || []).length) {
        clearNode(els.opsNavigationActions, "这里会显示跨面板 follow-up actions。");
      } else {
        const followUpCard = createListCard({
          title: "Follow-up Actions",
          score: `${(model.follow_up_actions || []).length} actions`,
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
              await runOpsNavigationFollowUpAction(item);
            } catch (error) {
              alert(`执行 follow-up action 失败：${error.message}`);
            }
          });
          actions.appendChild(button);
        });
        els.opsNavigationActions.appendChild(followUpCard);
        els.opsNavigationActions.appendChild(actions);
      }
    }
}

function renderOpsReviewReleaseSection() {
  clearNode(els.opsReviewQueue);
  if (!appState.opsReviewQueue.length) {
    clearNode(els.opsReviewQueue, "暂时没有待审核版本。");
  } else {
    appState.opsReviewQueue.forEach((item) => {
      const notePayload = parseMaybeJson(item.notes);
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.asset_id}</h3>
          <span class="list-card-score">${item.status}</span>
        </div>
        <p class="list-card-body">${typeof notePayload === "object" ? `latest ${notePayload.latest_decision || "-"}\ncross-pack ${Number(notePayload.cross_pack_pass_rate || 0).toFixed(3)}\n${(notePayload.top_failing_packs || []).map((pack) => pack.world_id).join(" / ")}${(item.publish_gate_errors || []).length ? `\n\npublish gate:\n${item.publish_gate_errors.join("\n")}` : ""}` : (item.notes || "待审核")}</p>
        <div class="composer-actions">
          <button class="primary-action review-publish">发布</button>
        </div>
      `;
      card.querySelector(".review-publish").addEventListener("click", async () => {
        await api(`/v1/ops/world-versions/${item.asset_id}/publish`, {
          method: "POST",
          body: JSON.stringify({ reviewer_id: "web_ops" }),
        });
        await refreshOpsReleaseFlow();
      });
      els.opsReviewQueue.appendChild(card);
    });
  }
  clearNode(els.opsWorldStatus);
  clearNode(els.opsReleaseWorkspaceSummary);
  clearNode(els.opsReleaseWorkspaceActions);
  clearNode(els.opsReleaseWorkspaceTimeline);
  clearNode(els.opsReleaseWorkspaceDetails);
  if (!appState.opsWorldStatuses.length) {
    clearNode(els.opsWorldStatus, "选择或刷新后，这里会显示 world version 状态。");
    clearNode(els.opsReleaseWorkspaceSummary, "这里会显示当前 world 的 release summary。");
    clearNode(els.opsReleaseWorkspaceActions, "这里会显示当前 world 的 quick actions。");
    clearNode(els.opsReleaseWorkspaceTimeline, "这里会显示当前 world 的 operator timeline。");
    clearNode(els.opsReleaseWorkspaceDetails, "这里会显示 publish blockers、version matrix 与 rollback workspace。");
  } else {
    appState.opsWorldStatuses.forEach((status) => {
      const card = document.createElement("article");
      card.className = "list-card";
      if (status.world_id === appState.selectedOpsWorldId) {
        card.classList.add("is-active");
      }
      const rollbackTarget = status.versions.find((item) => item.world_version_id !== status.published_version);
      const checklistSummary = status.publish_checklist_summary || {};
      const checklistDrilldown = (status.publish_checklist || [])
        .map((item) => `${item.ok ? "✓" : "×"} ${item.label} · ${item.reason || "-"}\nowner ${item.owner || "-"} · severity ${item.severity || "-"} · next ${item.next_action || "-"}\nevidence ${summarizeChecklistEvidence(item.evidence)}`)
        .join("\n\n") || "暂无 checklist";
      const reviewDrilldown = (status.recent_reviews_drilldown || [])
        .map((item) => summarizeReviewTimelineEntry(item))
        .join("\n\n") || "暂无 recent reviews";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${status.world_id}</h3>
          <span class="list-card-score">${status.published_version || "未发布"}</span>
        </div>
        <p class="list-card-body">${status.versions.map((item) => `${item.world_version_id} · ${item.status}`).join("\n")}\n\npublish checklist summary:\nready ${checklistSummary.publish_ready ? "yes" : "no"} · blocked ${checklistSummary.blocked_count ?? 0}/${checklistSummary.total ?? 0}\nowners ${(checklistSummary.owners || []).join(" / ") || "-"}\nnext ${(checklistSummary.next_actions || []).join(" / ") || "-"}\n\npublish checklist drill-down:\n${checklistDrilldown}\n\nrisk summary:\n可发布 ${status.risk_summary?.publish_ready ? "yes" : "no"}\ngate ${((status.risk_summary?.publish_gate_errors) || []).join(" / ") || "-"}\n最近回滚 ${status.risk_summary?.latest_rollback_target || "-"} · ${status.risk_summary?.latest_rollback_reason || "-"}\nentitlement alerts ${((status.risk_summary?.entitlement_alerts) || []).map((item) => `${item.event_name}:${item.reason || "-"}`).join(" / ") || "-"}\n\nlearned shadow:\nstatus ${status.learned_shadow_summary?.status || "-"} · agreement ${status.learned_shadow_summary?.agreement_rate !== null && status.learned_shadow_summary?.agreement_rate !== undefined ? Number(status.learned_shadow_summary.agreement_rate).toFixed(3) : "-"}\nissues ${((status.learned_shadow_summary?.top_mismatch_issue_codes) || []).slice(0, 3).map((item) => item.issue_code || item.key).join(" / ") || "-"}\nnext ${status.learned_shadow_summary?.recommended_next_action || "-"}\n\nreranker shadow:\nstatus ${status.learned_reranker_shadow_summary?.status || "-"} · accuracy ${status.learned_reranker_shadow_summary?.per_world_accuracy?.[status.world_id] !== undefined ? Number(status.learned_reranker_shadow_summary.per_world_accuracy[status.world_id]).toFixed(3) : "-"}\nnext ${status.learned_reranker_shadow_summary?.recommended_next_action || "-"}\n\nrecent review drill-down:\n${reviewDrilldown}${(status.recent_entitlement_events || []).length ? `\n\nrecent entitlement events:\n${status.recent_entitlement_events.slice(0, 5).map((item) => `${item.event_name} · ${item.reason || "-"} · ${formatTimestamp(item.occurred_at)}`).join("\n")}` : ""}</p>
        ${rollbackTarget ? `<div class="composer-actions"><button class="ghost-action rollback-world">回滚到 ${rollbackTarget.world_version_id}</button></div>` : ""}
      `;
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
        appState.selectedOpsWorldId = status.world_id;
        syncOpsNavigationContext({ world_id: status.world_id }, { preserveExisting: true });
        if (els.opsReleaseWorldId) {
          els.opsReleaseWorldId.value = status.world_id;
        }
        await refreshOpsReleaseWorkspace();
        renderOpsSurface();
      });
      els.opsWorldStatus.appendChild(card);
    });
  }

  if (!appState.opsReleaseWorkspace) {
    clearNode(els.opsReleaseWorkspaceSummary, "这里会显示当前 world 的 release summary。");
    clearNode(els.opsReleaseWorkspaceActions, "这里会显示当前 world 的 quick actions。");
    clearNode(els.opsReleaseWorkspaceTimeline, "这里会显示当前 world 的 operator timeline。");
    clearNode(els.opsReleaseWorkspaceDetails, "这里会显示 publish blockers、version matrix 与 rollback workspace。");
  } else {
    const release = appState.opsReleaseWorkspace;
    const summary = release.release_summary || {};
    const blockers = release.publish_blockers || {};
    const rollback = release.rollback_workspace || {};
    const investigation = release.investigation_summary || {};
    els.opsReleaseWorkspaceSummary.appendChild(
      createListCard({
        title: `Release Workspace · ${release.world_id}`,
        score: summary.health_status || "-",
        body:
          `published ${summary.published_version || "-"} · selected ${summary.selected_world_version_id || "-"}\n` +
          `publish_ready ${summary.publish_ready ? "yes" : "no"} · blocked ${summary.blocked_checklist_count ?? 0}\n` +
          `rollback count ${summary.recent_rollback_count ?? 0} · latest ${summary.latest_rollback_target || "-"}\n` +
          `recommended ${summary.recommended_action || "-"}\n` +
          `reviewers ${Object.entries(release.review_ownership_summary?.reviewer_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `checklist owners ${(release.review_ownership_summary?.checklist_owners || []).join(" / ") || "-"}\n` +
          `investigation ${(investigation.recommended_paths || []).map((item) => item.path_id).join(" / ") || "-"}`
      })
    );
    if (!(release.action_pack || []).length) {
      clearNode(els.opsReleaseWorkspaceActions, "这里会显示当前 world 的 quick actions。");
    } else {
      const actionCard = createListCard({
        title: "Release Actions",
        score: `${(release.action_pack || []).length} actions`,
        body: (release.action_pack || []).map((item) => `${item.label} · ${item.mode}\n${item.reason || "-"}`).join("\n\n"),
      });
      const actions = document.createElement("div");
      actions.className = "composer-actions";
      (release.action_pack || []).forEach((item) => {
        const button = document.createElement("button");
        button.className = item.mode === "execute" ? "primary-action" : "ghost-action";
        button.textContent = item.label;
        button.addEventListener("click", async () => {
          try {
            await runOpsReleaseWorkspaceAction(item);
          } catch (error) {
            alert(`执行 release action 失败：${error.message}`);
          }
        });
        actions.appendChild(button);
      });
      els.opsReleaseWorkspaceActions.appendChild(actionCard);
      els.opsReleaseWorkspaceActions.appendChild(actions);
    }
    if (!(release.operator_timeline || []).length) {
      clearNode(els.opsReleaseWorkspaceTimeline, "这里会显示当前 world 的 operator timeline。");
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
        els.opsReleaseWorkspaceTimeline.appendChild(card);
      });
    }
    const detailBody = [
      `publish blockers:\n${(blockers.items || []).map((item) => summarizeReleaseBlocker(item)).join("\n\n") || "-"}`,
      `version matrix:\n${(release.version_matrix || []).map((item) => `${item.world_version_id}\n${item.status} · decision ${item.latest_decision || "-"} · publish_ready ${item.publish_ready ? "yes" : "no"}\ncross-pack ${Number(item.cross_pack_pass_rate || 0).toFixed(3)} · block ${formatPercent(item.block_rate)} · regress ${item.regression_detected ? "yes" : "no"}\nweakest ${(item.top_failing_pack_ids || []).join(" / ") || "-"}\ngate ${(item.publish_gate_errors || []).join(" / ") || "-"}\nupdated ${formatTimestamp(item.updated_at)}`).join("\n\n") || "-"}`,
      `rollback workspace:\nlatest ${rollback.latest_rollback?.rollback_target_world_version_id || "-"} · ${rollback.latest_rollback?.rollback_reason || "-"}\ncandidates ${(rollback.rollback_candidates || []).map((item) => `${item.world_version_id}:${item.status}`).join(" / ") || "-"}\nsummary count ${(rollback.summary || {}).total_entries ?? 0} · latest reason ${(rollback.summary || {}).latest_reason || "-"}`,
    ].join("\n\n");
    els.opsReleaseWorkspaceDetails.appendChild(
      createListCard({
        title: "Release Drill-down",
        score: `${(blockers.items || []).length} blockers`,
        body: detailBody,
      })
    );
  }

  clearNode(els.opsReviewHistory);
  if (!appState.opsWorldHistories.length) {
    clearNode(els.opsReviewHistory, "这里会显示 world version 的审核、发布和回滚记录。");
  } else {
    appState.opsWorldHistories.forEach((history) => {
      const card = document.createElement("article");
      card.className = "list-card";
      const summary = history.review_summary || {};
      const rollbackSummary = history.rollback_summary || {};
      const timelineBody = (history.review_timeline || []).slice(0, 8).map((item) => summarizeReviewTimelineEntry(item)).join("\n\n") || "暂无审核记录";
      const rollbackBody = (history.rollback_drilldown || []).slice(0, 5).map((item) => summarizeRollbackEntry(item)).join("\n\n") || "暂无 rollback 记录";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${history.world_id}</h3>
          <span class="list-card-score">${summary.total_entries ?? (history.review_history || []).length} 条</span>
        </div>
        <p class="list-card-body">summary:\nstatus ${Object.entries(summary.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\nreviewers ${Object.entries(summary.reviewer_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\nlatest published ${summary.latest_published_world_version_id || "-"}\nlatest blocked ${summary.latest_blocked_world_version_id || "-"}\nlatest rollback ${summary.latest_rollback_target_world_version_id || "-"}\n\nrollback summary:\ncount ${rollbackSummary.total_entries ?? 0}\ntargets ${Object.entries(rollbackSummary.target_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\nreviewers ${Object.entries(rollbackSummary.reviewer_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\nlatest reason ${rollbackSummary.latest_reason || "-"}\n\nreview timeline:\n${timelineBody}\n\nrollback drill-down:\n${rollbackBody}</p>
      `;
      els.opsReviewHistory.appendChild(card);
    });
  }

  clearNode(els.opsQualityTrend);
  if (!appState.opsWorldHistories.length) {
    clearNode(els.opsQualityTrend, "这里会显示每个 world version 的 pass / rewrite / block 与 cross-pack 走势。");
  } else {
    appState.opsWorldHistories.forEach((history) => {
      const card = document.createElement("article");
      card.className = "list-card";
      const summary = history.quality_trend_summary || {};
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${history.world_id}</h3>
          <span class="list-card-score">${(history.quality_trend || []).length} 条</span>
        </div>
        <p class="list-card-body">summary:\nlatest ${summary.latest_world_version_id || "-"}\nstrongest ${summary.strongest_world_version_id || "-"}\nweakest ${summary.weakest_world_version_id || "-"}\nregressions ${(summary.regression_version_ids || []).join(" / ") || "-"}\nblocked ${(summary.blocked_version_ids || []).join(" / ") || "-"}\nimproving ${(summary.improving_version_ids || []).join(" / ") || "-"}\nlatest delta pass ${formatSignedDelta(summary.latest_delta?.pass_rate)} · block ${formatSignedDelta(summary.latest_delta?.block_rate)} · cross-pack ${formatSignedDelta(summary.latest_delta?.cross_pack_pass_rate)}\n\ntrend drill-down:\n${(history.quality_trend || []).map((item) => summarizeQualityTrendEntry(item)).join("\n\n") || "暂无版本级质量趋势。"}</p>
      `;
      els.opsQualityTrend.appendChild(card);
    });
  }
}

function renderOpsRuntimeSection() {
  clearNode(els.opsSchemaLifecycle);
  if (!appState.opsSchemaLifecycle) {
    clearNode(els.opsSchemaLifecycle, "这里会显示当前数据库 backend、migration pending 状态和 schema drift 摘要。");
  } else {
    const lifecycle = appState.opsSchemaLifecycle;
    els.opsSchemaLifecycle.appendChild(
      createListCard({
        title: "Schema Lifecycle",
        score: lifecycle.status || "-",
        body:
          `backend ${lifecycle.backend || "-"}\n` +
          `latest available ${lifecycle.latest_available_version || "-"} · latest applied ${lifecycle.latest_applied_version || "-"}\n` +
          `pending ${(lifecycle.pending_versions || []).join(" / ") || "-"}\n` +
          `schema matches migrations ${lifecycle.schema_matches_migrations ? "yes" : "no"}\n` +
          `schema fp ${(lifecycle.schema_sql_fingerprint || "-").slice(0, 12)}\n` +
          `migrations fp ${(lifecycle.migrations_fingerprint || "-").slice(0, 12)}`
      })
    );
  }

  clearNode(els.opsDeploymentRunbook);
  clearNode(els.opsIncidentPlaybook);
  clearNode(els.opsDeploymentHealthGate);
  clearNode(els.opsPreflightVerification);
  if (!appState.opsDeploymentRunbook) {
    clearNode(els.opsDeploymentHealthGate, "这里会显示 deployment health gate 和总体放行状态。");
    clearNode(els.opsPreflightVerification, "这里会显示 preflight verification bundle 与推荐验证命令。");
    clearNode(els.opsDeploymentRunbook, "这里会显示 deployment runbook 与最近 backups。");
    clearNode(els.opsIncidentPlaybook, "这里会显示 incident playbook 与建议恢复步骤。");
  } else {
    const healthGate = appState.opsDeploymentHealthGate || {};
    els.opsDeploymentHealthGate.appendChild(
      createListCard({
        title: "Deployment Health Gate",
        score: healthGate.status || "-",
        body:
          `recommended ${healthGate.recommended_action || "-"}\n` +
          `checks ${((healthGate.checks || []).map((item) => `${item.key}:${item.status}`).join(" / ")) || "-"}\n` +
          `schema ${healthGate.schema_lifecycle?.status || "-"} · incidents ${healthGate.incident_snapshot?.incident_count ?? 0}\n` +
          `provider ${(Object.entries(healthGate.incident_snapshot?.by_provider || {}).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}`
      })
    );

    const preflight = appState.opsPreflightVerification || {};
    els.opsPreflightVerification.appendChild(
      createListCard({
        title: "Preflight Verification Bundle",
        score: preflight.verification_summary?.gate_status || "-",
        body:
          `recommended ${preflight.verification_summary?.recommended_action || "-"}\n` +
          `schema ${preflight.verification_summary?.schema_status || "-"} · incidents ${preflight.verification_summary?.incident_count ?? 0}\n` +
          `commands:\n${(preflight.verification_commands || []).join("\n") || "-"}`
      })
    );

    const runbook = appState.opsDeploymentRunbook;
    els.opsDeploymentRunbook.appendChild(
      createListCard({
        title: "Deployment Runbook",
        score: runbook.schema_lifecycle?.status || runbook.backend || "-",
        body:
          `backend ${runbook.backend || "-"}\n` +
          `db ${runbook.database_url || "-"}\n` +
          `preflight ${((runbook.preflight_checks || []).map((item) => `${item.key}:${item.ok ? "ok" : item.reason}`).join(" / ")) || "-"}\n\n` +
          `deploy steps:\n${(runbook.deploy_steps || []).join("\n") || "-"}\n\n` +
          `rollback steps:\n${(runbook.rollback_steps || []).join("\n") || "-"}\n\n` +
          `recent backups:\n${(runbook.recent_backups || []).map((item) => `${item.backup_id} · ${item.status}\n${item.backup_path || "-"} · ${item.created_at}`).join("\n\n") || "-"}`
      })
    );
    if (!els.opsRestorePath?.value && runbook.recent_backups?.[0]?.backup_path && els.opsRestorePath) {
      els.opsRestorePath.value = runbook.recent_backups[0].backup_path;
    }
  }

  if (!appState.opsIncidentPlaybook) {
    clearNode(els.opsIncidentPlaybook, "这里会显示 incident playbook 与建议恢复步骤。");
  } else {
    const playbook = appState.opsIncidentPlaybook;
    els.opsIncidentPlaybook.appendChild(
      createListCard({
        title: "Incident Playbook",
        score: `${playbook.incident_snapshot?.incident_count ?? 0} incidents`,
        body:
          `schema ${playbook.deployment_runbook?.schema_lifecycle?.status || "-"}\n` +
          `triage:\n${(playbook.triage_steps || []).join("\n") || "-"}\n\n` +
          `recovery:\n${(playbook.recovery_steps || []).join("\n") || "-"}`
      })
    );
  }

  clearNode(els.opsRuntimeIncidentSnapshot);
  clearNode(els.opsRuntimeReceipts);
  clearNode(els.opsProviderRuntimeMetrics);
  if (!appState.opsRuntimeIncidentSnapshot) {
    clearNode(els.opsRuntimeIncidentSnapshot, "这里会显示 runtime incident snapshot、provider fallback、budget block 与 cache hit 概况。");
    clearNode(els.opsRuntimeReceipts, "这里会显示最近的 runtime receipts。");
    clearNode(els.opsProviderRuntimeMetrics, "这里会显示 provider runtime metrics 与 cost trend dashboard。");
  } else {
    const snapshot = appState.opsRuntimeIncidentSnapshot;
    els.opsRuntimeIncidentSnapshot.appendChild(
      createListCard({
        title: "Runtime Incident Snapshot",
        score: `${snapshot.incident_count ?? 0} incidents`,
        body:
          `health ${snapshot.health_status || "-"} · schema ${snapshot.schema_lifecycle_status || "-"}\n` +
          `receipts ${snapshot.receipt_count ?? 0} · cache hit ${snapshot.cache_hit_rate !== null && snapshot.cache_hit_rate !== undefined ? Number(snapshot.cache_hit_rate).toFixed(3) : "-"} · cost ${Number(snapshot.total_estimated_cost || 0).toFixed(3)}\n` +
          `incident type ${Object.entries(snapshot.by_incident_type || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `provider ${Object.entries(snapshot.by_provider || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `surface ${Object.entries(snapshot.by_surface || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n\n` +
          `latest incidents:\n${(snapshot.latest_incidents || []).map((item) => `${item.action} · ${item.response_status} · ${(item.incident_flags || []).join("/") || "-"}\n${item.selected_provider || item.provider || "-"} · ${item.session_id || "-"} · ${item.world_version_id || "-"}`).join("\n\n") || "-"}`
      })
    );

    if (!appState.opsRuntimeReceipts.length) {
      clearNode(els.opsRuntimeReceipts, "这里会显示最近的 runtime receipts。");
    } else {
      appState.opsRuntimeReceipts.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.action || "-"}</h3>
            <span class="list-card-score">${item.response_status || "-"}</span>
          </div>
          <p class="list-card-body">${formatTimestamp(item.occurred_at)}\n${item.surface || "-"} · provider ${item.selected_provider || item.provider || "-"}\nflags ${(item.incident_flags || []).join(" / ") || "-"}\ncache ${item.cache_hit === null || item.cache_hit === undefined ? "-" : item.cache_hit ? "hit" : "miss"} · budget ${item.budget_blocked ? "blocked" : "ok"} · fallback ${item.fallback_used ? "yes" : "no"}\nerror ${item.backend_error || "-"}\ncandidates ${(item.candidate_counts?.raw ?? 0)}/${(item.candidate_counts?.legal ?? 0)} · output ${item.output_chars ?? 0} · cost ${Number(item.estimated_cost || 0).toFixed(3)}</p>
        `;
        els.opsRuntimeReceipts.appendChild(card);
      });
    }
  }

  if (!appState.opsProviderRuntimeMetrics) {
    clearNode(els.opsProviderRuntimeMetrics, "这里会显示 provider runtime metrics 与 cost trend dashboard。");
  } else {
    const metrics = appState.opsProviderRuntimeMetrics;
    els.opsProviderRuntimeMetrics.appendChild(
      createListCard({
        title: "Provider Runtime Metrics",
        score: `${metrics.receipt_count ?? 0} receipts`,
        body:
          `total cost ${Number(metrics.total_estimated_cost || 0).toFixed(3)}\n` +
          `surface ${Object.entries(metrics.surface_summary || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `action ${Object.entries(metrics.action_summary || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n\n` +
          `providers:\n${(metrics.provider_summary || []).map((item) => `${item.provider}\nreceipts ${item.receipt_count} · incidents ${item.incident_count}\nfallback ${Number(item.fallback_rate || 0).toFixed(3)} · budget ${Number(item.budget_block_rate || 0).toFixed(3)} · cache ${item.cache_hit_rate === null || item.cache_hit_rate === undefined ? "-" : Number(item.cache_hit_rate).toFixed(3)}\ncost ${Number(item.total_estimated_cost || 0).toFixed(3)} · avg ${Number(item.avg_estimated_cost || 0).toFixed(3)} · chars ${Number(item.avg_output_chars || 0).toFixed(1)}`).join("\n\n") || "-" }\n\n` +
          `cost trend:\n${(metrics.cost_trend || []).map((item) => `${item.bucket} · cost ${Number(item.total_estimated_cost || 0).toFixed(3)} · receipts ${item.receipt_count} · incidents ${item.incident_count}`).join("\n") || "-"}`
      })
    );
  }

  clearNode(els.opsMeterList);
  if (!appState.opsMeters.length) {
    clearNode(els.opsMeterList, "继续阅读发生后，这里会出现 meter 记录。");
  } else {
    appState.opsMeters.forEach((meter) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${meter.action_type}</h3>
          <span class="list-card-score">${Number(meter.estimated_cost || 0).toFixed(3)}</span>
        </div>
        <p class="list-card-body">${meter.world_version_id || "-"}\n${meter.session_id || "-"}\nunits ${Number(meter.usage_units || 0).toFixed(3)} · wallet ${meter.wallet_type || "-"}\ntier ${meter.subscription_tier || "-"} · rule ${meter.model_policy_version || "-"}</p>
      `;
      els.opsMeterList.appendChild(card);
    });
  }
}

function renderOpsJobsSection() {
  clearNode(els.opsAsyncJobSummary);
  clearNode(els.opsAsyncJobBootReconcile);
  clearNode(els.opsAsyncJobIncidents);
  clearNode(els.opsAsyncJobArtifactRetention);
  clearNode(els.opsAsyncJobOperatorHistory);
  clearNode(els.opsAsyncJobHandoffBundle);
  clearNode(els.opsAsyncJobAdapterValidation);
  clearNode(els.opsAsyncJobAdapterHealthProbe);
  clearNode(els.opsAsyncJobNotificationReceipts);
  clearNode(els.opsAsyncNotificationRetryQueue);
  clearNode(els.opsAsyncNotificationDeadLetterQueue);
  clearNode(els.opsAsyncRetryOutcomeDashboard);
  clearNode(els.opsAsyncJobs);
  if (!appState.opsAsyncJobSummary) {
    clearNode(els.opsAsyncJobSummary, "这里会显示 long-running jobs 的队列摘要。");
    clearNode(els.opsAsyncJobBootReconcile, "这里会显示 boot-time async reconciler 的处理结果。");
    clearNode(els.opsAsyncJobIncidents, "这里会显示 failed / queued / stale running jobs 的 incident recovery 摘要。");
    clearNode(els.opsAsyncJobArtifactRetention, "这里会显示 async job artifact retention 与保留状态。");
    clearNode(els.opsAsyncJobOperatorHistory, "这里会显示 operator run history。");
    clearNode(els.opsAsyncJobHandoffBundle, "这里会显示 async job handoff bundle 与 acknowledgement 摘要。");
    clearNode(els.opsAsyncJobAdapterValidation, "这里会显示 async adapter config validation。");
    clearNode(els.opsAsyncJobAdapterHealthProbe, "这里会显示 async adapter health probe。");
    clearNode(els.opsAsyncJobNotificationReceipts, "这里会显示 notification delivery receipts。");
    clearNode(els.opsAsyncNotificationRetryQueue, "这里会显示 notification retry queue。");
    clearNode(els.opsAsyncNotificationDeadLetterQueue, "这里会显示 notification dead-letter queue。");
    clearNode(els.opsAsyncRetryOutcomeDashboard, "这里会显示 retry outcome dashboard。");
    clearNode(els.opsAsyncJobs, "这里会显示 learned training / runtime backup 的异步工作流状态。");
  } else {
    const summary = appState.opsAsyncJobSummary;
    els.opsAsyncJobSummary.appendChild(
      createListCard({
        title: "Async Job Summary",
        score: `${summary.job_count ?? 0} jobs`,
        body:
          `status ${Object.entries(summary.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `type ${Object.entries(summary.by_type || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `supported ${(summary.supported_job_types || []).join(" / ") || "-"}\n` +
          `lease ${Object.entries(summary.by_lease_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `latest finished ${summary.latest_finished_job?.job_id || "-"} · ${summary.latest_finished_job?.status || "-"}`
      })
    );
    const boot = appState.opsAsyncJobBootReconcile || {};
    els.opsAsyncJobBootReconcile.appendChild(
      createListCard({
        title: "Boot-time Async Reconciler",
        score: `${boot.reconciled_count ?? 0} reconciled`,
        body:
          `requested by ${boot.requested_by || "-"}\n` +
          `recommended ${boot.recommended_action || "-"}\n` +
          `jobs ${(boot.reconciled_jobs || []).map((item) => `${item.job_id}:${item.last_recovery_action || "-"}`).join(" / ") || "-"}`
      })
    );
    const incidents = appState.opsAsyncJobIncidents || {};
    els.opsAsyncJobIncidents.appendChild(
      createListCard({
        title: "Async Job Incident Recovery",
        score: incidents.status || "-",
        body:
          `recommended ${incidents.recommended_action || "-"}\n` +
          `failed ${incidents.failed_count ?? 0} · queued ${incidents.queued_count ?? 0} · stale ${incidents.stale_running_count ?? 0} · expired lease ${incidents.expired_lease_count ?? 0} · recoverable ${incidents.recoverable_count ?? 0}\n` +
          `by type ${Object.entries(incidents.by_type || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `failed jobs ${(incidents.failed_jobs || []).map((item) => item.job_id).join(" / ") || "-"}\n` +
          `stale jobs ${(incidents.stale_running_jobs || []).map((item) => item.job_id).join(" / ") || "-"}`
      })
    );
    const retention = appState.opsAsyncJobArtifactRetention || {};
    const remoteShipping = appState.opsAsyncJobRemoteShipping || {};
    els.opsAsyncJobArtifactRetention.appendChild(
      createListCard({
        title: "Async Job Artifact Retention",
        score: `${retention.jobs_with_artifacts ?? 0} jobs`,
        body:
          `artifact count ${retention.total_artifact_count ?? 0} · bytes ${retention.total_bytes ?? 0}\n` +
          `remote adapter ${(remoteShipping.registry?.default_adapter || "-")} · ${(remoteShipping.registry?.available_adapters || []).join(" / ") || "-"}\n` +
          `status ${Object.entries(retention.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `expiring soon ${retention.expiring_soon_count ?? 0} · expired ${retention.expired_count ?? 0} · missing ${retention.missing_count ?? 0}\n` +
          `remote ${Object.entries(remoteShipping.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `jobs ${(retention.artifact_jobs || []).map((item) => `${item.job_id}:${item.artifact_status}`).join(" / ") || "-"}`
      })
    );
    const operatorHistory = appState.opsAsyncJobOperatorHistory || {};
    els.opsAsyncJobOperatorHistory.appendChild(
      createListCard({
        title: "Operator Run History",
        score: `${operatorHistory.entry_count ?? 0} entries`,
        body:
          `operators ${Object.entries(operatorHistory.by_operator || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `actions ${Object.entries(operatorHistory.by_action || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `latest ${(operatorHistory.latest_entries || []).map((item) => `${item.operator_id || "-"}:${item.action}@${item.job_id}`).join(" / ") || "-"}`
      })
    );
    const handoff = appState.opsAsyncJobHandoffBundle || {};
    const bundle = handoff.handoff_bundle || handoff;
    const handoffSla = appState.opsAsyncJobHandoffSla || {};
    els.opsAsyncJobHandoffBundle.appendChild(
      createListCard({
        title: "Async Job Handoff Bundle",
        score: `${bundle.acknowledgement_summary?.pending_count ?? 0} pending`,
        body:
          `recommended ${bundle.recommended_next_action || "-"}\n` +
          `sink ${(bundle.notification_sinks?.default_sink || "-")} · ${(bundle.notification_sinks?.available_sinks || []).join(" / ") || "-"}\n` +
          `required ${bundle.acknowledgement_summary?.required_count ?? 0} · pending ${bundle.acknowledgement_summary?.pending_count ?? 0} · ack ${bundle.acknowledgement_summary?.acknowledged_count ?? 0}\n` +
          `sla overdue ${handoffSla.overdue_count ?? 0} · pending ${handoffSla.pending_count ?? 0}\n` +
          `jobs ${(bundle.jobs_requiring_handoff || []).map((item) => `${item.job_id}:${item.acknowledgement_status}/${item.handoff_sla_status || "-"}/${item.remote_shipping_status || "-"}`).join(" / ") || "-"}\n` +
          `export ${handoff.export_path || "-"} · notify ${handoff.notification_receipt?.sink_name || "-"}`
      })
    );
    const adapterValidation = appState.opsAsyncJobAdapterValidation || {};
    els.opsAsyncJobAdapterValidation.appendChild(
      createListCard({
        title: "Async Adapter Config Validation",
        score: adapterValidation.valid ? "valid" : "invalid",
        body:
          `remote ${adapterValidation.remote_shipping?.valid ? "ok" : "fail"} · default ${(adapterValidation.remote_shipping?.config_source?.resolved_default_adapter || "-")}\n` +
          `sinks ${adapterValidation.notification_sinks?.valid ? "ok" : "fail"} · default ${(adapterValidation.notification_sinks?.config_source?.resolved_default_sink || "-")}\n` +
          `remote checks ${(adapterValidation.remote_shipping?.checks || []).map((item) => `${item.adapter_name}:${item.valid ? "ok" : (item.issues || []).join("/")}`).join(" / ") || "-"}\n` +
          `sink checks ${(adapterValidation.notification_sinks?.checks || []).map((item) => `${item.sink_name}:${item.valid ? "ok" : (item.issues || []).join("/")}`).join(" / ") || "-"}`
      })
    );
    const adapterProbe = appState.opsAsyncJobAdapterHealthProbe || {};
    els.opsAsyncJobAdapterHealthProbe.appendChild(
      createListCard({
        title: "Async Adapter Health Probe",
        score: adapterProbe.status || "-",
        body:
          `remote default ${(adapterProbe.remote_shipping?.default_probe?.status || "-")} · ${(adapterProbe.remote_shipping?.default_adapter || "-")}\n` +
          `sink default ${(adapterProbe.notification_sinks?.default_probe?.status || "-")} · ${(adapterProbe.notification_sinks?.default_sink || "-")}\n` +
          `remote probes ${Object.entries(adapterProbe.remote_shipping?.probes || {}).map(([key, value]) => `${key}=${value.status}`).join(" / ") || "-"}\n` +
          `sink probes ${Object.entries(adapterProbe.notification_sinks?.probes || {}).map(([key, value]) => `${key}=${value.status}`).join(" / ") || "-"}`
      })
    );
    const notificationReceipts = appState.opsAsyncJobNotificationReceipts || {};
    els.opsAsyncJobNotificationReceipts.appendChild(
      createListCard({
        title: "Notification Delivery Receipts",
        score: `${notificationReceipts.receipt_count ?? 0} receipts`,
        body:
          `sink ${Object.entries(notificationReceipts.by_sink || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `event ${Object.entries(notificationReceipts.by_event_type || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `status ${Object.entries(notificationReceipts.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `latest ${(notificationReceipts.latest_receipts || []).map((item) => `#${item.event_id || "-"}:${item.sink_name || "-"}:${item.event_type || "-"}:${item.target_exists ? "exists" : "missing"}`).join(" / ") || "-"}`
      })
    );
    const retryQueue = appState.opsAsyncNotificationRetryQueue || {};
    const retryPolicies = appState.opsAsyncRetryPolicies || {};
    els.opsAsyncNotificationRetryQueue.appendChild(
      createListCard({
        title: "Notification Retry Queue",
        score: `${retryQueue.retry_count ?? 0} retries`,
        body:
          `default policy ${retryPolicies.default_policy_id || "-"}\n` +
          `policies ${(retryPolicies.available_policy_ids || []).join(" / ") || "-"}\n` +
          `status ${Object.entries(retryQueue.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `latest ${(retryQueue.retries || []).map((item) => `${item.retry_id || "-"}:${item.status || "-"}:${item.source_event_type || "-"}:${item.process_count || 0}:${item.failure_classification?.failure_class || "-"}/${item.retry_decision || "-"}`).join(" / ") || "-"}`
      })
    );
    const deadLetters = appState.opsAsyncNotificationDeadLetterQueue || {};
    els.opsAsyncNotificationDeadLetterQueue.appendChild(
      createListCard({
        title: "Notification Dead-letter Queue",
        score: `${deadLetters.dead_letter_count ?? 0} dead letters`,
        body:
          `status ${Object.entries(deadLetters.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `failure ${Object.entries(deadLetters.by_failure_class || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `latest ${(deadLetters.dead_letters || []).map((item) => `${item.dead_letter_id || "-"}:${item.failure_classification?.failure_class || "-"}`).join(" / ") || "-"}`
      })
    );
    const retryOutcome = appState.opsAsyncRetryOutcomeDashboard || {};
    els.opsAsyncRetryOutcomeDashboard.appendChild(
      createListCard({
        title: "Retry Outcome Dashboard",
        score: `${retryOutcome.retry_count ?? 0} retries`,
        body:
          `success ${(retryOutcome.successful_retry_count ?? 0)} · planned ${(retryOutcome.planned_retry_count ?? 0)} · terminal ${(retryOutcome.terminal_failure_count ?? 0)} · rate ${retryOutcome.success_rate ?? "-"}\n` +
          `status ${Object.entries(retryOutcome.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `decision ${Object.entries(retryOutcome.by_retry_decision || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `failure ${Object.entries(retryOutcome.by_failure_class || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`
      })
    );
    if (!appState.opsAsyncJobs.length) {
      clearNode(els.opsAsyncJobs, "这里会显示 learned training / runtime backup 的异步工作流状态。");
    } else {
      appState.opsAsyncJobs.forEach((job) => {
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
          if (els.opsAsyncJobId) {
            els.opsAsyncJobId.value = job.job_id || "";
          }
          if (els.opsAsyncJobNote) {
            els.opsAsyncJobNote.value = job.acknowledgement_note || "";
          }
        });
        els.opsAsyncJobs.appendChild(card);
      });
    }
  }
}

function renderOpsAccountSection() {
  clearNode(els.opsSubscriptionAudit);
  clearNode(els.opsAccountWorkspaceSummary);
  clearNode(els.opsAccountWorkspaceActions);
  clearNode(els.opsAccountWorkspaceTimeline);
  if (!appState.opsSubscriptionAudit) {
    clearNode(els.opsSubscriptionAudit, "这里会显示当前 account 的 subscription 与 wallets。");
  } else {
    const audit = appState.opsSubscriptionAudit;
    const card = document.createElement("article");
    card.className = "list-card";
    const subscriptions = (audit.subscriptions || []).map((item) => `${item.tier_id} · ${item.status} · ${item.provider}\nperiod ${item.period_end || "-"}\ncancel_at_period_end ${item.cancel_at_period_end ? "yes" : "no"}\nnext ${item.next_action || "-"}\nreason ${item.lifecycle_reason || "-"}`).join("\n\n") || "暂无";
    const entitlements = (audit.entitlements || []).map((item) => `${item.entitlement_id}\n${item.entitlement_type} · ${item.wallet_type || item.tier_id || "-"} · ${item.status}\nbalance ${item.balance ?? "-"} · reason ${item.reason || "-"}`).join("\n\n") || "暂无";
    const wallets = Object.entries(audit.wallets || {})
      .map(([walletType, value]) => `${walletType}=${Number(value.balance || 0).toFixed(0)} · ${value.status || "-"}`)
      .join("\n") || "暂无";
    const events = (audit.events || [])
      .map((item) => `${item.event_name} · ${formatTimestamp(item.occurred_at)}\n${Object.entries(item.payload_json || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`)
      .join("\n\n") || "暂无";
    const matrix = audit.entitlement_matrix || {};
    const matrixSummary = [
      `config ${audit.config_version || "-"}`,
      `reader continue -> ${(matrix.reader?.continue_story?.required_tier || "-")} / ${(matrix.reader?.continue_story?.wallet_type || "-")}`,
      `author brief -> ${(matrix.author?.draft_from_brief?.required_tier || "-")} / ${(matrix.author?.draft_from_brief?.wallet_type || "-")}`,
      `author simulate -> ${(matrix.author?.simulate?.required_tier || "-")} / ${(matrix.author?.simulate?.wallet_type || "-")}`,
    ].join("\n");
    const auditSummary = [
      `count ${audit.audit_summary?.entitlement_count ?? 0}`,
      `status ${Object.entries(audit.audit_summary?.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `type ${Object.entries(audit.audit_summary?.entitlement_type_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `latest ${audit.audit_summary?.latest_event_at || "-"}`,
      `lifecycle events ${audit.lifecycle_history_summary?.event_count ?? 0} · retries ${audit.lifecycle_history_summary?.retry_attempt_count ?? 0}`,
    ].join("\n");
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${audit.account_id}</h3>
        <span class="list-card-score">${(audit.subscriptions || []).length} subscriptions</span>
      </div>
      <p class="list-card-body">subscriptions:\n${subscriptions}\n\nwallets:\n${wallets}\n\nentitlements:\n${entitlements}\n\ncheckout sessions:\n${(audit.recent_checkout_sessions || []).map((item) => `${item.checkout_session_id} · ${item.status} · ${item.tier_id}\nexpires ${item.expires_at || "-"} · subscription ${item.subscription_id || "-"}`).join("\n\n") || "暂无"}\n\naudit summary:\n${auditSummary}\n\nentitlement matrix:\n${matrixSummary}\n\nevents:\n${events}</p>
    `;
    els.opsSubscriptionAudit.appendChild(card);
  }

  clearNode(els.opsSubscriptionTimeline);
  if (!appState.opsSubscriptionAudit?.audit_timeline?.length) {
    clearNode(els.opsSubscriptionTimeline, "这里会显示 entitlement grant / revoke / lifecycle 的审计时间线。");
  } else {
    appState.opsSubscriptionAudit.audit_timeline.forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.event_name}</h3>
          <span class="list-card-score">${item.status || "-"}</span>
        </div>
        <p class="list-card-body">${formatTimestamp(item.occurred_at)}\nentitlement ${item.entitlement_id || "-"}\nsubscription ${item.subscription_id || "-"}\nwallet ${item.wallet_type || "-"} · tier ${item.tier_id || "-"}\nreason ${item.reason || "-"} · balance ${item.balance ?? "-"}</p>
      `;
      if (item.entitlement_id && els.opsEntitlementId) {
        card.addEventListener("click", () => {
          els.opsEntitlementId.value = item.entitlement_id;
        });
      }
      els.opsSubscriptionTimeline.appendChild(card);
    });
    (appState.opsSubscriptionAudit?.lifecycle_history_summary?.latest_events || []).forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.event_type || "-"}</h3>
          <span class="list-card-score">${item.status || "-"}</span>
        </div>
        <p class="list-card-body">${formatTimestamp(item.occurred_at)}\nprovider ${item.provider || "-"}\nsubscription ${item.subscription_id || "-"}\ncheckout ${item.checkout_session_id || "-"}\nprovider_event ${item.provider_event_id || "-"}\nprocessed ${item.processed_at || "-"}</p>
      `;
      if (item.event_id && els.opsBillingEventId) {
        card.addEventListener("click", () => {
          els.opsBillingEventId.value = item.event_id;
        });
      }
      els.opsSubscriptionTimeline.appendChild(card);
    });
    (appState.opsSubscriptionAudit?.lifecycle_history_summary?.latest_retry_attempts || []).forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.retry_attempt_id}</h3>
          <span class="list-card-score">${item.status || "-"}</span>
        </div>
        <p class="list-card-body">${formatTimestamp(item.updated_at)}\nsubscription ${item.subscription_id || "-"}\nreason ${item.retry_reason || "-"}\nattempt ${item.attempt_count || 0}\nnext ${item.next_retry_at || "-"}</p>
      `;
      els.opsSubscriptionTimeline.appendChild(card);
    });
  }

  clearNode(els.opsAccountDetail);
  clearNode(els.opsAccountActivity);
  clearNode(els.opsSupportSummary);
  clearNode(els.opsSupportIssues);
  clearNode(els.opsAlertSummary);
  clearNode(els.opsAlertFeed);
  clearNode(els.opsAlertDetail);
  clearNode(els.opsGovernanceSummary);
  clearNode(els.opsGovernanceCases);
  clearNode(els.opsGovernanceDetail);
  clearNode(els.opsGovernanceExport);
  clearNode(els.opsAccountAuditSummary);
  clearNode(els.opsAccountAuditTrail);
  if (!appState.opsAccountDetail) {
    clearNode(els.opsAccountWorkspaceSummary, "这里会显示当前 account 的 operator workspace summary。");
    clearNode(els.opsAccountWorkspaceActions, "这里会显示当前 account 的 quick actions 与推荐处置顺序。");
    clearNode(els.opsAccountWorkspaceTimeline, "这里会显示 account 级 operator timeline。");
    clearNode(els.opsAccountDetail, "这里会显示当前 account 的订阅、钱包、gating 与最近 activity。");
    clearNode(els.opsAccountActivity, "这里会显示当前 account 的最近 sessions / drafts / meters。");
    clearNode(els.opsSupportSummary, "这里会显示当前 account 的 support summary 与推荐动作。");
    clearNode(els.opsSupportIssues, "这里会显示当前 account 的 issue lookup 结果。");
    clearNode(els.opsAlertSummary, "这里会显示当前 alert feed 的统计摘要。");
    clearNode(els.opsAlertFeed, "这里会显示主动告警 feed。");
    clearNode(els.opsAlertDetail, "这里会显示选中 alert 的标准处置 bundle、runbook 和 investigation ref。");
    clearNode(els.opsGovernanceSummary, "这里会显示当前 account 的 rights / moderation / abuse case 摘要。");
    clearNode(els.opsGovernanceCases, "这里会显示当前 account 关联的 governance cases。");
    clearNode(els.opsGovernanceDetail, "这里会显示选中 governance case 的 drill-down。");
    clearNode(els.opsGovernanceExport, "这里会显示治理审计导出摘要。");
    clearNode(els.opsAccountAuditSummary, "这里会显示当前 account 的完整审计摘要。");
    clearNode(els.opsAccountAuditTrail, "这里会显示当前 account 的完整 audit trail。");
  } else {
    const detail = appState.opsAccountDetail;
    const workspace = appState.opsAccountWorkspace || {};
    const governance = appState.opsGovernanceSnapshot || {};
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
      clearNode(els.opsAccountWorkspaceSummary, "这里会显示当前 account 的 operator workspace summary。");
      clearNode(els.opsAccountWorkspaceActions, "这里会显示当前 account 的 quick actions 与推荐处置顺序。");
      clearNode(els.opsAccountWorkspaceTimeline, "这里会显示 account 级 operator timeline。");
    } else {
      els.opsAccountWorkspaceSummary.appendChild(
        createListCard({
          title: `Operator Workspace · ${workspace.account_id || detail.account_id}`,
          score: workspaceSummary.health_status || "-",
          body:
            `subscription ${workspaceSummary.subscription_status || "-"} · tier ${workspaceSummary.tier_id || "-"}\n` +
            `alerts ${workspaceSummary.actionable_alert_count ?? 0} · support ${workspaceSummary.support_issue_count ?? 0} · governance ${workspaceSummary.open_governance_case_count ?? 0} · restrictions ${workspaceSummary.active_restriction_count ?? 0}\n` +
            `recommended path ${workspaceSummary.recommended_path || "-"}\n` +
            `reader ${workspaceSummary.surface_statuses?.reader?.status || "-"} · ${workspaceSummary.surface_statuses?.reader?.reason || "-"}\n` +
            `author ${workspaceSummary.surface_statuses?.author?.status || "-"} · ${workspaceSummary.surface_statuses?.author?.reason || "-"}\n\n` +
            `wallet posture:\n${(walletPosture.wallets || []).map((item) => `${item.wallet_type}=${Number(item.balance || 0).toFixed(0)} · ${item.status || "-"}${item.anomaly ? " · anomaly" : ""}`).join("\n") || "-"}\n\n` +
            `entitlements ${entitlementPosture.total_entitlements ?? 0} · revoke candidates ${(entitlementPosture.revoke_candidates || []).length}\n` +
            `status ${Object.entries(entitlementPosture.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n\n` +
            `blockers:\n${(workspace.top_blockers || []).map((item) => `${item.headline} · ${item.severity}\n${item.summary}`).join("\n\n") || "-"}`
        })
      );
      if (!(workspace.action_pack || []).length) {
        clearNode(els.opsAccountWorkspaceActions, "这里会显示当前 account 的 quick actions 与推荐处置顺序。");
      } else {
        const actionCard = createListCard({
          title: "Quick Actions",
          score: `${(workspace.action_pack || []).length} actions`,
          body: (workspace.action_pack || []).map((item) => `${item.label} · ${item.mode}\n${item.reason || "-"}`).join("\n\n"),
        });
        const actions = document.createElement("div");
        actions.className = "composer-actions";
        (workspace.action_pack || []).forEach((item) => {
          const button = document.createElement("button");
          button.className = item.mode === "execute" ? "primary-action" : "ghost-action";
          button.textContent = item.label;
          button.addEventListener("click", async () => {
            try {
              await runOpsWorkspaceAction(item);
            } catch (error) {
              alert(`执行 workspace action 失败：${error.message}`);
            }
          });
          actions.appendChild(button);
        });
        els.opsAccountWorkspaceActions.appendChild(actionCard);
        els.opsAccountWorkspaceActions.appendChild(actions);
      }
      if (!(workspace.operator_timeline || []).length) {
        clearNode(els.opsAccountWorkspaceTimeline, "这里会显示 account 级 operator timeline。");
      } else {
        (workspace.operator_timeline || []).forEach((item) => {
          const card = document.createElement("article");
          card.className = "list-card";
          card.innerHTML = `
            <div class="list-card-head">
              <h3>${item.headline || item.entry_id}</h3>
              <span class="list-card-score">${item.category || "-"}</span>
            </div>
            <p class="list-card-body">${formatTimestamp(item.occurred_at)}\n${item.summary || "-"}\nnext ${(item.next_actions || []).join(" / ") || "-"}</p>
          `;
          els.opsAccountWorkspaceTimeline.appendChild(card);
        });
      }
    }
    els.opsAccountDetail.appendChild(
      createListCard({
        title: `Account Detail · ${detail.account_id}`,
        score: subscription.status || "no-subscription",
        body:
          `subscription ${subscription.tier_id || "-"} · ${subscription.display_name || "-"}\n` +
          `provider ${subscription.provider || "-"} · next ${subscription.next_action || "-"} · reason ${subscription.lifecycle_reason || "-"}\n` +
          `period ${subscription.period_end || "-"} · renewable ${subscription.renewable ? "yes" : "no"}\n` +
          `checkout ${(detail.checkout_session?.checkout_session_id || "-")} · ${(detail.checkout_session?.status || "-")}\n` +
          `billing events ${detail.lifecycle_history_summary?.event_count ?? 0} · retries ${detail.lifecycle_history_summary?.retry_attempt_count ?? 0}\n\n` +
          `wallets:\n${wallets}\n\n` +
          `gating:\n${gatingSummary}\n\n` +
          `activity summary:\nmeters ${detail.activity_summary?.recent_meter_count ?? 0} · events ${detail.activity_summary?.recent_event_count ?? 0} · sessions ${detail.activity_summary?.recent_session_count ?? 0} · drafts ${detail.activity_summary?.recent_draft_count ?? 0}`
      })
    );

    els.opsAccountActivity.appendChild(
      createListCard({
        title: "Recent Sessions / Drafts / Meters",
        score: `${(detail.recent_sessions || []).length + (detail.recent_drafts || []).length}`,
        body:
          `${(detail.recent_sessions || []).length ? `sessions:\n${detail.recent_sessions.map((item) => `${item.session_id} · ${item.world_id}\nturn ${item.current_turn_index} · ${item.last_chapter_title || item.last_event_title || "-"}\naccess ${item.access_tier || "-"} · ${item.reason || "-"}`).join("\n\n")}` : "sessions: -"}\n\n` +
          `${(detail.recent_drafts || []).length ? `drafts:\n${detail.recent_drafts.map((item) => `${item.world_version_id} · ${item.status}\n${item.title || item.world_id} · risk ${item.risk_rating || "-"}`).join("\n\n")}` : "drafts: -"}\n\n` +
          `${(detail.recent_meters || []).length ? `meters:\n${detail.recent_meters.map((item) => `${item.action_type} · units ${Number(item.usage_units || 0).toFixed(3)} · ${item.wallet_type || "-"}\n${item.world_version_id || "-"} · ${item.session_id || "-"}`).join("\n\n")}` : "meters: -"}`
      })
    );

    const supportSummary = detail.support_summary || {};
    const supportTooling = detail.support_tooling || {};
    els.opsSupportSummary.appendChild(
      createListCard({
        title: `Support Summary · ${detail.account_id}`,
        score: `${supportSummary.open_issue_count ?? 0} issues`,
        body:
          `primary ${supportSummary.primary_issue_type || "-"}\n` +
          `high ${supportSummary.high_priority_issue_count ?? 0} · payment_required ${supportSummary.recent_payment_required_count ?? 0} · checkout ${supportSummary.recent_checkout_started_count ?? 0}\n` +
          `types ${Object.entries(supportSummary.issue_type_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `severity ${Object.entries(supportSummary.severity_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `latest ${supportSummary.latest_issue_at || "-"}\n\n` +
          `recommended:\n${(supportTooling.recommended_actions || []).map((item) => `${item.label} · ${item.action_type}`).join("\n") || "-"}`
      })
    );

    if (!detail.support_issues?.length) {
      clearNode(els.opsSupportIssues, "这里会显示当前 account 的 issue lookup 结果。");
    } else {
      detail.support_issues.forEach((issue) => {
        const card = document.createElement("article");
        card.className = "list-card";
        const actionsMarkup = (issue.suggested_operator_actions || [])
          .map((action, index) => `<button class="ghost-action support-prefill" data-issue-index="${issue.issue_id}" data-action-index="${index}">${action.label}</button>`)
          .join("") + `<button class="ghost-action support-escalate">升级治理 Case</button>`;
        const linkedCases = (governance.support_issue_refs || []).find((item) => item.issue_id === issue.issue_id)?.linked_cases || [];
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${issue.title}</h3>
            <span class="list-card-score">${issue.severity || "-"}</span>
          </div>
          <p class="list-card-body">${issue.summary || "-"}\nreason ${issue.reason || "-"} · detected ${issue.detected_at || "-"}\nsurfaces ${(issue.surfaces || []).join(" / ") || "-"}\nlinked cases ${linkedCases.map((item) => `${item.case_id}:${item.status}`).join(" / ") || "-"}\nobjects ${Object.entries(issue.related_objects || {}).map(([key, value]) => `${key}=${Array.isArray(value) ? value.join(",") : value}`).join(" / ") || "-"}\nevidence ${Object.entries(issue.evidence || {}).map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`).join(" / ") || "-"}</p>
          <div class="composer-actions">${actionsMarkup}</div>
        `;
        card.querySelectorAll(".support-prefill").forEach((button) => {
          button.addEventListener("click", () => {
            const actionIndex = Number(button.getAttribute("data-action-index") || 0);
            const action = (issue.suggested_operator_actions || [])[actionIndex];
            applySupportPrefill(action?.prefill || {});
          });
        });
        card.querySelector(".support-escalate")?.addEventListener("click", () => escalateSupportIssue(issue));
        els.opsSupportIssues.appendChild(card);
      });
    }

    const alertFeed = appState.opsAlertsFeed || {};
    if (!alertFeed.alerts?.length) {
      clearNode(els.opsAlertSummary, "这里会显示当前 alert feed 的统计摘要。");
      clearNode(els.opsAlertFeed, "这里会显示主动告警 feed。");
      clearNode(els.opsAlertDetail, "这里会显示选中 alert 的标准处置 bundle、runbook 和 investigation ref。");
    } else {
      const alertSummary = alertFeed.summary || {};
      els.opsAlertSummary.appendChild(
        createListCard({
          title: "Alert Feed Summary",
          score: `${alertSummary.actionable_alert_count ?? 0} actionable`,
          body:
            `latest ${alertSummary.latest_detected_at ? formatTimestamp(alertSummary.latest_detected_at) : "-"}\n` +
            `category ${Object.entries(alertSummary.by_category || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
            `severity ${Object.entries(alertSummary.by_severity || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
            `status ${Object.entries(alertSummary.by_status || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`
        })
      );
      alertFeed.alerts.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        if (item.alert_id === appState.selectedOpsAlertId) {
          card.classList.add("is-active");
        }
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.title || item.alert_id}</h3>
            <span class="list-card-score">${item.severity || "-"} · ${item.status || "-"}</span>
          </div>
          <p class="list-card-body">${formatTimestamp(item.detected_at)}\n${item.category || "-"} · ${item.source_type || "-"}\naccount ${item.account_id || "global"}\n${item.summary || "-"}\nnext ${(item.recommended_actions || []).join(" / ") || "-"}</p>
        `;
        card.addEventListener("click", async () => {
          appState.selectedOpsAlertId = item.alert_id;
          const accountId = currentOpsAlertFilters().accountId || item.account_id || "";
          syncOpsNavigationContext({ account_id: accountId, alert_id: item.alert_id }, { preserveExisting: true });
          appState.opsAlertDetail = await api(
            `/v1/ops/alerts/${encodeURIComponent(item.alert_id)}${
              accountId ? `?account_id=${encodeURIComponent(accountId)}` : ""
            }`
          );
          renderOpsSurface();
        });
        els.opsAlertFeed.appendChild(card);
      });
      if (!appState.opsAlertDetail) {
        clearNode(els.opsAlertDetail, "这里会显示选中 alert 的标准处置 bundle、runbook 和 investigation ref。");
      } else {
        const detailPayload = appState.opsAlertDetail;
        const alert = detailPayload.alert || {};
        const runbook = detailPayload.runbook || {};
        const responseBundle = detailPayload.standard_response_bundle || {};
        const investigation = detailPayload.investigation_bundle?.filters || alert.investigation_ref || {};
        const supportActions = (responseBundle.recommended_actions || [])
          .concat((responseBundle.support_issue?.suggested_operator_actions || []).map((item) => item.action_type))
          .filter(Boolean);
        els.opsAlertDetail.appendChild(
          createListCard({
            title: `Alert Detail · ${alert.alert_id || "-"}`,
            score: `${alert.status || "-"} · ${alert.severity || "-"}`,
            body:
              `account ${alert.account_id || "global"} · category ${alert.category || "-"} · source ${alert.source_type || "-"}\n` +
              `detected ${alert.detected_at ? formatTimestamp(alert.detected_at) : "-"}\n` +
              `summary ${alert.summary || "-"}\n` +
              `refs ${(alert.source_refs || []).map((item) => `${item.label || item.kind}:${item.ref_id || "-"}`).join(" / ") || "-"}\n` +
              `recommended ${(alert.recommended_actions || []).join(" / ") || "-"}\n` +
              `SOP ${(alert.standard_operating_path || []).join(" -> ") || "-"}\n` +
              `owner ${alert.state?.reviewer_id || "-"} · note ${alert.state?.note || "-"}\n\n` +
              `investigation ref:\naccount ${investigation.account_id || "-"} · world ${investigation.world_version_id || "-"} · case ${investigation.case_id || "-"}\n\n` +
              `runbook:\ntriage ${(runbook.triage_steps || []).join(" / ") || "-"}\nrecovery ${(runbook.recovery_steps || []).join(" / ") || "-"}\n\n` +
              `standard response:\n${supportActions.join(" / ") || (responseBundle.recommended_next_actions || []).join(" / ") || (runbook.standard_actions || []).join(" / ") || "-"}`
          })
        );
      }
    }

    const governanceSummary = governance.governance_summary || {};
    const restrictionSummary = governance.restriction_summary || {};
    els.opsGovernanceSummary.appendChild(
      createListCard({
        title: `Governance Summary · ${detail.account_id}`,
        score: `${governanceSummary.open_case_count ?? 0} open`,
        body:
          `total ${governanceSummary.total_cases ?? 0} · escalated ${governanceSummary.escalated_case_count ?? 0}\n` +
          `active restrictions ${restrictionSummary.active_restriction_count ?? 0}\n` +
          `overdue ${governanceSummary.overdue_case_count ?? 0}\n` +
          `status ${Object.entries(governanceSummary.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `type ${Object.entries(governanceSummary.case_type_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `severity ${Object.entries(governanceSummary.severity_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `queue ${Object.entries(governanceSummary.queue_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `owners ${Object.entries(governanceSummary.owner_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `latest ${governanceSummary.latest_case_id || "-"} · ${governanceSummary.latest_case_at || "-"}\n\n` +
          `recommended:\n${(governance.recommended_case_prefills || []).map((item) => item.label).join("\n") || "-"}`
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
      els.opsGovernanceSummary.appendChild(actions);
    }

    if (!governance.governance_cases?.length) {
      clearNode(els.opsGovernanceCases, "这里会显示当前 account 关联的 governance cases。");
    } else {
      governance.governance_cases.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        const restriction = item.restriction || {};
        const workflow = item.workflow_summary || {};
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.summary || item.case_id}</h3>
            <span class="list-card-score">${item.status || "-"}</span>
          </div>
          <p class="list-card-body">${item.case_id}\n${item.case_type || "-"} · ${item.queue || "-"} · ${item.severity || "-"}\ntarget ${item.target_type || "-"}:${item.target_id || "-"}\nowner ${workflow.owner_id || item.owner_id || "-"} · due ${workflow.due_at || item.due_at || "-"} · overdue ${workflow.is_overdue ? "yes" : "no"}\nreviewer ${item.reviewer_id || "-"} · updated ${item.updated_at || "-"}\npolicy ${(workflow.policy_labels || item.policy_labels || []).join(" / ") || "-"} · disposition ${workflow.disposition || item.disposition || "-"}\nevidence ${workflow.evidence_count ?? (item.evidence_refs || []).length ?? 0} · support ${(item.support_issue_ids || []).join(" / ") || "-"}\nrestriction ${restriction.restriction_id || "-"} · ${restriction.restriction_type || "-"} · ${restriction.status || "-"}\nresolution ${item.resolution_notes || "-"}\ntransitions ${(item.status_transitions || []).map((entry) => `${entry.status}@${entry.changed_at}`).join(" / ") || "-"}</p>
        `;
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
        els.opsGovernanceCases.appendChild(card);
      });
    }

    if (!appState.opsGovernanceDetail) {
      clearNode(els.opsGovernanceDetail, "这里会显示选中 governance case 的 drill-down。");
    } else {
      const item = appState.opsGovernanceDetail;
      const restriction = item.restriction || {};
      const workflow = item.workflow_summary || {};
      const permissions = item.permission_summary || {};
      els.opsGovernanceDetail.appendChild(
        createListCard({
          title: `Governance Detail · ${item.case_id}`,
          score: item.status || "-",
          body:
            `case ${item.case_type || "-"} · ${item.queue || "-"} · ${item.severity || "-"}\n` +
            `target ${item.target_type || "-"}:${item.target_id || "-"} · reviewer ${item.reviewer_id || "-"}\n` +
            `owner ${workflow.owner_id || item.owner_id || "-"} · due ${workflow.due_at || item.due_at || "-"} · overdue ${workflow.is_overdue ? "yes" : "no"}\n` +
            `support ${(item.support_issue_ids || []).join(" / ") || "-"}\n` +
            `restriction ${restriction.restriction_id || "-"} · ${restriction.restriction_type || "-"} · ${restriction.status || "-"}\n` +
            `policy ${(workflow.policy_labels || item.policy_labels || []).join(" / ") || "-"} · disposition ${workflow.disposition || item.disposition || "-"}\n` +
            `transition options ${(workflow.transition_options || []).join(" / ") || "-"}\n` +
            `permissions claim=${permissions.can_claim ? "yes" : "no"} assign=${permissions.can_assign ? "yes" : "no"} evidence=${permissions.can_add_evidence ? "yes" : "no"} transition=${permissions.can_transition ? "yes" : "no"} release=${permissions.can_release_restriction ? "yes" : "no"}\n` +
            `summary ${item.summary || "-"}\nresolution ${item.resolution_notes || "-"}\n\n` +
            `workflow checklist:\n${(item.workflow_checklist || []).map((entry) => `${entry.key} · ${entry.status}\n${entry.label}${entry.note ? ` · ${entry.note}` : ""}`).join("\n\n") || "-"}\n\n` +
            `evidence:\n${(item.evidence_refs || []).map((entry) => `${entry.title || entry.kind} · ${entry.kind}\n${entry.ref_id || "-"} · ${entry.preview || "-"}`).join("\n\n") || "-"}\n\n` +
            `next actions:\n${(item.recommended_next_actions || []).join("\n") || "-"}\n\n` +
            `transitions:\n${(item.status_transitions || []).map((entry) => `${entry.status} · ${entry.reviewer_id || "-"} · ${entry.changed_at}\n${entry.notes || "-"}`).join("\n\n") || "-"}\n\n` +
            `linked support:\n${(item.linked_support_issues || []).map((issue) => `${issue.issue_id} · ${issue.issue_type} · ${issue.severity}\n${issue.title || "-"}\n${issue.summary || "-"}`).join("\n\n") || "-"}\n\n` +
            `audit events:\n${(item.audit_events || []).map((event) => `${event.action} · ${event.status || "-"} · ${formatTimestamp(event.occurred_at)}\n${event.reason || "-"} · ${event.object_type || "-"}:${event.object_id || "-"}`).join("\n\n") || "-"}`
        })
      );
    }

    const governanceExport = appState.opsGovernanceExport || {};
    if (!governanceExport.cases?.length && !governanceExport.restrictions?.length) {
      clearNode(els.opsGovernanceExport, "这里会显示治理审计导出摘要。");
    } else {
      els.opsGovernanceExport.appendChild(
        createListCard({
          title: `Governance Audit Export · ${detail.account_id}`,
          score: `${governanceExport.governance_summary?.total_cases ?? 0} cases`,
          body:
            `generated ${governanceExport.export_generated_at || "-"}\n` +
            `case status ${Object.entries(governanceExport.governance_summary?.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
            `restriction status ${Object.entries(governanceExport.restriction_summary?.status_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
            `restriction type ${Object.entries(governanceExport.restriction_summary?.type_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n\n` +
            `restrictions:\n${(governanceExport.restrictions || []).map((item) => `${item.restriction_id} · ${item.restriction_type} · ${item.status}\ncase ${item.case_id} · target ${item.target_type}:${item.target_id}`).join("\n\n") || "-"}`
        })
      );
    }

    const auditBreakdown = detail.audit_breakdown || {};
    const auditSummary = [
      `total ${auditBreakdown.total_entries ?? 0}`,
      `latest ${auditBreakdown.latest_at || "-"}`,
      `categories ${Object.entries(auditBreakdown.by_category || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `surfaces ${Object.entries(auditBreakdown.by_surface || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `sources ${Object.entries(auditBreakdown.sources || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}`,
      `top actions ${((auditBreakdown.top_actions || []).map((item) => `${item.action}=${item.count}`).join(" / ")) || "-"}`,
      `cursor ${detail.timeline_cursor?.returned ?? 0}/${detail.timeline_cursor?.limit ?? 0} · more ${detail.timeline_cursor?.has_more ? "yes" : "no"}`,
    ].join("\n");
    els.opsAccountAuditSummary.appendChild(
      createListCard({
        title: "Audit Breakdown",
        score: `${auditBreakdown.total_entries ?? 0} entries`,
        body: auditSummary,
      })
    );

    if (!detail.audit_trail?.length) {
      clearNode(els.opsAccountAuditTrail, "这里会显示当前 account 的完整 audit trail。");
    } else {
      detail.audit_trail.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.action || "-"}</h3>
            <span class="list-card-score">${item.category || "-"}</span>
          </div>
          <p class="list-card-body">${formatTimestamp(item.occurred_at)}\n${item.surface || "-"} · ${item.source_type || "-"}\nactor ${item.actor_id || "-"} → ${item.object_type || "-"} ${item.object_id || "-"}\nstatus ${item.status || "-"} · reason ${item.reason || "-"}\nwallet ${item.wallet_type || "-"} · tier ${item.tier_id || "-"} · units ${item.usage_units ?? "-"}\nworld ${item.world_version_id || item.world_id || "-"} · session ${item.session_id || "-"}</p>
        `;
        if (item.object_type === "entitlement" && item.object_id && els.opsEntitlementId) {
          card.addEventListener("click", () => {
            els.opsEntitlementId.value = item.object_id;
          });
        }
        els.opsAccountAuditTrail.appendChild(card);
      });
    }
  }
}

function renderOpsInvestigationSection() {
  clearNode(els.opsInvestigationSummary);
  clearNode(els.opsInvestigationTimeline);
  clearNode(els.opsInvestigationEvidence);
  if (!appState.opsInvestigationBundle) {
    clearNode(els.opsInvestigationSummary, "这里会显示 investigation summary 与推荐排查路径。");
    clearNode(els.opsInvestigationTimeline, "这里会显示统一 trace timeline。");
    clearNode(els.opsInvestigationEvidence, "这里会显示 evidence index。");
  } else {
    const bundle = appState.opsInvestigationBundle;
    const summary = bundle.investigation_summary || {};
    const filters = bundle.filters || {};
    const linked = bundle.linked_entities || {};
    const recommended = (bundle.recommended_paths || [])
      .map((item, index) => `${index + 1}. ${item.path_id} · score ${item.score ?? 0}\n${item.reason || "-"}`)
      .join("\n\n") || "-";
    els.opsInvestigationSummary.appendChild(
      createListCard({
        title: `Investigation Summary · ${filters.account_id || linked.account_id || "-"}`,
        score: `${summary.trace_count ?? 0} traces`,
        body:
          `generated ${formatTimestamp(bundle.generated_at)}\n` +
          `filters account ${filters.account_id || "-"} · world ${filters.world_version_id || "-"} · case ${filters.case_id || "-"} · limit ${filters.limit || "-"}\n` +
          `linked subscription ${linked.subscription_id || "-"} · checkout ${linked.checkout_session_id || "-"}\n` +
          `governance ${(linked.governance_case_ids || []).join(" / ") || "-"}\n` +
          `world versions ${(linked.world_version_ids || []).join(" / ") || "-"}\n` +
          `support issues ${(linked.support_issue_ids || []).join(" / ") || "-"}\n\n` +
          `summary:\n` +
          `latest ${summary.latest_at ? formatTimestamp(summary.latest_at) : "-"}\n` +
          `categories ${Object.entries(summary.category_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `severity ${Object.entries(summary.severity_counts || {}).map(([key, value]) => `${key}=${value}`).join(" / ") || "-"}\n` +
          `restrictions ${summary.active_restriction_count ?? 0} · support ${summary.open_support_issue_count ?? 0} · billing events ${summary.billing_event_count ?? 0} · retries ${summary.billing_retry_attempt_count ?? 0}\n\n` +
          `recommended paths:\n${recommended}`
      })
    );

    if (!bundle.trace_timeline?.length) {
      clearNode(els.opsInvestigationTimeline, "这里会显示统一 trace timeline。");
    } else {
      bundle.trace_timeline.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.headline || item.trace_id}</h3>
            <span class="list-card-score">${item.category || "-"} · ${item.severity || "-"}</span>
          </div>
          <p class="list-card-body">${formatTimestamp(item.occurred_at)}\n${item.source_type || "-"} · status ${item.status || "-"}\n${item.summary || "-"}\naccount ${item.account_id || "-"} · world ${item.world_version_id || "-"} · case ${item.case_id || "-"} · session ${item.session_id || "-"}\nobject ${item.object_type || "-"}:${item.object_id || "-"}\nnext ${(item.next_actions || []).join(" / ") || "-"}\nrelated ${(item.related_trace_ids || []).join(" / ") || "-"}\nevidence ${(item.evidence_refs || []).map((ref) => `${ref.label || ref.kind}:${ref.ref_id || "-"}`).join(" / ") || "-"}</p>
        `;
        card.addEventListener("click", () => {
          if (item.case_id && els.opsGovernanceCaseId) {
            els.opsGovernanceCaseId.value = item.case_id;
          }
          if (item.world_version_id && els.opsInvestigationWorldVersionId) {
            els.opsInvestigationWorldVersionId.value = item.world_version_id;
          }
          if (item.account_id && els.opsInvestigationAccountId) {
            els.opsInvestigationAccountId.value = item.account_id;
          }
          if (item.source_type === "billing_lifecycle_event" && item.object_id && els.opsBillingEventId) {
            els.opsBillingEventId.value = item.object_id;
          }
        });
        els.opsInvestigationTimeline.appendChild(card);
      });
    }

    if (!bundle.evidence_index?.length) {
      clearNode(els.opsInvestigationEvidence, "这里会显示 evidence index。");
    } else {
      bundle.evidence_index.forEach((item) => {
        const card = document.createElement("article");
        card.className = "list-card";
        card.innerHTML = `
          <div class="list-card-head">
            <h3>${item.title || item.evidence_id}</h3>
            <span class="list-card-score">${item.source_type || "-"}</span>
          </div>
          <p class="list-card-body">${item.preview || "-"}\nsource ${item.source_id || "-"}\nlinked ${item.linked_object_type || "-"}:${item.linked_object_id || "-"}</p>
        `;
        els.opsInvestigationEvidence.appendChild(card);
      });
    }
  }
}

function renderOpsLearnedSection() {
  clearNode(els.opsEvalMetrics);
  if (!appState.opsEvalMetrics) {
    clearNode(els.opsEvalMetrics, "这里会显示 pass / rewrite / block、top issues 与质量趋势。");
  } else {
    const metric = appState.opsEvalMetrics;
    const continuationSummary = metric.continuation_signal_summary || {};
    const topCorrelations = (metric.quality_signal_correlations || []).slice(0, 3);
    const worldDetails = (metric.continuation_world_details || []).slice(0, 3);
    const versionDetails = (metric.continuation_version_details || []).slice(0, 4);
    const accumulation = metric.continuation_sample_accumulation || {};
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>当前质量概览</h3>
        <span class="list-card-score">pass ${(Number(metric.pass_rate || 0) * 100).toFixed(0)}%</span>
      </div>
      <p class="list-card-body">rewrite ${(Number(metric.rewrite_rate || 0) * 100).toFixed(0)}% · block ${(Number(metric.block_rate || 0) * 100).toFixed(0)}%\n继续相关性 ${Number(metric.online_continuation_correlation || 0).toFixed(2)}\n样本 ${continuationSummary.sample_count ?? 0} · 正样本 ${continuationSummary.positive_count ?? 0} · 负样本 ${continuationSummary.negative_count ?? 0}\nTop correlation ${(topCorrelations || []).map((item) => `${item.metric}=${Number(item.correlation || 0).toFixed(2)}`).join(" / ") || "-"}</p>
    `;
    els.opsEvalMetrics.appendChild(card);

    const drilldownCard = document.createElement("article");
    drilldownCard.className = "list-card";
    drilldownCard.innerHTML = `
      <div class="list-card-head">
        <h3>Continuation Drill-down</h3>
        <span class="list-card-score">${worldDetails.length} worlds</span>
      </div>
      <p class="list-card-body">worlds:\n${worldDetails.map((item) => `${item.world_id} · corr ${Number(item.online_continuation_correlation || 0).toFixed(2)} · samples ${item.sample_count ?? 0} · gap ${item.sample_gap ?? 0}\nrate ${(Number(item.continuation_rate || 0) * 100).toFixed(0)}% · action ${item.recommended_action || "-"}`).join("\n\n") || "-"}\n\nversions:\n${versionDetails.map((item) => `${item.world_version_id} · corr ${Number(item.online_continuation_correlation || 0).toFixed(2)} · samples ${item.sample_count ?? 0} · gap ${item.sample_gap ?? 0}`).join("\n") || "-"}</p>
    `;
    els.opsEvalMetrics.appendChild(drilldownCard);

    const accumulationCard = document.createElement("article");
    accumulationCard.className = "list-card";
    accumulationCard.innerHTML = `
      <div class="list-card-head">
        <h3>Sample Accumulation</h3>
        <span class="list-card-score">${accumulation.worlds_below_target_count ?? 0} worlds pending</span>
      </div>
      <p class="list-card-body">target/world ${accumulation.target_sample_count_per_world ?? 0} · target/version ${accumulation.target_sample_count_per_version ?? 0}\nnegative target ${accumulation.target_negative_samples ?? 0}\nworlds below target ${accumulation.worlds_below_target_count ?? 0} · versions below target ${accumulation.versions_below_target_count ?? 0}\n\nprioritized worlds:\n${(accumulation.prioritized_worlds || []).map((item) => `${item.world_id} · samples ${item.sample_count ?? 0} · negatives ${item.negative_count ?? 0} · gap ${item.sample_gap ?? 0} · ${item.recommended_action || "-"}`).join("\n") || "-"}\n\nprioritized versions:\n${(accumulation.prioritized_versions || []).map((item) => `${item.world_version_id} · samples ${item.sample_count ?? 0} · negatives ${item.negative_count ?? 0} · gap ${item.sample_gap ?? 0}`).join("\n") || "-"}</p>
    `;
    els.opsEvalMetrics.appendChild(accumulationCard);

    const issuesCard = document.createElement("article");
    issuesCard.className = "list-card";
    issuesCard.innerHTML = `
      <div class="list-card-head">
        <h3>Top Issues</h3>
        <span class="list-card-score">${(metric.top_issue_categories || []).length} 类</span>
      </div>
      <p class="list-card-body">${(metric.top_issue_categories || []).map((item) => `${item.issue_code} · ${item.count} · ${item.owning_module}\n修复建议：${item.fix_hint}`).join("\n\n") || "暂无 issue 聚合"}</p>
    `;
    els.opsEvalMetrics.appendChild(issuesCard);

    const trendCard = document.createElement("article");
    trendCard.className = "list-card";
    trendCard.innerHTML = `
      <div class="list-card-head">
        <h3>World Pack 趋势</h3>
        <span class="list-card-score">${(metric.per_world_pack_quality_trend || []).length} 条</span>
      </div>
      <p class="list-card-body">${(metric.per_world_pack_quality_trend || []).map((item) => `${item.world_version_id} · avg ${Number(item.avg_score || 0).toFixed(3)}`).join("\n") || "暂无趋势数据"}</p>
    `;
    els.opsEvalMetrics.appendChild(trendCard);

    const actionCard = document.createElement("article");
    actionCard.className = "list-card";
    actionCard.innerHTML = `
      <div class="list-card-head">
        <h3>建议修复顺序</h3>
        <span class="list-card-score">${(metric.next_actions || []).length} 项</span>
      </div>
      <p class="list-card-body">${(metric.next_actions || []).map((item, index) => `${index + 1}. ${item.issue_code} -> ${item.owning_module}\n${item.fix_hint}`).join("\n\n") || "当前没有额外修复建议。"}</p>
    `;
    els.opsEvalMetrics.appendChild(actionCard);

    const learnedCard = document.createElement("article");
    learnedCard.className = "list-card";
    learnedCard.innerHTML = `
      <div class="list-card-head">
        <h3>Learned Shadow</h3>
        <span class="list-card-score">${metric.learned_shadow_summary?.status || "unavailable"}</span>
      </div>
      <p class="list-card-body">available ${metric.learned_shadow_summary?.available ? "yes" : "no"}\nagreement ${metric.learned_shadow_summary?.agreement_rate !== null && metric.learned_shadow_summary?.agreement_rate !== undefined ? Number(metric.learned_shadow_summary.agreement_rate).toFixed(3) : "-"}\ntrain ${metric.learned_shadow_summary?.train_count ?? 0} · val ${metric.learned_shadow_summary?.val_count ?? 0} · test ${metric.learned_shadow_summary?.test_count ?? 0}\nwarnings ${(metric.learned_shadow_summary?.warnings || []).join(" / ") || "-"}\nnext ${metric.learned_shadow_summary?.recommended_next_action || "-"}\n\nworld mismatches:\n${(metric.learned_shadow_summary?.top_mismatch_worlds || []).map((item) => `${item.world_id}=${Number(item.value ?? item.count ?? 0).toFixed(3)}`).join("\n") || "-"}\n\nissue mismatches:\n${(metric.learned_shadow_summary?.top_mismatch_issue_codes || []).map((item) => `${item.issue_code || item.key}=${Number(item.value ?? item.count ?? 0).toFixed(3)}`).join("\n") || "-"}</p>
    `;
    els.opsEvalMetrics.appendChild(learnedCard);

    const rerankerCard = document.createElement("article");
    rerankerCard.className = "list-card";
    rerankerCard.innerHTML = `
      <div class="list-card-head">
        <h3>Reranker Shadow</h3>
        <span class="list-card-score">${metric.learned_reranker_shadow_summary?.status || "unavailable"}</span>
      </div>
      <p class="list-card-body">available ${metric.learned_reranker_shadow_summary?.available ? "yes" : "no"}\ntrain ${metric.learned_reranker_shadow_summary?.train_count ?? 0} · val ${metric.learned_reranker_shadow_summary?.val_count ?? 0} · test ${metric.learned_reranker_shadow_summary?.test_count ?? 0}\nwarnings ${(metric.learned_reranker_shadow_summary?.warnings || []).join(" / ") || "-"}\nnext ${metric.learned_reranker_shadow_summary?.recommended_next_action || "-"}\n\nworld accuracy:\n${Object.entries(metric.learned_reranker_shadow_summary?.per_world_accuracy || {}).map(([worldId, value]) => `${worldId}=${Number(value).toFixed(3)}`).join("\n") || "-"}\n\nissue error:\n${Object.entries(metric.learned_reranker_shadow_summary?.per_issue_code_error_rate || {}).map(([issueCode, value]) => `${issueCode}=${Number(value).toFixed(3)}`).join("\n") || "-"}\n\nlow coverage:\n${(metric.learned_reranker_shadow_summary?.low_pair_coverage_worlds || []).map((item) => `${item.world_id}=${item.count}`).join("\n") || "-"}</p>
    `;
    els.opsEvalMetrics.appendChild(rerankerCard);
  }

  clearNode(els.opsCrossPackQuality);
  if (!appState.opsCrossPackQuality) {
    clearNode(els.opsCrossPackQuality, "这里会显示 cross-pack pass rate、top failing packs 与 metric delta。");
  } else {
    const benchmark = appState.opsCrossPackQuality;
    const overviewCard = document.createElement("article");
    overviewCard.className = "list-card";
    overviewCard.innerHTML = `
      <div class="list-card-head">
        <h3>Cross-Pack 概览</h3>
        <span class="list-card-score">${formatPercent(benchmark.cross_pack_pass_rate)}</span>
      </div>
      <p class="list-card-body">覆盖 ${benchmark.worlds?.length || 0} 个 packs\npass rate delta ${benchmark.delta_summary?.cross_pack_pass_rate_delta >= 0 ? "+" : ""}${Number(benchmark.delta_summary?.cross_pack_pass_rate_delta || 0).toFixed(3)}</p>
    `;
    els.opsCrossPackQuality.appendChild(overviewCard);

    const failingCard = document.createElement("article");
    failingCard.className = "list-card";
    failingCard.innerHTML = `
      <div class="list-card-head">
        <h3>Top Failing Packs</h3>
        <span class="list-card-score">${(benchmark.top_failing_packs || []).length} 个</span>
      </div>
      <p class="list-card-body">${(benchmark.top_failing_packs || []).map((item) => `${item.world_id}\npass ${formatPercent(item.pass_rate)} · block ${formatPercent(item.block_rate)}\n主问题：${(item.top_issue_categories || []).map((issue) => issue.issue_code).join(" / ") || "-"}\n最弱维度：${(item.weakest_dimensions || []).map((dimension) => `${dimension.name}=${Number(dimension.value || 0).toFixed(3)}`).join(" / ") || "-"}\n建议目标：${item.recommended_target || "-"}\nvoice ${Number(item.voice_separation_score || 0).toFixed(2)} · action ${Number(item.emotion_action_specificity || 0).toFixed(2)} · leak ${Number(item.prose_leak_rate || 0).toFixed(3)}`).join("\n\n") || "暂无 cross-pack 弱项。"}</p>
    `;
    els.opsCrossPackQuality.appendChild(failingCard);

    const deltaCard = document.createElement("article");
    deltaCard.className = "list-card";
    deltaCard.innerHTML = `
      <div class="list-card-head">
        <h3>Metric Deltas</h3>
        <span class="list-card-score">${(benchmark.delta_summary?.regressions || []).length} 个回退</span>
      </div>
      <p class="list-card-body">${(benchmark.delta_summary?.regressions || []).map((item) => `${item.world_id}\n${item.metrics.join(" / ")}`).join("\n\n") || "当前没有跨 Pack 指标回退。"}</p>
    `;
    els.opsCrossPackQuality.appendChild(deltaCard);

    const diagnosisCard = document.createElement("article");
    diagnosisCard.className = "list-card";
    diagnosisCard.innerHTML = `
      <div class="list-card-head">
        <h3>Per-Pack Diagnosis</h3>
        <span class="list-card-score">${(benchmark.worlds || []).length} 个</span>
      </div>
      <p class="list-card-body">${(benchmark.worlds || []).map((item) => `${item.world_id}\n主问题：${item.issue_summary?.dominant_issue || "-"}\n最弱维度：${(item.issue_summary?.weakest_dimensions || []).map((dimension) => `${dimension.name}=${Number(dimension.value || 0).toFixed(3)}`).join(" / ") || "-"}\n建议目标：${item.issue_summary?.recommended_target || "-"}`).join("\n\n") || "暂无诊断数据。"}</p>
    `;
    els.opsCrossPackQuality.appendChild(diagnosisCard);
  }

  clearNode(els.opsLearnedDashboard);
  clearNode(els.opsLearnedTraining);
  clearNode(els.opsLearnedEvidence);
  if (!appState.opsLearnedDashboard) {
    clearNode(els.opsLearnedDashboard, "这里会显示 evaluator / reranker 的统一 learned summary。");
    clearNode(els.opsLearnedTraining, "这里会显示最近一次 learned training automation 结果。");
    clearNode(els.opsLearnedEvidence, "这里会显示 evaluator / reranker 的 promotion evidence pack 摘要。");
  } else {
    const dashboard = appState.opsLearnedDashboard;
    const overviewCard = document.createElement("article");
    overviewCard.className = "list-card";
    overviewCard.innerHTML = `
      <div class="list-card-head">
        <h3>Unified Learned Dashboard</h3>
        <span class="list-card-score">${dashboard.recommended_next_focus || "-"}</span>
      </div>
      <p class="list-card-body">generated ${formatTimestamp(dashboard.generated_at)}\nwarnings ${(dashboard.warnings || []).join(" / ") || "-"}\nshared weak worlds ${(dashboard.shared_weak_worlds || []).join(" / ") || "-"}\nshared weak issues ${(dashboard.shared_weak_issue_codes || []).join(" / ") || "-"}\nnext ${dashboard.recommended_next_focus || "-"}</p>
    `;
    els.opsLearnedDashboard.appendChild(overviewCard);

    const artifactCard = document.createElement("article");
    artifactCard.className = "list-card";
    artifactCard.innerHTML = `
      <div class="list-card-head">
        <h3>Artifact Status</h3>
        <span class="list-card-score">${dashboard.artifact_status?.evaluator?.available || dashboard.artifact_status?.reranker?.available ? "ready" : "partial"}</span>
      </div>
      <p class="list-card-body">evaluator ${dashboard.artifact_status?.evaluator?.available ? "available" : "missing"} · ${dashboard.artifact_status?.evaluator?.artifact_dir || "-"}\npublished ${dashboard.evaluator_shadow_summary?.published_at ? formatTimestamp(dashboard.evaluator_shadow_summary.published_at) : "-"}\nsource ${dashboard.evaluator_shadow_summary?.source_output_dir || "-"}\nfiles ${(dashboard.evaluator_shadow_summary?.artifact_files || []).join(" / ") || "-"}\n\nreranker ${dashboard.artifact_status?.reranker?.available ? "available" : "missing"} · ${dashboard.artifact_status?.reranker?.artifact_dir || "-"}\npublished ${dashboard.reranker_shadow_summary?.published_at ? formatTimestamp(dashboard.reranker_shadow_summary.published_at) : "-"}\nsource ${dashboard.reranker_shadow_summary?.source_output_dir || "-"}\nfiles ${(dashboard.reranker_shadow_summary?.artifact_files || []).join(" / ") || "-"}</p>
    `;
    els.opsLearnedDashboard.appendChild(artifactCard);

    const coverageCard = document.createElement("article");
    coverageCard.className = "list-card";
    coverageCard.innerHTML = `
      <div class="list-card-head">
        <h3>Coverage Summary</h3>
        <span class="list-card-score">${((dashboard.coverage_summary?.evaluator_low_coverage_worlds || []).length + (dashboard.coverage_summary?.reranker_low_pair_coverage_worlds || []).length)}</span>
      </div>
      <p class="list-card-body">evaluator low coverage:\n${(dashboard.coverage_summary?.evaluator_low_coverage_worlds || []).map((item) => `${item.world_id}=${item.count}`).join("\n") || "-"}\n\nreranker low coverage:\n${(dashboard.coverage_summary?.reranker_low_pair_coverage_worlds || []).map((item) => `${item.world_id}=${item.count}`).join("\n") || "-"}</p>
    `;
    els.opsLearnedDashboard.appendChild(coverageCard);

    if (!appState.opsLearnedTrainingResult) {
      clearNode(els.opsLearnedTraining, "这里会显示最近一次 learned training automation 结果。");
    } else {
      const run = appState.opsLearnedTrainingResult;
      if (run.job) {
        els.opsLearnedTraining.appendChild(
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
        els.opsLearnedTraining.appendChild(
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

    if (!appState.opsLearnedEvidence) {
      clearNode(els.opsLearnedEvidence, "这里会显示 evaluator / reranker 的 promotion evidence pack 摘要。");
    } else {
      ["evaluator", "reranker"].forEach((track) => {
        const evidence = appState.opsLearnedEvidence?.[track];
        if (!evidence || !evidence.evidence_pack) return;
        const pack = evidence.evidence_pack;
        const summary = pack.evidence_summary || {};
        const artifactState = pack.artifact_state || {};
        els.opsLearnedEvidence.appendChild(
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

  clearNode(els.opsLearnedCompare);
  if (!appState.opsLearnedCompare) {
    clearNode(els.opsLearnedCompare, "这里会显示 evaluator / reranker 的 shadow candidate compare。");
  } else {
    const compare = appState.opsLearnedCompare;
    const compareCard = document.createElement("article");
    compareCard.className = "list-card";
    compareCard.innerHTML = `
      <div class="list-card-head">
        <h3>Shadow Candidate Compare</h3>
        <span class="list-card-score">${compare.preferred_shadow_candidate || "neither"}</span>
      </div>
      <p class="list-card-body">next ${compare.recommended_next_action || "-"}\nsafe rollout ${(compare.safe_rollout_candidates || []).join(" / ") || "-"}\n\nevaluator:\nstatus ${compare.evaluator_status || "-"}\nagreement ${compare.evaluator_scorecard?.agreement_rate !== null && compare.evaluator_scorecard?.agreement_rate !== undefined ? Number(compare.evaluator_scorecard.agreement_rate).toFixed(3) : "-"}\nsplits ${compare.evaluator_scorecard?.train_count || 0}/${compare.evaluator_scorecard?.val_count || 0}/${compare.evaluator_scorecard?.test_count || 0}\nwarnings ${(compare.evaluator_scorecard?.warnings || []).join(" / ") || "-"}\nrollout ${compare.rollout_readiness?.evaluator?.candidate_ready ? "ready" : "hold"} · hint ${compare.rollout_readiness?.evaluator?.approval_hint || "-"}\n\nreranker:\nstatus ${compare.reranker_status || "-"}\navg accuracy ${compare.reranker_scorecard?.average_world_accuracy !== null && compare.reranker_scorecard?.average_world_accuracy !== undefined ? Number(compare.reranker_scorecard.average_world_accuracy).toFixed(3) : "-"}\nsplits ${compare.reranker_scorecard?.train_count || 0}/${compare.reranker_scorecard?.val_count || 0}/${compare.reranker_scorecard?.test_count || 0}\nwarnings ${(compare.reranker_scorecard?.warnings || []).join(" / ") || "-"}\nrollout ${compare.rollout_readiness?.reranker?.candidate_ready ? "ready" : "hold"} · hint ${compare.rollout_readiness?.reranker?.approval_hint || "-"}\n\ndisagreement worlds ${(compare.disagreement_worlds || []).map((item) => `${item.world_id}:${item.evaluator_signal}/${item.reranker_signal}`).join(" / ") || "-"}\ndisagreement issues ${(compare.disagreement_issue_codes || []).map((item) => item.issue_code).join(" / ") || "-"}</p>
    `;
    els.opsLearnedCompare.appendChild(compareCard);
  }

  clearNode(els.opsLearnedRollout);
  if (!appState.opsLearnedRollout) {
    clearNode(els.opsLearnedRollout, "这里会显示 learned rollout summary、safe candidates 与 rollback watchlist。");
  } else {
    const rollout = appState.opsLearnedRollout;
    const summaryCard = document.createElement("article");
    summaryCard.className = "list-card";
    summaryCard.innerHTML = `
      <div class="list-card-head">
        <h3>Learned Rollout Summary</h3>
        <span class="list-card-score">${(rollout.active_tracks || []).join(" / ") || "shadow"}</span>
      </div>
      <p class="list-card-body">preferred ${rollout.preferred_shadow_candidate || "neither"}\nnext ${rollout.recommended_next_action || "-"}\nactive ${(rollout.active_tracks || []).join(" / ") || "-"}\nsafe ${(rollout.safe_rollout_candidates || []).join(" / ") || "-"}\nrollback ${(rollout.rollback_watchlist || []).join(" / ") || "-"}</p>
    `;
    els.opsLearnedRollout.appendChild(summaryCard);

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
      els.opsLearnedRollout.appendChild(card);
    });
  }

  clearNode(els.opsLearnedPromotion);
  if (!appState.opsLearnedPromotion) {
    clearNode(els.opsLearnedPromotion, "这里会显示 evaluator 的 promotion recommendation、blockers、advisories 与 checklist。");
  } else {
    const promotion = appState.opsLearnedPromotion;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>Evaluator Promotion Gate</h3>
        <span class="list-card-score">${promotion.approval_status || promotion.recommendation_status || "-"}</span>
      </div>
      <p class="list-card-body">track ${promotion.track || "evaluator"} · scope ${promotion.scope || "global"} · mode ${promotion.mode || "manual_approval"}\nrecommendation ${promotion.recommendation_status || promotion.status || "-"}\napproval ${promotion.approval_status || "unapproved"}\nreconfirm required ${promotion.reconfirm_required ? "yes" : "no"}\nnext ${promotion.recommended_action || "-"}\n\nlatest approval:\n${promotion.latest_approval_record ? `${promotion.latest_approval_record.status} · ${promotion.latest_approval_record.reviewer_id || "-"} · ${promotion.latest_approval_record.updated_at || "-"}\nreason ${promotion.latest_approval_record.reason || "-"}` : "暂无"}\n\nblockers ${(promotion.blockers || []).join(" / ") || "-"}\nadvisories ${(promotion.advisories || []).join(" / ") || "-"}\n\nevidence:\nagreement ${promotion.evidence?.agreement_rate !== null && promotion.evidence?.agreement_rate !== undefined ? Number(promotion.evidence.agreement_rate).toFixed(3) : "-"}\ntrain ${promotion.evidence?.train_count ?? 0} · val ${promotion.evidence?.val_count ?? 0} · test ${promotion.evidence?.test_count ?? 0}\npreferred ${promotion.evidence?.preferred_shadow_candidate || "neither"}\nreview backlog ${promotion.evidence?.review_backlog_count ?? 0}\npair backlog ${promotion.evidence?.pair_backlog_count ?? 0}\ndisagreement worlds ${promotion.evidence?.disagreement_world_count ?? 0}\ndisagreement issues ${promotion.evidence?.disagreement_issue_count ?? 0}\n\nchecklist:\n${(promotion.checklist || []).map((item) => `${item.ok ? "✓" : "×"} ${item.key} · ${item.reason}`).join("\n") || "-"}</p>
    `;
    els.opsLearnedPromotion.appendChild(card);
  }

  clearNode(els.opsLearnedRerankerPromotion);
  if (!appState.opsLearnedRerankerPromotion) {
    clearNode(els.opsLearnedRerankerPromotion, "这里会显示 reranker 的 promotion recommendation、blockers、advisories 与 checklist。");
  } else {
    const promotion = appState.opsLearnedRerankerPromotion;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>Reranker Promotion Gate</h3>
        <span class="list-card-score">${promotion.approval_status || promotion.recommendation_status || "-"}</span>
      </div>
      <p class="list-card-body">track ${promotion.track || "reranker"} · scope ${promotion.scope || "global"} · mode ${promotion.mode || "manual_approval"}\nrecommendation ${promotion.recommendation_status || promotion.status || "-"}\napproval ${promotion.approval_status || "unapproved"}\nreconfirm required ${promotion.reconfirm_required ? "yes" : "no"}\nnext ${promotion.recommended_action || "-"}\n\nlatest approval:\n${promotion.latest_approval_record ? `${promotion.latest_approval_record.status} · ${promotion.latest_approval_record.reviewer_id || "-"} · ${promotion.latest_approval_record.updated_at || "-"}\nreason ${promotion.latest_approval_record.reason || "-"}` : "暂无"}\n\nblockers ${(promotion.blockers || []).join(" / ") || "-"}\nadvisories ${(promotion.advisories || []).join(" / ") || "-"}\n\nevidence:\navg accuracy ${promotion.evidence?.average_world_accuracy !== null && promotion.evidence?.average_world_accuracy !== undefined ? Number(promotion.evidence.average_world_accuracy).toFixed(3) : "-"}\nlow error worlds ${promotion.evidence?.low_error_world_count ?? 0}\ntrain ${promotion.evidence?.train_count ?? 0} · val ${promotion.evidence?.val_count ?? 0} · test ${promotion.evidence?.test_count ?? 0}\npreferred ${promotion.evidence?.preferred_shadow_candidate || "neither"}\nreview backlog ${promotion.evidence?.review_backlog_count ?? 0}\npair backlog ${promotion.evidence?.pair_backlog_count ?? 0}\ndisagreement worlds ${promotion.evidence?.disagreement_world_count ?? 0}\ndisagreement issues ${promotion.evidence?.disagreement_issue_count ?? 0}\n\nchecklist:\n${(promotion.checklist || []).map((item) => `${item.ok ? "✓" : "×"} ${item.key} · ${item.reason}`).join("\n") || "-"}</p>
    `;
    els.opsLearnedRerankerPromotion.appendChild(card);
  }

  clearNode(els.opsLearnedWorlds);
  if (!appState.opsLearnedDashboard?.world_details?.length) {
    clearNode(els.opsLearnedWorlds, "这里会显示需要优先看的 worlds。");
  } else {
    appState.opsLearnedDashboard.world_details.forEach((item) => {
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
      els.opsLearnedWorlds.appendChild(card);
    });
  }

  clearNode(els.opsLearnedIssues);
  if (!appState.opsLearnedDashboard?.issue_details?.length) {
    clearNode(els.opsLearnedIssues, "这里会显示需要优先看的 issue codes。");
  } else {
    appState.opsLearnedDashboard.issue_details.forEach((item) => {
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
      els.opsLearnedIssues.appendChild(card);
    });
  }

  clearNode(els.opsLearnedDetail);
  if (!appState.opsLearnedDetail) {
    clearNode(els.opsLearnedDetail, "点击一个 world 或 issue 后，这里会显示 detail。");
  } else if (appState.opsLearnedDetail.world_id) {
    const detail = appState.opsLearnedDetail;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>World Detail · ${detail.world_id}</h3>
        <span class="list-card-score">${detail.recommended_action || "-"}</span>
      </div>
      <p class="list-card-body">evaluator agreement ${detail.evaluator_agreement_rate !== null && detail.evaluator_agreement_rate !== undefined ? Number(detail.evaluator_agreement_rate).toFixed(3) : "-"}\nreranker accuracy ${detail.reranker_accuracy !== null && detail.reranker_accuracy !== undefined ? Number(detail.reranker_accuracy).toFixed(3) : "-"}\nevaluator coverage ${detail.evaluator_low_coverage ? "low" : "ok"}\nreranker coverage ${detail.reranker_low_coverage ? "low" : "ok"}\nevaluator issues ${(detail.evaluator_top_issues || []).join(" / ") || "-"}\nreranker issues ${(detail.reranker_top_issues || []).join(" / ") || "-"}</p>
    `;
    els.opsLearnedDetail.appendChild(card);
  } else if (appState.opsLearnedDetail.issue_code) {
    const detail = appState.opsLearnedDetail;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>Issue Detail · ${detail.issue_code}</h3>
        <span class="list-card-score">${detail.recommended_action || "-"}</span>
      </div>
      <p class="list-card-body">evaluator error ${detail.evaluator_error_rate !== null && detail.evaluator_error_rate !== undefined ? Number(detail.evaluator_error_rate).toFixed(3) : "-"}\nreranker error ${detail.reranker_error_rate !== null && detail.reranker_error_rate !== undefined ? Number(detail.reranker_error_rate).toFixed(3) : "-"}\naffected worlds ${(detail.affected_worlds || []).join(" / ") || "-"}</p>
    `;
    els.opsLearnedDetail.appendChild(card);
  }

  clearNode(els.opsLearnedDataOps);
  if (!appState.opsLearnedDataOps) {
    clearNode(els.opsLearnedDataOps, "这里会显示 review backlog、pair coverage backlog 和 action queue。");
  } else {
    const summary = appState.opsLearnedDataOps;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>Learned Data Ops</h3>
        <span class="list-card-score">${summary.recommended_next_action || "-"}</span>
      </div>
      <p class="list-card-body">preferred ${summary.preferred_shadow_candidate || "neither"}\nreview backlog ${summary.coverage_gaps?.review_sample_backlog_count ?? 0}\npair backlog ${summary.coverage_gaps?.pair_coverage_backlog_count ?? 0}\nshared weak worlds ${(summary.coverage_gaps?.shared_weak_worlds || []).join(" / ") || "-"}\nshared weak issues ${(summary.coverage_gaps?.shared_weak_issue_codes || []).join(" / ") || "-"}\naction queue:\n${(summary.action_queue || []).map((item) => `${item.action_type} · ${item.world_id || "-"} · ${item.issue_code || item.chapter_id || "-"} · ${item.recommended_action || "-"}`).join("\n") || "-"}</p>
    `;
    els.opsLearnedDataOps.appendChild(card);
  }

  clearNode(els.opsReviewSampleBacklog);
  if (!appState.opsLearnedDataOps?.review_sample_backlog?.length) {
    clearNode(els.opsReviewSampleBacklog, "这里会显示优先需要人工补样本的章节。");
  } else {
    appState.opsLearnedDataOps.review_sample_backlog.forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      if (appState.opsReviewCaptureTarget?.chapter_id === item.chapter_id) {
        card.classList.add("is-selected");
      }
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.chapter_id}</h3>
          <span class="list-card-score">${item.recommended_action || item.priority || "-"}</span>
        </div>
        <p class="list-card-body">world ${item.world_id}\ndecision ${item.decision}\npriority ${item.priority}\nissues ${(item.issue_codes || []).join(" / ") || "-"}\nworld signal ${item.world_compare_signal || "-"}\nissue signal ${(item.issue_compare_signal || []).join(" / ") || "-"}\nsummary ${item.summary || "-"}</p>
      `;
      card.addEventListener("click", () => selectReviewBacklogItem(item));
      els.opsReviewSampleBacklog.appendChild(card);
    });
  }

  clearNode(els.opsPairCoverageBacklog);
  if (!appState.opsLearnedDataOps?.pair_coverage_backlog?.length) {
    clearNode(els.opsPairCoverageBacklog, "这里会显示需要更多 revision / review 才能长出 inferred pairs 的位置。");
  } else {
    appState.opsLearnedDataOps.pair_coverage_backlog.forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.world_id} · ${item.issue_code}</h3>
          <span class="list-card-score">${item.recommended_action || "-"}</span>
        </div>
        <p class="list-card-body">coverage ${item.coverage_count ?? 0}\nrecent revisions ${(item.recent_revision_ids || []).join(" / ") || "-"}\nchanged sections ${(item.changed_sections || []).join(" / ") || "-"}\nshadow next ${item.shadow_context?.recommended_next_action || "-"}</p>
      `;
      els.opsPairCoverageBacklog.appendChild(card);
    });
  }

  clearNode(els.opsReviewCaptureContext);
  if (!appState.opsReviewCaptureTarget) {
    clearNode(els.opsReviewCaptureContext, "点击 Review Backlog 里的章节后，这里会自动填充上下文。");
  } else {
    const target = appState.opsReviewCaptureTarget;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${target.chapter_id}</h3>
        <span class="list-card-score">${target.recommended_action || "-"}</span>
      </div>
      <p class="list-card-body">world ${target.world_id}\nworld_version ${target.world_version_id}\nsession ${target.session_id || "-"}\nissues ${(target.issue_codes || []).join(" / ") || "-"}\nshadow ${(target.shadow_context?.preferred_shadow_candidate || "neither")} · ${target.shadow_context?.recommended_next_action || "-"}</p>
    `;
    els.opsReviewCaptureContext.appendChild(card);
  }

  clearNode(els.opsLastActionImpact);
  if (!appState.opsLastActionImpact) {
    clearNode(els.opsLastActionImpact, "提交一条 Human Review 后，这里会显示对 backlog / compare / next action 的即时影响。");
  } else {
    const impact = appState.opsLastActionImpact;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${impact.chapter_id || "-"}</h3>
        <span class="list-card-score">${impact.cleared_backlog_target ? "cleared" : "updated"}</span>
      </div>
      <p class="list-card-body">world ${impact.world_id || "-"}\nworld_version ${impact.world_version_id || "-"}\nreview sample ${impact.review_sample_id || "-"}\npreferred ${impact.preferred_shadow_candidate_before || "neither"} -> ${impact.preferred_shadow_candidate_after || "neither"}\nnext ${impact.recommended_next_action_before || "-"} -> ${impact.recommended_next_action_after || "-"}\nreview backlog ${impact.review_backlog_count_before ?? 0} -> ${impact.review_backlog_count_after ?? 0}\npair backlog ${impact.pair_backlog_count_before ?? 0} -> ${impact.pair_backlog_count_after ?? 0}\naction queue ${impact.action_queue_count_before ?? 0} -> ${impact.action_queue_count_after ?? 0}\ncleared backlog target ${impact.cleared_backlog_target ? "yes" : "no"}\nwarnings before ${(impact.warnings_before || []).join(" / ") || "-"}\nwarnings after ${(impact.warnings_after || []).join(" / ") || "-"}</p>
    `;
    els.opsLastActionImpact.appendChild(card);
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

  els.opsPendingCount.textContent = String(appState.opsReviewQueue.length);
  els.opsPublishedWorlds.textContent = String(
    appState.opsWorldStatuses.filter((status) => Boolean(status.published_version)).length
  );
  const totalCost = appState.opsMeters.reduce((sum, item) => sum + Number(item.estimated_cost || 0), 0);
  els.opsTotalCost.textContent = `¥${totalCost.toFixed(2)}`;

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
