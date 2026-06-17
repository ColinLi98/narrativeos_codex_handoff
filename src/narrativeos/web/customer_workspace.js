// Customer-facing reporting workspace runtime.

var CustomerWorkspaceRuntime = (() => {
  const dom = CustomerDOM;
  const {
    api,
    clearNode,
    createListCard,
    downloadBase64File,
    downloadJsonFile,
    downloadTextFile,
    formatPercent,
    parseErrorDetail,
    reportUiMessage,
  } = UIShared;

  function _identity() {
    return authorState.authorAuthSession?.identity || null;
  }

  function _token() {
    return authorState.authorAuthSession?.accessToken || null;
  }

  function _canViewCustomerWorkspace() {
    const role = String(_identity()?.actor_role || "").trim();
    return ["customer", "reviewer", "ops", "admin"].includes(role);
  }

  function _headers() {
    return {
      Authorization: `Bearer ${_token()}`,
    };
  }

  function _renderEmpty(message) {
    [
      dom.customerCampaignEditor,
      dom.customerCampaignList,
      dom.customerCampaignSummary,
      dom.customerAccountSummary,
      dom.customerPlanSummary,
      dom.customerBillingSummary,
      dom.customerLimitSummary,
      dom.customerPartnerPerformance,
      dom.customerQualitySummary,
      dom.customerGroundednessSummary,
      dom.customerReceiptSummary,
      dom.customerHandoffSummary,
      dom.customerDisputeSummary,
      dom.customerDisputeList,
      dom.customerSupportSummary,
      dom.customerSupportList,
      dom.customerLatestTraces,
      dom.customerExportSummary,
    ].forEach((node) => clearNode(node, message));
  }

  function _parseLines(value) {
    return String(value || "")
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function _parseCommaList(value) {
    return String(value || "")
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function _campaignFormPayload() {
    return {
      campaign_id: (dom.customerCampaignId?.value || "").trim() || null,
      title: (dom.customerCampaignTitle?.value || "").trim(),
      target_icp_vertical: (dom.customerCampaignTargetIcp?.value || "").trim(),
      cta_text: (dom.customerCampaignCta?.value || "").trim(),
      disclosure_text: (dom.customerCampaignDisclosure?.value || "").trim(),
      selected_channels: _parseCommaList(dom.customerCampaignChannels?.value || ""),
      selected_partner_refs: _parseCommaList(dom.customerCampaignPartners?.value || ""),
      proof_points: _parseLines(dom.customerCampaignProofPoints?.value || ""),
      proof_source_urls: _parseLines(dom.customerCampaignProofUrls?.value || ""),
      proof_artifact_refs: _parseLines(dom.customerCampaignArtifactRefs?.value || ""),
    };
  }

  function loadCampaignIntoEditor(campaignDetail) {
    const campaign = campaignDetail?.campaign || campaignDetail || {};
    const proofBundle = (campaignDetail?.proof_bundles || [])[0] || {};
    if (dom.customerCampaignId) dom.customerCampaignId.value = campaign.campaign_id || "";
    if (dom.customerCampaignTitle) dom.customerCampaignTitle.value = campaign.title || "";
    if (dom.customerCampaignTargetIcp) dom.customerCampaignTargetIcp.value = campaign.target_icp_vertical || "";
    if (dom.customerCampaignCta) dom.customerCampaignCta.value = campaign.cta_text || "";
    if (dom.customerCampaignDisclosure) dom.customerCampaignDisclosure.value = campaign.disclosure_text || "";
    if (dom.customerCampaignChannels) dom.customerCampaignChannels.value = (campaign.selected_channels_json || []).join(", ");
    if (dom.customerCampaignPartners) dom.customerCampaignPartners.value = (campaign.selected_partner_refs_json || []).join(", ");
    if (dom.customerCampaignProofPoints) dom.customerCampaignProofPoints.value = (proofBundle.proof_points_json || []).join("\n");
    if (dom.customerCampaignProofUrls) dom.customerCampaignProofUrls.value = (proofBundle.source_urls_json || []).join("\n");
    if (dom.customerCampaignArtifactRefs) dom.customerCampaignArtifactRefs.value = (proofBundle.artifact_refs_json || []).join("\n");
    customerState.selectedCampaignId = campaign.campaign_id || null;
  }

  function _accountScore(lifecycle) {
    const status = String(lifecycle?.status || "unknown");
    if (status === "active") return "active";
    if (status === "trial") return "trial";
    if (status === "renewal_due") return "renewal_due";
    return status;
  }

  function _limitBody(limitPosture) {
    return [
      `席位 ${Number(limitPosture?.seat_count || 0)}/${Number(limitPosture?.seat_limit || 0)}`,
      `工作区 ${Number(limitPosture?.workspace_count || 0)}/${Number(limitPosture?.workspace_limit || 0)}`,
      `Campaign ${Number(limitPosture?.campaign_count || 0)}/${Number(limitPosture?.campaign_limit || 0)}`,
      `超限 ${limitPosture?.is_over_limit ? "是" : "否"}`,
    ].join("\n");
  }

  function _lineAmount(lineItems, metricType) {
    const item = (lineItems || []).find((entry) => entry.metric_type === metricType);
    return item ? item.line_amount_usd : 0;
  }

  function renderCustomerSurface(payload) {
    customerState.workspacePayload = payload;
    const customer = payload?.customer_account || {};
    const plan = payload?.plan || {};
    const billingProfile = payload?.billing_profile || {};
    const lifecycle = payload?.lifecycle_summary || {};
    const limits = payload?.limit_posture || {};
    const campaignSummary = payload?.campaign_summary || {};
    const qualitySummary = payload?.quality_summary || {};
    const groundednessSummary = payload?.groundedness_summary || {};
    const receiptSummary = payload?.receipt_summary || {};
    const partnerPerformance = payload?.channel_partner_performance || {};
    const handoffSummary = payload?.handoff_conversion_summary || {};
    const disputeSummary = payload?.dispute_summary || {};
    const disputes = payload?.disputes || [];
    const supportSummary = payload?.support_summary || {};
    const supportCases = payload?.support_cases || [];
    const renewalSummary = payload?.renewal_summary || {};
    const dunningSummary = payload?.dunning_summary || {};
    const pilotConversionSummary = payload?.pilot_conversion_summary || {};
    const expansionSummary = payload?.expansion_summary || {};
    const churnRiskSummary = payload?.churn_risk_summary || {};
    const invoicePreview = payload?.invoice_preview || {};
    const lineItems = handoffSummary?.line_items || [];
    const latestTraces = payload?.linked_traces || [];
    const campaigns = payload?.campaign_details || [];

    clearNode(dom.customerCampaignEditor);
    clearNode(dom.customerCampaignList);
    clearNode(dom.customerCampaignSummary);
    clearNode(dom.customerAccountSummary);
    clearNode(dom.customerPlanSummary);
    clearNode(dom.customerBillingSummary);
    clearNode(dom.customerLimitSummary);
    clearNode(dom.customerPartnerPerformance);
    clearNode(dom.customerQualitySummary);
    clearNode(dom.customerGroundednessSummary);
    clearNode(dom.customerReceiptSummary);
    clearNode(dom.customerHandoffSummary);
    clearNode(dom.customerDisputeSummary);
    clearNode(dom.customerDisputeList);
    clearNode(dom.customerSupportSummary);
    clearNode(dom.customerSupportList);
    clearNode(dom.customerLatestTraces);
    clearNode(dom.customerExportSummary);

    dom.customerCampaignSummary?.appendChild(
      createListCard({
        title: "Campaign 摘要",
        score: campaignSummary.activation_status || "campaign_workflow_pending",
        body: [
          `campaign_count ${campaignSummary.campaign_count || 0}`,
          `campaign_limit ${campaignSummary.campaign_limit || 0}`,
          `status_counts ${Object.entries(campaignSummary.status_counts || {}).map(([key, value]) => `${key}:${value}`).join(" / ") || "-"}`,
          `requested_campaign_id ${campaignSummary.requested_campaign_id || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerCampaignEditor?.appendChild(
      createListCard({
        title: customerState.selectedCampaignId ? `当前编辑 ${customerState.selectedCampaignId}` : "Campaign 编辑器",
        score: customerState.selectedCampaignId ? "editing" : "new_draft",
        body: customerState.selectedCampaignId
          ? "修改当前 campaign 后可继续保存 Draft，或直接再次提交送审。"
          : "填写标题、ICP、CTA、proof bundle、disclosure 和渠道后，可以先保存 Draft，再提交送审。",
      })
    );
    if (!campaigns.length) {
      clearNode(dom.customerCampaignList, "当前还没有 campaign。先在上面的表单里保存一个 Draft。");
    } else {
      campaigns.forEach((detail) => {
        const campaign = detail?.campaign || {};
        const card = createListCard({
          title: campaign.title || campaign.campaign_id || "campaign",
          score: campaign.activation_status || "draft",
          body: [
            `campaign_id ${campaign.campaign_id || "-"}`,
            `target_icp_vertical ${campaign.target_icp_vertical || "-"}`,
            `channels ${(campaign.selected_channels_json || []).join(" / ") || "-"}`,
          ].join("\n"),
          active: customerState.selectedCampaignId === campaign.campaign_id,
        });
        card.addEventListener("click", () => {
          loadCampaignIntoEditor(detail);
          renderCustomerSurface(customerState.workspacePayload || payload);
        });
        dom.customerCampaignList?.appendChild(card);
      });
    }

    dom.customerAccountSummary?.appendChild(
      createListCard({
        title: customer.display_name || customer.account_id || "客户账户",
        score: _accountScore(lifecycle),
        body: [
          `customer_account_id ${customer.customer_account_id || "-"}`,
          `account_id ${customer.account_id || "-"}`,
          `plan ${plan.display_name || plan.plan_id || "-"}`,
          `renewal_due_at ${lifecycle.renewal_due_at || "-"}`,
          `renewal_risk ${lifecycle.renewal_risk || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerAccountSummary?.appendChild(
      createListCard({
        title: "续费 / 风险自动化",
        score: renewalSummary.status || "stable",
        body: [
          `renewal_due_at ${renewalSummary.renewal_due_at || "-"}`,
          `renewal_risk ${renewalSummary.renewal_risk || "-"}`,
          `churn_risk ${churnRiskSummary.risk_level || "-"} / ${churnRiskSummary.status || "-"}`,
          `open_disputes ${churnRiskSummary.open_disputes || 0} · open_support_cases ${churnRiskSummary.open_support_cases || 0}`,
        ].join("\n"),
      })
    );

    dom.customerPlanSummary?.appendChild(
      createListCard({
        title: "套餐与定价",
        score: plan.display_name || plan.plan_id || "-",
        body: [
          `subscription_tier ${plan.subscription_tier || "-"}`,
          `monthly_price_usd ${plan.monthly_price_usd ?? "-"}`,
          `invoice_due_usd ${invoicePreview.total_due_usd ?? 0}`,
          `credits_applied_usd ${invoicePreview.credits_applied_usd ?? 0}`,
        ].join("\n"),
      })
    );

    dom.customerPlanSummary?.appendChild(
      createListCard({
        title: "Pilot Conversion / Expansion",
        score: pilotConversionSummary.status || "watch",
        body: [
          `validated_billable_count ${pilotConversionSummary.validated_billable_count || 0}`,
          `active_campaign_count ${pilotConversionSummary.active_campaign_count || 0}`,
          `upgrade_recommendation ${expansionSummary.recommended_plan_id || "-"}`,
          `expansion_status ${expansionSummary.status || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerBillingSummary?.appendChild(
      createListCard({
        title: "结算资料",
        score: billingProfile.status || "not_configured",
        body: [
          `provider ${billingProfile.provider || "-"}`,
          `invoice_email ${billingProfile.invoice_email || "-"}`,
          `legal_name ${billingProfile.legal_name || "-"}`,
          `billing_country ${billingProfile.billing_country || "-"}`,
          `tax_status ${billingProfile.tax_status || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerBillingSummary?.appendChild(
      createListCard({
        title: "Dunning / 催缴",
        score: dunningSummary.status || "clear",
        body: [
          `current_step ${dunningSummary.current_step || "-"}`,
          `invoice_id ${dunningSummary.invoice_id || "-"}`,
          `invoice_due_usd ${dunningSummary.invoice_due_usd ?? 0}`,
          `retry_count ${dunningSummary.retry_count || 0}`,
        ].join("\n"),
      })
    );

    dom.customerLimitSummary?.appendChild(
      createListCard({
        title: "账户限额",
        score: limits.is_over_limit ? "over_limit" : "within_limit",
        body: _limitBody(limits),
      })
    );

    dom.customerLimitSummary?.appendChild(
      createListCard({
        title: "升级建议",
        score: expansionSummary.status || "clear",
        body: [
          `trigger_type ${expansionSummary.trigger_type || "-"}`,
          `active_overage_flag_count ${expansionSummary.active_overage_flag_count || 0}`,
          `invoice_due_usd ${expansionSummary.invoice_due_usd ?? 0}`,
          `recommended_plan_id ${expansionSummary.recommended_plan_id || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerQualitySummary?.appendChild(
      createListCard({
        title: "质量摘要",
        score: `${qualitySummary.event_count || 0} events`,
        body: [
          `open_review_case_count ${qualitySummary.open_review_case_count || 0}`,
          `blocked_event_count ${qualitySummary.blocked_event_count || 0}`,
          `review_required_event_count ${qualitySummary.review_required_event_count || 0}`,
          `top_reason_codes ${((qualitySummary.top_reason_codes || []).map((item) => item.reason_code).join(" / ")) || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerPartnerPerformance?.appendChild(
      createListCard({
        title: "Channel / Partner Performance",
        score: `${Object.keys(partnerPerformance.partner_mix || {}).length} partner states`,
        body: [
          `channel_mix ${Object.entries(partnerPerformance.channel_mix || {}).map(([key, value]) => `${key}:${value}`).join(" / ") || "-"}`,
          `partner_mix ${Object.entries(partnerPerformance.partner_mix || {}).map(([key, value]) => `${key}:${value}`).join(" / ") || "-"}`,
          `allowlisted_channels ${(partnerPerformance.allowlisted_channels || []).join(" / ") || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerGroundednessSummary?.appendChild(
      createListCard({
        title: "Groundedness 摘要",
        score: formatPercent(groundednessSummary.pass_rate || 0),
        body: [
          `weak_count ${groundednessSummary.weak_count || 0}`,
          `failed_count ${groundednessSummary.failed_count || 0}`,
          `unsupported_claim_count ${groundednessSummary.unsupported_claim_count || 0}`,
        ].join("\n"),
      })
    );

    dom.customerReceiptSummary?.appendChild(
      createListCard({
        title: "回执摘要",
        score: `${receiptSummary.receipt_count || 0} receipts`,
        body: [
          `incident_count ${receiptSummary.incident_count || 0}`,
          `providers ${Object.keys(receiptSummary.by_provider || {}).join(" / ") || "-"}`,
          `surfaces ${Object.keys(receiptSummary.by_surface || {}).join(" / ") || "-"}`,
        ].join("\n"),
      })
    );

    dom.customerHandoffSummary?.appendChild(
      createListCard({
        title: "Presented / Handoff / Conversion",
        score: `${handoffSummary.validated_conversion_count || 0} conversions`,
        body: [
          `validated_presented ${handoffSummary.validated_presented_count || 0} · usd ${_lineAmount(lineItems, "validated_presented")}`,
          `validated_handoff ${handoffSummary.validated_handoff_count || 0} · usd ${_lineAmount(lineItems, "validated_handoff")}`,
          `validated_conversion ${handoffSummary.validated_conversion_count || 0} · usd ${_lineAmount(lineItems, "validated_conversion")}`,
        ].join("\n"),
      })
    );

    dom.customerDisputeSummary?.appendChild(
      createListCard({
        title: "Dispute 摘要",
        score: `${disputeSummary.dispute_count || 0} disputes`,
        body: `status_counts ${Object.entries(disputeSummary.status_counts || {}).map(([key, value]) => `${key}:${value}`).join(" / ") || "-"}`,
      })
    );

    if (!disputes.length) {
      clearNode(dom.customerDisputeList, "当前没有 disputes。");
    } else {
      disputes.forEach((item) => {
        dom.customerDisputeList?.appendChild(
          createListCard({
            title: item.dispute_reason_code || item.dispute_id || "dispute",
            score: item.status || "-",
            body: [
              `billable_event_id ${item.billable_event_id || "-"}`,
              `requested_amount_usd ${item.requested_amount_usd ?? 0}`,
              `resolved_amount_usd ${item.resolved_amount_usd ?? 0}`,
            ].join("\n"),
          })
        );
      });
    }

    dom.customerSupportSummary?.appendChild(
      createListCard({
        title: "Support 摘要",
        score: `${supportSummary.case_count || 0} cases`,
        body: `status_counts ${Object.entries(supportSummary.status_counts || {}).map(([key, value]) => `${key}:${value}`).join(" / ") || "-"}`,
      })
    );

    if (!supportCases.length) {
      clearNode(dom.customerSupportList, "当前没有 support cases。");
    } else {
      supportCases.forEach((item) => {
        dom.customerSupportList?.appendChild(
          createListCard({
            title: item.subject || item.support_case_id || "support_case",
            score: item.status || "-",
            body: [
              `case_type ${item.case_type || "-"}`,
              `priority ${item.priority || "-"}`,
              `billable_event_id ${item.billable_event_id || "-"}`,
            ].join("\n"),
          })
        );
      });
    }

    if (!latestTraces.length) {
      clearNode(dom.customerLatestTraces, "当前还没有可展示的质量 trace。");
    } else {
      latestTraces.forEach((item) => {
        dom.customerLatestTraces?.appendChild(
          createListCard({
            title: item.trace_id || "trace",
            score: item.status || "-",
            body: [
              `surface ${item.source_surface || "-"}`,
              `overall_score ${item.overall_score ?? "-"}`,
              `grounding_status ${item.grounding_status || "-"}`,
            ].join("\n"),
          })
        );
      });
    }

    dom.customerExportSummary?.appendChild(
      createListCard({
        title: "导出",
        score: "export_ready",
        body: [
          `available ${((payload.exports || {}).available_reports || []).join(" / ")}`,
          `invoice_due_usd ${invoicePreview.total_due_usd ?? 0}`,
        ].join("\n"),
      })
    );

    if (dom.customerWorkspaceNote) {
      dom.customerWorkspaceNote.textContent = "这个工作台只展示客户安全字段：账户、续费 / 催缴 / 升级建议、计费、质量摘要、groundedness、回执和 handoff / conversion，不暴露 Ops 原始审阅面板。";
    }
  }

  async function refreshCustomerSurface() {
    if (!_canViewCustomerWorkspace()) {
      _renderEmpty("客户工作台仅对 customer / reviewer / ops / admin 开放。");
      return;
    }
    if (!_token()) {
      _renderEmpty("登录后，这里会显示客户账户、质量摘要、回执和 invoice preview。");
      return;
    }
    try {
      const payload = await api("/v1/customer/workspace", {
        headers: _headers(),
      });
      if (!customerState.selectedCampaignId && payload?.campaign_details?.length) {
        loadCampaignIntoEditor(payload.campaign_details[0]);
      }
      renderCustomerSurface(payload);
    } catch (error) {
      customerState.workspacePayload = null;
      const detail = parseErrorDetail(error);
      _renderEmpty("客户工作台暂时无法加载，请先确认账号角色和账户数据。");
      reportUiMessage(`客户工作台刷新失败：${detail?.reason || error.message}`, "warning");
    }
  }

  async function saveCustomerCampaignDraft() {
    if (!_token()) {
      reportUiMessage("请先登录后再保存 campaign。", "warning");
      return;
    }
    try {
      const payload = await api("/v1/customer/campaigns", {
        method: "POST",
        headers: _headers(),
        body: JSON.stringify(_campaignFormPayload()),
      });
      loadCampaignIntoEditor(payload);
      reportUiMessage("Campaign draft 已保存。", "success");
      await refreshCustomerSurface();
    } catch (error) {
      reportUiMessage(`保存 campaign 失败：${error.message}`, "error");
    }
  }

  async function submitCustomerCampaignReview() {
    if (!_token()) {
      reportUiMessage("请先登录后再提交送审。", "warning");
      return;
    }
    const campaignId = (dom.customerCampaignId?.value || "").trim();
    if (!campaignId) {
      reportUiMessage("请先保存 Draft，再提交送审。", "warning");
      return;
    }
    try {
      await api(`/v1/customer/campaigns/${encodeURIComponent(campaignId)}/submit`, {
        method: "POST",
        headers: _headers(),
        body: JSON.stringify({}),
      });
      reportUiMessage("Campaign 已提交送审，Ops review hub 会看到这条激活申请。", "success");
      await refreshCustomerSurface();
    } catch (error) {
      reportUiMessage(`提交送审失败：${error.message}`, "error");
    }
  }

  async function submitCustomerDispute() {
    if (!_token()) {
      reportUiMessage("请先登录后再提交 dispute。", "warning");
      return;
    }
    try {
      await api("/v1/customer/disputes", {
        method: "POST",
        headers: _headers(),
        body: JSON.stringify({
          billable_event_id: (dom.customerDisputeBillableEventId?.value || "").trim() || null,
          dispute_reason_code: (dom.customerDisputeReason?.value || "").trim(),
          requested_amount_usd: Number(dom.customerDisputeAmount?.value || 0),
          note: (dom.customerDisputeNote?.value || "").trim() || null,
        }),
      });
      reportUiMessage("Dispute 已提交。", "success");
      await refreshCustomerSurface();
    } catch (error) {
      reportUiMessage(`提交 dispute 失败：${error.message}`, "error");
    }
  }

  async function submitCustomerSupportCase() {
    if (!_token()) {
      reportUiMessage("请先登录后再提交 support case。", "warning");
      return;
    }
    try {
      await api("/v1/customer/support", {
        method: "POST",
        headers: _headers(),
        body: JSON.stringify({
          subject: (dom.customerSupportSubject?.value || "").trim(),
          description: (dom.customerSupportDescription?.value || "").trim(),
          priority: (dom.customerSupportPriority?.value || "medium").trim() || "medium",
        }),
      });
      reportUiMessage("Support case 已提交。", "success");
      await refreshCustomerSurface();
    } catch (error) {
      reportUiMessage(`提交 support case 失败：${error.message}`, "error");
    }
  }

  async function exportCustomerWorkspaceReport(reportType) {
    if (!_token()) {
      reportUiMessage("请先登录后再导出客户报告。", "warning");
      return;
    }
    try {
      const payload = await api(`/v1/customer/exports/${encodeURIComponent(reportType)}`, {
        headers: _headers(),
      });
      if (payload.content_type === "application/json") {
        downloadJsonFile(payload.filename || `${reportType}.json`, payload.content || {});
      } else if (payload.content_base64) {
        downloadBase64File(payload.filename || `${reportType}.bin`, payload.content_base64, payload.content_type || "application/octet-stream");
      } else {
        downloadTextFile(payload.filename || `${reportType}.txt`, payload.content || "", payload.content_type || "text/plain");
      }
      reportUiMessage(`已导出 ${payload.filename || reportType}。`, "success");
    } catch (error) {
      reportUiMessage(`导出失败：${error.message}`, "error");
    }
  }

  function bindCustomerWorkspaceEvents() {
    dom.customerRefresh?.addEventListener("click", async () => {
      await refreshCustomerSurface();
    });
    dom.customerExportJson?.addEventListener("click", async () => {
      await exportCustomerWorkspaceReport("workspace_json");
    });
    dom.customerExportCsv?.addEventListener("click", async () => {
      await exportCustomerWorkspaceReport("workspace_csv");
    });
    dom.customerExportPdf?.addEventListener("click", async () => {
      await exportCustomerWorkspaceReport("workspace_pdf");
    });
    dom.customerExportInvoiceCsv?.addEventListener("click", async () => {
      await exportCustomerWorkspaceReport("invoice_csv");
    });
    dom.customerCampaignSave?.addEventListener("click", async () => {
      await saveCustomerCampaignDraft();
    });
    dom.customerCampaignSubmit?.addEventListener("click", async () => {
      await submitCustomerCampaignReview();
    });
    dom.customerDisputeSubmit?.addEventListener("click", async () => {
      await submitCustomerDispute();
    });
    dom.customerSupportSubmit?.addEventListener("click", async () => {
      await submitCustomerSupportCase();
    });
  }

  function initializeCustomerWorkspaceRuntime() {
    bindCustomerWorkspaceEvents();
  }

  return {
    initializeCustomerWorkspaceRuntime,
    refreshCustomerSurface,
    renderCustomerSurface,
    exportCustomerWorkspaceReport,
    loadCampaignIntoEditor,
    saveCustomerCampaignDraft,
    submitCustomerCampaignReview,
    submitCustomerDispute,
    submitCustomerSupportCase,
  };
})();
