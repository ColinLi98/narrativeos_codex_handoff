// Agent Studio interactive workbench runtime.

var AgentStudioRuntime = (() => {
  const dom = AgentStudioDOM;
  const {
    api,
    clearNode,
    reportUiMessage,
    setBusy,
    downloadTextFile,
    formatTimestamp,
  } = UIShared;

  const QUICK_INTENTS = [
    "增加反转",
    "增加细节",
    "增加对白",
    "放慢节奏",
    "推进关系",
    "制造误会",
    "加强悬疑",
    "不要收束",
  ];

  let initialized = false;
  let currentChapterIndex = null;
  let activeChoicePayload = null;
  let originalAuthorRefresh = null;
  const NOSBOOK_CONTENT_TYPE = "application/vnd.narrativeos.nosbook+json";

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function clampLabel(value, fallback = "新的走向") {
    const normalized = String(value || "").trim();
    return normalized ? normalized.slice(0, 28) : fallback;
  }

  function activeAccountId() {
    const identity = authorState.authorAuthSession?.identity || {};
    return (
      identity.account_id ||
      identity.actor_id ||
      AuthorDOM.authorAccountId?.value?.trim?.() ||
      "web_author"
    );
  }

  function ensureAgentStudioState() {
    if (!authorState.agentStudio) {
      authorState.agentStudio = { quickIntents: QUICK_INTENTS };
    }
    return authorState.agentStudio;
  }

  function chapters() {
    return [...(authorState.activeWorkDetail?.chapters || [])].sort(
      (left, right) => Number(left.chapter_index || 0) - Number(right.chapter_index || 0)
    );
  }

  function selectedChapter() {
    const list = chapters();
    if (!list.length) return null;
    if (!currentChapterIndex || !list.some((item) => Number(item.chapter_index) === Number(currentChapterIndex))) {
      currentChapterIndex = Number(list[list.length - 1].chapter_index || 0);
    }
    return list.find((item) => Number(item.chapter_index) === Number(currentChapterIndex)) || list[list.length - 1];
  }

  function routeName(branch, index) {
    if (index === 0 || branch.branch_kind === "mainline") return "主线";
    const letter = String.fromCharCode("A".charCodeAt(0) + Math.max(0, index - 1));
    return `路线 ${letter}：${clampLabel(branch.branch_origin_label || branch.branch_name)}`;
  }

  function setGenerationStatus(message, kind = "info", detail = "") {
    const state = ensureAgentStudioState();
    const previous = state.generationStatus || {};
    state.generationStatus = message
      ? {
          kind,
          message,
          detail,
          startedAt:
            previous.message === message && previous.kind === kind
              ? previous.startedAt || new Date().toISOString()
              : new Date().toISOString(),
        }
      : null;
    if (!dom.generationStatus) return;
    dom.generationStatus.innerHTML = message
      ? `<strong>${escapeHtml(message)}</strong>${detail ? `<span>${escapeHtml(detail)}</span>` : ""}`
      : "";
    dom.generationStatus.dataset.kind = kind;
    dom.generationStatus.classList.toggle("is-hidden", !message);
  }

  function productQualitySummary() {
    const diagnostics = authorState.activeWorkDetail?.diagnostics_summary || {};
    const decision = String(diagnostics.latest_decision || diagnostics?.evaluation_summary?.decision || "pass");
    const needsAttention = decision && decision !== "pass" && decision !== "approved";
    const chaptersCount = Number(authorState.activeWorkDetail?.chapter_count || 0);
    return [
      ["重复感", needsAttention ? "需留意" : "良好"],
      ["场景细节", chaptersCount ? "充足" : "待生成"],
      ["节奏", needsAttention ? "需观察" : "稳定"],
      ["结尾风险", needsAttention ? "偏高" : "正常"],
    ];
  }

  function renderQuality() {
    if (!dom.quality) return;
    clearNode(dom.quality);
    for (const [label, value] of productQualitySummary()) {
      const item = document.createElement("div");
      item.className = "agent-studio-quality-item";
      item.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
      dom.quality.appendChild(item);
    }
  }

  function renderChapters() {
    if (!dom.chapters) return;
    const list = chapters();
    clearNode(dom.chapters, list.length ? "" : "还没有章节，先生成第一章。");
    list.forEach((chapter) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `agent-studio-chapter-link${Number(chapter.chapter_index) === Number(currentChapterIndex) ? " is-active" : ""}`;
      button.innerHTML = `<span>第 ${Number(chapter.chapter_index || 0)} 章</span><strong>${escapeHtml(chapter.chapter_title || "未命名章节")}</strong>`;
      button.addEventListener("click", () => {
        currentChapterIndex = Number(chapter.chapter_index || 0);
        render();
      });
      dom.chapters.appendChild(button);
    });
  }

  function renderBranches() {
    const family = authorState.activeWorkDetail?.branch_family || [];
    if (!dom.branches) return;
    clearNode(dom.branches, family.length ? "" : "还没有分支路线。");
    if (dom.branchRouteSelect) {
      dom.branchRouteSelect.innerHTML = "";
    }
    family.forEach((branch, index) => {
      const name = routeName(branch, index);
      const card = document.createElement("article");
      card.className = `agent-studio-route-card${branch.is_active_line ? " is-active" : ""}`;
      card.innerHTML = `
        <div>
          <strong>${escapeHtml(name)}</strong>
          <span>${Number(branch.chapter_count || 0)} 章 · 最近选择：${escapeHtml(branch.branch_origin_label || "持续主线")}</span>
        </div>
        <button class="ghost-action" type="button">${branch.is_active_line ? "导出主线" : "切换"}</button>
      `;
      card.querySelector("button")?.addEventListener("click", async () => {
        if (branch.is_active_line) return;
        await activateRoute(branch.work_id);
      });
      dom.branches.appendChild(card);
      if (dom.branchRouteSelect) {
        const option = document.createElement("option");
        option.value = branch.work_id;
        option.textContent = name;
        option.selected = Boolean(branch.is_active_line);
        dom.branchRouteSelect.appendChild(option);
      }
    });
  }

  function renderChoices(chapter) {
    if (!dom.choiceCards) return;
    const choices = chapter?.choices || chapter?.choices_json || [];
    const impacts = chapter?.choice_impacts || [];
    clearNode(dom.choiceCards, choices.length ? "" : "本章暂时没有下一步选择，可以直接写导演意图。");
    choices.forEach((choiceText, index) => {
      const impact = impacts[index] || {};
      const card = document.createElement("article");
      card.className = "agent-studio-choice-card";
      card.innerHTML = `
        <div class="agent-studio-choice-main">
          <strong>${escapeHtml(impact.label || choiceText || "继续推进")}</strong>
          <p>${escapeHtml(impact.expected_effect || "会改变下一章的推进重点。")}</p>
        </div>
        <div class="agent-studio-choice-tags">
          <span>风险：${escapeHtml(impact.risk_level || "中")}</span>
          <span>情感：${escapeHtml(impact.emotion || "波动")}</span>
          <span>节奏：${escapeHtml(impact.pacing || "推进")}</span>
          <span>关系：${escapeHtml(impact.relationship || "拉扯")}</span>
          <span>悬疑：${escapeHtml(impact.mystery || "维持")}</span>
        </div>
        <button class="primary-action" type="button">选择这条走向</button>
      `;
      card.querySelector("button")?.addEventListener("click", () => selectChoice(choiceText, impact));
      dom.choiceCards.appendChild(card);
    });
  }

  function renderReader() {
    const chapter = selectedChapter();
    const list = chapters();
    const activeIndex = list.findIndex((item) => Number(item.chapter_index) === Number(chapter?.chapter_index));
    if (dom.readerTitle) {
      dom.readerTitle.textContent = chapter?.chapter_title || "等待第一章";
    }
    if (dom.readerBody) {
      dom.readerBody.innerHTML = chapter?.body
        ? String(chapter.body)
            .split(/\n{2,}/)
            .map((para) => `<p>${escapeHtml(para)}</p>`)
            .join("")
        : "<p>设定故事目标后，第一章会出现在这里。</p>";
    }
    if (dom.readerProgress) {
      dom.readerProgress.textContent = chapter
        ? `第 ${Number(chapter.chapter_index || 0)} 章 / ${Number(authorState.activeWorkDetail?.target_chapter_count || list.length || 1)} 章`
        : "尚未开始";
    }
    if (dom.readerFeedback) {
      const title = chapter ? `第 ${Number(chapter.chapter_index || 0)} 章已完成` : "等待章节生成";
      const focus = chapter ? "本章强化了：人物冲突、场景细节" : "先填写创作启动页。";
      const next = chapter ? "下一章建议：继续追查 / 转入关系冲突 / 开启新分支" : "准备好后开始生成第一章。";
      dom.readerFeedback.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(focus)}</span><span>${escapeHtml(next)}</span>`;
    }
    if (dom.chapterPrev) {
      dom.chapterPrev.disabled = activeIndex <= 0;
      dom.chapterPrev.onclick = () => {
        if (activeIndex > 0) {
          currentChapterIndex = Number(list[activeIndex - 1].chapter_index || 0);
          render();
        }
      };
    }
    if (dom.chapterNext) {
      dom.chapterNext.disabled = activeIndex < 0 || activeIndex >= list.length - 1;
      dom.chapterNext.onclick = () => {
        if (activeIndex >= 0 && activeIndex < list.length - 1) {
          currentChapterIndex = Number(list[activeIndex + 1].chapter_index || 0);
          render();
        }
      };
    }
    renderChoices(chapter);
  }

  function renderWorkbench() {
    const hasWork = Boolean(authorState.activeWorkDetail?.work_id || authorState.activeWorkId);
    dom.start?.classList.toggle("is-hidden", hasWork);
    dom.workbench?.classList.toggle("is-hidden", !hasWork);
    if (!hasWork) return;
    if (dom.workTitle) dom.workTitle.textContent = authorState.activeWorkDetail?.title || "未命名作品";
    if (dom.workMeta) {
      dom.workMeta.textContent = `${Number(authorState.activeWorkDetail?.chapter_count || 0)} 章 · ${authorState.activeWorkDetail?.branch_name || "主线"}`;
    }
    renderChapters();
    renderBranches();
    renderReader();
    renderQuality();
  }

  function render() {
    renderWorkbench();
  }

  async function refreshStudio() {
    if (typeof AuthorWorkspaceRuntime?.refreshAuthorSurface === "function") {
      await AuthorWorkspaceRuntime.refreshAuthorSurface();
    }
    render();
  }

  function setBriefFieldsFromStartup() {
    const title = String(dom.title?.value || "").trim() || "未命名作品";
    const genre = String(dom.genre?.value || "urban_mystery");
    const readerGoal = String(dom.readerGoal?.value || "").trim();
    const lengthGoal = String(dom.length?.value || "").trim();
    const remixAllowed = dom.remix?.checked ? "允许读者二创。" : "不允许读者二创。";
    if (AuthorDOM.authorWorldTitle) AuthorDOM.authorWorldTitle.value = title;
    if (AuthorDOM.authorGenrePreset && genre !== "custom") AuthorDOM.authorGenrePreset.value = genre;
    if (AuthorDOM.authorLifeTheme) AuthorDOM.authorLifeTheme.value = readerGoal || "让读者持续想知道下一章会怎样";
    if (AuthorDOM.authorCorePremise) {
      AuthorDOM.authorCorePremise.value = [
        `作品标题：${title}`,
        `读者体验目标：${readerGoal || "稳定追更"}`,
        `长度目标：${lengthGoal || "短篇"}`,
        remixAllowed,
      ].join("\n");
    }
  }

  async function startStudio() {
    const releaseBusy = dom.startButton ? setBusy(dom.startButton, "正在启动…") : null;
    setGenerationStatus("第一章生成中", "pending", "正在建立作品设定、人物冲突和章节正文，可能需要一两分钟。");
    try {
      setBriefFieldsFromStartup();
      const accountId = activeAccountId();
      const brief = AuthorWorkspaceRuntime.buildAuthorBriefPayload
        ? AuthorWorkspaceRuntime.buildAuthorBriefPayload()
        : {
            genre_preset: String(dom.genre?.value || "urban_mystery"),
            world_title: String(dom.title?.value || "未命名作品"),
            core_premise: String(AuthorDOM.authorCorePremise?.value || ""),
            life_theme: String(AuthorDOM.authorLifeTheme?.value || ""),
            author_id: accountId,
            account_id: accountId,
          };
      const draft = await api("/v1/author/drafts/from-brief", {
        method: "POST",
        body: JSON.stringify({ brief: { ...brief, author_id: accountId, account_id: accountId }, account_id: accountId }),
      });
      authorState.activeDraftVersionId = draft.world_version_id;
      authorState.activeDraftDetail = await api(`/v1/author/drafts/${encodeURIComponent(draft.world_version_id)}`);
      const work = await api("/v1/author/works", {
        method: "POST",
        body: JSON.stringify({ world_version_id: draft.world_version_id, account_id: accountId }),
      });
      authorState.activeWorkId = work.work_id;
      try {
        authorState.activeWorkDetail = await api(`/v1/author/works/${encodeURIComponent(work.work_id)}/chapters/generate`, {
          method: "POST",
          body: JSON.stringify({ mode: "first", account_id: accountId }),
        });
      } catch (error) {
        authorState.activeWorkDetail = await api(`/v1/author/works/${encodeURIComponent(work.work_id)}`);
        reportUiMessage(`第一章暂时没有入库：${error.message}`, "warning");
      }
      currentChapterIndex = Number(authorState.activeWorkDetail?.active_chapter_index || authorState.activeWorkDetail?.chapter_count || 0) || null;
      setGenerationStatus("第 1 章已完成。", "success", "本章已加入当前路线，可以继续阅读或选择下一步。");
      render();
    } catch (error) {
      setGenerationStatus("启动失败，请检查账号权限后重试。", "error", "当前作品草稿已尽量保留，可以稍后重试。");
      reportUiMessage(`Agent Studio 启动失败：${error.message}`, "error");
    } finally {
      releaseBusy?.();
    }
  }

  async function activateRoute(workId) {
    const normalized = String(workId || "").trim();
    if (!normalized) return;
    setGenerationStatus("正在切换路线。", "pending", "阅读器会切到这条路线的最新章节。");
    const accountId = activeAccountId();
    const payload = await api(`/v1/author/works/${encodeURIComponent(normalized)}/activate-line`, {
      method: "POST",
      body: JSON.stringify({ account_id: accountId }),
    });
    authorState.activeWorkId = payload.work_id || normalized;
    authorState.activeWorkDetail = payload;
    currentChapterIndex = Number(payload.active_chapter_index || payload.chapter_count || currentChapterIndex || 0) || null;
    setGenerationStatus("路线已切换。", "success", "当前路线已成为导出主线。");
    render();
  }

  async function createBranchFromIntent(intentText) {
    const intent = String(intentText || "").trim();
    const chapter = selectedChapter();
    if (!authorState.activeWorkId || !chapter || !intent) return null;
    const sourceChapterIndex = Number(chapter.chapter_index || 0);
    if (!sourceChapterIndex) return null;
    const payload = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/branches`, {
      method: "POST",
      body: JSON.stringify({
        source_chapter_index: sourceChapterIndex,
        label: clampLabel(intent),
        choice_source: activeChoicePayload?.label || intent,
        account_id: activeAccountId(),
        steering_directive: {
          current_user_intent: intent,
          summary: intent,
        },
      }),
    });
    authorState.activeWorkId = payload.work_id;
    authorState.activeWorkDetail = payload;
    currentChapterIndex = Number(payload.active_chapter_index || payload.chapter_count || sourceChapterIndex || 0);
    return payload;
  }

  async function generateNextChapter() {
    if (!authorState.activeWorkId) {
      reportUiMessage("请先从创作启动页创建作品。", "warning");
      return;
    }
    const releaseBusy = dom.generateButton ? setBusy(dom.generateButton, "生成中…") : null;
    const intent = String(dom.directorIntent?.value || "").trim();
    setGenerationStatus("续写中", "pending", "正在沿导演意图推进下一章，完成后会自动跳到新章节。");
    try {
      if (intent) {
        await createBranchFromIntent(intent);
      }
      const mode = Number(authorState.activeWorkDetail?.chapter_count || 0) > 0 ? "next" : "first";
      authorState.activeWorkDetail = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/chapters/generate`, {
        method: "POST",
        body: JSON.stringify({ mode, account_id: activeAccountId() }),
      });
      currentChapterIndex = Number(authorState.activeWorkDetail?.active_chapter_index || authorState.activeWorkDetail?.chapter_count || 0) || currentChapterIndex;
      dom.directorIntent.value = "";
      activeChoicePayload = null;
      setGenerationStatus(`第 ${currentChapterIndex || ""} 章已完成。`, "success", "新章节已加入当前路线，下一步选择也已更新。");
      render();
    } catch (error) {
      setGenerationStatus("续写失败，当前路线已保留。", "error", "可以调整导演意图后重试。");
      reportUiMessage(`续写失败：${error.message}`, "error");
    } finally {
      releaseBusy?.();
    }
  }

  function selectChoice(choiceText, impact) {
    activeChoicePayload = { choiceText, ...impact };
    if (dom.directorIntent) {
      dom.directorIntent.value = impact.director_intent_prefill || `沿着「${choiceText}」继续。`;
    }
    generateNextChapter();
  }

  async function createBranchOnly() {
    const intent = String(dom.directorIntent?.value || "").trim();
    if (!intent) {
      reportUiMessage("先写一句导演意图，再开新路线。", "warning");
      return;
    }
    const releaseBusy = dom.branchButton ? setBusy(dom.branchButton, "开分支…") : null;
    setGenerationStatus("新路线创建中", "pending", "正在从当前章节保存分支。");
    try {
      await createBranchFromIntent(intent);
      setGenerationStatus("新路线已创建。", "success", "你可以继续写这条路线，或切回主线比较。");
      render();
    } catch (error) {
      setGenerationStatus("新路线创建失败。", "error", "当前章节没有丢失，可以稍后再开路线。");
      reportUiMessage(`创建路线失败：${error.message}`, "error");
    } finally {
      releaseBusy?.();
    }
  }

  async function runValidation() {
    if (!authorState.activeWorkId) return;
    const releaseBusy = dom.validateButton ? setBusy(dom.validateButton, "校验中…") : null;
    setGenerationStatus("正在校验当前导出主线。", "pending", "正在查看重复感、场景细节、节奏和结尾风险。");
    try {
      authorState.activeWorkDetail = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/diagnostics/run`, {
        method: "POST",
        body: JSON.stringify({ account_id: activeAccountId() }),
      });
      setGenerationStatus(`校验完成：${formatTimestamp(new Date().toISOString())}`, "success", "质量状态已刷新。");
      render();
    } catch (error) {
      setGenerationStatus("校验失败。", "error", "当前章节和路线仍然保留。");
      reportUiMessage(`校验失败：${error.message}`, "error");
    } finally {
      releaseBusy?.();
    }
  }

  async function exportNosbook() {
    if (!authorState.activeWorkId) return;
    const releaseBusy = dom.exportButton ? setBusy(dom.exportButton, "导出中…") : null;
    try {
      const payload = await api(`/v1/author/works/${encodeURIComponent(authorState.activeWorkId)}/export?format=nosbook&route=active`);
      ensureAgentStudioState().lastNosbookExport = {
        filename: payload.filename || "narrativeos-work.nosbook",
        contentType: NOSBOOK_CONTENT_TYPE,
        payload,
      };
      downloadTextFile(
        payload.filename || "narrativeos-work.nosbook",
        JSON.stringify(payload, null, 2),
        NOSBOOK_CONTENT_TYPE
      );
      setGenerationStatus("已导出当前主线。", "success", ".nosbook 已按当前导出主线生成。");
    } catch (error) {
      reportUiMessage(`导出失败：${error.message}`, "error");
    } finally {
      releaseBusy?.();
    }
  }

  function installAuthorRefreshHook() {
    if (originalAuthorRefresh || typeof AuthorWorkspaceRuntime?.refreshAuthorSurface !== "function") return;
    originalAuthorRefresh = AuthorWorkspaceRuntime.refreshAuthorSurface;
    AuthorWorkspaceRuntime.refreshAuthorSurface = async (...args) => {
      const result = await originalAuthorRefresh(...args);
      render();
      return result;
    };
  }

  function bindEvents() {
    dom.startButton?.addEventListener("click", startStudio);
    dom.advancedButton?.addEventListener("click", () => {
      WorkspaceLayoutRuntime.setAuthorWorkspace("brief");
      ShellStatusRuntime.syncProductMode();
    });
    dom.generateButton?.addEventListener("click", generateNextChapter);
    dom.branchButton?.addEventListener("click", createBranchOnly);
    dom.validateButton?.addEventListener("click", runValidation);
    dom.previewButton?.addEventListener("click", () => {
      currentChapterIndex = Number(authorState.activeWorkDetail?.chapter_count || currentChapterIndex || 0) || null;
      render();
    });
    dom.exportButton?.addEventListener("click", exportNosbook);
    dom.branchRouteSelect?.addEventListener("change", () => activateRoute(dom.branchRouteSelect.value));
    dom.quickButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const intent = String(button.dataset.agentStudioIntent || button.textContent || "").trim();
        const existing = String(dom.directorIntent?.value || "").trim();
        dom.directorIntent.value = existing ? `${existing}；${intent}` : intent;
      });
    });
  }

  function initializeAgentStudioRuntime() {
    if (initialized) return;
    initialized = true;
    if (!dom.shell) return;
    ensureAgentStudioState();
    installAuthorRefreshHook();
    bindEvents();
    render();
  }

  installAuthorRefreshHook();

  return {
    initializeAgentStudioRuntime,
    render,
    refreshStudio,
    QUICK_INTENTS,
  };
})();
