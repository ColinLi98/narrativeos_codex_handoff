// Reader shell v2. Uses the legacy Reader runtime as a data/actions adapter while replacing the visible Reader shell.

var ReaderShellV2 = (() => {
  const legacyReaderRuntime = typeof ReaderRuntime === "object" && ReaderRuntime ? ReaderRuntime : {};
  const legacyReaderDom = typeof ReaderDOM === "object" && ReaderDOM ? ReaderDOM : {};
  const shellDom = ShellDOM;
  const dom = ReaderShellV2DOM;
  const {
    api,
    clearNode,
    createListCard,
    formatTimestamp,
    reportUiMessage,
    setBusy,
  } = UIShared;
  const { tierLabel, accessReasonLabel } = ReaderAccessors;

  let readerShellV2Initialized = false;
  let readerShellV2EventsBound = false;

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function firstImageUrl(...values) {
    return values
      .map((value) => String(value || "").trim())
      .find((value) => value.startsWith("/") || value.startsWith("http://") || value.startsWith("https://")) || "";
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function readerGenerationJobId(payload) {
    return String(payload?.jobId || payload?.job_id || "").trim();
  }

  function updateReaderGenerationJob(job, phase = "") {
    if (!job) {
      readerState.readerGenerationJob = null;
      return;
    }
    readerState.readerGenerationJob = {
      jobId: readerGenerationJobId(job),
      status: String(job.status || ""),
      readerStatus: String(job.readerStatus || job.result?.reader_status || ""),
      phase,
      error: job.error || "",
      updatedAt: job.updatedAt || job.updated_at || new Date().toISOString(),
      retryable: Boolean(job.retryable),
    };
  }

  function readerGenerationPending() {
    const status = String(readerState.readerGenerationJob?.status || "");
    return status === "queued" || status === "running";
  }

  function imageMarkup(imageUrl, altText, className) {
    const safeUrl = firstImageUrl(imageUrl);
    if (!safeUrl) return "";
    return `
      <figure class="${escapeHtml(className)}">
        <img src="${escapeHtml(safeUrl)}" alt="${escapeHtml(altText)}" loading="lazy" decoding="async" />
      </figure>
    `;
  }

  function setReaderShellMode() {
    shellDom.appShell.dataset.readerShell = "v2";
  }

  function currentAccountId() {
    if (typeof legacyReaderRuntime.activeReaderId === "function") {
      return legacyReaderRuntime.activeReaderId();
    }
    return readerState.readerId || "reader_demo";
  }

  function activeReaderPaywall() {
    const latest = readerState.latestStep?.paywall || null;
    if (latest?.required) return latest;
    if (readerState.latestStepFailure?.paywall?.required) return readerState.latestStepFailure.paywall;
    if (readerState.sessionPaywall?.required) return readerState.sessionPaywall;
    return null;
  }

  function activeReaderQualityFailure() {
    if (readerState.continuityContract?.status === "quality_guard_failed" && readerState.latestStepFailure) {
      return readerState.latestStepFailure;
    }
    return null;
  }

  function currentReaderViewSource() {
    if (readerState.latestStep?.reader_view) {
      return readerState.latestStep.reader_view;
    }
    if (readerState.latestStepFailure?.reader_view) {
      return readerState.latestStepFailure.reader_view;
    }
    return null;
  }

  function readerChapterLabel(chapterIndex, fallbackTurnIndex = null) {
    const numericIndex = Number(chapterIndex || 0);
    if (numericIndex > 0) return `第 ${numericIndex} 章`;
    const numericTurnIndex = Number(fallbackTurnIndex || 0);
    if (numericTurnIndex > 0) return `Turn ${numericTurnIndex}`;
    return "序章";
  }

  function selectedStorybookReplayIndex() {
    const replayViews = readerState.replay?.reader_views || [];
    if (!replayViews.length) return null;
    if (readerState.selectedReplayIndex === null || readerState.selectedReplayIndex === undefined) {
      return replayViews.length - 1;
    }
    const requestedIndex = Number(readerState.selectedReplayIndex);
    if (Number.isInteger(requestedIndex) && requestedIndex >= 0 && requestedIndex < replayViews.length) {
      return requestedIndex;
    }
    return replayViews.length - 1;
  }

  function currentStorybookSource() {
    const replayIndex = selectedStorybookReplayIndex();
    if (replayIndex !== null) {
      return {
        readerView: readerState.replay.reader_views[replayIndex],
        renderedScene: readerState.replay.rendered_scenes?.[replayIndex] || null,
        promiseSnapshot: readerState.replay.promise_ledger_snapshots?.[replayIndex] || [],
        turnIndex: replayIndex + 1,
        selectionIndex: replayIndex,
        isPrologue: false,
      };
    }

    const latestRecord = readerState.latestStep || readerState.latestStepFailure;
    if (latestRecord?.reader_view) {
      return {
        readerView: latestRecord.reader_view,
        renderedScene: latestRecord.rendered_scene || null,
        promiseSnapshot: latestRecord.promise_ledger_snapshot || [],
        turnIndex: Number(
          readerState.replay?.event_trace?.length ||
          latestRecord.step_index ||
          latestRecord.reader_view.chapter_index ||
          1
        ),
        selectionIndex: null,
        isPrologue: false,
      };
    }

    if (readerState.sessionId && readerState.currentBundle) {
      const worldMeta = selectedWorldMeta();
      const quote = readerState.currentBundle.player_inputs?.[0]?.raw_input || "先写下你真正想做的第一件事。";
      return {
        readerView: {
          chapter_title: `${readerWorldLabel()} · 序章`,
          recap: "世界已经就位，真正的章节还没落笔。先稳住气味、代价和入口，再把第一幕推开。",
          body:
            `${readerState.currentBundle.description || "这个世界已经为你准备好了第一层情绪和第一道门槛。"}\n\n` +
            "继续前，先确认你要把自己送进什么处境。",
          relationship_hints: [worldMeta.mood, worldMeta.hook, "等待第一章"],
          chapter_index: 0,
          scene_card: {
            quote,
            summary: "先让入口动作带着情绪落地，再把真正的冲突推出来。",
            palette_hint: worldMeta.mood,
            story_beats: ["先确认要不要延续旧旅程", "把这一轮故事的入口动作写清楚", "让第一幕带着代价和悬念落下"],
            visual_details: [worldMeta.mood, "序章态", "等待第一幕"],
          },
        },
        renderedScene: null,
        promiseSnapshot: [],
        turnIndex: 0,
        selectionIndex: null,
        isPrologue: true,
      };
    }

    return null;
  }

  function storybookSequenceEntries(activeSource) {
    const replayViews = readerState.replay?.reader_views || [];
    if (replayViews.length) {
      const activeReplayIndex = activeSource?.selectionIndex ?? selectedStorybookReplayIndex();
      const startIndex = Math.max(0, replayViews.length - 6);
      return replayViews.slice(startIndex).map((item, offset) => {
        const absoluteIndex = startIndex + offset;
        return {
          chapterTitle: item.chapter_title || `章节 ${absoluteIndex + 1}`,
          recap: item.recap || "这一章暂时没有 recap。",
          chapterIndex: item.chapter_index || absoluteIndex + 1,
          turnIndex: absoluteIndex + 1,
          relationshipHints: item.relationship_hints || [],
          promiseCount: (readerState.replay.promise_ledger_snapshots?.[absoluteIndex] || []).length,
          isActive: absoluteIndex === activeReplayIndex,
          action: `jump-storybook:${absoluteIndex}`,
        };
      });
    }

    if (!activeSource?.readerView) return [];
    return [
      {
        chapterTitle: activeSource.readerView.chapter_title || "当前章节",
        recap: activeSource.readerView.recap || "当前阅读位置已经就位。",
        chapterIndex: activeSource.readerView.chapter_index || 0,
        turnIndex: activeSource.turnIndex || activeSource.readerView.chapter_index || 0,
        relationshipHints: activeSource.readerView.relationship_hints || [],
        promiseCount: (activeSource.promiseSnapshot || []).length,
        isActive: true,
        action: null,
      },
    ];
  }

  function readerWorldLabel() {
    if (readerState.currentBundle?.label) return readerState.currentBundle.label;
    if (readerState.currentBundle?.world_bible?.title) return readerState.currentBundle.world_bible.title;
    return "尚未选择世界";
  }

  function readerStatusItems() {
    const subscription = readerState.readerSubscription?.subscription || {};
    const qualityFailure = activeReaderQualityFailure();
    const paywall = activeReaderPaywall();
    const creditBalance = Number(readerState.readerSubscription?.wallets?.story_credits?.balance || readerState.readerEntitlements?.find?.((item) => item.entitlement_type === "credits" && item.status === "active")?.balance || 0);
    return [
      { label: "世界", value: readerWorldLabel() },
      { label: "旅程", value: readerState.sessionId ? `进行中` : "未创建" },
      { label: "当前视图", value: shellState.readerWorkspace === "read" ? (readerState.activeView || "experience") : "landing" },
      { label: "会员", value: subscription.tier_id ? tierLabel(subscription.tier_id) : "试读 / 未订阅" },
      { label: "故事点数", value: String(Number.isFinite(creditBalance) ? creditBalance.toFixed(0) : "-") },
      { label: "状态", value: readerGenerationPending() ? "生成中" : qualityFailure ? "quality_guard_failed" : paywall?.required ? accessReasonLabel(paywall.reason) : "ok" },
    ];
  }

  function renderStatusStrip() {
    clearNode(dom.status);
    readerStatusItems().forEach((item) => {
      const chip = document.createElement("div");
      chip.className = "status-chip reader-shell-v2__status-chip";
      chip.innerHTML = `<span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong>`;
      dom.status.appendChild(chip);
    });
  }

  function activeSessionCard() {
    if (!readerState.sessionLibrary?.length) return null;
    return (readerState.sessionLibrary || []).find((item) => item.session_id === readerState.sessionId) || readerState.sessionLibrary[0];
  }

  function activeCoverImage() {
    const session = activeSessionCard();
    return firstImageUrl(
      readerState.sessionMedia?.coverImage,
      readerState.latestStep?.coverImage,
      session?.coverImage
    );
  }

  function activeAtmosphereImage() {
    const session = activeSessionCard();
    return firstImageUrl(
      readerState.sessionMedia?.atmosphereImage,
      readerState.latestStep?.atmosphereImage,
      session?.atmosphereImage,
      activeCoverImage()
    );
  }

  function narrativeHints() {
    const readerView = currentReaderViewSource();
    return (readerView?.relationship_hints || []).filter(Boolean).slice(0, 4);
  }

  function selectedWorldMeta() {
    if (!readerState.currentBundle) {
      return {
        label: "尚未选择世界",
        mood: "等待进入",
        hook: "先挑一个世界，再开始旅程。",
      };
    }
    return worldDisplayMeta(readerState.currentBundle);
  }

  function renderReaderShellHeadline() {
    if (!dom.title || !dom.copy) return;
    if (shellState.readerWorkspace === "landing") {
      const activeSession = activeSessionCard();
      const worldMeta = selectedWorldMeta();
      dom.title.textContent = activeSession
        ? "回到那一章停下来的地方，再决定要不要把这条命继续推下去。"
        : "先挑一个世界，再把这一轮故事真正开出来。";
      dom.copy.textContent = activeSession
        ? `当前最安全的动作是继续你已经打开的那段旅程；如果不想回去，再切到 ${worldMeta.label} 重新开篇。`
        : `Reader shell v2 会先把世界、续读和解锁放到最前面。当前推荐世界是 ${worldMeta.label}，它更偏向 ${worldMeta.mood}。`;
      return;
    }
    if (readerState.activeView === "storybook") {
      dom.title.textContent = currentStorybookSource()?.readerView?.chapter_title || "图文阅读";
      dom.copy.textContent = "把章节当成一张展开的画页来读：先看引句，再看节拍与余波，最后决定下一句心意。";
      return;
    }
    if (readerState.activeView === "backstage") {
      dom.title.textContent = "幕后档案";
      dom.copy.textContent = "幕后档案只保留 Reader 真正需要的三个问题：当前章哪里最紧、下一步往哪偏、前几章留下了什么余波。";
      return;
    }
    dom.title.textContent = currentReaderViewSource()?.chapter_title || "沉浸阅读";
    dom.copy.textContent = "章节本身应该占据最大视觉权重；续写、解锁和恢复路径只在真正需要的时候出现。";
  }

  function createActionButton({ label, action, variant = "ghost-action", disabled = false }) {
    return `<button type="button" class="${variant}" data-reader-v2-action="${escapeHtml(action)}"${disabled ? " disabled" : ""}>${escapeHtml(label)}</button>`;
  }

  function renderLandingCardList(id, title, description, items, emptyText) {
    const section = document.createElement("section");
    section.id = id;
    section.className = "panel reader-shell-v2__panel reader-shell-v2__collection";
    section.innerHTML = `
      <div class="panel-head reader-shell-v2__collection-head">
        <p class="panel-label">${escapeHtml(title)}</p>
        <h3>${escapeHtml(description)}</h3>
      </div>
    `;
    const stack = document.createElement("div");
    stack.id = `${id}-list`;
    stack.className = "reader-shell-v2__collection-list";
    section.appendChild(stack);
    if (!items.length) {
      clearNode(stack, emptyText);
      return section;
    }
    items.forEach((item) => stack.appendChild(item));
    return section;
  }

  function worldCards() {
    return (readerState.examples || []).map((example) => {
      const shelfWorld = (readerState.shelfWorlds || []).find((item) => item.world_id === example.world_id) || {};
      const meta = worldDisplayMeta(example);
      const coverImage = firstImageUrl(shelfWorld.coverImage, example.coverImage);
      const card = document.createElement("article");
      card.className = "list-card reader-shell-v2__world-card";
      if (readerState.currentBundle?.example_id === example.example_id) {
        card.classList.add("is-active");
      }
      card.innerHTML = `
        ${imageMarkup(coverImage, example.label || example.world_id || "世界封面", "reader-shell-v2__card-media")}
        <div class="reader-shell-v2__eyebrow-row">
          <span class="reader-shell-v2__eyebrow">世界书架</span>
          <span class="reader-shell-v2__access">${escapeHtml(shelfWorld.access_state || "trial")}</span>
        </div>
        <div class="list-card-head">
          <h3>${escapeHtml(example.label || example.world_id)}</h3>
          <span class="list-card-score">${escapeHtml(shelfWorld.risk_rating || "PG-13")}</span>
        </div>
        <p class="list-card-body">${escapeHtml(example.description || "进入这个世界前，先看清它当前的命题和准入状态。")}</p>
        <div class="reader-shell-v2__fact-row">
          <span>${escapeHtml(meta.mood)}</span>
          <span>${escapeHtml(meta.hook)}</span>
        </div>
        <div class="reader-shell-v2__actions">
          ${createActionButton({ label: "浏览世界", action: `preview-world:${example.example_id}` })}
          ${createActionButton({ label: "开始旅程", action: `start-world:${example.example_id}`, variant: "primary-action" })}
        </div>
      `;
      return card;
    });
  }

  function sessionCards() {
    return (readerState.sessionLibrary || []).map((session) => {
      const card = document.createElement("article");
      card.className = "list-card reader-shell-v2__session-card";
      if (readerState.sessionId === session.session_id) {
        card.classList.add("is-active");
      }
      const coverImage = firstImageUrl(
        session.coverImage,
        readerState.sessionId === session.session_id ? readerState.sessionMedia?.coverImage : ""
      );
      card.innerHTML = `
        ${imageMarkup(coverImage, session.last_chapter_title || session.last_event_title || "旅程封面", "reader-shell-v2__card-media")}
        <div class="reader-shell-v2__eyebrow-row">
          <span class="reader-shell-v2__eyebrow">${escapeHtml(readerState.sessionId === session.session_id ? "当前旅程" : "可安全续读")}</span>
          <span class="reader-shell-v2__access">第 ${escapeHtml(session.current_turn_index || 0)} 幕</span>
        </div>
        <div class="list-card-head">
          <h3>${escapeHtml(session.last_chapter_title || session.last_event_title || "刚刚开始")}</h3>
          <span class="list-card-score">${escapeHtml(formatTimestamp(session.created_at))}</span>
        </div>
        <p class="list-card-body">停在你上次退出的那一章。最安全的动作是直接回去继续，而不是重新从书架开一段新旅程。</p>
        <div class="reader-shell-v2__actions">
          ${createActionButton({ label: "继续阅读", action: `resume-session:${session.session_id}`, variant: "primary-action" })}
          ${createActionButton({ label: "删除旅程", action: `delete-session:${session.session_id}` })}
        </div>
      `;
      return card;
    });
  }

  function authoredWorkCards() {
    return (readerState.authoredWorkLibrary || []).map((work) => {
      const chapterCount = Number(work.chapter_count || 0);
      const card = document.createElement("article");
      card.className = "list-card reader-shell-v2__work-card";
      card.innerHTML = `
        ${imageMarkup(work.coverImage, work.title || work.work_id || "作品封面", "reader-shell-v2__card-media")}
        <div class="reader-shell-v2__eyebrow-row">
          <span class="reader-shell-v2__eyebrow">作品入口</span>
          <span class="reader-shell-v2__access">${escapeHtml(work.status || "draft")}</span>
        </div>
        <div class="list-card-head">
          <h3>${escapeHtml(work.title || work.work_id)}</h3>
          <span class="list-card-score">${chapterCount}/${escapeHtml(work.target_chapter_count || "-")}</span>
        </div>
        <p class="list-card-body">${chapterCount > 0 ? "Reader 保留作品入口，但不在这里展开创作语义；先把你送回正确的创作工作区。" : "还没有可读章节，回创作台继续生成。"} </p>
        <div class="reader-shell-v2__actions">
          ${createActionButton({ label: "去创作台", action: `open-author-work:${work.world_version_id || work.work_id}`, variant: "primary-action" })}
        </div>
      `;
      return card;
    });
  }

  function renderLanding() {
    renderReaderShellHeadline();
    renderStatusStrip();
    clearNode(dom.body);
    const session = activeSessionCard();
    const worldMeta = selectedWorldMeta();
    const currentShelfWorld = (readerState.shelfWorlds || []).find(
      (item) => item.world_id === readerState.currentBundle?.world_bible?.world_id
    ) || {};
    const spotlightImage = session
      ? firstImageUrl(session.coverImage, activeCoverImage())
      : firstImageUrl(currentShelfWorld.coverImage, readerState.currentBundle?.coverImage);

    const spotlight = document.createElement("section");
    spotlight.id = "reader-v2-spotlight";
    spotlight.className = "reader-shell-v2__spotlight panel";
    spotlight.innerHTML = session
      ? `
        <div class="reader-shell-v2__spotlight-grid">
          <div class="reader-shell-v2__spotlight-copy">
            <p class="reader-shell-v2__spotlight-kicker">继续这段旅程</p>
            <h3 id="reader-v2-spotlight-title">${escapeHtml(session.last_chapter_title || session.last_event_title || "刚刚开始")}</h3>
            <p id="reader-v2-spotlight-copy">${escapeHtml(`你已经在 ${readerWorldLabel()} 里停下了一次。现在最好的动作不是重开，而是回到那一章继续把这条命运往前推。`)}</p>
            <div class="reader-shell-v2__actions">
              ${createActionButton({ label: "继续阅读", action: `resume-session:${session.session_id}`, variant: "primary-action" })}
              ${createActionButton({ label: "浏览世界", action: `preview-world:${readerState.currentBundle?.example_id || "demo"}` })}
            </div>
          </div>
          <div class="reader-shell-v2__spotlight-side">
            ${imageMarkup(spotlightImage, session.last_chapter_title || "旅程封面", "reader-shell-v2__spotlight-media")}
            <div class="reader-shell-v2__spotlight-stat">
              <span>最近停在</span>
              <strong>第 ${escapeHtml(session.current_turn_index || 0)} 幕</strong>
            </div>
            <div class="reader-shell-v2__spotlight-stat">
              <span>建立于</span>
              <strong>${escapeHtml(formatTimestamp(session.created_at))}</strong>
            </div>
            <div class="reader-shell-v2__spotlight-stat">
              <span>当前世界</span>
              <strong>${escapeHtml(readerWorldLabel())}</strong>
            </div>
          </div>
        </div>
      `
      : `
        <div class="reader-shell-v2__spotlight-grid">
          <div class="reader-shell-v2__spotlight-copy">
            <p class="reader-shell-v2__spotlight-kicker">开始一段新旅程</p>
            <h3 id="reader-v2-spotlight-title">${escapeHtml(worldMeta.label)}</h3>
            <p id="reader-v2-spotlight-copy">${escapeHtml(`当前推荐世界是 ${worldMeta.label}。它更偏向 ${worldMeta.mood}，适合从“${worldMeta.hook}”这种入口切进去。`)}</p>
            <div class="reader-shell-v2__actions">
              ${createActionButton({ label: "开始旅程", action: `start-world:${readerState.currentBundle?.example_id || "demo"}`, variant: "primary-action" })}
              ${createActionButton({ label: "浏览世界", action: `preview-world:${readerState.currentBundle?.example_id || "demo"}` })}
            </div>
          </div>
          <div class="reader-shell-v2__spotlight-side">
            ${imageMarkup(spotlightImage, worldMeta.label || "世界封面", "reader-shell-v2__spotlight-media")}
            <div class="reader-shell-v2__spotlight-stat">
              <span>气质</span>
              <strong>${escapeHtml(worldMeta.mood)}</strong>
            </div>
            <div class="reader-shell-v2__spotlight-stat">
              <span>玩法</span>
              <strong>${escapeHtml(worldMeta.hook)}</strong>
            </div>
            <div class="reader-shell-v2__spotlight-stat">
              <span>状态</span>
              <strong>等待开篇</strong>
            </div>
          </div>
        </div>
      `;
    dom.body.appendChild(spotlight);

    const grid = document.createElement("div");
    grid.className = "reader-shell-v2__grid";
    grid.appendChild(renderLandingCardList("reader-v2-sessions", "Reader · 续读", "你已经开始的旅程", sessionCards(), "还没有可恢复的旅程。"));
    grid.appendChild(renderLandingCardList("reader-v2-worlds", "Reader · 世界", "从这里挑一个世界", worldCards(), "先读取世界入口，再决定从哪个世界起步。"));
    grid.appendChild(renderLandingCardList("reader-v2-authored-works", "Reader · 我的作品", "回到创作台", authoredWorkCards(), "登录作者账号后，这里会显示可跳回创作台的作品入口。"));
    dom.body.appendChild(grid);
  }

  function renderReadHeader() {
    const readerView = currentReaderViewSource();
    const coverImage = activeCoverImage();
    const section = document.createElement("section");
    section.id = "reader-v2-read-hero";
    section.className = `panel reader-shell-v2__read-hero${coverImage ? " reader-shell-v2__read-hero--with-media" : ""}`;
    section.innerHTML = `
      <div class="reader-shell-v2__read-hero-grid">
        <div class="reader-shell-v2__read-hero-copy">
          <p class="reader-shell-v2__spotlight-kicker">当前章节</p>
          <h3>${escapeHtml(readerView?.chapter_title || "旅程已启动")}</h3>
          <p>${escapeHtml(readerView?.recap || "从当前阅读位置继续，优先保留 session、视图和恢复路径。")}</p>
        </div>
        ${imageMarkup(coverImage, readerView?.chapter_title || "当前旅程封面", "reader-shell-v2__read-hero-media")}
        <div class="reader-shell-v2__read-hero-actions">
          ${createActionButton({ label: "返回书架", action: "return-landing" })}
          ${createActionButton({ label: "沉浸阅读", action: "view:experience", variant: readerState.activeView === "experience" ? "primary-action" : "ghost-action" })}
          ${createActionButton({ label: "图文阅读", action: "view:storybook", variant: readerState.activeView === "storybook" ? "primary-action" : "ghost-action" })}
          ${createActionButton({ label: "幕后档案", action: "view:backstage", variant: readerState.activeView === "backstage" ? "primary-action" : "ghost-action" })}
        </div>
      </div>
      <div class="reader-shell-v2__hint-row">
        ${narrativeHints().map((hint) => `<span>${escapeHtml(hint)}</span>`).join("") || "<span>这一章还没有额外关系提示。</span>"}
      </div>
    `;
    return section;
  }

  function buildReaderPaywallCard(paywall) {
    if (!paywall?.required) return null;
    const section = document.createElement("section");
    section.id = "reader-v2-paywall-card";
    section.className = "panel reader-shell-v2__panel reader-shell-v2__panel--warning";
    section.innerHTML = `
      <div class="panel-head">
        <p class="panel-label">Reader · 解锁</p>
        <h3>${escapeHtml(accessReasonLabel(paywall.reason))}</h3>
      </div>
      <p class="panel-copy">继续前需要先解锁。推荐档位 ${escapeHtml(paywall.required_display_name || tierLabel(paywall.tier_id) || paywall.tier_id || "play_pass")}，当前报价 ${paywall.quote !== undefined && paywall.quote !== null ? `¥${Number(paywall.quote).toFixed(2)}` : "-"}。Reader v2 会把解锁动作留在当前阅读路径里，而不是把你踢回书架。</p>
      <div class="reader-shell-v2__actions">
        ${createActionButton({ label: "解锁并继续阅读", action: `start-checkout:${paywall.suggested_checkout_tier || paywall.tier_id || "play_pass"}`, variant: "primary-action" })}
      </div>
    `;
    return section;
  }

  function buildReaderQualityFailureCard(stepFailure) {
    if (!stepFailure || stepFailure.status !== "quality_guard_failed") return null;
    const gate = stepFailure.quality_gate || {};
    const issues = (gate.issues || []).map((item) => item.issue_code).filter(Boolean);
    const section = document.createElement("section");
    section.id = "reader-v2-quality-card";
    section.className = "panel reader-shell-v2__panel reader-shell-v2__panel--warning";
    section.innerHTML = `
      <div class="panel-head">
        <p class="panel-label">Reader · 质量守卫</p>
        <h3>当前章未入库，但 session 已保留</h3>
      </div>
      <p class="panel-copy">${escapeHtml(stepFailure.continuity_contract?.message || gate.summary || "系统保留了当前 session、视图和上一章内容，可以直接重试。")}</p>
      <div class="reader-shell-v2__meta">
        <span>当前文本 ${escapeHtml(gate.actual_text_units || 0)}/${escapeHtml(gate.required_text_units || "-")}</span>
        <span>主要问题 ${escapeHtml(issues.join(" / ") || gate.enforced_decision || "rewrite")}</span>
      </div>
      <div class="reader-shell-v2__actions">
        ${createActionButton({ label: "重试当前章", action: "retry-current-chapter", variant: "primary-action" })}
      </div>
    `;
    return section;
  }

  function buildComposerCard() {
    const section = document.createElement("section");
    const suggested = readerState.intentPrefill?.suggested_prefill || "我想先看看这条命会把我带去哪里。";
    const suggestions = (readerState.currentBundle?.player_inputs || []).slice(0, 3);
    section.className = "panel reader-shell-v2__panel reader-shell-v2__composer";
    section.innerHTML = `
      <div class="panel-head">
        <p class="panel-label">Reader · 下一句心意</p>
        <h3>读完这一章之后，你想先怎么做</h3>
      </div>
      <p class="panel-copy">${escapeHtml(readerState.intentPrefill?.current_pressure || "上一章留下的余波还没散。")}</p>
      <div class="reader-shell-v2__suggestion-row">
        ${suggestions.map((item) => `<button type="button" class="ghost-action reader-shell-v2__suggestion" data-reader-v2-action="suggestion:${escapeHtml(item.raw_input)}">${escapeHtml(item.raw_input)}</button>`).join("")}
      </div>
      <label class="input-label" for="reader-shell-v2-input">玩家输入</label>
      <textarea id="reader-shell-v2-input" class="field-input" rows="4" placeholder="例如：我想先试探她的态度，再决定是否顺从家族安排。">${escapeHtml(legacyReaderDom.playerInput?.value || suggested)}</textarea>
      <p class="field-hint">推荐起笔：${escapeHtml(suggested)}</p>
      <div class="reader-shell-v2__actions">
        ${createActionButton({ label: "看看接下来", action: "preview-route" })}
        ${createActionButton({ label: "推进这一幕", action: "step-session", variant: "primary-action", disabled: !readerState.sessionId })}
        ${createActionButton({ label: "重置输入", action: "reset-output" })}
      </div>
    `;
    return section;
  }

  function buildExperienceCard() {
    const section = document.createElement("section");
    section.id = "reader-v2-experience";
    const readerView = currentReaderViewSource();
    section.className = "panel reader-shell-v2__panel reader-shell-v2__panel--story";
    section.innerHTML = `
      <div class="panel-head">
        <p class="panel-label">沉浸阅读</p>
        <h3 id="reader-v2-experience-title">${escapeHtml(readerView?.chapter_title || "故事还没开始")}</h3>
      </div>
      <article id="reader-v2-experience-prose" class="rendered-scene reader-shell-v2__prose">${escapeHtml(readerView?.body || "进入世界后，这里会显示当前章节正文。")}</article>
    `;
    return section;
  }

  function buildStorybookCard() {
    const section = document.createElement("section");
    section.id = "reader-v2-storybook";
    const storySource = currentStorybookSource();
    const readerView = storySource?.readerView || null;
    const renderedScene = storySource?.renderedScene || {};
    const sceneCard = readerView?.scene_card || {};
    const quote = sceneCard.quote || renderedScene.pull_quote || readerView?.recap || "这里会显示章节引句。";
    const quoteNote = sceneCard.summary || renderedScene.chapter_summary || readerView?.recap || "这一句会先把这一章最该记住的余波钉住。";
    const beatItems = (sceneCard.story_beats || renderedScene.story_beats || []).slice(0, 4);
    const visualDetails = (sceneCard.visual_details || renderedScene.visual_details || []).slice(0, 4);
    const relationshipHints = (readerView?.relationship_hints || []).filter(Boolean).slice(0, 4);
    const canvasMeta = [
      readerChapterLabel(readerView?.chapter_index, storySource?.turnIndex),
      storySource?.turnIndex ? `Turn ${storySource.turnIndex}` : null,
      storySource?.promiseSnapshot?.length ? `未解牵挂 ${storySource.promiseSnapshot.length}` : null,
      sceneCard.palette_hint || renderedScene.palette_hint || renderedScene.image_motif || null,
    ].filter(Boolean);
    const beatSummary = beatItems.length > 1
      ? `先抓住这 ${beatItems.length} 个节拍，再回到正文会更容易看清这一章怎么抬势、落子和留余波。`
      : beatItems.length === 1
        ? "这一章最关键的动作先落在这一拍上。"
        : "这一章还没有显式节拍，先从正文和引句里读余波。";
    const detailTags = [...relationshipHints, ...visualDetails]
      .filter(Boolean)
      .slice(0, 6);
    const storyImage = storySource?.isPrologue ? activeCoverImage() : activeAtmosphereImage();
    const sequenceEntries = storybookSequenceEntries(storySource);
    const sequenceSummary = sequenceEntries.length > 1
      ? `连续章节轨迹已累计 ${readerState.replay?.reader_views?.length || sequenceEntries.length} 章，当前停在 ${readerChapterLabel(readerView?.chapter_index, storySource?.turnIndex)}。`
      : storySource?.isPrologue
        ? "旅程刚启动，真正推进之后这里会把章节余波连成一条连续轨迹。"
        : "继续推进之后，这里会把相邻章节的余波逐步连成一条连续轨迹。";
    section.className = "panel reader-shell-v2__panel reader-shell-v2__panel--story";
    section.innerHTML = `
      <div class="panel-head">
        <div>
          <p class="panel-label">图文阅读</p>
          <h3 id="reader-v2-storybook-title">${escapeHtml(readerView?.chapter_title || "图文版本")}</h3>
        </div>
        <div id="reader-v2-storybook-canvas-meta" class="reader-shell-v2__canvas-meta">
          ${canvasMeta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
        </div>
      </div>
      <div id="reader-v2-storybook-canvas" class="reader-shell-v2__chapter-canvas">
        <div class="reader-shell-v2__chapter-main">
          <p id="reader-v2-storybook-recap" class="reader-shell-v2__chapter-recap">${escapeHtml(readerView?.recap || "这里会显示章节 recap。")}</p>
          <article id="reader-v2-storybook-prose" class="rendered-scene reader-shell-v2__prose">${escapeHtml(readerView?.body || "这里会显示章节正文。")}</article>
        </div>
        <div class="reader-shell-v2__chapter-side">
          ${imageMarkup(storyImage, readerView?.chapter_title || "章节插图", "reader-shell-v2__image-panel")}
          <section class="reader-shell-v2__quote-card">
            <p class="reader-shell-v2__section-label">${escapeHtml(storySource?.isPrologue ? "起笔句" : "本章引句")}</p>
            <blockquote id="reader-v2-storybook-quote" class="story-quote reader-shell-v2__quote">${escapeHtml(quote)}</blockquote>
            <p id="reader-v2-storybook-quote-note" class="reader-shell-v2__quote-note">${escapeHtml(quoteNote)}</p>
          </section>
          <section class="reader-shell-v2__beat-card">
            <div class="reader-shell-v2__beat-head">
              <p class="reader-shell-v2__section-label">关键节拍</p>
              <p id="reader-v2-storybook-beat-summary" class="reader-shell-v2__minor-copy">${escapeHtml(beatSummary)}</p>
            </div>
            <ol id="reader-v2-storybook-beats" class="reader-shell-v2__beat-list">
              ${beatItems.length ? beatItems.map((beat, index) => `
                <li class="reader-shell-v2__beat-item">
                  <span class="reader-shell-v2__beat-index">${String(index + 1).padStart(2, "0")}</span>
                  <span class="reader-shell-v2__beat-copy">${escapeHtml(beat)}</span>
                </li>
              `).join("") : `
                <li class="reader-shell-v2__beat-item reader-shell-v2__beat-item--empty">
                  <span class="reader-shell-v2__beat-copy">这一章还没有显式节拍，先从正文和引句里读余波。</span>
                </li>
              `}
            </ol>
          </section>
          <div id="reader-v2-storybook-hints" class="reader-shell-v2__meta reader-shell-v2__meta--storybook">
            ${detailTags.length ? detailTags.map((hint) => `<span>${escapeHtml(hint)}</span>`).join("") : "<span>这一章的关系和画面提示还在慢慢浮出来。</span>"}
          </div>
        </div>
      </div>
      <section class="reader-shell-v2__trajectory">
        <div class="reader-shell-v2__trajectory-head">
          <div>
            <p class="reader-shell-v2__section-label">连续章节轨迹</p>
            <p id="reader-v2-storybook-sequence-summary" class="reader-shell-v2__minor-copy">${escapeHtml(sequenceSummary)}</p>
          </div>
        </div>
        <div id="reader-v2-storybook-sequence" class="reader-shell-v2__story-sequence">
          ${sequenceEntries.length ? sequenceEntries.map((item) => {
            const tag = item.action ? "button" : "article";
            const actionAttr = item.action ? ` data-reader-v2-action="${escapeHtml(item.action)}"` : "";
            const typeAttr = item.action ? " type=\"button\"" : "";
            const activeClass = item.isActive ? " is-active" : "";
            const secondaryMeta = [
              item.promiseCount ? `未解牵挂 ${item.promiseCount}` : null,
              item.relationshipHints?.[0] || null,
            ].filter(Boolean);
            return `
              <${tag}${typeAttr} class="story-sequence-card reader-shell-v2__trajectory-card${activeClass}"${actionAttr}>
                <span class="reader-shell-v2__trajectory-kicker">${escapeHtml(item.isActive ? `${readerChapterLabel(item.chapterIndex, item.turnIndex)} · 当前阅读位置` : readerChapterLabel(item.chapterIndex, item.turnIndex))}</span>
                <strong>${escapeHtml(item.chapterTitle)}</strong>
                <p>${escapeHtml(item.recap)}</p>
                ${secondaryMeta.length ? `<div class="reader-shell-v2__trajectory-meta">${secondaryMeta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>` : ""}
              </${tag}>
            `;
          }).join("") : "<p class=\"panel-copy\">真正推进之后，这里会把最近几章压成一条可快速回看的轨迹。</p>"}
        </div>
      </section>
    `;
    return section;
  }

  function buildBackstageCard() {
    const section = document.createElement("section");
    section.id = "reader-v2-backstage";
    section.className = "reader-shell-v2__backstage-drawer";
    const routes = (readerState.latestPreview?.routes || []).slice(0, 3);
    const replayItems = (readerState.replay?.reader_views || []).slice(-3);
    section.innerHTML = `
      <div class="panel-head reader-shell-v2__drawer-head">
        <div>
          <p class="panel-label">Reader · 幕后档案</p>
          <h3 id="reader-v2-backstage-title">当前阅读路径的轻量分析</h3>
        </div>
        <button id="reader-v2-backstage-close" class="ghost-action backstage-close" type="button" data-reader-v2-action="close-backstage">返回阅读</button>
      </div>
      <p id="reader-v2-backstage-copy" class="panel-copy">这里只回答当前章哪里最紧、下一步往哪偏、前几章留下了什么余波，不把 Author / Ops 语义带进来。</p>
      <div class="reader-shell-v2__backstage-grid">
        <div>
          <p class="toolbar-label">Continuity</p>
          <p class="panel-copy">${escapeHtml(readerState.continuityContract?.message || "当前没有额外 continuity 提示。")}</p>
        </div>
        <div>
          <p class="toolbar-label">Preview</p>
          <div class="list-stack">${routes.length ? routes.map((route) => `<article class="list-card"><div class="list-card-head"><h3>${escapeHtml(route.events?.[0]?.title || "下一步命运")}</h3><span class="list-card-score">${escapeHtml(Number(route.total_score || 0).toFixed(3))}</span></div><p class="list-card-body">${escapeHtml(route.events?.[0]?.summary || route.explanation || "暂无说明。")}</p></article>`).join("") : "还没有 preview。先继续阅读或预览下一步。"}</div>
        </div>
        <div>
          <p class="toolbar-label">Replay</p>
          <div class="list-stack">${replayItems.length ? replayItems.map((item, index) => `<article class="list-card"><div class="list-card-head"><h3>${escapeHtml(item.chapter_title || `章节 ${index + 1}`)}</h3><span class="list-card-score">${escapeHtml(item.chapter_index || index + 1)}</span></div><p class="list-card-body">${escapeHtml(item.recap || "暂无 recap。")}</p></article>`).join("") : "当前还没有 replay 轨迹。"}</div>
        </div>
      </div>
    `;
    return section;
  }

  function renderRead() {
    renderReaderShellHeadline();
    renderStatusStrip();
    clearNode(dom.body);
    dom.body.appendChild(renderReadHeader());
    const qualityFailure = activeReaderQualityFailure();
    const paywall = activeReaderPaywall();
    const readingView = readerState.activeView === "backstage"
      ? (shellState.lastReaderView === "storybook" ? "storybook" : "experience")
      : readerState.activeView;
    const readGrid = document.createElement("div");
    readGrid.id = "reader-v2-read-grid";
    readGrid.className = "reader-shell-v2__read-grid";

    const main = document.createElement("div");
    main.id = "reader-v2-main-column";
    main.className = "reader-shell-v2__main-column";
    if (readingView === "storybook") {
      main.appendChild(buildStorybookCard());
    } else {
      main.appendChild(buildExperienceCard());
    }

    const side = document.createElement("div");
    side.id = "reader-v2-side-column";
    side.className = "reader-shell-v2__side-column";
    if (qualityFailure) {
      side.appendChild(buildReaderQualityFailureCard(qualityFailure));
    } else if (paywall) {
      side.appendChild(buildReaderPaywallCard(paywall));
    }
    side.appendChild(buildComposerCard());

    readGrid.appendChild(main);
    readGrid.appendChild(side);
    dom.body.appendChild(readGrid);
    if (readerState.activeView === "backstage") {
      dom.body.appendChild(buildBackstageCard());
    }
  }

  function refresh() {
    if (!dom.root) return;
    setReaderShellMode();
    if (shellState.activeProduct !== "reader" || shellState.authPage) return;
    if (shellState.readerWorkspace === "read") {
      renderRead();
      return;
    }
    renderLanding();
  }

  async function refreshExamplesV2() {
    if (typeof legacyReaderRuntime.refreshExamples === "function") {
      await legacyReaderRuntime.refreshExamples();
    }
    refresh();
  }

  async function refreshSessionLibraryV2() {
    if (typeof legacyReaderRuntime.refreshSessionLibrary === "function") {
      await legacyReaderRuntime.refreshSessionLibrary();
    }
    refresh();
  }

  async function refreshAuthoredWorkLibraryV2() {
    if (typeof legacyReaderRuntime.refreshAuthoredWorkLibrary === "function") {
      await legacyReaderRuntime.refreshAuthoredWorkLibrary();
    }
    refresh();
  }

  async function restoreSessionV2(sessionId, triggerButton = null) {
    if (!sessionId) return;
    const restore = triggerButton ? setBusy(triggerButton, "回到这一幕…") : () => {};
    try {
      const sessionPayload = await api(`/v1/sessions/${sessionId}`);
      const replayPayload = await api(`/v1/sessions/${sessionId}/replay`);
      const prefillPayload = await api(`/v1/sessions/${sessionId}/prefill`);
      const matchingExample = (readerState.examples || []).find((item) => item.world_id === sessionPayload.session.world_id);
      if (matchingExample && readerState.currentBundle?.example_id !== matchingExample.example_id && typeof legacyReaderRuntime.loadExampleBundle === "function") {
        await legacyReaderRuntime.loadExampleBundle(matchingExample.example_id);
      }
      readerState.sessionId = sessionId;
      readerState.currentState = sessionPayload.session.current_state;
      readerState.sessionPaywall = sessionPayload.paywall || readerState.sessionPaywall || null;
      readerState.latestStep = sessionPayload.latest_step || null;
      readerState.latestStepFailure = null;
      readerState.readerGenerationJob = null;
      readerState.continuityContract = null;
      readerState.replay = replayPayload;
      readerState.selectedReplayIndex = replayPayload.event_trace?.length
        ? replayPayload.event_trace.length - 1
        : null;
      readerState.intentPrefill = prefillPayload;
      readerState.worldId = sessionPayload.session.world_id;
      readerState.worldVersionId = sessionPayload.world_version_id || sessionPayload.session.metadata?.world_version_id || null;
      readerState.readerId = sessionPayload.session.metadata?.reader_id || currentAccountId();
      shellState.pendingSessionId = null;
      shellState.readerWorkspace = "read";
      readerState.activeView = "experience";
      await refreshReaderEntitlementsV2();
      refresh();
      if (typeof ShellStatusRuntime !== "undefined") {
        ShellStatusRuntime.syncProductMode();
      }
    } catch (error) {
      reportUiMessage(`继续旅程失败：${error.message}`, "error");
    } finally {
      restore();
    }
  }

  async function bootstrapWorldV2(triggerButton = null) {
    if (!readerState.currentBundle?.world_bible?.world_id) return;
    const restore = triggerButton ? setBusy(triggerButton, "进入中…") : () => {};
    try {
      const sessionResult = await api("/v1/reader/sessions", {
        method: "POST",
        body: JSON.stringify({
          world_id: readerState.currentBundle.world_bible.world_id,
          account_id: currentAccountId(),
        }),
      });
      readerState.sessionId = sessionResult.session_id;
      readerState.currentState = sessionResult.current_state;
      readerState.sessionPaywall = sessionResult.paywall || null;
      readerState.worldId = sessionResult.world_id || readerState.currentBundle.world_bible.world_id;
      readerState.worldVersionId = sessionResult.world_version_id || null;
      readerState.readerId = sessionResult.account_id || sessionResult.reader_id || currentAccountId();
      readerState.latestStep = null;
      readerState.latestStepFailure = null;
      readerState.readerGenerationJob = null;
      readerState.continuityContract = null;
      readerState.replay = null;
      readerState.selectedReplayIndex = null;
      readerState.intentPrefill = {
        last_player_intent: "",
        current_pressure: "故事刚刚开始。",
        suggested_prefill: "我想先试探眼前这条路到底会把我带到哪一边。",
      };
      shellState.readerWorkspace = "read";
      readerState.activeView = "experience";
      await refreshSessionLibraryV2();
      await refreshReaderEntitlementsV2();
      refresh();
      if (typeof ShellStatusRuntime !== "undefined") {
        ShellStatusRuntime.syncProductMode();
      }
      reportUiMessage("旅程已经开始，接下来可以先阅读当前章，再写下一句心意。", "success");
    } catch (error) {
      reportUiMessage(`开始旅程失败：${error.message}`, "error");
    } finally {
      restore();
    }
  }

  async function pollReaderGenerationJob(initialJob) {
    let job = initialJob || {};
    const jobId = readerGenerationJobId(job);
    if (!jobId) {
      const error = new Error("reader_generation_job_missing");
      error.code = "reader_job_missing";
      throw error;
    }
    const timeoutMs = 60000;
    const resumeAfterMs = 5000;
    const start = Date.now();
    let resumed = false;
    while (Date.now() - start < timeoutMs) {
      updateReaderGenerationJob(job, resumed ? "resumed" : "polling");
      refresh();
      const status = String(job.status || "");
      if (status === "succeeded") {
        return job;
      }
      if (status === "failed") {
        const error = new Error(job.error || "reader_generation_job_failed");
        error.code = "reader_job_failed";
        error.job = job;
        throw error;
      }
      const shouldResume =
        !resumed &&
        Boolean(job.retryable) &&
        Date.now() - start >= resumeAfterMs &&
        (status === "queued" || status === "running");
      if (shouldResume) {
        const resumedPayload = await api(`/v1/reader/jobs/${encodeURIComponent(jobId)}/resume`, {
          method: "POST",
        });
        job = resumedPayload.job || job;
        resumed = true;
        continue;
      }
      await sleep(Number(job.pollAfterMs || 1000));
      const payload = await api(`/v1/reader/jobs/${encodeURIComponent(jobId)}`);
      job = payload.job || job;
    }
    const error = new Error(`reader_generation_job_timeout:${jobId}`);
    error.code = "reader_job_timeout";
    error.job = job;
    throw error;
  }

  async function reloadReaderSessionAfterGeneration(job) {
    const sessionId = String(job?.sessionId || readerState.sessionId || "").trim();
    if (!sessionId) {
      const error = new Error("reader_generation_session_missing_after_job");
      error.code = "reader_ui_sync_stale";
      throw error;
    }
    const sessionPayload = await api(`/v1/sessions/${encodeURIComponent(sessionId)}`);
    const replayPayload = await api(`/v1/sessions/${encodeURIComponent(sessionId)}/replay`);
    const prefillPayload = await api(`/v1/sessions/${encodeURIComponent(sessionId)}/prefill`);
    readerState.sessionId = sessionId;
    readerState.currentState = sessionPayload.session?.current_state || readerState.currentState;
    readerState.sessionPaywall = sessionPayload.paywall || job?.result?.paywall || readerState.sessionPaywall || null;
    readerState.worldId = sessionPayload.session?.world_id || readerState.worldId;
    readerState.worldVersionId = sessionPayload.world_version_id || sessionPayload.session?.metadata?.world_version_id || readerState.worldVersionId;
    readerState.readerId = sessionPayload.session?.metadata?.reader_id || readerState.readerId || currentAccountId();
    readerState.replay = replayPayload;
    readerState.selectedReplayIndex = replayPayload.event_trace?.length ? replayPayload.event_trace.length - 1 : null;
    readerState.intentPrefill = prefillPayload;
    readerState.continuityContract = job?.result?.continuity_contract || null;
    const readerStatus = String(job?.readerStatus || job?.result?.reader_status || "ok");
    if (readerStatus === "quality_guard_failed") {
      readerState.latestStepFailure = {
        status: "quality_guard_failed",
        quality_gate: job?.result?.quality_gate || null,
        continuity_contract: job?.result?.continuity_contract || null,
        paywall: job?.result?.paywall || null,
      };
    } else {
      readerState.latestStepFailure = null;
    }
    readerState.latestStep = sessionPayload.latest_step || null;
    updateReaderGenerationJob(job, "succeeded");
    await refreshSessionLibraryV2();
    await refreshReaderEntitlementsV2();
    readerState.readerGenerationJob = null;
    refresh();
    if (readerStatus === "quality_guard_failed") {
      reportUiMessage(job?.result?.continuity_contract?.message || "当前章未入库，但阅读位置已保留。", "warning");
      return;
    }
    if (!readerState.latestStep) {
      const error = new Error("reader_ui_sync_stale");
      error.code = "reader_ui_sync_stale";
      error.job = job;
      throw error;
    }
    reportUiMessage("这一幕已经推进，新的章节和回放都已更新。", "success");
  }

  async function stepSessionV2() {
    if (!readerState.sessionId) return;
    const input = dom.root?.querySelector("#reader-shell-v2-input");
    const playerInput = String(input?.value || "").trim();
    if (!playerInput) {
      reportUiMessage("先写下一句你现在真正想做的事。", "warning");
      return;
    }
    if (legacyReaderDom.playerInput) {
      legacyReaderDom.playerInput.value = playerInput;
    }
    const stepButton = dom.root?.querySelector('[data-reader-v2-action="step-session"]');
    const restore = stepButton ? setBusy(stepButton, "执行中…") : () => {};
    try {
      const stepResult = await api("/v1/reader/continue", {
        method: "POST",
        body: JSON.stringify({
          session_id: readerState.sessionId,
          account_id: currentAccountId(),
          freeform_intent: playerInput,
        }),
      });
      if (stepResult.status === "queued" && stepResult.job) {
        updateReaderGenerationJob(stepResult.job, "queued");
        refresh();
        reportUiMessage("生成中，完成后会自动更新阅读位置。", "info");
        const completedJob = await pollReaderGenerationJob(stepResult.job);
        await reloadReaderSessionAfterGeneration(completedJob);
        return;
      }
      readerState.continuityContract = stepResult.continuity_contract || null;
      readerState.readerGenerationJob = null;
      if (stepResult.status === "quality_guard_failed") {
        readerState.latestStepFailure = stepResult;
        readerState.sessionPaywall = stepResult.paywall || readerState.sessionPaywall || null;
        await refreshReaderEntitlementsV2();
        refresh();
        reportUiMessage(stepResult.continuity_contract?.message || "当前章未入库，但阅读位置已保留。", "warning");
        return;
      }
      if (stepResult.status && stepResult.status !== "ok") {
        readerState.latestStepFailure = null;
        readerState.sessionPaywall = stepResult.paywall || readerState.sessionPaywall || null;
        await refreshReaderEntitlementsV2();
        refresh();
        reportUiMessage(stepResult.continuity_contract?.message || `继续前需要先解锁：${accessReasonLabel(stepResult.paywall?.reason)}。`, "warning");
        return;
      }
      readerState.latestStep = stepResult;
      readerState.latestStepFailure = null;
      readerState.currentState = stepResult.updated_state;
      readerState.worldVersionId = stepResult.world_version_id || readerState.worldVersionId;
      readerState.sessionPaywall = stepResult.paywall || readerState.sessionPaywall || null;
      readerState.replay = await api(`/v1/sessions/${readerState.sessionId}/replay`);
      readerState.selectedReplayIndex = readerState.replay?.event_trace?.length
        ? readerState.replay.event_trace.length - 1
        : null;
      readerState.intentPrefill = await api(`/v1/sessions/${readerState.sessionId}/prefill`);
      await refreshSessionLibraryV2();
      await refreshReaderEntitlementsV2();
      refresh();
      reportUiMessage("这一幕已经推进，新的章节和回放都已更新。", "success");
    } catch (error) {
      reportUiMessage(`这一幕没能推进：${error.message}`, "error");
    } finally {
      restore();
    }
  }

  function resetOutputV2() {
    readerState.latestStep = null;
    readerState.latestStepFailure = null;
    readerState.readerGenerationJob = null;
    readerState.continuityContract = null;
    readerState.replay = null;
    readerState.intentPrefill = null;
    readerState.selectedReplayIndex = null;
    if (legacyReaderDom.playerInput) {
      legacyReaderDom.playerInput.value = "";
    }
    refresh();
  }

  async function refreshReaderEntitlementsV2() {
    if (typeof legacyReaderRuntime.refreshReaderEntitlements === "function") {
      await legacyReaderRuntime.refreshReaderEntitlements();
    }
    refresh();
  }

  async function startReaderCheckoutV2(tierId = "play_pass") {
    if (typeof legacyReaderRuntime.startReaderCheckout === "function") {
      await legacyReaderRuntime.startReaderCheckout(tierId);
    }
    refresh();
  }

  async function restoreCheckoutContext() {
    if (typeof legacyReaderRuntime.completePendingCheckoutReturn === "function") {
      await legacyReaderRuntime.completePendingCheckoutReturn();
    }
    refresh();
  }

  async function deleteSessionV2(sessionId) {
    if (typeof legacyReaderRuntime.deleteSession === "function") {
      await legacyReaderRuntime.deleteSession(sessionId);
    }
    refresh();
  }

  async function openAuthorWorkV2(worldVersionId) {
    shellState.activeProduct = "author";
    shellState.authorWorkspace = "draft";
    authorState.activeDraftVersionId = worldVersionId || authorState.activeDraftVersionId;
    if (typeof ShellStatusRuntime !== "undefined") {
      ShellStatusRuntime.syncProductMode();
    }
    if (typeof AuthorWorkspaceRuntime !== "undefined" && typeof AuthorWorkspaceRuntime.refreshAuthorSurface === "function") {
      await AuthorWorkspaceRuntime.refreshAuthorSurface();
    }
  }

  async function handleAction(action) {
    if (!action) return;
    if (action === "return-landing") {
      shellState.readerWorkspace = "landing";
      refresh();
      if (typeof ShellStatusRuntime !== "undefined") {
        ShellStatusRuntime.syncProductMode();
      }
      return;
    }
    if (action === "step-session") {
      await stepSessionV2();
      return;
    }
    if (action === "preview-route") {
      if (typeof legacyReaderRuntime.previewRoute === "function") {
        await legacyReaderRuntime.previewRoute();
      }
      refresh();
      return;
    }
    if (action === "retry-current-chapter") {
      await stepSessionV2();
      return;
    }
    if (action === "close-backstage") {
      readerState.activeView = shellState.lastReaderView || "experience";
      refresh();
      if (typeof ShellStatusRuntime !== "undefined") {
        ShellStatusRuntime.syncViewMode();
      }
      return;
    }
    if (action === "reset-output") {
      resetOutputV2();
      return;
    }
    if (action.startsWith("preview-world:")) {
      const exampleId = action.split(":")[1];
      if (typeof legacyReaderRuntime.loadExampleBundle === "function") {
        await legacyReaderRuntime.loadExampleBundle(exampleId);
      }
      refresh();
      return;
    }
    if (action.startsWith("start-world:")) {
      const exampleId = action.split(":")[1];
      if (typeof legacyReaderRuntime.loadExampleBundle === "function") {
        await legacyReaderRuntime.loadExampleBundle(exampleId);
      }
      const trigger = dom.root?.querySelector(`[data-reader-v2-action="${action}"]`);
      await bootstrapWorldV2(trigger);
      return;
    }
    if (action.startsWith("resume-session:")) {
      const sessionId = action.split(":")[1];
      const trigger = dom.root?.querySelector(`[data-reader-v2-action="${action}"]`);
      await restoreSessionV2(sessionId, trigger);
      return;
    }
    if (action.startsWith("delete-session:")) {
      await deleteSessionV2(action.split(":")[1]);
      return;
    }
    if (action.startsWith("open-author-work:")) {
      await openAuthorWorkV2(action.split(":")[1]);
      return;
    }
    if (action.startsWith("start-checkout:")) {
      await startReaderCheckoutV2(action.split(":")[1]);
      return;
    }
    if (action.startsWith("suggestion:")) {
      const value = action.slice("suggestion:".length);
      const input = dom.root?.querySelector("#reader-shell-v2-input");
      if (input) {
        input.value = value;
      }
      if (legacyReaderDom.playerInput) {
        legacyReaderDom.playerInput.value = value;
      }
      return;
    }
    if (action.startsWith("jump-storybook:")) {
      const nextIndex = Number(action.split(":")[1]);
      if (Number.isInteger(nextIndex) && nextIndex >= 0) {
        readerState.selectedReplayIndex = nextIndex;
        readerState.activeView = "storybook";
        refresh();
        if (typeof ShellStatusRuntime !== "undefined") {
          ShellStatusRuntime.syncViewMode();
        }
      }
      return;
    }
    if (action.startsWith("view:")) {
      readerState.activeView = action.split(":")[1];
      refresh();
      if (typeof ShellStatusRuntime !== "undefined") {
        ShellStatusRuntime.syncViewMode();
      }
    }
  }

  function bindReaderShellV2Events() {
    if (readerShellV2EventsBound || !dom.root) return;
    readerShellV2EventsBound = true;
    dom.root.addEventListener("click", async (event) => {
      const target = event.target.closest("[data-reader-v2-action]");
      if (!target) return;
      event.preventDefault();
      try {
        await handleAction(target.dataset.readerV2Action);
      } catch (error) {
        reportUiMessage(`Reader shell v2 操作失败：${error.message}`, "error");
      }
    });
  }

  function scheduleBootstrapRefresh() {
    [0, 250, 1000].forEach((delay) => {
      window.setTimeout(() => {
        refresh();
      }, delay);
    });
  }

  function initializeReaderRuntime() {
    if (readerShellV2Initialized) return;
    readerShellV2Initialized = true;
    if (typeof legacyReaderRuntime.initializeReaderRuntime === "function") {
      legacyReaderRuntime.initializeReaderRuntime();
    }
    setReaderShellMode();
    bindReaderShellV2Events();
    scheduleBootstrapRefresh();
    refresh();
  }

  const apiSurface = {
    ...legacyReaderRuntime,
    initialize: initializeReaderRuntime,
    refresh,
    renderLanding,
    renderRead,
    renderStorybook: refresh,
    renderBackstage: refresh,
    restoreCheckoutContext,
    initializeReaderRuntime,
    refreshExamples: refreshExamplesV2,
    refreshSessionLibrary: refreshSessionLibraryV2,
    refreshAuthoredWorkLibrary: refreshAuthoredWorkLibraryV2,
    refreshReaderEntitlements: refreshReaderEntitlementsV2,
    bootstrapWorld: bootstrapWorldV2,
    restoreSession: restoreSessionV2,
    stepSession: stepSessionV2,
    resetOutput: resetOutputV2,
    startReaderCheckout: startReaderCheckoutV2,
    deleteSession: deleteSessionV2,
    renderLatestStep: refresh,
    renderReplay: refresh,
    renderIntentPrefill: refresh,
    renderStoryFeed: refresh,
    renderRoutePreview: refresh,
    bindReaderEvents: bindReaderShellV2Events,
  };

  return apiSurface;
})();

if (typeof window !== "undefined") {
  window.ReaderRuntimeLegacy = typeof ReaderRuntime === "object" && ReaderRuntime ? ReaderRuntime : null;
  window.ReaderShellV2 = ReaderShellV2;
  window.ReaderRuntime = ReaderShellV2;
}
