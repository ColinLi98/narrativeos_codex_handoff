// Ops state accessors shared across ops refresh/render helpers.

var OpsAccessors = (() => {
  function latestAsyncJob(jobType) {
    return (opsState.opsAsyncJobs || []).find((item) => item.job_type === jobType) || null;
  }

  function selectedReviewItem() {
    return (opsState.opsReviewHub?.items || []).find((item) => item.review_item_id === opsState.opsSelectedReviewItemId) || null;
  }

  return {
    latestAsyncJob,
    selectedReviewItem,
  };
})();
