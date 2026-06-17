// Author draft/workbench accessors shared across author runtime and shell helpers.

var AuthorAccessors = (() => {
  const { reportUiMessage } = UIShared;
  const { tierLabel, accessReasonLabel } = ReaderAccessors;

  function getActiveDraftWorldpack() {
    return authorState.activeDraftDetail?.worldpack_json || authorState.activeDraftDetail?.worldpack || null;
  }

  function getActiveRevisionHistory() {
    return authorState.activeDraftDetail?.revision_history || getActiveDraftWorldpack()?.metadata?.revision_history || [];
  }

  function getLatestDiffSummary() {
    return authorState.activeDraftDetail?.latest_diff_summary || getActiveDraftWorldpack()?.metadata?.latest_diff_summary || {};
  }

  function getDiffDrilldown() {
    return authorState.activeDraftDetail?.diff_drilldown || {};
  }

  function getSimulationDrilldown() {
    return (
      authorState.authorSimulationReport?.simulation_drilldown ||
      authorState.activeDraftDetail?.simulation_drilldown ||
      {}
    );
  }

  function getLongformDrilldown() {
    return (
      authorState.authorSimulationReport?.longform_drilldown ||
      authorState.activeDraftDetail?.longform_drilldown ||
      {}
    );
  }

  function getPromiseLedgerWorkbench() {
    return authorState.activeDraftDetail?.promise_ledger_workbench || {};
  }

  function getPromiseStateWorkbench() {
    return authorState.activeDraftDetail?.promise_state_workbench || {};
  }

  function getSeriesVolumeArcPromiseMapping() {
    return authorState.activeDraftDetail?.series_volume_arc_promise_mapping || {};
  }

  function getChapterTaskSimulationLinking() {
    return authorState.activeDraftDetail?.chapter_task_simulation_linking || {};
  }

  function getContinuityDiffWorkbench() {
    return authorState.activeDraftDetail?.continuity_diff_workbench || {};
  }

  function getContinuityOverrideWorkbench() {
    return authorState.activeDraftDetail?.continuity_override_workbench || {};
  }

  function getSimulationDiffCheckpoint() {
    return authorState.activeDraftDetail?.simulation_diff_checkpoint || {};
  }

  function selectedAuthorChapterMarker(chapterIndex) {
    return Number(authorState.selectedAuthorSimulationChapterIndex || 0) === Number(chapterIndex || 0) ? ">> " : "";
  }

  function selectedAuthorCompareMarker(chapterIndex) {
    return Number(authorState.selectedAuthorContinuityChapterIndex || 0) === Number(chapterIndex || 0) ? ">> " : "";
  }

  function alertAuthorGating(errorDetail, actionLabel) {
    reportUiMessage(
      `当前不能${actionLabel}：${accessReasonLabel(errorDetail.reason)}。需要 ${errorDetail.required_display_name || tierLabel(errorDetail.required_tier)}，当前 ${errorDetail.wallet_type || "-"} 余额 ${Number(errorDetail.balance || 0).toFixed(0)}${errorDetail.required_units !== undefined ? ` / 需要 ${Number(errorDetail.required_units).toFixed(0)}` : ""}。`,
      "warning"
    );
  }

  return {
    getActiveDraftWorldpack,
    getActiveRevisionHistory,
    getLatestDiffSummary,
    getDiffDrilldown,
    getSimulationDrilldown,
    getLongformDrilldown,
    getPromiseLedgerWorkbench,
    getPromiseStateWorkbench,
    getSeriesVolumeArcPromiseMapping,
    getChapterTaskSimulationLinking,
    getContinuityDiffWorkbench,
    getContinuityOverrideWorkbench,
    getSimulationDiffCheckpoint,
    selectedAuthorChapterMarker,
    selectedAuthorCompareMarker,
    alertAuthorGating,
  };
})();
