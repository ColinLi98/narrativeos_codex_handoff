const appState = {
  examples: [],
  activeProduct: "reader",
  shelfWorlds: [],
  currentBundle: null,
  worldId: null,
  worldVersionId: null,
  readerId: "reader_demo",
  readerEntitlements: [],
  readerCheckoutSession: null,
  readerSubscription: null,
  sessionPaywall: null,
  sessionId: null,
  currentState: null,
  latestStep: null,
  latestPreview: null,
  replay: null,
  intentPrefill: null,
  sessionLibrary: [],
  activeTone: "premium_prose",
  activeView: "experience",
  selectedReplayIndex: null,
  selectedIntentOverride: null,
  authorDrafts: [],
  activeDraftVersionId: null,
  activeDraftDetail: null,
  authorValidationReport: null,
  authorSimulationReport: null,
  authorPreviousSimulationReport: null,
  selectedAuthorRevisionIndex: null,
  authorBriefTemplate: null,
  authorAccessSnapshot: null,
  authorWorkflowSummary: null,
  authorCollaborationSummary: null,
  authorReviewerInbox: null,
  authorReviewerInboxNextCursor: null,
  authorReviewerInboxHasMore: false,
  authorReviewerInboxSearch: "",
  authorNotificationPreferences: null,
  authorAuthSession: null,
  selectedAuthorThreadId: null,
  authorInlineReplyDraft: "",
  authorReviewerInboxVisibleNotificationIds: [],
  opsReviewQueue: [],
  opsWorldStatuses: [],
  opsWorldHistories: [],
  selectedOpsWorldId: null,
  opsNavigationModel: null,
  opsNavigationPinned: false,
  opsInvestigationPinned: false,
  opsRefreshRequestId: 0,
  opsReleaseWorkspace: null,
  opsMeters: [],
  opsSchemaLifecycle: null,
  opsDataIntegrity: null,
  opsDataIntegrityRepair: null,
  opsDeploymentHealthGate: null,
  opsPreflightVerification: null,
  opsDeploymentRunbook: null,
  opsIncidentPlaybook: null,
  opsRecoveryDrillResult: null,
  opsAsyncJobSummary: null,
  opsAsyncJobBootReconcile: null,
  opsAsyncJobIncidents: null,
  opsAsyncJobArtifactRetention: null,
  opsAsyncJobOperatorHistory: null,
  opsAsyncJobHandoffBundle: null,
  opsAsyncJobRemoteShipping: null,
  opsAsyncJobHandoffSla: null,
  opsAsyncJobAdapterValidation: null,
  opsAsyncJobAdapterHealthProbe: null,
  opsAsyncJobNotificationReceipts: null,
  opsAsyncNotificationRetryQueue: null,
  opsAsyncRetryPolicies: null,
  opsAsyncNotificationDeadLetterQueue: null,
  opsAsyncRetryOutcomeDashboard: null,
  opsAsyncJobs: [],
  opsRuntimeIncidentSnapshot: null,
  opsRuntimeReceipts: [],
  opsProviderRouting: null,
  opsProviderRollout: null,
  opsProviderRuntimeMetrics: null,
  opsSubscriptionAudit: null,
  opsAccountDetail: null,
  opsAccountWorkspace: null,
  opsAlertsFeed: null,
  opsAlertDetail: null,
  selectedOpsAlertId: null,
  opsGovernanceSnapshot: null,
  opsGovernanceExport: null,
  opsGovernanceDetail: null,
  opsInvestigationBundle: null,
  opsEvalMetrics: null,
  opsCrossPackQuality: null,
  opsLearnedDashboard: null,
  opsLearnedImpact: null,
  opsLearnedCadence: null,
  opsLearnedAssistedGate: null,
  opsLearnedAssistedRerank: null,
  opsLearnedReviewQuality: null,
  opsLearnedTrainingResult: null,
  opsLearnedEvidence: null,
  opsLearnedCompare: null,
  opsLearnedRollout: null,
  opsLearnedDataOps: null,
  opsLearnedPromotion: null,
  opsLearnedRerankerPromotion: null,
  opsPreferenceSamples: [],
  opsRankingSamples: [],
  opsLearnedDetail: null,
  opsLastActionImpact: null,
  opsReviewCaptureTarget: null,
};

const els = {
  appShell: document.querySelector("#app-shell"),
  modeReader: document.querySelector("#mode-reader"),
  modeAuthor: document.querySelector("#mode-author"),
  modeOps: document.querySelector("#mode-ops"),
  readerShell: document.querySelector("#reader-shell"),
  authorShell: document.querySelector("#author-shell"),
  opsShell: document.querySelector("#ops-shell"),
  apiStatus: document.querySelector("#api-status"),
  turnStatus: document.querySelector("#turn-status"),
  worldStatus: document.querySelector("#world-status"),
  sessionStatus: document.querySelector("#session-status"),
  worldVersionStatus: document.querySelector("#world-version-status"),
  accessTierStatus: document.querySelector("#access-tier-status"),
  quoteStatus: document.querySelector("#quote-status"),
  paywallBanner: document.querySelector("#paywall-banner"),
  paywallBannerCopy: document.querySelector("#paywall-banner-copy"),
  paywallBannerCheckout: document.querySelector("#paywall-banner-checkout"),
  readerIdInput: document.querySelector("#reader-id-input"),
  readerEntitlementType: document.querySelector("#reader-entitlement-type"),
  readerSubscriptionStatus: document.querySelector("#reader-subscription-status"),
  readerCreditBalance: document.querySelector("#reader-credit-balance"),
  readerWorldUnlockStatus: document.querySelector("#reader-world-unlock-status"),
  readerEntitlementReason: document.querySelector("#reader-entitlement-reason"),
  grantEntitlementType: document.querySelector("#grant-entitlement-type"),
  grantEntitlementBalance: document.querySelector("#grant-entitlement-balance"),
  readerRefreshEntitlements: document.querySelector("#reader-refresh-entitlements"),
  readerGrantEntitlement: document.querySelector("#reader-grant-entitlement"),
  readerStartCheckout: document.querySelector("#reader-start-checkout"),
  readerRetryPayment: document.querySelector("#reader-retry-payment"),
  readerRenewSubscription: document.querySelector("#reader-renew-subscription"),
  readerCancelSubscription: document.querySelector("#reader-cancel-subscription"),
  readerEntitlementList: document.querySelector("#reader-entitlement-list"),
  readerMembershipOffers: document.querySelector("#reader-membership-offers"),
  readerCheckoutStatus: document.querySelector("#reader-checkout-status"),
  worldGallery: document.querySelector("#world-gallery"),
  sessionLibrary: document.querySelector("#session-library"),
  previewRoute: document.querySelector("#preview-route"),
  stepSession: document.querySelector("#step-session"),
  resetOutput: document.querySelector("#reset-output"),
  viewExperience: document.querySelector("#view-experience"),
  viewStorybook: document.querySelector("#view-storybook"),
  viewBackstage: document.querySelector("#view-backstage"),
  experienceView: document.querySelector("#experience-view"),
  storybookView: document.querySelector("#storybook-view"),
  backstageView: document.querySelector("#backstage-view"),
  worldTitle: document.querySelector("#world-title"),
  worldDescription: document.querySelector("#world-description"),
  featuredWorldTitle: document.querySelector("#featured-world-title"),
  featuredWorldCopy: document.querySelector("#featured-world-copy"),
  featuredWorldMood: document.querySelector("#featured-world-mood"),
  featuredWorldHook: document.querySelector("#featured-world-hook"),
  worldId: document.querySelector("#world-id"),
  sessionId: document.querySelector("#session-id"),
  lastEventTitle: document.querySelector("#last-event-title"),
  suggestedInputs: document.querySelector("#suggested-inputs"),
  playerInput: document.querySelector("#player-input"),
  currentPressureText: document.querySelector("#current-pressure-text"),
  lastIntentText: document.querySelector("#last-intent-text"),
  suggestedPrefillText: document.querySelector("#suggested-prefill-text"),
  factCount: document.querySelector("#fact-count"),
  promiseCount: document.querySelector("#promise-count"),
  tensionValue: document.querySelector("#tension-value"),
  sceneWindow: document.querySelector("#scene-window"),
  chosenEventTitle: document.querySelector("#chosen-event-title"),
  chapterPanel: document.querySelector("#chapter-panel"),
  bestRoute: document.querySelector("#best-route"),
  storyFeed: document.querySelector("#story-feed"),
  routePreview: document.querySelector("#route-preview"),
  routePreviewPanel: document.querySelector("#route-preview-panel"),
  candidateSummary: document.querySelector("#candidate-summary"),
  scoredCandidates: document.querySelector("#scored-candidates"),
  criticTrace: document.querySelector("#critic-trace"),
  replayTimeline: document.querySelector("#replay-timeline"),
  storyHero: document.querySelector("#story-hero"),
  storyTitle: document.querySelector("#story-title"),
  storyCaption: document.querySelector("#story-caption"),
  storyQuote: document.querySelector("#story-quote"),
  storyPrompt: document.querySelector("#story-prompt"),
  storyMotif: document.querySelector("#story-motif"),
  storyBeats: document.querySelector("#story-beats"),
  storyDetails: document.querySelector("#story-details"),
  storyProse: document.querySelector("#story-prose"),
  storySequence: document.querySelector("#story-sequence"),
  authorCreateDraft: document.querySelector("#author-create-draft"),
  authorCreateDraftFromBrief: document.querySelector("#author-create-draft-from-brief"),
  authorRefresh: document.querySelector("#author-refresh"),
  authorAccountId: document.querySelector("#author-account-id"),
  authorAuthActorId: document.querySelector("#author-auth-actor-id"),
  authorAuthRole: document.querySelector("#author-auth-role"),
  authorAuthDisplayName: document.querySelector("#author-auth-display-name"),
  authorAuthPassword: document.querySelector("#author-auth-password"),
  authorAuthRegister: document.querySelector("#author-auth-register"),
  authorAuthLogin: document.querySelector("#author-auth-login"),
  authorAuthLogout: document.querySelector("#author-auth-logout"),
  authorAuthStatus: document.querySelector("#author-auth-status"),
  authorActiveDraft: document.querySelector("#author-active-draft"),
  authorValidationStatus: document.querySelector("#author-validation-status"),
  authorSimulationChapters: document.querySelector("#author-simulation-chapters"),
  authorTier: document.querySelector("#author-tier"),
  authorStudioCredits: document.querySelector("#author-studio-credits"),
  authorBriefAccess: document.querySelector("#author-brief-access"),
  authorSimulateAccess: document.querySelector("#author-simulate-access"),
  authorWorkflow: document.querySelector("#author-workflow"),
  authorGenrePreset: document.querySelector("#author-genre-preset"),
  authorWorldTitle: document.querySelector("#author-world-title"),
  authorLeadName: document.querySelector("#author-lead-name"),
  authorCounterpartName: document.querySelector("#author-counterpart-name"),
  authorSupportingName: document.querySelector("#author-supporting-name"),
  authorLifeTheme: document.querySelector("#author-life-theme"),
  authorCorePremise: document.querySelector("#author-core-premise"),
  authorLocations: document.querySelector("#author-locations"),
  authorDraftList: document.querySelector("#author-draft-list"),
  authorDraftDetail: document.querySelector("#author-draft-detail"),
  authorValidationReport: document.querySelector("#author-validation-report"),
  authorSimulationReport: document.querySelector("#author-simulation-report"),
  authorAssetDiff: document.querySelector("#author-asset-diff"),
  authorCompare: document.querySelector("#author-compare"),
  authorVersionHistory: document.querySelector("#author-version-history"),
  authorCollaboration: document.querySelector("#author-collaboration"),
  authorReviewerInbox: document.querySelector("#author-reviewer-inbox"),
  authorCharacterSelect: document.querySelector("#author-character-select"),
  authorCharacterName: document.querySelector("#author-character-name"),
  authorCharacterRole: document.querySelector("#author-character-role"),
  authorCharacterLifeTheme: document.querySelector("#author-character-life-theme"),
  authorCharacterCoreWound: document.querySelector("#author-character-core-wound"),
  authorCharacterPublicSelf: document.querySelector("#author-character-public-self"),
  authorCharacterShadowDesire: document.querySelector("#author-character-shadow-desire"),
  authorCharacterVows: document.querySelector("#author-character-vows"),
  authorSaveCharacter: document.querySelector("#author-save-character"),
  authorSceneSelect: document.querySelector("#author-scene-select"),
  authorSceneId: document.querySelector("#author-scene-id"),
  authorSceneFunction: document.querySelector("#author-scene-function"),
  authorSceneRequiredRoles: document.querySelector("#author-scene-required-roles"),
  authorSceneBeats: document.querySelector("#author-scene-beats"),
  authorSaveScene: document.querySelector("#author-save-scene"),
  authorVoiceEditor: document.querySelector("#author-voice-editor"),
  authorActionEditor: document.querySelector("#author-action-editor"),
  authorSensoryEditor: document.querySelector("#author-sensory-editor"),
  authorSceneEditor: document.querySelector("#author-scene-editor"),
  authorStyleLexicon: document.querySelector("#author-style-lexicon"),
  authorThemeLabels: document.querySelector("#author-theme-labels"),
  authorHookTemplates: document.querySelector("#author-hook-templates"),
  authorPacingRequireTurnTaking: document.querySelector("#author-pacing-require-turn-taking"),
  authorPacingRequireCounterReaction: document.querySelector("#author-pacing-require-counter-reaction"),
  authorPacingMinTurns: document.querySelector("#author-pacing-min-turns"),
  authorPacingMaxTurns: document.querySelector("#author-pacing-max-turns"),
  authorPacingMinimumExchanges: document.querySelector("#author-pacing-minimum-exchanges"),
  authorPacingTurnPattern: document.querySelector("#author-pacing-turn-pattern"),
  authorSceneHooks: document.querySelector("#author-scene-hooks"),
  authorSaveCapabilities: document.querySelector("#author-save-capabilities"),
  authorSaveStyleControls: document.querySelector("#author-save-style-controls"),
  authorCommentAnchorType: document.querySelector("#author-comment-anchor-type"),
  authorCommentAnchorKey: document.querySelector("#author-comment-anchor-key"),
  authorCommentSeverity: document.querySelector("#author-comment-severity"),
  authorCommentAssignee: document.querySelector("#author-comment-assignee"),
  authorInboxReviewerId: document.querySelector("#author-inbox-reviewer-id"),
  authorInboxStatusFilter: document.querySelector("#author-inbox-status-filter"),
  authorInboxWorldVersionFilter: document.querySelector("#author-inbox-world-version-filter"),
  authorInboxNotificationTypeFilter: document.querySelector("#author-inbox-notification-type-filter"),
  authorInboxBlockingOnly: document.querySelector("#author-inbox-blocking-only"),
  authorInboxSearch: document.querySelector("#author-inbox-search"),
  authorRefreshReviewerInbox: document.querySelector("#author-refresh-reviewer-inbox"),
  authorSearchReviewerInbox: document.querySelector("#author-search-reviewer-inbox"),
  authorLoadMoreReviewerInbox: document.querySelector("#author-load-more-reviewer-inbox"),
  authorBulkReadVisible: document.querySelector("#author-bulk-read-visible"),
  authorBulkArchiveVisible: document.querySelector("#author-bulk-archive-visible"),
  authorDraftWatcherId: document.querySelector("#author-draft-watcher-id"),
  authorAddDraftWatcher: document.querySelector("#author-add-draft-watcher"),
  authorRemoveDraftWatcher: document.querySelector("#author-remove-draft-watcher"),
  authorNotificationPrefType: document.querySelector("#author-notification-pref-type"),
  authorNotificationPrefInApp: document.querySelector("#author-notification-pref-in-app"),
  authorNotificationPrefAsync: document.querySelector("#author-notification-pref-async"),
  authorNotificationPrefSink: document.querySelector("#author-notification-pref-sink"),
  authorNotificationPrefTarget: document.querySelector("#author-notification-pref-target"),
  authorRefreshNotificationPreferences: document.querySelector("#author-refresh-notification-preferences"),
  authorSaveNotificationPreference: document.querySelector("#author-save-notification-preference"),
  authorNotificationPreferences: document.querySelector("#author-notification-preferences"),
  authorCommentBody: document.querySelector("#author-comment-body"),
  authorApprovalReviewer: document.querySelector("#author-approval-reviewer"),
  authorApprovalReason: document.querySelector("#author-approval-reason"),
  authorCreateCommentThread: document.querySelector("#author-create-comment-thread"),
  authorRequestApproval: document.querySelector("#author-request-approval"),
  authorApproveDraft: document.querySelector("#author-approve-draft"),
  authorRequestChanges: document.querySelector("#author-request-changes"),
  opsRefresh: document.querySelector("#ops-refresh"),
  opsNavAccountId: document.querySelector("#ops-nav-account-id"),
  opsNavWorldId: document.querySelector("#ops-nav-world-id"),
  opsNavCaseId: document.querySelector("#ops-nav-case-id"),
  opsNavAlertId: document.querySelector("#ops-nav-alert-id"),
  opsSyncNavigation: document.querySelector("#ops-sync-navigation"),
  opsFollowRecommendation: document.querySelector("#ops-follow-recommendation"),
  opsNavigationSummary: document.querySelector("#ops-navigation-summary"),
  opsNavigationTargets: document.querySelector("#ops-navigation-targets"),
  opsNavigationActions: document.querySelector("#ops-navigation-actions"),
  opsPendingCount: document.querySelector("#ops-pending-count"),
  opsPublishedWorlds: document.querySelector("#ops-published-worlds"),
  opsTotalCost: document.querySelector("#ops-total-cost"),
  opsReviewQueue: document.querySelector("#ops-review-queue"),
  opsWorldStatus: document.querySelector("#ops-world-status"),
  opsReleaseWorldId: document.querySelector("#ops-release-world-id"),
  opsRefreshReleaseWorkspace: document.querySelector("#ops-refresh-release-workspace"),
  opsReleaseWorkspaceSummary: document.querySelector("#ops-release-workspace-summary"),
  opsReleaseWorkspaceActions: document.querySelector("#ops-release-workspace-actions"),
  opsReleaseWorkspaceTimeline: document.querySelector("#ops-release-workspace-timeline"),
  opsReleaseWorkspaceDetails: document.querySelector("#ops-release-workspace-details"),
  opsReviewHistory: document.querySelector("#ops-review-history"),
  opsQualityTrend: document.querySelector("#ops-quality-trend"),
  opsSchemaLifecycle: document.querySelector("#ops-schema-lifecycle"),
  opsDataIntegrityActions: document.querySelector("#ops-data-integrity-actions"),
  opsRunDataIntegrityDryRun: document.querySelector("#ops-run-data-integrity-dry-run"),
  opsApplyDataIntegrityRepair: document.querySelector("#ops-apply-data-integrity-repair"),
  opsDataIntegrity: document.querySelector("#ops-data-integrity"),
  opsBackupLabel: document.querySelector("#ops-backup-label"),
  opsRestorePath: document.querySelector("#ops-restore-path"),
  opsRestoreRequestId: document.querySelector("#ops-restore-request-id"),
  opsRestoreRequesterId: document.querySelector("#ops-restore-requester-id"),
  opsRestoreApproverId: document.querySelector("#ops-restore-approver-id"),
  opsRestoreReason: document.querySelector("#ops-restore-reason"),
  opsCreateRuntimeBackup: document.querySelector("#ops-create-runtime-backup"),
  opsRestoreRuntimeBackup: document.querySelector("#ops-restore-runtime-backup"),
  opsRunRecoveryDrill: document.querySelector("#ops-run-recovery-drill"),
  opsRequestRuntimeRestore: document.querySelector("#ops-request-runtime-restore"),
  opsApproveRuntimeRestore: document.querySelector("#ops-approve-runtime-restore"),
  opsRevokeRuntimeRestore: document.querySelector("#ops-revoke-runtime-restore"),
  opsExecuteRuntimeRestore: document.querySelector("#ops-execute-runtime-restore"),
  opsDeploymentHealthGate: document.querySelector("#ops-deployment-health-gate"),
  opsPreflightVerification: document.querySelector("#ops-preflight-verification"),
  opsDeploymentRunbook: document.querySelector("#ops-deployment-runbook"),
  opsIncidentPlaybook: document.querySelector("#ops-incident-playbook"),
  opsAsyncJobId: document.querySelector("#ops-async-job-id"),
  opsAsyncJobNote: document.querySelector("#ops-async-job-note"),
  opsNotificationReceiptId: document.querySelector("#ops-notification-receipt-id"),
  opsExportHandoffBundle: document.querySelector("#ops-export-handoff-bundle"),
  opsAcknowledgeAsyncJob: document.querySelector("#ops-acknowledge-async-job"),
  opsShipRemoteArtifacts: document.querySelector("#ops-ship-remote-artifacts"),
  opsEscalateHandoffSla: document.querySelector("#ops-escalate-handoff-sla"),
  opsEnqueueNotificationRetry: document.querySelector("#ops-enqueue-notification-retry"),
  opsProcessNotificationRetry: document.querySelector("#ops-process-notification-retry"),
  opsRetryAsyncJob: document.querySelector("#ops-retry-async-job"),
  opsResumeAsyncJob: document.querySelector("#ops-resume-async-job"),
  opsRecoverAsyncJobs: document.querySelector("#ops-recover-async-jobs"),
  opsEnforceAsyncRetention: document.querySelector("#ops-enforce-async-retention"),
  opsRunColdStartDrill: document.querySelector("#ops-run-cold-start-drill"),
  opsAsyncJobSummary: document.querySelector("#ops-async-job-summary"),
  opsAsyncJobBootReconcile: document.querySelector("#ops-async-job-boot-reconcile"),
  opsAsyncJobIncidents: document.querySelector("#ops-async-job-incidents"),
  opsAsyncJobArtifactRetention: document.querySelector("#ops-async-job-artifact-retention"),
  opsAsyncJobOperatorHistory: document.querySelector("#ops-async-job-operator-history"),
  opsAsyncJobHandoffBundle: document.querySelector("#ops-async-job-handoff-bundle"),
  opsAsyncJobAdapterValidation: document.querySelector("#ops-async-job-adapter-validation"),
  opsAsyncJobAdapterHealthProbe: document.querySelector("#ops-async-job-adapter-health-probe"),
  opsAsyncJobNotificationReceipts: document.querySelector("#ops-async-job-notification-receipts"),
  opsAsyncNotificationRetryQueue: document.querySelector("#ops-async-job-notification-retry-queue"),
  opsAsyncNotificationDeadLetterQueue: document.querySelector("#ops-async-job-dead-letter-queue"),
  opsAsyncRetryOutcomeDashboard: document.querySelector("#ops-async-job-retry-outcome-dashboard"),
  opsAsyncJobs: document.querySelector("#ops-async-jobs"),
  opsRuntimeIncidentSnapshot: document.querySelector("#ops-runtime-incident-snapshot"),
  opsRuntimeReceipts: document.querySelector("#ops-runtime-receipts"),
  opsProviderRouting: document.querySelector("#ops-provider-routing"),
  opsProviderRollout: document.querySelector("#ops-provider-rollout"),
  opsProviderRolloutReviewerId: document.querySelector("#ops-provider-rollout-reviewer-id"),
  opsProviderRolloutReason: document.querySelector("#ops-provider-rollout-reason"),
  opsProviderRolloutBucket: document.querySelector("#ops-provider-rollout-bucket"),
  opsProviderRolloutWorldAllowlist: document.querySelector("#ops-provider-rollout-world-allowlist"),
  opsProviderCandidateCanary: document.querySelector("#ops-provider-candidate-canary"),
  opsProviderCandidateActivate: document.querySelector("#ops-provider-candidate-activate"),
  opsProviderCandidateRollback: document.querySelector("#ops-provider-candidate-rollback"),
  opsProviderRendererCanary: document.querySelector("#ops-provider-renderer-canary"),
  opsProviderRendererActivate: document.querySelector("#ops-provider-renderer-activate"),
  opsProviderRendererRollback: document.querySelector("#ops-provider-renderer-rollback"),
  opsProviderRuntimeMetrics: document.querySelector("#ops-provider-runtime-metrics"),
  opsMeterList: document.querySelector("#ops-meter-list"),
  opsAccountId: document.querySelector("#ops-account-id"),
  opsWalletType: document.querySelector("#ops-wallet-type"),
  opsTierId: document.querySelector("#ops-tier-id"),
  opsWalletAmount: document.querySelector("#ops-wallet-amount"),
  opsSubscriptionStatus: document.querySelector("#ops-subscription-status"),
  opsEntitlementId: document.querySelector("#ops-entitlement-id"),
  opsEntitlementReason: document.querySelector("#ops-entitlement-reason"),
  opsBillingEventId: document.querySelector("#ops-billing-event-id"),
  opsGrantSubscription: document.querySelector("#ops-grant-subscription"),
  opsChangeSubscriptionState: document.querySelector("#ops-change-subscription-state"),
  opsGrantWallet: document.querySelector("#ops-grant-wallet"),
  opsDebitWallet: document.querySelector("#ops-debit-wallet"),
  opsRevokeEntitlement: document.querySelector("#ops-revoke-entitlement"),
  opsReconcileSubscription: document.querySelector("#ops-reconcile-subscription"),
  opsRetrySubscriptionPayment: document.querySelector("#ops-retry-subscription-payment"),
  opsReplayBillingEvent: document.querySelector("#ops-replay-billing-event"),
  opsSubscriptionAudit: document.querySelector("#ops-subscription-audit"),
  opsSubscriptionTimeline: document.querySelector("#ops-subscription-timeline"),
  opsAccountWorkspaceSummary: document.querySelector("#ops-account-workspace-summary"),
  opsAccountWorkspaceActions: document.querySelector("#ops-account-workspace-actions"),
  opsAccountWorkspaceTimeline: document.querySelector("#ops-account-workspace-timeline"),
  opsAccountDetail: document.querySelector("#ops-account-detail"),
  opsAccountActivity: document.querySelector("#ops-account-activity"),
  opsSupportSummary: document.querySelector("#ops-support-summary"),
  opsSupportIssues: document.querySelector("#ops-support-issues"),
  opsAlertAccountId: document.querySelector("#ops-alert-account-id"),
  opsAlertStatusFilter: document.querySelector("#ops-alert-status-filter"),
  opsAlertSeverityFilter: document.querySelector("#ops-alert-severity-filter"),
  opsAlertNote: document.querySelector("#ops-alert-note"),
  opsRefreshAlerts: document.querySelector("#ops-refresh-alerts"),
  opsAcknowledgeAlert: document.querySelector("#ops-acknowledge-alert"),
  opsResolveAlert: document.querySelector("#ops-resolve-alert"),
  opsOpenAlertInvestigation: document.querySelector("#ops-open-alert-investigation"),
  opsAlertSummary: document.querySelector("#ops-alert-summary"),
  opsAlertFeed: document.querySelector("#ops-alert-feed"),
  opsAlertDetail: document.querySelector("#ops-alert-detail"),
  opsGovernanceCaseId: document.querySelector("#ops-governance-case-id"),
  opsGovernanceCaseType: document.querySelector("#ops-governance-case-type"),
  opsGovernanceTargetType: document.querySelector("#ops-governance-target-type"),
  opsGovernanceTargetId: document.querySelector("#ops-governance-target-id"),
  opsGovernanceSeverity: document.querySelector("#ops-governance-severity"),
  opsGovernanceReviewerId: document.querySelector("#ops-governance-reviewer-id"),
  opsGovernanceOwnerId: document.querySelector("#ops-governance-owner-id"),
  opsGovernanceSummaryInput: document.querySelector("#ops-governance-summary-input"),
  opsGovernanceNotes: document.querySelector("#ops-governance-notes"),
  opsGovernanceStatus: document.querySelector("#ops-governance-status"),
  opsGovernanceDueAt: document.querySelector("#ops-governance-due-at"),
  opsGovernancePolicyLabels: document.querySelector("#ops-governance-policy-labels"),
  opsGovernanceDisposition: document.querySelector("#ops-governance-disposition"),
  opsGovernanceEvidenceTitle: document.querySelector("#ops-governance-evidence-title"),
  opsGovernanceEvidencePreview: document.querySelector("#ops-governance-evidence-preview"),
  opsGovernanceRestrictionType: document.querySelector("#ops-governance-restriction-type"),
  opsGovernanceRestrictionExpiresAt: document.querySelector("#ops-governance-restriction-expires-at"),
  opsCreateGovernanceCase: document.querySelector("#ops-create-governance-case"),
  opsAssignGovernanceCase: document.querySelector("#ops-assign-governance-case"),
  opsAddGovernanceEvidence: document.querySelector("#ops-add-governance-evidence"),
  opsUpdateGovernanceCase: document.querySelector("#ops-update-governance-case"),
  opsApplyGovernanceRestriction: document.querySelector("#ops-apply-governance-restriction"),
  opsReleaseGovernanceRestriction: document.querySelector("#ops-release-governance-restriction"),
  opsExportGovernanceAudit: document.querySelector("#ops-export-governance-audit"),
  opsGovernanceSummary: document.querySelector("#ops-governance-summary"),
  opsGovernanceCases: document.querySelector("#ops-governance-cases"),
  opsGovernanceExport: document.querySelector("#ops-governance-export"),
  opsGovernanceDetail: document.querySelector("#ops-governance-detail"),
  opsAccountAuditSummary: document.querySelector("#ops-account-audit-summary"),
  opsAccountAuditTrail: document.querySelector("#ops-account-audit-trail"),
  opsInvestigationAccountId: document.querySelector("#ops-investigation-account-id"),
  opsInvestigationWorldVersionId: document.querySelector("#ops-investigation-world-version-id"),
  opsInvestigationCaseId: document.querySelector("#ops-investigation-case-id"),
  opsRunInvestigation: document.querySelector("#ops-run-investigation"),
  opsExportInvestigationTrace: document.querySelector("#ops-export-investigation-trace"),
  opsInvestigationSummary: document.querySelector("#ops-investigation-summary"),
  opsInvestigationTimeline: document.querySelector("#ops-investigation-timeline"),
  opsInvestigationEvidence: document.querySelector("#ops-investigation-evidence"),
  opsEvalMetrics: document.querySelector("#ops-eval-metrics"),
  opsCrossPackQuality: document.querySelector("#ops-cross-pack-quality"),
  opsLearnedDashboard: document.querySelector("#ops-learned-dashboard"),
  opsLearnedImpact: document.querySelector("#ops-learned-impact"),
  opsLearnedCadence: document.querySelector("#ops-learned-cadence"),
  opsLearnedAssistedGate: document.querySelector("#ops-learned-assisted-gate"),
  opsLearnedAssistedRerank: document.querySelector("#ops-learned-assisted-rerank"),
  opsLearnedReviewQuality: document.querySelector("#ops-learned-review-quality"),
  opsAssistedGateReviewerId: document.querySelector("#ops-assisted-gate-reviewer-id"),
  opsAssistedGateReason: document.querySelector("#ops-assisted-gate-reason"),
  opsAssistedGateBucket: document.querySelector("#ops-assisted-gate-bucket"),
  opsAssistedGateConfidence: document.querySelector("#ops-assisted-gate-confidence"),
  opsAssistedGateWorldAllowlist: document.querySelector("#ops-assisted-gate-world-allowlist"),
  opsSetAssistedShadow: document.querySelector("#ops-set-assisted-shadow"),
  opsSetAssistedActive: document.querySelector("#ops-set-assisted-active"),
  opsDisableAssistedGate: document.querySelector("#ops-disable-assisted-gate"),
  opsAssistedRerankReviewerId: document.querySelector("#ops-assisted-rerank-reviewer-id"),
  opsAssistedRerankReason: document.querySelector("#ops-assisted-rerank-reason"),
  opsAssistedRerankBucket: document.querySelector("#ops-assisted-rerank-bucket"),
  opsAssistedRerankConfidence: document.querySelector("#ops-assisted-rerank-confidence"),
  opsAssistedRerankCandidateWindow: document.querySelector("#ops-assisted-rerank-candidate-window"),
  opsAssistedRerankMaxScoreGap: document.querySelector("#ops-assisted-rerank-max-score-gap"),
  opsAssistedRerankWorldAllowlist: document.querySelector("#ops-assisted-rerank-world-allowlist"),
  opsSetAssistedRerankShadow: document.querySelector("#ops-set-assisted-rerank-shadow"),
  opsSetAssistedRerankActive: document.querySelector("#ops-set-assisted-rerank-active"),
  opsDisableAssistedRerank: document.querySelector("#ops-disable-assisted-rerank"),
  opsRunEvaluatorTraining: document.querySelector("#ops-run-evaluator-training"),
  opsRunRerankerTraining: document.querySelector("#ops-run-reranker-training"),
  opsRunBothTraining: document.querySelector("#ops-run-both-training"),
  opsLearnedTraining: document.querySelector("#ops-learned-training"),
  opsLearnedEvidence: document.querySelector("#ops-learned-evidence"),
  opsLearnedCompare: document.querySelector("#ops-learned-compare"),
  opsLearnedRollout: document.querySelector("#ops-learned-rollout"),
  opsLearnedDataOps: document.querySelector("#ops-learned-data-ops"),
  opsLearnedPromotion: document.querySelector("#ops-learned-promotion"),
  opsLearnedRerankerPromotion: document.querySelector("#ops-learned-reranker-promotion"),
  opsPromotionReviewerId: document.querySelector("#ops-promotion-reviewer-id"),
  opsPromotionReason: document.querySelector("#ops-promotion-reason"),
  opsApprovePromotion: document.querySelector("#ops-approve-promotion"),
  opsRevokePromotion: document.querySelector("#ops-revoke-promotion"),
  opsRerankerPromotionReviewerId: document.querySelector("#ops-reranker-promotion-reviewer-id"),
  opsRerankerPromotionReason: document.querySelector("#ops-reranker-promotion-reason"),
  opsApproveRerankerPromotion: document.querySelector("#ops-approve-reranker-promotion"),
  opsRevokeRerankerPromotion: document.querySelector("#ops-revoke-reranker-promotion"),
  opsLearnedWorlds: document.querySelector("#ops-learned-worlds"),
  opsLearnedIssues: document.querySelector("#ops-learned-issues"),
  opsLearnedDetail: document.querySelector("#ops-learned-detail"),
  opsReviewSampleBacklog: document.querySelector("#ops-review-sample-backlog"),
  opsPairCoverageBacklog: document.querySelector("#ops-pair-coverage-backlog"),
  opsReviewCaptureContext: document.querySelector("#ops-review-capture-context"),
  opsLastActionImpact: document.querySelector("#ops-last-action-impact"),
  opsReviewerId: document.querySelector("#ops-reviewer-id"),
  opsReviewScore: document.querySelector("#ops-review-score"),
  opsReviewIssueCodes: document.querySelector("#ops-review-issue-codes"),
  opsReviewNotes: document.querySelector("#ops-review-notes"),
  opsReviewWouldContinue: document.querySelector("#ops-review-would-continue"),
  opsReviewWouldPay: document.querySelector("#ops-review-would-pay"),
  opsSubmitReviewCapture: document.querySelector("#ops-submit-review-capture"),
  opsPreferenceLeftRevisionId: document.querySelector("#ops-preference-left-revision-id"),
  opsPreferenceRightRevisionId: document.querySelector("#ops-preference-right-revision-id"),
  opsPreferencePreferredRevisionId: document.querySelector("#ops-preference-preferred-revision-id"),
  opsPreferenceStrength: document.querySelector("#ops-preference-strength"),
  opsPreferenceNotes: document.querySelector("#ops-preference-notes"),
  opsSubmitPreferenceCapture: document.querySelector("#ops-submit-preference-capture"),
  opsPreferenceSamples: document.querySelector("#ops-preference-samples"),
  opsRankingRevisionIds: document.querySelector("#ops-ranking-revision-ids"),
  opsRankingNotes: document.querySelector("#ops-ranking-notes"),
  opsSubmitRankingCapture: document.querySelector("#ops-submit-ranking-capture"),
  opsRankingSamples: document.querySelector("#ops-ranking-samples"),
  tonePills: [...document.querySelectorAll(".tone-pill")],
  suggestionTemplate: document.querySelector("#suggested-input-template"),
  listCardTemplate: document.querySelector("#list-card-template"),
};

async function api(path, options = {}) {
  const shouldAttachAuthorToken =
    Boolean(appState.authorAuthSession?.accessToken) &&
    (
      path.startsWith("/v1/author") ||
      path.startsWith("/v1/ops") ||
      (path.startsWith("/v1/auth") && !path.startsWith("/v1/auth/login") && !path.startsWith("/v1/auth/register"))
    );
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(shouldAttachAuthorToken ? { Authorization: `Bearer ${appState.authorAuthSession.accessToken}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch (error) {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return response.json();
}

function parseErrorDetail(error) {
  try {
    return JSON.parse(error.message);
  } catch (_error) {
    return null;
  }
}

function setBusy(button, busyLabel) {
  const previous = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  return () => {
    button.disabled = false;
    button.textContent = previous;
  };
}

function clearNode(node, emptyText = "") {
  node.innerHTML = "";
  if (emptyText) {
    node.classList.add("empty-state");
    node.textContent = emptyText;
  } else {
    node.classList.remove("empty-state");
  }
}

function createListCard({ title, score = "", body = "", active = false }) {
  const card = document.createElement("article");
  card.className = "list-card";
  if (active) {
    card.classList.add("is-active");
  }
  card.innerHTML = `
    <div class="list-card-head">
      <h3>${title}</h3>
      <span class="list-card-score">${score}</span>
    </div>
    <p class="list-card-body">${body}</p>
  `;
  return card;
}

function latestAsyncJob(jobType) {
  return (appState.opsAsyncJobs || []).find((item) => item.job_type === jobType) || null;
}

function formatTimestamp(value) {
  if (!value) return "未知时间";
  try {
    return new Date(value).toLocaleString("zh-CN");
  } catch (error) {
    return value;
  }
}

function downloadJsonFile(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function getActiveDraftWorldpack() {
  return appState.activeDraftDetail?.worldpack_json || appState.activeDraftDetail?.worldpack || null;
}

function getActiveRevisionHistory() {
  return appState.activeDraftDetail?.revision_history || getActiveDraftWorldpack()?.metadata?.revision_history || [];
}

function getLatestDiffSummary() {
  return appState.activeDraftDetail?.latest_diff_summary || getActiveDraftWorldpack()?.metadata?.latest_diff_summary || {};
}

function getDiffDrilldown() {
  return appState.activeDraftDetail?.diff_drilldown || {};
}

function getSimulationDrilldown() {
  return (
    appState.authorSimulationReport?.simulation_drilldown ||
    appState.activeDraftDetail?.simulation_drilldown ||
    {}
  );
}

function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(0)}%`;
}

function parseIssueCodes(value) {
  return String(value || "")
    .split(/[\s,，]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseTagList(value) {
  return String(value || "")
    .split(/[\s,，]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function currentTierCatalog() {
  return (
    appState.readerSubscription?.tiers ||
    appState.opsSubscriptionAudit?.tiers ||
    []
  );
}

function tierLabel(tierId) {
  const tier = currentTierCatalog().find((item) => item.tier_id === tierId);
  return tier?.display_name || tierId || "-";
}

function accessReasonLabel(reason) {
  return {
    trial_chapter: "试读章节",
    grace_window: "宽限章节",
    continue_requires_entitlement: "需要更高权限",
    subscriber_active: "会员已生效",
    subscription_active: "会员已生效",
    subscription_required: "需要 Creator/Studio 会员",
    world_pass_active: "世界已解锁",
    credits_balance: "Story Credits 可用",
    credits_consumed: "已消耗 Story Credits",
    credits_exhausted: "Story Credits 已耗尽",
    studio_credits_balance: "Studio Credits 可用",
    studio_credits_exhausted: "Studio Credits 已耗尽",
    author_tier_required: "当前会员档位不支持创作",
    entitlement_expired: "权益已过期",
    missing_reader: "缺少 reader_id",
    missing_account: "缺少 account_id",
  }[reason] || reason || "-";
}

function worldUnlockLabel(paywall) {
  if (!appState.worldId) return "-";
  if (!paywall) return "试读中";
  if (paywall.entitlement_type === "subscriber") return `${paywall.tier_id || "会员"} 已解锁`;
  if (paywall.entitlement_type === "world_pass") return "world pass 已解锁";
  if (paywall.entitlement_type === "credits") return paywall.required ? "需消耗 Story Credits" : "Story Credits 可继续";
  if (!paywall.required) return "试读中";
  return "未解锁";
}

function gatingStatusLabel(access) {
  if (!access) return "-";
  if (access.allowed === true || access.required === false) {
    return "可用";
  }
  return `受限 · ${accessReasonLabel(access.reason)}`;
}

function gatingHint(access) {
  if (!access) return "-";
  const tierText = access.required_display_name || tierLabel(access.required_tier);
  const balanceText = access.balance !== null && access.balance !== undefined ? Number(access.balance).toFixed(0) : "-";
  const unitsText = access.required_units !== null && access.required_units !== undefined ? ` · 需要 ${Number(access.required_units).toFixed(0)}` : "";
  return `${gatingStatusLabel(access)} · ${tierText || "-"} · ${access.wallet_type || "-"} · 余额 ${balanceText}${unitsText}`;
}

function alertAuthorGating(errorDetail, actionLabel) {
  alert(`当前不能${actionLabel}：${accessReasonLabel(errorDetail.reason)}。需要 ${errorDetail.required_display_name || tierLabel(errorDetail.required_tier)}，当前 ${errorDetail.wallet_type || "-"} 余额 ${Number(errorDetail.balance || 0).toFixed(0)}${errorDetail.required_units !== undefined ? ` / 需要 ${Number(errorDetail.required_units).toFixed(0)}` : ""}。`);
}

function authorStageLabel(stage) {
  return {
    brief: "写 Brief",
    draft_created: "创建 Draft",
    validated: "校验通过",
    simulated: "完成 Simulation",
    revised_after_simulation: "修改后待重跑",
    ready_to_submit: "准备送审",
    submitted: "已提交审核",
  }[stage] || stage || "-";
}

function focusAuthorPanel(panelKey) {
  const mapping = {
    workflow: els.authorWorkflow,
    draft_detail: els.authorDraftDetail,
    validation: els.authorValidationReport,
    simulation: els.authorSimulationReport,
    diff: els.authorAssetDiff,
    compare: els.authorCompare,
    collaboration: els.authorCollaboration,
    version_history: els.authorVersionHistory,
    brief: els.authorCorePremise,
  };
  const target = mapping[panelKey];
  const node = target?.closest(".panel") || target;
  node?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function prefillAuthorCommentAnchor(anchorType, anchorKey) {
  if (els.authorCommentAnchorType) {
    els.authorCommentAnchorType.value = anchorType || "draft";
  }
  if (els.authorCommentAnchorKey) {
    els.authorCommentAnchorKey.value = anchorKey || "";
  }
  focusAuthorPanel("collaboration");
}

function activeAuthorReviewerId() {
  return (
    els.authorInboxReviewerId?.value.trim() ||
    (appState.authorAuthSession?.identity?.actor_role === "reviewer" ? appState.authorAuthSession.identity.actor_id : "") ||
    els.authorApprovalReviewer?.value.trim() ||
    els.authorAccountId?.value.trim() ||
    "ops_author_reviewer"
  );
}

function activeAuthorActorId(options = {}) {
  if (options.preferReviewer) {
    return activeAuthorReviewerId() || els.authorAccountId?.value.trim() || "ops_author_reviewer";
  }
  return appState.authorAuthSession?.identity?.actor_id || els.authorAccountId?.value.trim() || activeAuthorReviewerId() || "web_author";
}

function activeAuthorActorRole(actorId = activeAuthorActorId()) {
  if (appState.authorAuthSession?.identity?.actor_role) {
    return appState.authorAuthSession.identity.actor_role;
  }
  const draftAuthorId = appState.activeDraftDetail?.worldpack?.manifest?.author_id || "";
  return actorId && draftAuthorId && actorId === draftAuthorId ? "author" : "reviewer";
}

function currentAuthorInboxFilters() {
  return {
    reviewerId: activeAuthorReviewerId(),
    statusFilter: els.authorInboxStatusFilter?.value || "all",
    worldVersionId: els.authorInboxWorldVersionFilter?.value.trim() || "",
    notificationType: els.authorInboxNotificationTypeFilter?.value || "",
    blockingOnly: Boolean(els.authorInboxBlockingOnly?.checked),
    query: (els.authorInboxSearch?.value || "").trim(),
  };
}

function authorCollaborationHeaders(options = {}) {
  const actorId = options.actorId || (options.preferReviewer ? activeAuthorReviewerId() : activeAuthorActorId(options));
  const actorRole = options.actorRole || (options.preferReviewer ? "reviewer" : activeAuthorActorRole(actorId));
  const accountId = els.authorAccountId?.value.trim() || "";
  return {
    "X-NarrativeOS-Actor-Id": actorId,
    "X-NarrativeOS-Actor-Role": actorRole,
    ...(accountId ? { "X-NarrativeOS-Account-Id": accountId } : {}),
  };
}

async function selectAuthorThread(threadId, worldVersionId = "") {
  appState.selectedAuthorThreadId = threadId || null;
  if (worldVersionId && worldVersionId !== appState.activeDraftVersionId) {
    appState.activeDraftVersionId = worldVersionId;
    await refreshAuthorSurface();
    return;
  }
  renderAuthorReports();
  focusAuthorPanel("collaboration");
}

function mergeAuthorReviewerInbox(existing, nextPayload) {
  if (!existing) {
    return nextPayload;
  }
  const mergedNotifications = [...(existing.notifications || []), ...(nextPayload.notifications || [])];
  const seen = new Set();
  const uniqueNotifications = [];
  for (const item of mergedNotifications) {
    if (!item?.notification_id || seen.has(item.notification_id)) continue;
    seen.add(item.notification_id);
    uniqueNotifications.push(item);
  }
  return {
    ...existing,
    filters: nextPayload.filters || existing.filters,
    has_more: nextPayload.has_more,
    next_cursor: nextPayload.next_cursor,
    returned_count: uniqueNotifications.length,
    notifications: uniqueNotifications,
    unread_notifications: uniqueNotifications.filter((item) => item.status === "unread"),
  };
}

function syncAuthorNotificationPreferenceInputs() {
  const targetType = els.authorNotificationPrefType?.value || "thread_assigned";
  const preferences = appState.authorNotificationPreferences?.preferences || [];
  const selected = preferences.find((item) => item.notification_type === targetType);
  if (els.authorNotificationPrefInApp) {
    els.authorNotificationPrefInApp.checked = selected ? Boolean(selected.in_app_enabled) : true;
  }
  if (els.authorNotificationPrefAsync) {
    els.authorNotificationPrefAsync.checked = selected ? Boolean(selected.async_mirror_enabled) : true;
  }
  if (els.authorNotificationPrefSink) {
    els.authorNotificationPrefSink.value = selected?.async_sink_name || "default";
  }
  if (els.authorNotificationPrefTarget) {
    els.authorNotificationPrefTarget.value = selected?.delivery_target || "";
  }
}

function persistAuthorAuthSession() {
  if (typeof window === "undefined") return;
  if (appState.authorAuthSession?.accessToken) {
    window.localStorage.setItem("narrativeos_author_auth", JSON.stringify(appState.authorAuthSession));
  } else {
    window.localStorage.removeItem("narrativeos_author_auth");
  }
}

function restoreAuthorAuthSession() {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem("narrativeos_author_auth");
    appState.authorAuthSession = raw ? JSON.parse(raw) : null;
  } catch (_error) {
    appState.authorAuthSession = null;
  }
}

function renderAuthorAuthStatus() {
  clearNode(els.authorAuthStatus);
  const session = appState.authorAuthSession;
  if (!session?.identity) {
    clearNode(els.authorAuthStatus, "这里会显示当前 bearer token 会话与身份信息。");
    return;
  }
  els.authorAuthStatus.appendChild(
    createListCard({
      title: `Signed In · ${session.identity.actor_id || "-"}`,
      score: session.identity.actor_role || "-",
      body:
        `account ${session.identity.account_id || "-"}\n` +
        `display ${session.identity.display_name || "-"}\n` +
        `token ${(session.accessToken || "").slice(0, 18)}...\n` +
        `expires ${session.expiresAt || "-"}`
    })
  );
}

async function refreshAuthorReviewerInbox(options = {}) {
  const { reviewerId, statusFilter, worldVersionId, notificationType, blockingOnly, query: searchQuery } = currentAuthorInboxFilters();
  if (!reviewerId) {
    appState.authorReviewerInbox = null;
    appState.authorReviewerInboxNextCursor = null;
    appState.authorReviewerInboxHasMore = false;
    return;
  }
  const params = new URLSearchParams();
  params.set("reviewer_id", reviewerId);
  params.set("limit", "12");
  params.set("status_filter", statusFilter);
  if (worldVersionId) {
    params.set("world_version_id", worldVersionId);
  }
  if (notificationType) {
    params.set("notification_type", notificationType);
  }
  if (blockingOnly) {
    params.set("blocking_only", "true");
  }
  if (searchQuery) {
    params.set("q", searchQuery);
  }
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  const payload = await api(`/v1/author/reviewer-inbox?${params.toString()}`, {
    headers: authorCollaborationHeaders({ preferReviewer: true }),
  });
  appState.authorReviewerInbox = options.append ? mergeAuthorReviewerInbox(appState.authorReviewerInbox, payload) : payload;
  appState.authorReviewerInboxNextCursor = payload.next_cursor || null;
  appState.authorReviewerInboxHasMore = Boolean(payload.has_more);
  appState.authorReviewerInboxSearch = searchQuery;
}

async function updateAuthorThreadStatusInline(threadId, status, options = {}) {
  const body = options.body || "";
  const actorId = options.actorId || activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/status`, {
    method: "POST",
    headers: authorCollaborationHeaders({
      actorId,
      actorRole: options.actorRole || activeAuthorActorRole(actorId),
    }),
    body: JSON.stringify({
      status,
      assignee_id: options.assigneeId === undefined ? undefined : options.assigneeId,
      actor_id: actorId,
      actor_role: options.actorRole || activeAuthorActorRole(actorId),
      body: body || undefined,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function updateAuthorNotificationStatus(notificationId, status) {
  await api(`/v1/author/notifications/${encodeURIComponent(notificationId)}/status`, {
    method: "POST",
    headers: authorCollaborationHeaders({ preferReviewer: true }),
    body: JSON.stringify({
      status,
      recipient_id: activeAuthorReviewerId(),
      limit: 12,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function bulkUpdateAuthorNotificationStatus(status) {
  const notificationIds = appState.authorReviewerInboxVisibleNotificationIds || [];
  if (!notificationIds.length) {
    alert("当前没有可批量处理的 notifications。");
    return;
  }
  await api("/v1/author/notifications/bulk-status", {
    method: "POST",
    headers: authorCollaborationHeaders({ preferReviewer: true }),
    body: JSON.stringify({
      notification_ids: notificationIds,
      recipient_id: activeAuthorReviewerId(),
      status,
      limit: 12,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function decideAuthorApprovalForWorld(worldVersionId, status, reviewerId, reason) {
  await api(`/v1/author/drafts/${encodeURIComponent(worldVersionId)}/approval/decision`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId: reviewerId || activeAuthorReviewerId(), actorRole: "reviewer" }),
    body: JSON.stringify({
      reviewer_id: reviewerId || activeAuthorReviewerId(),
      status,
      reason: reason || (status === "approved" ? "Reviewer inbox 快速批准。" : "Reviewer inbox 要求修改。"),
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function addAuthorThreadWatcher(threadId, watcherId = "") {
  const actorId = activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/watchers`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId || actorId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function removeAuthorThreadWatcher(threadId, watcherId) {
  const actorId = activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/watchers/${encodeURIComponent(watcherId)}/remove`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function replyToSelectedAuthorThread(threadId) {
  const body = (appState.authorInlineReplyDraft || "").trim();
  if (!body) {
    alert("先写回复内容。");
    return;
  }
  const actorId = activeAuthorActorId();
  await api(`/v1/author/comments/${encodeURIComponent(threadId)}/reply`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      actor_role: activeAuthorActorRole(actorId),
      body,
    }),
  });
  appState.authorInlineReplyDraft = "";
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function addAuthorDraftWatcher() {
  if (!appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const watcherId = (els.authorDraftWatcherId?.value || "").trim() || activeAuthorActorId();
  const actorId = activeAuthorActorId();
  await api(`/v1/author/drafts/${encodeURIComponent(appState.activeDraftVersionId)}/watchers`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function removeAuthorDraftWatcher() {
  if (!appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const watcherId = (els.authorDraftWatcherId?.value || "").trim();
  if (!watcherId) {
    alert("先填写 draft watcher id。");
    return;
  }
  const actorId = activeAuthorActorId();
  await api(`/v1/author/drafts/${encodeURIComponent(appState.activeDraftVersionId)}/watchers/${encodeURIComponent(watcherId)}/remove`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      watcher_id: watcherId,
    }),
  });
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function refreshAuthorNotificationPreferences() {
  const actorId = activeAuthorActorId();
  appState.authorNotificationPreferences = await api(
    `/v1/author/notification-preferences?actor_id=${encodeURIComponent(actorId)}`,
    {
      headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    }
  );
  syncAuthorNotificationPreferenceInputs();
}

async function saveAuthorNotificationPreference() {
  const actorId = activeAuthorActorId();
  await api("/v1/author/notification-preferences", {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      actor_id: actorId,
      notification_type: els.authorNotificationPrefType?.value || "thread_assigned",
      in_app_enabled: Boolean(els.authorNotificationPrefInApp?.checked),
      async_mirror_enabled: Boolean(els.authorNotificationPrefAsync?.checked),
      async_sink_name: els.authorNotificationPrefSink?.value || "default",
      delivery_target: (els.authorNotificationPrefTarget?.value || "").trim() || null,
    }),
  });
  await refreshAuthorNotificationPreferences();
  renderAuthorReports();
}

async function registerAuthorAuthIdentity() {
  const actorId = (els.authorAuthActorId?.value || "").trim() || activeAuthorActorId();
  const password = (els.authorAuthPassword?.value || "").trim();
  if (!actorId || !password) {
    alert("请先填写 actor id 和 password。");
    return;
  }
  await api("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      actor_id: actorId,
      actor_role: els.authorAuthRole?.value || "author",
      password,
      account_id: els.authorAccountId?.value.trim() || actorId,
      display_name: (els.authorAuthDisplayName?.value || "").trim() || null,
    }),
  });
  await loginAuthorAuthIdentity();
}

async function loginAuthorAuthIdentity() {
  const actorId = (els.authorAuthActorId?.value || "").trim() || activeAuthorActorId();
  const password = (els.authorAuthPassword?.value || "").trim();
  if (!actorId || !password) {
    alert("请先填写 actor id 和 password。");
    return;
  }
  const payload = await api("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({
      actor_id: actorId,
      password,
    }),
  });
  appState.authorAuthSession = {
    accessToken: payload.token?.access_token,
    expiresAt: payload.token?.expires_at,
    identity: payload.identity,
    tokenType: payload.token?.token_type || "bearer",
  };
  persistAuthorAuthSession();
  if (els.authorAccountId && payload.identity?.account_id) {
    els.authorAccountId.value = payload.identity.account_id;
  }
  renderAuthorAuthStatus();
  await refreshAuthorSurface();
}

async function hydrateAuthorAuthSession() {
  if (!appState.authorAuthSession?.accessToken) {
    renderAuthorAuthStatus();
    return;
  }
  try {
    const payload = await api("/v1/auth/me");
    appState.authorAuthSession = {
      ...appState.authorAuthSession,
      identity: payload.identity,
      expiresAt: payload.identity?.expires_at || appState.authorAuthSession.expiresAt,
    };
    persistAuthorAuthSession();
  } catch (error) {
    appState.authorAuthSession = null;
    persistAuthorAuthSession();
  }
  if (els.authorAccountId && appState.authorAuthSession?.identity?.account_id) {
    els.authorAccountId.value = appState.authorAuthSession.identity.account_id;
  }
  renderAuthorAuthStatus();
}

async function logoutAuthorAuthIdentity() {
  if (!appState.authorAuthSession?.accessToken) {
    appState.authorAuthSession = null;
    persistAuthorAuthSession();
    renderAuthorAuthStatus();
    return;
  }
  try {
    await api("/v1/auth/logout", { method: "POST" });
  } catch (_error) {
    // Even if logout fails remotely, clear local session for safety.
  }
  appState.authorAuthSession = null;
  persistAuthorAuthSession();
  renderAuthorAuthStatus();
}

async function validateDraftVersion(worldVersionId) {
  const detail = await api(`/v1/author/drafts/${worldVersionId}`);
  const report = await api("/v1/author/drafts/validate", {
    method: "POST",
    body: JSON.stringify({
      worldpack: detail.worldpack,
      account_id: els.authorAccountId?.value.trim() || "web_author",
    }),
  });
  appState.activeDraftVersionId = worldVersionId;
  appState.activeDraftDetail = detail;
  appState.selectedAuthorRevisionIndex = null;
  appState.authorValidationReport = report;
  appState.authorWorkflowSummary = null;
  await refreshAuthorSurface();
  focusAuthorPanel("validation");
  return report;
}

async function simulateDraftVersion(worldVersionId) {
  appState.activeDraftDetail = await api(`/v1/author/drafts/${worldVersionId}`);
  appState.authorPreviousSimulationReport = appState.authorSimulationReport;
  const report = await api(`/v1/author/drafts/${worldVersionId}/simulate`, { method: "POST" });
  appState.activeDraftVersionId = worldVersionId;
  appState.authorSimulationReport = report;
  appState.activeDraftDetail = await api(`/v1/author/drafts/${worldVersionId}`);
  appState.selectedAuthorRevisionIndex = null;
  appState.authorWorkflowSummary = null;
  await refreshAuthorSurface();
  await refreshOpsSurface();
  focusAuthorPanel("simulation");
  return report;
}

async function submitDraftVersion(worldVersionId) {
  appState.activeDraftDetail = await api(`/v1/author/drafts/${worldVersionId}`);
  const report = await api(
    `/v1/author/drafts/${worldVersionId}/submit?account_id=${encodeURIComponent(els.authorAccountId?.value.trim() || "web_author")}`,
    { method: "POST" }
  );
  appState.activeDraftVersionId = worldVersionId;
  appState.authorValidationReport = report;
  appState.selectedAuthorRevisionIndex = null;
  appState.authorWorkflowSummary = null;
  await refreshAuthorSurface();
  await refreshOpsSurface();
  focusAuthorPanel("version_history");
  return report;
}

async function createAuthorCommentThread() {
  if (!appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const body = els.authorCommentBody?.value.trim() || "";
  if (!body) {
    alert("先写评论内容。");
    return;
  }
  const actorId = activeAuthorActorId();
  const created = await api(`/v1/author/drafts/${appState.activeDraftVersionId}/comments`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      revision_id: getActiveRevisionHistory().slice(-1)[0]?.revision_id || null,
      anchor_type: els.authorCommentAnchorType?.value || "draft",
      anchor_key: els.authorCommentAnchorKey?.value.trim() || appState.activeDraftVersionId,
      severity: els.authorCommentSeverity?.value || "normal",
      assignee_id: els.authorCommentAssignee?.value.trim() || null,
      actor_id: actorId,
      actor_role: activeAuthorActorRole(actorId),
      body,
    }),
  });
  appState.selectedAuthorThreadId = created.thread?.thread_id || appState.selectedAuthorThreadId;
  if (els.authorCommentBody) els.authorCommentBody.value = "";
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function requestAuthorApproval() {
  if (!appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const reviewerId = els.authorApprovalReviewer?.value.trim() || activeAuthorReviewerId();
  const actorId = activeAuthorActorId();
  await api(`/v1/author/drafts/${appState.activeDraftVersionId}/approval/request`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId, actorRole: activeAuthorActorRole(actorId) }),
    body: JSON.stringify({
      revision_id: getActiveRevisionHistory().slice(-1)[0]?.revision_id || null,
      reviewer_id: reviewerId,
      reason: els.authorApprovalReason?.value.trim() || "请求内部审批。",
      actor_id: actorId,
      actor_role: activeAuthorActorRole(actorId),
    }),
  });
  if (els.authorInboxReviewerId && reviewerId) {
    els.authorInboxReviewerId.value = reviewerId;
  }
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function decideAuthorApproval(status) {
  if (!appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const reviewerId = els.authorApprovalReviewer?.value.trim() || activeAuthorReviewerId();
  await api(`/v1/author/drafts/${appState.activeDraftVersionId}/approval/decision`, {
    method: "POST",
    headers: authorCollaborationHeaders({ actorId: reviewerId, actorRole: "reviewer" }),
    body: JSON.stringify({
      revision_id: getActiveRevisionHistory().slice(-1)[0]?.revision_id || null,
      reviewer_id: reviewerId,
      status,
      reason: els.authorApprovalReason?.value.trim() || (status === "approved" ? "批准送审。" : "需要修改。"),
    }),
  });
  if (els.authorInboxReviewerId && reviewerId) {
    els.authorInboxReviewerId.value = reviewerId;
  }
  await refreshAuthorSurface();
  focusAuthorPanel("collaboration");
}

async function runAuthorWorkflowAction(actionId) {
  const draftId = appState.authorWorkflowSummary?.world_version_id || appState.activeDraftVersionId;
  if (actionId === "create_from_brief") {
    focusAuthorPanel("brief");
    await createDraftFromBrief();
    return;
  }
  if (actionId === "copy_current_world") {
    await createDraftFromCurrentWorld();
    return;
  }
  if (actionId === "validate_draft" && draftId) {
    await validateDraftVersion(draftId);
    return;
  }
  if (actionId === "simulate_draft" && draftId) {
    await simulateDraftVersion(draftId);
    return;
  }
  if (actionId === "submit_draft" && draftId) {
    await submitDraftVersion(draftId);
    return;
  }
  if (actionId === "focus_validation") {
    focusAuthorPanel("validation");
    return;
  }
  if (actionId === "focus_simulation") {
    focusAuthorPanel("simulation");
    return;
  }
  if (actionId === "focus_diff" || actionId === "focus_revision") {
    focusAuthorPanel("diff");
    return;
  }
  if (actionId === "focus_version_history") {
    focusAuthorPanel("version_history");
    return;
  }
  if (actionId === "focus_draft_detail") {
    focusAuthorPanel("draft_detail");
    return;
  }
}

function populateAuthorBriefForm(force = false) {
  const payload = appState.authorBriefTemplate;
  if (!payload) return;
  const defaults = payload.defaults || {};
  const presets = payload.genre_presets || [];
  if (!els.authorGenrePreset) return;
  if (!els.authorGenrePreset.options.length) {
    els.authorGenrePreset.innerHTML = presets
      .map((preset) => `<option value="${preset.id}">${preset.label}</option>`)
      .join("");
  }
  const hasUserInput =
    els.authorWorldTitle?.value ||
    els.authorLeadName?.value ||
    els.authorCorePremise?.value ||
    els.authorLifeTheme?.value;
  if (!force && hasUserInput) return;
  els.authorGenrePreset.value = defaults.genre_preset || presets[0]?.id || "urban_mystery";
  els.authorWorldTitle.value = defaults.world_title || "";
  els.authorLeadName.value = defaults.lead_name || "";
  els.authorCounterpartName.value = defaults.counterpart_name || "";
  els.authorSupportingName.value = defaults.supporting_name || "";
  els.authorLifeTheme.value = defaults.life_theme || "";
  els.authorCorePremise.value = defaults.core_premise || "";
  els.authorLocations.value = defaults.locations || "";
}

function applyAuthorPresetDefaults() {
  const payload = appState.authorBriefTemplate;
  if (!payload) return;
  const selected = els.authorGenrePreset?.value;
  const defaults = payload.preset_defaults?.[selected];
  if (!defaults) return;
  els.authorWorldTitle.value = defaults.world_title || "";
  els.authorLeadName.value = defaults.lead_name || "";
  els.authorCounterpartName.value = defaults.counterpart_name || "";
  els.authorSupportingName.value = defaults.supporting_name || "";
  els.authorLifeTheme.value = defaults.life_theme || "";
  els.authorCorePremise.value = defaults.core_premise || "";
  els.authorLocations.value = defaults.locations || "";
}

function buildAuthorBriefPayload() {
  return {
    genre_preset: els.authorGenrePreset?.value || "urban_mystery",
    world_title: els.authorWorldTitle?.value.trim() || "",
    lead_name: els.authorLeadName?.value.trim() || "",
    counterpart_name: els.authorCounterpartName?.value.trim() || "",
    supporting_name: els.authorSupportingName?.value.trim() || "",
    life_theme: els.authorLifeTheme?.value.trim() || "",
    core_premise: els.authorCorePremise?.value.trim() || "",
    locations: els.authorLocations?.value || "",
    author_id: els.authorAccountId?.value.trim() || "web_author",
    account_id: els.authorAccountId?.value.trim() || "web_author",
  };
}

function getActiveDraftCharacters() {
  return getActiveDraftWorldpack()?.characters || [];
}

function getActiveDraftScenes() {
  return getActiveDraftWorldpack()?.scene_blueprints || [];
}

function selectedCharacterIndex() {
  return Math.max(0, Number(els.authorCharacterSelect?.value || 0));
}

function selectedSceneIndex() {
  return Math.max(0, Number(els.authorSceneSelect?.value || 0));
}

function renderAuthorDraftDetail() {
  clearNode(els.authorDraftDetail);
  const worldpack = getActiveDraftWorldpack();
  if (!worldpack || !appState.activeDraftVersionId) {
    clearNode(els.authorDraftDetail, "选择一个 draft 后，这里会显示 world / manifest / capability diagnosis。");
    return;
  }
  const validation = appState.activeDraftDetail?.validation_report || appState.authorValidationReport || {};
  const simulation = appState.activeDraftDetail?.simulation_report || appState.authorSimulationReport || {};
  const simulationDrilldown = getSimulationDrilldown();
  const latestDiff = getLatestDiffSummary();
  const stylePack = worldpack.narrative_style_pack || {};
  const detail = document.createElement("article");
  detail.className = "list-card";
  const diagnosis = simulation.cross_pack_summary?.worlds?.find((item) => item.world_id === appState.activeDraftDetail?.world_id) || null;
  detail.innerHTML = `
    <div class="list-card-head">
      <h3>${worldpack.title || appState.activeDraftDetail?.world_id || appState.activeDraftVersionId}</h3>
      <span class="list-card-score">${appState.activeDraftDetail?.status || "draft"}</span>
    </div>
    <p class="list-card-body">
world_id: ${appState.activeDraftDetail?.world_id || "-"}\n
world_version_id: ${appState.activeDraftVersionId}\n
manifest: ${(worldpack.manifest?.genres || []).join(" / ") || "-"} · ${worldpack.manifest?.risk_rating || "-"}\n
validation: ${validation.ok ? "ok" : "pending"} · errors ${(validation.errors || []).length || 0} · warnings ${(validation.warnings || []).length || 0}\n
simulation: ${simulation.latest_decision || "-"} · pass ${formatPercent(simulation.evaluation_summary?.pass_rate)} · rewrite ${formatPercent(simulation.evaluation_summary?.rewrite_rate)} · block ${formatPercent(simulation.evaluation_summary?.block_rate)}\n
simulation drill-down: completion ${simulationDrilldown.completion_ratio !== undefined ? Number(simulationDrilldown.completion_ratio).toFixed(3) : "-"} · stop ${simulationDrilldown.stop_reason || "-"} · chapters ${simulationDrilldown.completed_chapters ?? simulation.completed_chapters ?? 0}\n
style / pacing / hook: tone ${(stylePack.tonal_lexicon || []).slice(0, 3).join(" / ") || "-"} · hook ${(stylePack.hook_templates || [])[0] || "-"} · turns ${worldpack.dialogue_realism_policy?.min_turns || 2}-${worldpack.dialogue_realism_policy?.max_turns || 3}\n
diagnosis: ${diagnosis?.issue_summary?.dominant_issue || "-"}\n
weakest: ${(diagnosis?.issue_summary?.weakest_dimensions || []).map((item) => `${item.name}=${Number(item.value || 0).toFixed(3)}`).join(" / ") || "-"}\n
recommended: ${diagnosis?.issue_summary?.recommended_target || "-"}\n
latest diff: ${latestDiff.summary_text || "-"}
    </p>
  `;
  els.authorDraftDetail.appendChild(detail);
}

function renderCharacterEditor() {
  const characters = getActiveDraftCharacters();
  if (!els.authorCharacterSelect) return;
  if (!characters.length) {
    els.authorCharacterSelect.innerHTML = "";
    els.authorCharacterName.value = "";
    els.authorCharacterRole.value = "";
    els.authorCharacterLifeTheme.value = "";
    els.authorCharacterCoreWound.value = "";
    els.authorCharacterPublicSelf.value = "";
    els.authorCharacterShadowDesire.value = "";
    els.authorCharacterVows.value = "";
    return;
  }
  els.authorCharacterSelect.innerHTML = characters
    .map((character, index) => `<option value="${index}">${character.display_name || character.character_id}</option>`)
    .join("");
  const character = characters[Math.min(selectedCharacterIndex(), characters.length - 1)];
  els.authorCharacterSelect.value = String(Math.min(selectedCharacterIndex(), characters.length - 1));
  els.authorCharacterName.value = character.display_name || "";
  els.authorCharacterRole.value = character.role || "";
  els.authorCharacterLifeTheme.value = character.destiny_contract?.life_theme || "";
  els.authorCharacterCoreWound.value = character.wound_profile?.core_wound || "";
  els.authorCharacterPublicSelf.value = character.wound_profile?.public_self || "";
  els.authorCharacterShadowDesire.value = character.wound_profile?.shadow_desire || "";
  els.authorCharacterVows.value = (character.vow_profile?.vows || []).join("\n");
}

function renderSceneEditor() {
  const scenes = getActiveDraftScenes();
  if (!els.authorSceneSelect) return;
  if (!scenes.length) {
    els.authorSceneSelect.innerHTML = "";
    els.authorSceneId.value = "";
    els.authorSceneFunction.value = "";
    els.authorSceneRequiredRoles.value = "";
    els.authorSceneBeats.value = "";
    return;
  }
  els.authorSceneSelect.innerHTML = scenes
    .map((scene, index) => `<option value="${index}">${scene.scene_id || `scene_${index + 1}`}</option>`)
    .join("");
  const scene = scenes[Math.min(selectedSceneIndex(), scenes.length - 1)];
  els.authorSceneSelect.value = String(Math.min(selectedSceneIndex(), scenes.length - 1));
  els.authorSceneId.value = scene.scene_id || "";
  els.authorSceneFunction.value = scene.scene_function || "";
  els.authorSceneRequiredRoles.value = (scene.required_roles || []).join("\n");
  els.authorSceneBeats.value = (scene.beats_template || []).join("\n");
}

function parseMultilineList(value) {
  return String(value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatMultilineList(values) {
  return (values || []).join("\n");
}

function parseLabelMap(value) {
  const result = {};
  for (const rawLine of String(value || "").split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const separatorIndex = line.includes(":") ? line.indexOf(":") : line.indexOf("=");
    if (separatorIndex <= 0) continue;
    const key = line.slice(0, separatorIndex).trim();
    const label = line.slice(separatorIndex + 1).trim();
    if (key && label) {
      result[key] = label;
    }
  }
  return result;
}

function formatLabelMap(value) {
  return Object.entries(value || {})
    .map(([key, label]) => `${key}: ${label}`)
    .join("\n");
}

function parseSceneHooks(value) {
  const hooks = {};
  for (const rawLine of String(value || "").split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const separatorIndex = line.includes(":") ? line.indexOf(":") : line.indexOf("=");
    if (separatorIndex <= 0) continue;
    const sceneFunction = line.slice(0, separatorIndex).trim();
    const hook = line.slice(separatorIndex + 1).trim();
    if (!sceneFunction || !hook) continue;
    hooks[sceneFunction] = hooks[sceneFunction] || [];
    hooks[sceneFunction].push(hook);
  }
  return hooks;
}

function formatSceneHooks(value) {
  const lines = [];
  Object.entries(value || {}).forEach(([sceneFunction, hooks]) => {
    (hooks || []).forEach((hook) => {
      if (hook) {
        lines.push(`${sceneFunction}: ${hook}`);
      }
    });
  });
  return lines.join("\n");
}

function renderStylePacingHookControls() {
  const worldpack = getActiveDraftWorldpack() || {};
  const stylePack = worldpack.narrative_style_pack || {};
  const dialoguePolicy = worldpack.dialogue_realism_policy || stylePack.dialogue || {};
  const sceneContracts = worldpack.scene_realization_contracts || {};
  const defaultSceneContract = Object.values(sceneContracts)[0] || stylePack.scene_realization || {};
  const thematicLabels = stylePack.thematic_axis_labels || {};

  if (els.authorStyleLexicon) {
    els.authorStyleLexicon.value = formatMultilineList(stylePack.tonal_lexicon || []);
  }
  if (els.authorThemeLabels) {
    els.authorThemeLabels.value = formatLabelMap(thematicLabels);
  }
  if (els.authorHookTemplates) {
    els.authorHookTemplates.value = formatMultilineList(stylePack.hook_templates || []);
  }
  if (els.authorPacingRequireTurnTaking) {
    els.authorPacingRequireTurnTaking.checked = Boolean(dialoguePolicy.require_turn_taking ?? true);
  }
  if (els.authorPacingRequireCounterReaction) {
    els.authorPacingRequireCounterReaction.checked = Boolean(dialoguePolicy.require_counter_reaction ?? true);
  }
  if (els.authorPacingMinTurns) {
    els.authorPacingMinTurns.value = String(Number(dialoguePolicy.min_turns || 2));
  }
  if (els.authorPacingMaxTurns) {
    els.authorPacingMaxTurns.value = String(Number(dialoguePolicy.max_turns || 3));
  }
  if (els.authorPacingMinimumExchanges) {
    els.authorPacingMinimumExchanges.value = String(Number(dialoguePolicy.minimum_exchanges || 1));
  }
  if (els.authorPacingTurnPattern) {
    els.authorPacingTurnPattern.value = formatMultilineList(dialoguePolicy.turn_pattern || ["speaker", "reaction", "reply"]);
  }
  if (els.authorSceneHooks) {
    els.authorSceneHooks.value = formatSceneHooks(defaultSceneContract.scene_hooks || {});
  }
}

function applyStylePacingHookControls(worldpack) {
  worldpack.narrative_style_pack = worldpack.narrative_style_pack || {};
  const stylePack = worldpack.narrative_style_pack;
  const thematicLabels = parseLabelMap(els.authorThemeLabels?.value || "");
  stylePack.tonal_lexicon = parseMultilineList(els.authorStyleLexicon?.value || "");
  stylePack.thematic_axis_labels = thematicLabels;
  stylePack.hook_templates = parseMultilineList(els.authorHookTemplates?.value || "");
  stylePack.tag_labels = {
    ...(stylePack.tag_labels || {}),
    ...thematicLabels,
  };

  worldpack.dialogue_realism_policy = worldpack.dialogue_realism_policy || {};
  const minTurns = Math.max(1, Number(els.authorPacingMinTurns?.value || 2));
  const maxTurns = Math.max(minTurns, Number(els.authorPacingMaxTurns?.value || 3));
  worldpack.dialogue_realism_policy.require_turn_taking = Boolean(els.authorPacingRequireTurnTaking?.checked);
  worldpack.dialogue_realism_policy.require_counter_reaction = Boolean(els.authorPacingRequireCounterReaction?.checked);
  worldpack.dialogue_realism_policy.min_turns = minTurns;
  worldpack.dialogue_realism_policy.max_turns = maxTurns;
  worldpack.dialogue_realism_policy.minimum_exchanges = Math.max(1, Number(els.authorPacingMinimumExchanges?.value || 1));
  worldpack.dialogue_realism_policy.turn_pattern = parseMultilineList(els.authorPacingTurnPattern?.value || "") || ["speaker", "reaction", "reply"];

  const defaultContractKey = Object.keys(worldpack.scene_realization_contracts || {})[0] || "default";
  worldpack.scene_realization_contracts = worldpack.scene_realization_contracts || {};
  worldpack.scene_realization_contracts[defaultContractKey] = {
    ...(worldpack.scene_realization_contracts[defaultContractKey] || {}),
    scene_hooks: parseSceneHooks(els.authorSceneHooks?.value || ""),
  };
}

function buildSimulationDiffSummary(previousReport, currentReport) {
  if (!previousReport || !currentReport) return "";
  const previous = previousReport.evaluation_summary || {};
  const current = currentReport.evaluation_summary || {};
  const parts = [];
  for (const key of ["pass_rate", "rewrite_rate", "block_rate"]) {
    const delta = Number(current[key] || 0) - Number(previous[key] || 0);
    if (delta !== 0) {
      parts.push(`${key}: ${delta >= 0 ? "+" : ""}${delta.toFixed(3)}`);
    }
  }
  return parts.join("\n");
}

function renderAuthorRevisionPanels() {
  clearNode(els.authorAssetDiff);
  clearNode(els.authorVersionHistory);
  const revisions = getActiveRevisionHistory();
  const diffDrilldown = getDiffDrilldown();
  const revisionEntries = diffDrilldown.revisions || [];
  const latestDiff = getLatestDiffSummary();
  if (!revisions.length) {
    clearNode(els.authorAssetDiff, "保存角色、场景或能力配置后，这里会显示结构化 diff 摘要。");
    clearNode(els.authorVersionHistory, "这里会显示最近几次 revision 与对应的修改来源。");
    return;
  }

  const selectedIndex = Math.max(0, Math.min(appState.selectedAuthorRevisionIndex ?? revisions.length - 1, revisions.length - 1));
  appState.selectedAuthorRevisionIndex = selectedIndex;
  const selectedRevision = revisions[selectedIndex];
  const selectedEntry = revisionEntries[selectedIndex] || {};
  const previousEntry = selectedIndex > 0 ? revisionEntries[selectedIndex - 1] || {} : {};
  const diffPayload = selectedEntry.diff_summary || (selectedIndex === revisions.length - 1 ? latestDiff : {
    changed_sections: selectedRevision.changed_sections || [],
    summary_text: selectedRevision.summary || "",
    character_changes: [],
    scene_changes: [],
    capability_changes: [],
  });

  els.authorAssetDiff.appendChild(
    createListCard({
      title: selectedRevision.label || "最近一次修改",
      score: selectedRevision.source || "-",
      body:
        `summary: ${diffPayload.summary_text || selectedRevision.summary || "-"}\n` +
        `compare: ${previousEntry.snapshot_summary || "初始版本"} -> ${selectedEntry.snapshot_summary || "-"}\n` +
        `changed_sections: ${(diffPayload.changed_sections || []).join(" / ") || "-"}\n\n` +
        `section counts: sections ${diffDrilldown.section_change_counts?.sections ?? 0} · characters ${diffDrilldown.section_change_counts?.characters ?? 0} · scenes ${diffDrilldown.section_change_counts?.scenes ?? 0} · capabilities ${diffDrilldown.section_change_counts?.capabilities ?? 0}\n` +
        `simulation freshness: ${diffDrilldown.simulation_freshness?.status || "-"}\n` +
        `recommended next: ${(diffDrilldown.recommended_next_actions || []).join(" / ") || "-"}\n\n` +
        `${(diffPayload.character_changes || []).length ? `角色改动:\n${diffPayload.character_changes.map((item) => `${item.character_id}: ${(item.changed_fields || []).join(", ")}`).join("\n")}` : "角色改动: -"}\n\n` +
        `${(diffPayload.scene_changes || []).length ? `场景改动:\n${diffPayload.scene_changes.map((item) => `${item.scene_id}: ${(item.changed_fields || []).join(", ")}`).join("\n")}` : "场景改动: -"}\n\n` +
        `${(diffPayload.capability_changes || []).length ? `能力改动:\n${diffPayload.capability_changes.join("\n")}` : "能力改动: -"}\n\n` +
        `${selectedEntry.simulation_delta && Object.keys(selectedEntry.simulation_delta).length ? `simulation_delta:\n${Object.entries(selectedEntry.simulation_delta).map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join("\n")}` : "simulation_delta: -"}`
    })
  );
  const diffActions = document.createElement("div");
  diffActions.className = "composer-actions";
  const commentCurrentDiff = document.createElement("button");
  commentCurrentDiff.className = "ghost-action";
  commentCurrentDiff.textContent = "评论当前 Diff";
  commentCurrentDiff.addEventListener("click", () => {
    prefillAuthorCommentAnchor("draft", selectedRevision.revision_id || appState.activeDraftVersionId || "");
  });
  diffActions.appendChild(commentCurrentDiff);
  els.authorAssetDiff.appendChild(diffActions);

  revisions.slice().reverse().forEach((revision, reverseIndex) => {
      const actualIndex = revisions.length - 1 - reverseIndex;
      const revisionEntry = revisionEntries[actualIndex] || {};
      const card = document.createElement("article");
      card.className = "list-card";
      if (actualIndex === selectedIndex) {
        card.classList.add("is-active");
      }
      const snapshot = revision.worldpack_snapshot || {};
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${revision.label || revision.source || "revision"}</h3>
          <span class="list-card-score">${revision.source || "-"}</span>
        </div>
        <p class="list-card-body">${formatTimestamp(revision.created_at)}\n${revision.summary || "-"}\n${revisionEntry.snapshot_summary || `${snapshot.title || snapshot.world_id || "-"} · 角色 ${(snapshot.characters || []).length || 0} · 场景 ${(snapshot.scene_blueprints || []).length || 0}`}\nchanged ${(revisionEntry.diff_summary?.changed_sections || revision.changed_sections || []).join(" / ") || "-"}</p>
      `;
      card.addEventListener("click", () => {
        appState.selectedAuthorRevisionIndex = actualIndex;
        renderAuthorRevisionPanels();
      });
      els.authorVersionHistory.appendChild(card);
    });
}

function renderAuthorCompare() {
  clearNode(els.authorCompare);
  const detail = appState.activeDraftDetail || {};
  const revisionCompare = detail.revision_compare || {};
  const chapterCompare = detail.before_after_chapter_compare || {};
  if (!revisionCompare.available && !chapterCompare.available) {
    clearNode(els.authorCompare, "这里会显示 revision compare 与 before-after chapter compare。");
    return;
  }
  if (revisionCompare.available) {
    const card = createListCard({
      title: "Revision Compare",
      score: `${revisionCompare.before_revision_id || "-"} -> ${revisionCompare.after_revision_id || "-"}`,
      body:
        `before ${revisionCompare.before_label || "-"}\nafter ${revisionCompare.after_label || "-"}\nsummary ${revisionCompare.after_summary || "-"}\nchanged ${(revisionCompare.after_diff_summary?.changed_sections || []).join(" / ") || "-"}\nsection counts before ${revisionCompare.section_counts?.before_changed_sections ?? 0} · after ${revisionCompare.section_counts?.after_changed_sections ?? 0}\nsimulation freshness ${revisionCompare.simulation_freshness?.status || "-"}\nsimulation delta ${(revisionCompare.simulation_delta && Object.keys(revisionCompare.simulation_delta).length) ? Object.entries(revisionCompare.simulation_delta).map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`).join(" / ") : "-"}`
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const button = document.createElement("button");
    button.className = "ghost-action";
    button.textContent = "评论当前 Diff";
    button.addEventListener("click", () => {
      prefillAuthorCommentAnchor("draft", revisionCompare.after_revision_id || appState.activeDraftVersionId || "");
    });
    actions.appendChild(button);
    card.appendChild(actions);
    els.authorCompare.appendChild(card);
  }
  if (chapterCompare.available) {
    const topChanged = chapterCompare.top_changed_chapters || [];
    const card = createListCard({
      title: "Before / After Chapter Compare",
      score: `${topChanged.length} 章`,
      body:
        `${topChanged.map((item) => `${item.chapter_index}. ${item.before_title || "-"} -> ${item.after_title || "-"}\n${item.before_decision || "-"} -> ${item.after_decision || "-"} · score delta ${Number(item.overall_score_delta || 0).toFixed(3)}\nissues + ${(item.issue_codes_added || []).join("/") || "-"} · - ${(item.issue_codes_removed || []).join("/") || "-"}\nsignals ${(item.signal_deltas || {}) ? Object.entries(item.signal_deltas).map(([key, value]) => `${key}=${Number(value || 0).toFixed(3)}`).join(" / ") : "-"}\nBEFORE: ${item.before_excerpt || "-"}\nAFTER: ${item.after_excerpt || "-"}`).join("\n\n") || "-"}`
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const firstTarget = topChanged[0];
    if (firstTarget) {
      const button = document.createElement("button");
      button.className = "ghost-action";
      button.textContent = "评论首个章节对照";
      button.addEventListener("click", () => {
        prefillAuthorCommentAnchor("simulation", String(firstTarget.chapter_index));
      });
      actions.appendChild(button);
    }
    card.appendChild(actions);
    els.authorCompare.appendChild(card);
  }
}

function renderAuthorCollaboration() {
  clearNode(els.authorCollaboration);
  clearNode(els.authorReviewerInbox);
  clearNode(els.authorNotificationPreferences);
  appState.authorReviewerInboxVisibleNotificationIds = [];
  const summary = appState.authorCollaborationSummary || {};
  if (!appState.activeDraftVersionId) {
    clearNode(els.authorCollaboration, "这里会显示 anchored comments、blocking threads 与审批状态。");
    clearNode(els.authorReviewerInbox, "这里会显示 reviewer inbox、notifications 与待处理 approval。");
    return;
  }
  const approval = summary.approval_summary || {};
  const notificationSummary = summary.notification_summary || {};
  const draftWatcherSummary = summary.draft_watcher_summary || {};
  const reviewerId = activeAuthorReviewerId();
  const inbox = appState.authorReviewerInbox || {};
  const threads = summary.threads || [];
  const selectedThread =
    threads.find((item) => item.thread_id === appState.selectedAuthorThreadId) ||
    threads[0] ||
    null;
  const card = createListCard({
    title: "Collaboration Summary",
    score: summary.recommended_next_action || "-",
    body:
      `open ${summary.open_thread_count ?? 0} · blocking ${summary.blocking_thread_count ?? 0}\napproval ${approval.latest_status || "-"}\nnotifications unread ${notificationSummary.unread_count ?? 0} / total ${notificationSummary.notification_count ?? 0}\nqueue ${(summary.queue_summary?.status_counts && Object.entries(summary.queue_summary.status_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\nthreads by anchor ${(summary.threads_by_anchor || []).map((item) => `${item.anchor_type}:${item.anchor_key}=${item.thread_count}`).join(" / ") || "-"}`
  });
  els.authorCollaboration.appendChild(card);
  if ((summary.assignee_queues || []).length) {
    els.authorCollaboration.appendChild(
      createListCard({
        title: "Assignee Queues",
        score: `${summary.assignee_queues.length} queues`,
        body:
          `${summary.assignee_queues.map((item) => `${item.assignee_id} · open ${item.open_count} · blocking ${item.blocking_count} · total ${item.thread_count}`).join("\n") || "-"}`
      })
    );
  }
  if ((draftWatcherSummary.watcher_ids || []).length) {
    els.authorCollaboration.appendChild(
      createListCard({
        title: "Draft Watchers",
        score: `${draftWatcherSummary.watcher_count ?? 0} watchers`,
        body:
          `explicit ${draftWatcherSummary.explicit_watcher_count ?? 0}\nwatchers ${(draftWatcherSummary.watcher_ids || []).join(" / ") || "-"}`
      })
    );
  }
  if (selectedThread) {
    const selectedCard = document.createElement("article");
    selectedCard.className = "list-card is-active";
    selectedCard.innerHTML = `
      <div class="list-card-head">
        <h3>Thread Detail · ${selectedThread.anchor_type}:${selectedThread.anchor_key}</h3>
        <span class="list-card-score">${selectedThread.status || "-"} / ${selectedThread.severity || "-"}</span>
      </div>
      <p class="list-card-body">thread ${selectedThread.thread_id}\nassignee ${selectedThread.assignee_id || "-"} · created_by ${selectedThread.created_by || "-"}\nwatchers ${(selectedThread.watcher_ids || []).join(" / ") || "-"}\nnotifications ${selectedThread.unread_notification_count ?? 0} unread / ${selectedThread.notification_count ?? 0}\nlatest ${selectedThread.latest_message_actor_id || "-"} · ${selectedThread.latest_message_at || "-"}</p>
    `;
    const selectedActions = document.createElement("div");
    selectedActions.className = "composer-actions";
    const toggleWatchButton = document.createElement("button");
    toggleWatchButton.className = "ghost-action";
    const currentActorId = activeAuthorActorId();
    const isWatching = (selectedThread.watcher_ids || []).includes(currentActorId);
    toggleWatchButton.textContent = isWatching ? "Unwatch" : "Watch";
    toggleWatchButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (isWatching) {
        await removeAuthorThreadWatcher(selectedThread.thread_id, currentActorId);
      } else {
        await addAuthorThreadWatcher(selectedThread.thread_id, currentActorId);
      }
    });
    selectedActions.appendChild(toggleWatchButton);
    if (reviewerId && selectedThread.assignee_id !== reviewerId) {
      const assignReviewerButton = document.createElement("button");
      assignReviewerButton.className = "ghost-action";
      assignReviewerButton.textContent = "Assign Reviewer";
      assignReviewerButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        await updateAuthorThreadStatusInline(selectedThread.thread_id, selectedThread.status || "open", {
          assigneeId: reviewerId,
          body: `指派给 ${reviewerId}。`,
        });
      });
      selectedActions.appendChild(assignReviewerButton);
    }
    const toggleStatusButton = document.createElement("button");
    toggleStatusButton.className = "ghost-action";
    toggleStatusButton.textContent = selectedThread.status === "open" ? "Resolve" : "Reopen";
    toggleStatusButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorThreadStatusInline(selectedThread.thread_id, selectedThread.status === "open" ? "resolved" : "open", {
        assigneeId: selectedThread.assignee_id || undefined,
        body: selectedThread.status === "open" ? "Inline thread detail 标记为已处理。" : "Inline thread detail 重新打开。",
      });
    });
    selectedActions.appendChild(toggleStatusButton);
    selectedCard.appendChild(selectedActions);

    (selectedThread.messages || []).forEach((message) => {
      selectedCard.appendChild(
        createListCard({
          title: `${message.actor_id || "-"} · ${message.actor_role || "-"}`,
          score: message.created_at || "-",
          body:
            `${message.body || "-"}\nmentions ${(message.mentioned_actor_ids || []).join(" / ") || "-"}`
        })
      );
    });

    const replyBox = document.createElement("div");
    replyBox.className = "list-card";
    const replyTitle = document.createElement("div");
    replyTitle.className = "list-card-head";
    replyTitle.innerHTML = `<h3>Reply Inline</h3><span class="list-card-score">${activeAuthorActorId()} / ${activeAuthorActorRole()}</span>`;
    replyBox.appendChild(replyTitle);
    const replyInput = document.createElement("textarea");
    replyInput.rows = 4;
    replyInput.placeholder = "输入 thread 回复，可继续用 @mention。";
    replyInput.value = appState.authorInlineReplyDraft || "";
    replyInput.addEventListener("input", () => {
      appState.authorInlineReplyDraft = replyInput.value;
    });
    replyBox.appendChild(replyInput);
    const replyActions = document.createElement("div");
    replyActions.className = "composer-actions";
    const replyButton = document.createElement("button");
    replyButton.className = "ghost-action";
    replyButton.textContent = "Send Reply";
    replyButton.addEventListener("click", async () => {
      await replyToSelectedAuthorThread(selectedThread.thread_id);
    });
    replyActions.appendChild(replyButton);
    replyBox.appendChild(replyActions);
    selectedCard.appendChild(replyBox);
    els.authorCollaboration.appendChild(selectedCard);
  }
  if ((notificationSummary.latest_notifications || []).length) {
    els.authorCollaboration.appendChild(
      createListCard({
        title: "Latest Notifications",
        score: `${notificationSummary.unread_count ?? 0} unread`,
        body:
          `${(notificationSummary.latest_notifications || []).map((item) => `${item.recipient_id} · ${item.notification_type} · ${item.status}\n${item.title}\n${item.body || "-"}`).join("\n\n") || "-"}`
      })
    );
  }
  threads.slice(0, 8).forEach((thread) => {
    const threadCard = createListCard({
      title: `${thread.anchor_type}:${thread.anchor_key}`,
      score: `${thread.status || "-"} / ${thread.severity || "-"}`,
      body:
        `assignee ${thread.assignee_id || "-"} · created_by ${thread.created_by || "-"}\nparticipants ${(thread.participant_ids || []).join(" / ") || "-"}\nmentions ${(thread.mentioned_actor_ids || []).join(" / ") || "-"}\nnotifications ${thread.unread_notification_count ?? 0} unread / ${thread.notification_count ?? 0}\nlatest ${thread.latest_message_preview || "-"}`
      ,
      active: appState.selectedAuthorThreadId === thread.thread_id
    });
    threadCard.addEventListener("click", async () => {
      await selectAuthorThread(thread.thread_id, thread.world_version_id);
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const focusButton = document.createElement("button");
    focusButton.className = "ghost-action";
    focusButton.textContent = "定位 Anchor";
    focusButton.addEventListener("click", (event) => {
      event.stopPropagation();
      prefillAuthorCommentAnchor(thread.anchor_type, thread.anchor_key);
    });
    actions.appendChild(focusButton);
    if (reviewerId && thread.assignee_id !== reviewerId) {
      const assignButton = document.createElement("button");
      assignButton.className = "ghost-action";
      assignButton.textContent = "指派给 Reviewer";
      assignButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        await updateAuthorThreadStatusInline(thread.thread_id, thread.status || "open", {
          assigneeId: reviewerId,
          body: `指派给 ${reviewerId}。`,
        });
      });
      actions.appendChild(assignButton);
    }
    const statusButton = document.createElement("button");
    statusButton.className = "ghost-action";
    statusButton.textContent = thread.status === "open" ? "标记 Resolved" : "重新打开";
    statusButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorThreadStatusInline(thread.thread_id, thread.status === "open" ? "resolved" : "open", {
        assigneeId: thread.assignee_id || undefined,
        body: thread.status === "open" ? "Reviewer inbox 已处理。" : "重新打开继续跟进。",
      });
    });
    actions.appendChild(statusButton);
    threadCard.appendChild(actions);
    els.authorCollaboration.appendChild(threadCard);
  });

  if (!reviewerId) {
    clearNode(els.authorReviewerInbox, "这里会显示 reviewer inbox、notifications 与待处理 approval。");
    return;
  }

  if (els.authorLoadMoreReviewerInbox) {
    els.authorLoadMoreReviewerInbox.disabled = !appState.authorReviewerInboxHasMore;
    els.authorLoadMoreReviewerInbox.textContent = appState.authorReviewerInboxHasMore ? "Load More" : "No More Results";
  }

  els.authorReviewerInbox.appendChild(
    createListCard({
      title: "Reviewer Inbox Summary",
      score: inbox.recommended_next_action || "-",
      body:
        `reviewer ${reviewerId}\nassigned ${inbox.queue_summary?.assigned_open_thread_count ?? 0} · blocking ${inbox.queue_summary?.blocking_assigned_thread_count ?? 0}\npending approvals ${inbox.queue_summary?.pending_approval_count ?? 0}\nunread notifications ${inbox.queue_summary?.unread_notification_count ?? 0}\nreturned ${inbox.returned_count ?? (inbox.notifications || []).length} · more ${inbox.has_more ? "yes" : "no"}\nstatus ${(inbox.queue_summary?.status_counts && Object.entries(inbox.queue_summary.status_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}\ntypes ${(inbox.queue_summary?.notification_type_counts && Object.entries(inbox.queue_summary.notification_type_counts).map(([key, value]) => `${key}=${value}`).join(" / ")) || "-"}`
    })
  );

  if ((inbox.world_version_queues || []).length) {
    els.authorReviewerInbox.appendChild(
      createListCard({
        title: "Inbox by Draft",
        score: `${inbox.world_version_queues.length} drafts`,
        body:
          `${(inbox.world_version_queues || []).map((item) => `${item.world_version_id} · unread ${item.unread_count} · total ${item.notification_count}`).join("\n") || "-"}`
      })
    );
  }

  (inbox.pending_approvals || []).slice(0, 4).forEach((approvalItem) => {
    const approvalCard = createListCard({
      title: `Approval ${approvalItem.world_version_id}`,
      score: approvalItem.status || "requested",
      body:
        `reviewer ${approvalItem.reviewer_id || "-"}\nrevision ${approvalItem.revision_id || "-"}\nreason ${approvalItem.reason || "-"}`
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const approveButton = document.createElement("button");
    approveButton.className = "ghost-action";
    approveButton.textContent = "批准";
    approveButton.addEventListener("click", async () => {
      await decideAuthorApprovalForWorld(approvalItem.world_version_id, "approved", reviewerId, "Reviewer inbox 快速批准。");
    });
    actions.appendChild(approveButton);
    const changesButton = document.createElement("button");
    changesButton.className = "ghost-action";
    changesButton.textContent = "要求修改";
    changesButton.addEventListener("click", async () => {
      await decideAuthorApprovalForWorld(approvalItem.world_version_id, "changes_requested", reviewerId, "Reviewer inbox 要求修改。");
    });
    actions.appendChild(changesButton);
    approvalCard.appendChild(actions);
    els.authorReviewerInbox.appendChild(approvalCard);
  });

  const visibleNotifications = (inbox.notifications || []).slice(0, 8);
  appState.authorReviewerInboxVisibleNotificationIds = visibleNotifications.map((item) => item.notification_id).filter(Boolean);
  visibleNotifications.forEach((notification) => {
    const notificationCard = createListCard({
      title: notification.title || notification.notification_type || "Notification",
      score: `${notification.status || "-"} / ${notification.recipient_role || "-"}`,
      body:
        `type ${notification.notification_type || "-"} · world ${notification.world_version_id || "-"}\nactor ${notification.actor_id || "-"} · recipient ${notification.recipient_id || "-"}\nanchor ${notification.anchor_type || "-"}:${notification.anchor_key || "-"}\n${notification.body || "-"}`
    });
    notificationCard.addEventListener("click", async () => {
      if (notification.thread_id) {
        await selectAuthorThread(notification.thread_id, notification.world_version_id || "");
      }
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const readButton = document.createElement("button");
    readButton.className = "ghost-action";
    readButton.textContent = "标记已读";
    readButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorNotificationStatus(notification.notification_id, "read");
    });
    actions.appendChild(readButton);
    const archiveButton = document.createElement("button");
    archiveButton.className = "ghost-action";
    archiveButton.textContent = "归档";
    archiveButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorNotificationStatus(notification.notification_id, "archived");
    });
    actions.appendChild(archiveButton);
    if (notification.anchor_type && notification.anchor_key) {
      const focusButton = document.createElement("button");
      focusButton.className = "ghost-action";
      focusButton.textContent = "跳到线程";
      focusButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        if (notification.thread_id) {
          await selectAuthorThread(notification.thread_id, notification.world_version_id || "");
        }
        prefillAuthorCommentAnchor(notification.anchor_type, notification.anchor_key);
      });
      actions.appendChild(focusButton);
    }
    notificationCard.appendChild(actions);
    els.authorReviewerInbox.appendChild(notificationCard);
  });

  (inbox.blocking_assigned_threads || []).slice(0, 4).forEach((thread) => {
    const blockingCard = createListCard({
      title: `Blocking ${thread.anchor_type}:${thread.anchor_key}`,
      score: thread.severity || "blocker",
      body:
        `thread ${thread.thread_id}\nlatest ${thread.latest_message_preview || "-"}\nstatus ${thread.status || "-"} · assignee ${thread.assignee_id || "-"}`
    });
    blockingCard.addEventListener("click", async () => {
      await selectAuthorThread(thread.thread_id, thread.world_version_id);
    });
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    const resolveButton = document.createElement("button");
    resolveButton.className = "ghost-action";
    resolveButton.textContent = "处理完成";
    resolveButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await updateAuthorThreadStatusInline(thread.thread_id, "resolved", {
        actorId: reviewerId,
        assigneeId: reviewerId,
        body: "Reviewer inbox 标记为已处理。",
      });
    });
    actions.appendChild(resolveButton);
    blockingCard.appendChild(actions);
    els.authorReviewerInbox.appendChild(blockingCard);
  });

  const preferences = appState.authorNotificationPreferences?.preferences || [];
  if (!preferences.length) {
    clearNode(els.authorNotificationPreferences, "这里会显示当前 actor 的 notification preferences。");
  } else {
    els.authorNotificationPreferences.appendChild(
      createListCard({
        title: `Notification Preferences · ${appState.authorNotificationPreferences?.actor_id || activeAuthorActorId()}`,
        score: `${preferences.length} types`,
        body:
          `${preferences.map((item) => `${item.notification_type} · in-app ${item.in_app_enabled ? "on" : "off"} · async ${item.async_mirror_enabled ? "on" : "off"} · sink ${item.async_sink_name || "default"} · target ${item.delivery_target || "-"}${item.is_default ? " · default" : ""}`).join("\n") || "-"}`
      })
    );
  }
}

function parseMaybeJson(value) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch (error) {
    return value;
  }
}

function activeReaderId() {
  return els.readerIdInput?.value.trim() || appState.readerId || "reader_demo";
}

async function refreshReaderEntitlements() {
  const readerId = activeReaderId();
  appState.readerId = readerId;
  if (els.readerIdInput) {
    els.readerIdInput.value = readerId;
  }
  const [payload, subscriptionPayload] = await Promise.all([
    api(`/v1/reader/entitlements?account_id=${encodeURIComponent(readerId)}${appState.worldId ? `&world_id=${encodeURIComponent(appState.worldId)}` : ""}`),
    api(`/v1/reader/subscription?account_id=${encodeURIComponent(readerId)}`),
  ]);
  appState.readerSubscription = subscriptionPayload;
  appState.readerEntitlements = payload.entitlements || [];
  const credits = payload.wallets?.story_credits || appState.readerEntitlements.find((item) => item.entitlement_type === "credits" && item.status === "active");
  const subscriber = subscriptionPayload.subscription || payload.subscription || appState.readerEntitlements.find((item) => item.entitlement_type === "subscriber" && item.status === "active");
  const worldPass = appState.readerEntitlements.find((item) => item.entitlement_type === "world_pass" && item.status === "active");
  els.readerEntitlementType.textContent = subscriber
    ? subscriber.tier_id || "subscriber"
    : worldPass
      ? "world_pass"
      : credits
        ? credits.wallet_type || "credits"
        : "trial";
  if (els.readerSubscriptionStatus) {
    els.readerSubscriptionStatus.textContent = subscriber?.status || "inactive";
  }
  els.readerCreditBalance.textContent = credits ? String(Number(credits.balance || 0).toFixed(0)) : "-";
  const activePaywall = appState.latestStep?.paywall || appState.sessionPaywall || {};
  if (els.readerWorldUnlockStatus) {
    els.readerWorldUnlockStatus.textContent = worldUnlockLabel(activePaywall);
  }
  if (els.readerEntitlementReason) {
    els.readerEntitlementReason.textContent = accessReasonLabel(activePaywall.reason || subscriber?.reason || worldPass?.reason || credits?.reason || "trial_chapter");
  }
  clearNode(els.readerEntitlementList);
  if (!appState.readerEntitlements.length) {
    clearNode(els.readerEntitlementList, "这里会显示当前 reader 的 entitlement 列表。");
    return;
  }
  appState.readerEntitlements.forEach((item) => {
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${item.wallet_type || item.tier_id || item.entitlement_type}</h3>
        <span class="list-card-score">${item.status}</span>
      </div>
      <p class="list-card-body">world ${item.world_id || "all"}\nbalance ${item.balance ?? "-"}\nreason ${accessReasonLabel(item.reason)}\nexpires ${item.expires_at || "-"}</p>
    `;
    els.readerEntitlementList.appendChild(card);
  });
  if (payload.subscription) {
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${payload.subscription.tier_id || "subscription"}</h3>
        <span class="list-card-score">${payload.subscription.status || "-"}</span>
      </div>
      <p class="list-card-body">price ${payload.subscription.price_usd_monthly ? `$${payload.subscription.price_usd_monthly}/month` : "-"}\nprovider ${payload.subscription.provider || "-"}\nperiod ${payload.subscription.period_end || "-"}\nnext ${payload.subscription.next_action || "-"}\nreason ${payload.subscription.lifecycle_reason || "-"}\nretryable ${payload.retryable ? "yes" : "no"} · renewable ${payload.renewable ? "yes" : "no"}\nrecommended ${payload.recommended_action || "-"}</p>
    `;
    els.readerEntitlementList.prepend(card);
  }
  clearNode(els.readerMembershipOffers);
  const tiers = subscriptionPayload.tiers || [];
  if (!tiers.length) {
    clearNode(els.readerMembershipOffers, "这里会显示 Play / Creator / Studio Pass 的方案与 checkout 入口。");
  } else {
    tiers.forEach((tier) => {
      const card = document.createElement("article");
      card.className = "list-card";
      if (subscriber?.tier_id === tier.tier_id) {
        card.classList.add("is-selected");
      }
      const buttonLabel = subscriber?.tier_id === tier.tier_id ? "当前方案" : `开始 ${tier.tier_id}`;
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${tierLabel(tier.tier_id)}</h3>
          <span class="list-card-score">$${Number(tier.price_usd_monthly || 0).toFixed(0)}/month</span>
        </div>
        <p class="list-card-body">${tier.description || "-"}\nreader access ${tier.reader_access ? "yes" : "no"}\nauthor access ${tier.author_access || "none"}\nmonthly story ${tier.monthly_story_credits ?? 0}\nmonthly studio ${tier.monthly_studio_credits ?? 0}\ncapabilities ${(tier.capabilities ? Object.entries(tier.capabilities).filter(([, value]) => value).map(([key]) => key).join(" / ") : "-") || "-"}</p>
        <div class="composer-actions">
          <button class="ghost-action reader-tier-checkout">${buttonLabel}</button>
        </div>
      `;
      const button = card.querySelector(".reader-tier-checkout");
      if (subscriber?.tier_id === tier.tier_id) {
        button.disabled = true;
      } else {
        button.addEventListener("click", () => startReaderCheckout(tier.tier_id));
      }
      els.readerMembershipOffers.appendChild(card);
    });
  }
  clearNode(els.readerCheckoutStatus);
  if (!appState.readerCheckoutSession) {
    clearNode(els.readerCheckoutStatus, "这里会显示最近一次 checkout 创建结果。");
  } else {
    const checkout = appState.readerCheckoutSession;
    const card = document.createElement("article");
    card.className = "list-card";
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${tierLabel(checkout.tier_id)}</h3>
        <span class="list-card-score">${checkout.status || "-"}</span>
      </div>
      <p class="list-card-body">provider ${checkout.provider || "-"}\nsession ${checkout.session_id || checkout.checkout_session_id || "-"}\nexpires ${checkout.expires_at || "-"}\nurl ${checkout.checkout_url || "-"}</p>
    `;
    els.readerCheckoutStatus.appendChild(card);
  }
  if (payload.lifecycle_history_summary?.latest_events?.length) {
    payload.lifecycle_history_summary.latest_events.slice(0, 4).forEach((item) => {
      const card = document.createElement("article");
      card.className = "list-card";
      card.innerHTML = `
        <div class="list-card-head">
          <h3>${item.event_type || "-"}</h3>
          <span class="list-card-score">${item.status || "-"}</span>
        </div>
        <p class="list-card-body">${formatTimestamp(item.occurred_at)}\nprovider ${item.provider || "-"}\nsubscription ${item.subscription_id || "-"}\ncheckout ${item.checkout_session_id || "-"}</p>
      `;
      els.readerCheckoutStatus.appendChild(card);
    });
  }
}

async function startReaderCheckout(tierId = "play_pass") {
  const accountId = activeReaderId();
  const restore = setBusy(els.readerStartCheckout, "创建中…");
  try {
    const payload = await api("/v1/reader/checkout/start", {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        tier_id: tierId,
        provider: "web_stub",
      }),
    });
    appState.readerCheckoutSession = payload.checkout;
    renderLatestStep();
    await refreshReaderEntitlements();
  } catch (error) {
    alert(`创建 checkout 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function retryReaderSubscriptionPayment() {
  const accountId = activeReaderId();
  try {
    await api(`/v1/reader/subscription/${encodeURIComponent(accountId)}/retry-payment`, { method: "POST" });
    await refreshReaderEntitlements();
  } catch (error) {
    alert(`重试支付失败：${error.message}`);
  }
}

async function renewReaderSubscription() {
  const accountId = activeReaderId();
  try {
    await api(`/v1/reader/subscription/${encodeURIComponent(accountId)}/renew`, { method: "POST" });
    await refreshReaderEntitlements();
  } catch (error) {
    alert(`续费失败：${error.message}`);
  }
}

async function cancelReaderSubscription() {
  const accountId = activeReaderId();
  try {
    await api(`/v1/reader/subscription/${encodeURIComponent(accountId)}/cancel`, { method: "POST" });
    await refreshReaderEntitlements();
  } catch (error) {
    alert(`取消订阅失败：${error.message}`);
  }
}

async function grantReaderEntitlement() {
  const readerId = activeReaderId();
  const entitlementType = els.grantEntitlementType?.value || "credits";
  const payload = {
    reader_id: readerId,
    entitlement_type: entitlementType === "story_credits" ? "credits" : entitlementType,
  };
  if (entitlementType === "story_credits") {
    payload.wallet_type = "story_credits";
    payload.balance = Number(els.grantEntitlementBalance?.value || 3);
  }
  if (entitlementType === "world_pass" && appState.worldId) {
    payload.world_id = appState.worldId;
  }
  await api("/v1/reader/entitlements/grant", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshReaderEntitlements();
  updateStatus();
}

function reviewStatusLabel(status) {
  return {
    submitted: "已提交审核",
    approved: "审核通过",
    published: "已发布",
    rolled_back: "已回滚",
    publish_blocked: "发布被阻止",
  }[status] || status;
}

function summarizeChecklistEvidence(evidence) {
  if (!evidence || typeof evidence !== "object") return "-";
  const parts = [];
  if (evidence.cross_pack_pass_rate !== undefined && evidence.cross_pack_pass_rate !== null) {
    parts.push(`cross-pack ${Number(evidence.cross_pack_pass_rate || 0).toFixed(3)}`);
  }
  if (evidence.cross_pack_pass_rate_delta !== undefined && evidence.cross_pack_pass_rate_delta !== null) {
    parts.push(`delta ${Number(evidence.cross_pack_pass_rate_delta || 0).toFixed(3)}`);
  }
  if (evidence.block_rate !== undefined && evidence.block_rate !== null) {
    parts.push(`block ${formatPercent(evidence.block_rate)}`);
  }
  if (evidence.max_prose_leak_rate !== undefined && evidence.max_prose_leak_rate !== null) {
    parts.push(`max leak ${Number(evidence.max_prose_leak_rate || 0).toFixed(3)}`);
  }
  if (Array.isArray(evidence.top_failing_pack_ids) && evidence.top_failing_pack_ids.length) {
    parts.push(`weak ${evidence.top_failing_pack_ids.join(" / ")}`);
  }
  if (Array.isArray(evidence.regressions) && evidence.regressions.length) {
    parts.push(`regressions ${evidence.regressions.join(" / ")}`);
  }
  if (Array.isArray(evidence.leaking_worlds) && evidence.leaking_worlds.length) {
    parts.push(`leaks ${evidence.leaking_worlds.map((item) => `${item.world_id}:${Number(item.prose_leak_rate || 0).toFixed(3)}`).join(" / ")}`);
  }
  if (evidence.latest_decision) {
    parts.push(`decision ${evidence.latest_decision}`);
  }
  if (evidence.present !== undefined) {
    parts.push(`present ${evidence.present ? "yes" : "no"}`);
  }
  if (evidence.completed_chapters !== undefined && evidence.completed_chapters !== null) {
    parts.push(`chapters ${evidence.completed_chapters}`);
  }
  return parts.join(" · ") || JSON.stringify(evidence);
}

function applySupportPrefill(prefill = {}) {
  if (prefill.account_id && els.opsAccountId) {
    els.opsAccountId.value = prefill.account_id;
  }
  if (prefill.wallet_type && els.opsWalletType) {
    els.opsWalletType.value = prefill.wallet_type;
  }
  if (prefill.amount !== undefined && prefill.amount !== null && els.opsWalletAmount) {
    els.opsWalletAmount.value = String(prefill.amount);
  }
  if (prefill.tier_id && els.opsTierId) {
    els.opsTierId.value = prefill.tier_id;
  }
  if (prefill.subscription_status && els.opsSubscriptionStatus) {
    els.opsSubscriptionStatus.value = prefill.subscription_status;
  }
  if (prefill.entitlement_id && els.opsEntitlementId) {
    els.opsEntitlementId.value = prefill.entitlement_id;
  }
  if (prefill.entitlement_reason && els.opsEntitlementReason) {
    els.opsEntitlementReason.value = prefill.entitlement_reason;
  }
}

function applyGovernanceCasePrefill(prefill = {}) {
  if (prefill.account_id && els.opsAccountId) {
    els.opsAccountId.value = prefill.account_id;
  }
  if (prefill.case_id && els.opsGovernanceCaseId) {
    els.opsGovernanceCaseId.value = prefill.case_id;
  }
  if (prefill.case_type && els.opsGovernanceCaseType) {
    els.opsGovernanceCaseType.value = prefill.case_type;
  }
  if (prefill.target_type && els.opsGovernanceTargetType) {
    els.opsGovernanceTargetType.value = prefill.target_type;
  }
  if (prefill.target_id && els.opsGovernanceTargetId) {
    els.opsGovernanceTargetId.value = prefill.target_id;
  }
  if (prefill.severity && els.opsGovernanceSeverity) {
    els.opsGovernanceSeverity.value = prefill.severity;
  }
  if (prefill.reviewer_id && els.opsGovernanceReviewerId) {
    els.opsGovernanceReviewerId.value = prefill.reviewer_id;
  }
  if (prefill.owner_id && els.opsGovernanceOwnerId) {
    els.opsGovernanceOwnerId.value = prefill.owner_id;
  }
  if (prefill.summary && els.opsGovernanceSummaryInput) {
    els.opsGovernanceSummaryInput.value = prefill.summary;
  }
  if (prefill.description && els.opsGovernanceNotes) {
    els.opsGovernanceNotes.value = prefill.description;
  }
  if (prefill.status && els.opsGovernanceStatus) {
    els.opsGovernanceStatus.value = prefill.status;
  }
  if (prefill.due_at && els.opsGovernanceDueAt) {
    els.opsGovernanceDueAt.value = prefill.due_at;
  }
  if (prefill.disposition && els.opsGovernanceDisposition) {
    els.opsGovernanceDisposition.value = prefill.disposition;
  }
  if (prefill.policy_labels && els.opsGovernancePolicyLabels) {
    els.opsGovernancePolicyLabels.value = Array.isArray(prefill.policy_labels) ? prefill.policy_labels.join(", ") : String(prefill.policy_labels);
  }
}

async function openLearnedWorldDetail(worldId) {
  appState.opsLearnedDetail = await api(`/v1/ops/learned-dashboard/worlds/${worldId}`);
  renderOpsSurface(scopes);
}

async function openLearnedIssueDetail(issueCode) {
  appState.opsLearnedDetail = await api(`/v1/ops/learned-dashboard/issues/${issueCode}`);
  renderOpsSurface();
}

function selectReviewBacklogItem(item) {
  appState.opsReviewCaptureTarget = item;
  if (els.opsReviewIssueCodes) {
    els.opsReviewIssueCodes.value = (item.issue_codes || []).join(",");
  }
  if (els.opsReviewNotes) {
    els.opsReviewNotes.value = item.summary || "";
  }
  if (els.opsReviewScore) {
    els.opsReviewScore.value = item.score_overall !== null && item.score_overall !== undefined
      ? Number(item.score_overall).toFixed(2)
      : "0.65";
  }
  if (els.opsReviewWouldContinue) {
    els.opsReviewWouldContinue.checked = item.decision !== "block";
  }
  if (els.opsReviewWouldPay) {
    els.opsReviewWouldPay.checked = item.decision === "pass";
  }
  if (els.opsPreferenceNotes) {
    els.opsPreferenceNotes.value = item.summary || "";
  }
  if (els.opsRankingNotes) {
    els.opsRankingNotes.value = item.summary || "";
  }
  renderOpsSurface();
}

async function submitOpsReviewCapture() {
  if (!appState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节。");
    return;
  }
  const reviewerId = els.opsReviewerId?.value.trim() || "ops_web";
  const issueCodes = parseIssueCodes(els.opsReviewIssueCodes?.value || "");
  if (!reviewerId || !issueCodes.length) {
    alert("请至少填写 reviewer_id 和 issue codes。");
    return;
  }
  const restore = setBusy(els.opsSubmitReviewCapture, "提交中…");
  try {
    const result = await api("/v1/ops/review-samples", {
      method: "POST",
      body: JSON.stringify({
        chapter_id: appState.opsReviewCaptureTarget.chapter_id,
        world_id: appState.opsReviewCaptureTarget.world_id,
        world_version_id: appState.opsReviewCaptureTarget.world_version_id,
        session_id: appState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        score_overall: Number(els.opsReviewScore?.value || 0.65),
        issue_codes: issueCodes,
        freeform_notes: els.opsReviewNotes?.value || "",
        would_continue: Boolean(els.opsReviewWouldContinue?.checked),
        would_pay: Boolean(els.opsReviewWouldPay?.checked),
      }),
    });
    appState.opsLastActionImpact = result.impact_receipt || null;
    appState.opsReviewCaptureTarget = null;
    if (els.opsReviewNotes) els.opsReviewNotes.value = "";
    if (els.opsReviewIssueCodes) els.opsReviewIssueCodes.value = "";
    await refreshOpsSurface({ preserveLastActionImpact: true });
  } catch (error) {
    alert(`提交 Human Review 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitOpsPreferenceCapture() {
  if (!appState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节，作为 preference 的上下文。");
    return;
  }
  const reviewerId = els.opsReviewerId?.value.trim() || "ops_web";
  const leftRevisionId = els.opsPreferenceLeftRevisionId?.value.trim() || "";
  const rightRevisionId = els.opsPreferenceRightRevisionId?.value.trim() || "";
  const preferredRevisionId = els.opsPreferencePreferredRevisionId?.value.trim() || "";
  if (!reviewerId || !leftRevisionId || !rightRevisionId || !preferredRevisionId) {
    alert("请填写 reviewer_id、left/right revision id 和 preferred revision id。");
    return;
  }
  const restore = setBusy(els.opsSubmitPreferenceCapture, "提交中…");
  try {
    await api("/v1/ops/preference-samples", {
      method: "POST",
      body: JSON.stringify({
        world_id: appState.opsReviewCaptureTarget.world_id,
        world_version_id: appState.opsReviewCaptureTarget.world_version_id,
        chapter_id: appState.opsReviewCaptureTarget.chapter_id,
        session_id: appState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        left_revision_id: leftRevisionId,
        right_revision_id: rightRevisionId,
        preferred_revision_id: preferredRevisionId,
        freeform_notes: els.opsPreferenceNotes?.value || "",
        linked_issue_codes: parseIssueCodes(els.opsReviewIssueCodes?.value || ""),
        preference_strength: els.opsPreferenceStrength?.value || "medium",
      }),
    });
    if (els.opsPreferenceNotes) els.opsPreferenceNotes.value = "";
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`提交 Preference 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitOpsRankingCapture() {
  if (!appState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节，作为 ranking 的上下文。");
    return;
  }
  const reviewerId = els.opsReviewerId?.value.trim() || "ops_web";
  const rankedRevisionIds = (els.opsRankingRevisionIds?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!reviewerId || rankedRevisionIds.length < 2) {
    alert("请填写 reviewer_id，且 ranked revision ids 至少包含两个。");
    return;
  }
  const restore = setBusy(els.opsSubmitRankingCapture, "提交中…");
  try {
    await api("/v1/ops/ranking-samples", {
      method: "POST",
      body: JSON.stringify({
        world_id: appState.opsReviewCaptureTarget.world_id,
        world_version_id: appState.opsReviewCaptureTarget.world_version_id,
        chapter_id: appState.opsReviewCaptureTarget.chapter_id,
        session_id: appState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        ranked_revision_ids: rankedRevisionIds,
        freeform_notes: els.opsRankingNotes?.value || "",
        linked_issue_codes: parseIssueCodes(els.opsReviewIssueCodes?.value || ""),
      }),
    });
    if (els.opsRankingNotes) els.opsRankingNotes.value = "";
    if (els.opsRankingRevisionIds) els.opsRankingRevisionIds.value = "";
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`提交 Ranking 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitOpsPreferenceCapture() {
  if (!appState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节，作为 preference 的上下文。");
    return;
  }
  const reviewerId = els.opsReviewerId?.value.trim() || "ops_web";
  const leftRevisionId = els.opsPreferenceLeftRevisionId?.value.trim() || "";
  const rightRevisionId = els.opsPreferenceRightRevisionId?.value.trim() || "";
  const preferredRevisionId = els.opsPreferencePreferredRevisionId?.value.trim() || "";
  if (!reviewerId || !leftRevisionId || !rightRevisionId || !preferredRevisionId) {
    alert("请填写 reviewer_id、left/right revision id 和 preferred revision id。");
    return;
  }
  const restore = setBusy(els.opsSubmitPreferenceCapture, "提交中…");
  try {
    await api("/v1/ops/preference-samples", {
      method: "POST",
      body: JSON.stringify({
        world_id: appState.opsReviewCaptureTarget.world_id,
        world_version_id: appState.opsReviewCaptureTarget.world_version_id,
        chapter_id: appState.opsReviewCaptureTarget.chapter_id,
        session_id: appState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        left_revision_id: leftRevisionId,
        right_revision_id: rightRevisionId,
        preferred_revision_id: preferredRevisionId,
        freeform_notes: els.opsPreferenceNotes?.value || "",
        linked_issue_codes: parseIssueCodes(els.opsReviewIssueCodes?.value || ""),
        preference_strength: els.opsPreferenceStrength?.value || "medium",
      }),
    });
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`提交 Preference 失败：${error.message}`);
  } finally {
    restore();
  }
}

async function submitOpsRankingCapture() {
  if (!appState.opsReviewCaptureTarget) {
    alert("先从 Review Backlog 里选择一条章节，作为 ranking 的上下文。");
    return;
  }
  const reviewerId = els.opsReviewerId?.value.trim() || "ops_web";
  const rankedRevisionIds = (els.opsRankingRevisionIds?.value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!reviewerId || rankedRevisionIds.length < 2) {
    alert("请填写 reviewer_id，且 ranked revision ids 至少包含两个。");
    return;
  }
  const restore = setBusy(els.opsSubmitRankingCapture, "提交中…");
  try {
    await api("/v1/ops/ranking-samples", {
      method: "POST",
      body: JSON.stringify({
        world_id: appState.opsReviewCaptureTarget.world_id,
        world_version_id: appState.opsReviewCaptureTarget.world_version_id,
        chapter_id: appState.opsReviewCaptureTarget.chapter_id,
        session_id: appState.opsReviewCaptureTarget.session_id,
        reviewer_id: reviewerId,
        ranked_revision_ids: rankedRevisionIds,
        freeform_notes: els.opsRankingNotes?.value || "",
        linked_issue_codes: parseIssueCodes(els.opsReviewIssueCodes?.value || ""),
      }),
    });
    await refreshOpsLearnedFlow();
  } catch (error) {
    alert(`提交 Ranking 失败：${error.message}`);
  } finally {
    restore();
  }
}

function syncViewMode() {
  els.appShell.dataset.view = appState.activeView;
  els.viewExperience.classList.toggle("is-active", appState.activeView === "experience");
  els.viewStorybook.classList.toggle("is-active", appState.activeView === "storybook");
  els.viewBackstage.classList.toggle("is-active", appState.activeView === "backstage");
  els.experienceView.classList.toggle("is-hidden", appState.activeView !== "experience");
  els.storybookView.classList.toggle("is-hidden", appState.activeView !== "storybook");
  els.backstageView.classList.toggle("is-hidden", appState.activeView !== "backstage");
}

function syncProductMode() {
  els.modeReader.classList.toggle("is-active", appState.activeProduct === "reader");
  els.modeAuthor.classList.toggle("is-active", appState.activeProduct === "author");
  els.modeOps.classList.toggle("is-active", appState.activeProduct === "ops");
  els.readerShell.classList.toggle("is-hidden", appState.activeProduct !== "reader");
  els.authorShell.classList.toggle("is-hidden", appState.activeProduct !== "author");
  els.opsShell.classList.toggle("is-hidden", appState.activeProduct !== "ops");
}

function updateStatus() {
  els.worldStatus.textContent = appState.worldId ? "已加载" : "未加载";
  els.sessionStatus.textContent = appState.sessionId ? "运行中" : "未创建";
  els.turnStatus.textContent = appState.currentState ? String(appState.currentState.turn_index) : "-";
  els.worldVersionStatus.textContent = appState.worldVersionId || "-";
  const activePaywall = appState.latestStep?.paywall || appState.sessionPaywall || {};
  const creditEntitlement = appState.readerEntitlements.find((item) => item.entitlement_type === "credits" && item.status === "active");
  els.accessTierStatus.textContent = activePaywall.access_tier || "试读";
  els.quoteStatus.textContent = activePaywall.quote ? `¥${Number(activePaywall.quote).toFixed(2)}` : "¥0.00";
  els.worldId.textContent = appState.sessionId ? "已经开始" : "尚未启程";
  els.sessionId.textContent = appState.currentBundle
    ? (appState.currentBundle.world_bible.creator_controls?.theme_targets || appState.currentBundle.world_bible.themes || [])
        .slice(0, 3)
        .join(" / ") || "未设定"
    : "-";
  els.previewRoute.disabled = !appState.currentState || !appState.currentBundle;
  els.stepSession.disabled = !appState.sessionId;

  if (appState.currentState) {
    els.factCount.textContent = String(appState.currentState.world_facts.length);
    els.promiseCount.textContent = String(appState.currentState.open_promises.length);
    els.tensionValue.textContent = Number(appState.currentState.tension).toFixed(2);
    els.sceneWindow.textContent =
      appState.currentState.recent_scene_functions.length > 0
        ? appState.currentState.recent_scene_functions.join(" / ")
        : "-";
  } else {
    els.factCount.textContent = "0";
    els.promiseCount.textContent = "0";
    els.tensionValue.textContent = "0.00";
    els.sceneWindow.textContent = "-";
  }
  if (els.readerCreditBalance) {
    els.readerCreditBalance.textContent = creditEntitlement ? String(Number(creditEntitlement.balance || 0).toFixed(0)) : "-";
  }
  if (els.readerWorldUnlockStatus) {
    els.readerWorldUnlockStatus.textContent = worldUnlockLabel(activePaywall);
  }
  if (els.readerEntitlementReason) {
    els.readerEntitlementReason.textContent = accessReasonLabel(activePaywall.reason);
  }
}

function renderIntentPrefill() {
  if (!appState.intentPrefill) {
    els.currentPressureText.textContent = "故事还没真正卷起来。";
    els.lastIntentText.textContent = "-";
    els.suggestedPrefillText.textContent = "我想先看看这条命会把我带去哪里。";
    return;
  }
  els.currentPressureText.textContent = appState.intentPrefill.current_pressure || "上一章留下的余波还没散。";
  els.lastIntentText.textContent = appState.intentPrefill.last_player_intent || "-";
  els.suggestedPrefillText.textContent = appState.intentPrefill.suggested_prefill || "";
  if (!els.playerInput.value.trim()) {
    els.playerInput.value = appState.intentPrefill.suggested_prefill || "";
  }
}

function worldDisplayMeta(example) {
  if (example.example_id === "romance") {
    return {
      mood: "爱 / 自我 / 迟疑",
      hook: "更适合试探、坦白和关系拉扯。",
    };
  }
  return {
    mood: "职责 / 名誉 / 自我",
    hook: "更适合承诺、权衡和命运抉择。",
  };
}

function renderWorldGallery() {
  clearNode(els.worldGallery);
  for (const example of appState.examples) {
    const meta = worldDisplayMeta(example);
    const shelfWorld = appState.shelfWorlds.find((item) => item.world_id === example.world_id);
    const card = document.createElement("article");
    card.className = "world-card";
    card.dataset.exampleId = example.example_id;
    if (appState.currentBundle?.example_id === example.example_id) {
      card.classList.add("is-selected");
    }
    card.innerHTML = `
      <h3 class="world-card-title">${example.label}</h3>
      <p class="world-card-body">${example.description}</p>
      <div class="world-card-meta">
        <span>${meta.mood}</span>
        <span>${shelfWorld?.risk_rating || "PG-13"} / ${shelfWorld?.access_state || "trial"}</span>
      </div>
      <div class="world-card-actions">
        <button class="ghost-action world-card-preview">浏览这个世界</button>
        <button class="primary-action world-card-start">进入世界</button>
      </div>
    `;
    card.querySelector(".world-card-preview").addEventListener("click", async () => {
      await loadExampleBundle(example.example_id);
    });
    card.querySelector(".world-card-start").addEventListener("click", async (event) => {
      await loadExampleBundle(example.example_id);
      await bootstrapWorld(event.currentTarget);
    });
    els.worldGallery.appendChild(card);
  }
}

function renderSessionLibrary() {
  clearNode(els.sessionLibrary);
  if (!appState.sessionLibrary.length) {
    clearNode(els.sessionLibrary, "你还没有在这个世界里留下脚印。开始一段新旅程吧。");
    return;
  }

  for (const session of appState.sessionLibrary) {
    const card = document.createElement("article");
    card.className = "session-card";
    if (appState.sessionId === session.session_id) {
      card.classList.add("is-selected");
    }
    card.innerHTML = `
      <h3 class="session-card-title">${session.last_chapter_title || session.last_event_title || "刚刚开始"}</h3>
      <p class="session-card-body">
        已经走到第 ${session.current_turn_index} 幕。${formatTimestamp(session.created_at)} 留下这段旅程。
      </p>
      <div class="session-card-meta">
        <span>${session.current_turn_index} 幕</span>
        <span>${session.last_chapter_title || session.last_event_title ? "可继续阅读" : "等待第一幕"}</span>
      </div>
      <div class="session-card-actions">
        <button class="ghost-action session-card-open">继续阅读</button>
        <button class="ghost-action session-card-delete">删除</button>
      </div>
    `;
    card.querySelector(".session-card-open").addEventListener("click", async (event) => {
      await restoreSession(session.session_id, event.currentTarget);
    });
    card.querySelector(".session-card-delete").addEventListener("click", async () => {
      await deleteSession(session.session_id);
    });
    els.sessionLibrary.appendChild(card);
  }
}

function renderSuggestedInputs() {
  clearNode(els.suggestedInputs);
  if (!appState.currentBundle) return;
  for (const item of appState.currentBundle.player_inputs) {
    const fragment = els.suggestionTemplate.content.cloneNode(true);
    const button = fragment.querySelector("button");
    button.textContent = item.raw_input;
    button.addEventListener("click", () => {
      els.playerInput.value = item.raw_input;
      appState.selectedIntentOverride = item.intent_vector || null;
    });
    els.suggestedInputs.appendChild(fragment);
  }
}

function renderRoutePreview() {
  if (!appState.latestPreview?.routes?.length) {
    clearNode(els.routePreview, "还没有看到命运分岔。先开始一段旅程，再点“看看接下来”。");
    return;
  }
  clearNode(els.routePreview);
  const ranks = ["最有可能", "另一种走向", "隐秘支线"];
  appState.latestPreview.routes.forEach((route, index) => {
    const leadEvent = route.events?.[0];
    const line = document.createElement("div");
    line.className = "route-line";
    line.innerHTML = `
      <span class="route-rank">${ranks[index] || "可能的命运"}</span>
      <strong>${leadEvent?.title || route.event_ids.join(" → ")}</strong>
      <span class="list-card-score">命运热度 ${route.total_score.toFixed(3)}</span>
      <p class="list-card-body">${leadEvent?.summary || route.explanation}</p>
    `;
    els.routePreview.appendChild(line);
  });
}

function spotlightPreviewResult() {
  if (!els.routePreviewPanel) return;
  els.routePreviewPanel.classList.remove("is-highlighted");
  void els.routePreviewPanel.offsetWidth;
  els.routePreviewPanel.classList.add("is-highlighted");
  els.routePreviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => {
    els.routePreviewPanel?.classList.remove("is-highlighted");
  }, 1400);
}

function spotlightChapter() {
  if (!els.chapterPanel) return;
  els.chapterPanel.classList.remove("is-highlighted");
  void els.chapterPanel.offsetWidth;
  els.chapterPanel.classList.add("is-highlighted");
  els.chapterPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => {
    els.chapterPanel?.classList.remove("is-highlighted");
  }, 1400);
}

function renderCards(target, items, formatter, emptyText) {
  clearNode(target);
  if (!items.length) {
    clearNode(target, emptyText);
    return;
  }
  target.classList.remove("empty-state");
  for (const item of items) {
    const fragment = els.listCardTemplate.content.cloneNode(true);
    const title = fragment.querySelector("h3");
    const score = fragment.querySelector(".list-card-score");
    const body = fragment.querySelector(".list-card-body");
    const formatted = formatter(item);
    title.textContent = formatted.title;
    score.textContent = formatted.score;
    body.textContent = formatted.body;
    if (formatted.active) {
      fragment.querySelector(".list-card").classList.add("is-active");
    }
    target.appendChild(fragment);
  }
}

function setTone(tone) {
  appState.activeTone = tone;
  for (const pill of els.tonePills) {
    pill.classList.toggle("is-active", pill.dataset.tone === tone);
  }
  renderStorybook();
  renderStoryFeed();
}

function getStorySource() {
  if (appState.selectedReplayIndex !== null && appState.replay?.event_trace?.[appState.selectedReplayIndex]) {
    return {
      event: appState.replay.event_trace[appState.selectedReplayIndex],
      rendered: appState.replay.rendered_scenes?.[appState.selectedReplayIndex] || null,
      reader_view: appState.replay.reader_views?.[appState.selectedReplayIndex] || null,
      index: appState.selectedReplayIndex,
    };
  }
  if (appState.latestStep?.chosen_event) {
    return {
      event: appState.latestStep.chosen_event,
      rendered: appState.latestStep.rendered_scene,
      reader_view: appState.latestStep.reader_view || null,
      index: null,
    };
  }
  return null;
}

function renderStorybook() {
  const source = getStorySource();
  if (!source) {
    els.storyHero.dataset.motif = "";
    els.storyTitle.textContent = "画面会在这里展开";
    els.storyCaption.textContent = "推进一幕之后，这里会变成一张带情绪和光影的故事画面。";
    els.storyQuote.textContent = "当故事开始流动，这里会出现一句最能代表这一幕的引句。";
    els.storyPrompt.textContent = "-";
    els.storyMotif.textContent = "-";
    clearNode(els.storyBeats, "这里会显示这一幕最值得抓住的三个节拍。");
    clearNode(els.storyDetails, "这里会显示画面中的气味、动作和情绪提示。");
    els.storyProse.textContent = "这里会显示图文版本对应的正文。";
    clearNode(els.storySequence, "故事累积起来后，这里会变成一条可以回看的章节画卷。");
    return;
  }

  const rendered = source.rendered || {};
  const readerView = source.reader_view || {};
  const sceneCard = readerView.scene_card || {};
  els.storyHero.dataset.motif = rendered.image_motif || source.event.scene_function || "";
  els.storyTitle.textContent = readerView.chapter_title || rendered.story_title || source.event.title || "当前剧情";
  els.storyCaption.textContent = readerView.recap || rendered.chapter_summary || rendered.image_caption || source.event.summary || "暂无说明。";
  els.storyQuote.textContent = sceneCard.quote || rendered.pull_quote || "这一幕还没有留下自己的引句。";
  els.storyPrompt.textContent = sceneCard.summary || rendered.visual_prompt || "暂无 visual prompt";
  els.storyMotif.textContent = sceneCard.palette_hint || rendered.image_motif || source.event.scene_function || "-";
  clearNode(els.storyBeats);
  const beatItems = sceneCard.story_beats || rendered.story_beats || [];
  if (beatItems.length) {
    beatItems.forEach((beat) => {
      const node = document.createElement("span");
      node.className = "story-beat";
      node.textContent = beat;
      els.storyBeats.appendChild(node);
    });
  } else {
    clearNode(els.storyBeats, "这里会显示这一幕最值得抓住的三个节拍。");
  }
  clearNode(els.storyDetails);
  const detailItems = sceneCard.visual_details || rendered.visual_details || [];
  if (detailItems.length) {
    detailItems.forEach((detail) => {
      const node = document.createElement("span");
      node.className = "story-detail";
      node.textContent = detail;
      els.storyDetails.appendChild(node);
    });
  } else {
    clearNode(els.storyDetails, "这里会显示画面中的气味、动作和情绪提示。");
  }
  els.storyProse.textContent =
    readerView.body ||
    rendered[appState.activeTone] ||
    rendered.premium_prose ||
    source.event.summary ||
    "暂无正文。";

  clearNode(els.storySequence);
  if (!appState.replay?.event_trace?.length) {
    clearNode(els.storySequence, "故事累积起来后，这里会变成一条可以回看的章节画卷。");
    return;
  }

  appState.replay.event_trace.forEach((event, index) => {
    const renderedScene = appState.replay.rendered_scenes?.[index] || {};
    const readerView = appState.replay.reader_views?.[index] || {};
    const card = document.createElement("article");
    card.className = "story-sequence-card";
    if (index === appState.selectedReplayIndex) {
      card.classList.add("is-active");
    }
    card.innerHTML = `
      <h3>Turn ${index + 1} · ${readerView.chapter_title || renderedScene.story_title || event.title}</h3>
      <p class="list-card-body">${readerView.recap || renderedScene.chapter_summary || renderedScene.image_caption || event.summary}</p>
    `;
    card.addEventListener("click", () => {
      appState.selectedReplayIndex = index;
      renderReplay();
      renderStorybook();
    });
    els.storySequence.appendChild(card);
  });
}

function renderLatestStep() {
  if (!appState.latestStep) {
    els.chosenEventTitle.textContent = "故事还没开始";
    els.bestRoute.textContent = "当你写下一句心意，系统会在这里接住它。";
    clearNode(els.storyFeed, "载入 world 并执行一步后，这里会按时间顺序出现连续章节。");
    clearNode(els.scoredCandidates, "幕后会在这里比较不同走向。");
    clearNode(els.criticTrace, "幕后会在这里解释为什么这条线更成立。");
    els.lastEventTitle.textContent = "-";
    els.paywallBanner.classList.add("is-hidden");
    renderStorybook();
    renderIntentPrefill();
    return;
  }

  const readerView = appState.latestStep.reader_view || {};
  els.chosenEventTitle.textContent = readerView.chapter_title || appState.latestStep.chosen_event.title;
  els.lastEventTitle.textContent = readerView.chapter_title || appState.latestStep.chosen_event.title;
  els.bestRoute.textContent = appState.latestStep.routes?.length
    ? (() => {
        const routeEvents = appState.latestStep.routes[0].events || [];
        const titles = routeEvents.map((event) => event.title).filter(Boolean);
        if (!titles.length) return "主线已经开始往下一处更难退开的命运口子靠近。";
        if (titles.length === 1) return `接下来更可能逼近的是：${titles[0]}。`;
        return `接下来更可能先逼近“${titles[0]}”，随后余波会把你带向“${titles[1]}”。`;
      })()
    : readerView.recap || "此刻还没有新的主线判断。";

  const batch = appState.latestStep.candidate_batch || { raw_candidates: [], legal_candidates: [], debug: {} };
  els.candidateSummary.textContent =
    batch.raw_candidates?.length
      ? `系统刚才比对了 ${batch.raw_candidates.length} 种可能，留下 ${batch.legal_candidates.length} 条真正说得通的走向。`
      : "幕后会在这里比较不同走向。";

  renderCards(
    els.scoredCandidates,
    appState.latestStep.scored_candidates || [],
    (item) => ({
      title: item.event.title,
      score: `匹配度 ${item.total_score.toFixed(3)}`,
      body:
        `${item.explanation}\n` +
        (item.critic_decisions?.length
          ? item.critic_decisions
              .map((decision) => `${decision.critic_name}: ${decision.verdict} · ${decision.reasons.join(" / ")}`)
              .join("\n")
          : "这一条线没有额外诊断备注。"),
    }),
    "幕后会在这里比较不同走向。"
  );

  renderCards(
    els.criticTrace,
    appState.latestStep.critic_trace || [],
    (item) => ({
      title: item.event_id,
      score: `修正 ${Number(item.critic_penalty || 0).toFixed(3)}`,
      body:
        (item.critic_decisions || [])
          .map((decision) => `${decision.critic_name}: ${decision.verdict} · ${decision.reasons.join(" / ")}`)
          .join("\n") || "这一步没有额外诊断。",
    }),
    "幕后会在这里解释为什么这条线更成立。"
  );

  if (appState.latestStep?.paywall?.required) {
    els.paywallBanner.classList.remove("is-hidden");
    const paywall = appState.latestStep.paywall;
    const tierText = paywall.required_display_name || (paywall.tier_id ? tierLabel(paywall.tier_id) : "付费权益");
    const balanceText = paywall.balance !== null && paywall.balance !== undefined
      ? `${Number(paywall.balance).toFixed(0)} Story Credits`
      : "没有可用 Story Credits";
    const capabilityText = paywall.required_capability ? `需要能力 ${paywall.required_capability}` : "需要继续阅读权益";
    els.paywallBannerCopy.textContent = `当前继续被拦截：${accessReasonLabel(paywall.reason)}。${capabilityText}，推荐通过 ${tierText} 解锁，当前报价 $${Number(paywall.quote || 0).toFixed(2)} / month。你的账户目前有 ${balanceText}，当前世界状态：${worldUnlockLabel(paywall)}。`;
    els.paywallBannerCheckout.textContent = `解锁 ${tierText}`;
    els.paywallBannerCheckout.onclick = () => startReaderCheckout(paywall.suggested_checkout_tier || paywall.tier_id || "play_pass");
  } else {
    els.paywallBanner.classList.add("is-hidden");
    if (els.paywallBannerCheckout) {
      els.paywallBannerCheckout.onclick = null;
    }
  }
  for (const pill of els.tonePills) {
    pill.classList.toggle("is-active", pill.dataset.tone === appState.activeTone);
  }
  renderStorybook();
  renderStoryFeed();
  renderIntentPrefill();
}

function renderStoryFeed() {
  const chapters = [];
  if (appState.replay?.reader_views?.length) {
    appState.replay.reader_views.forEach((readerView, index) => {
      chapters.push({
        chapterTitle: readerView.chapter_title,
        recap: readerView.recap,
        body: readerView.body,
        relationshipHints: readerView.relationship_hints || [],
        chapterIndex: readerView.chapter_index || index + 1,
      });
    });
  } else if (appState.latestStep?.reader_view) {
    chapters.push({
      chapterTitle: appState.latestStep.reader_view.chapter_title,
      recap: appState.latestStep.reader_view.recap,
      body: appState.latestStep.reader_view.body,
      relationshipHints: appState.latestStep.reader_view.relationship_hints || [],
      chapterIndex: appState.latestStep.reader_view.chapter_index || 1,
    });
  }

  clearNode(els.storyFeed);
  if (!chapters.length) {
    clearNode(els.storyFeed, "载入 world 并执行一步后，这里会按时间顺序出现连续章节。");
    return;
  }

  chapters.forEach((chapter, index) => {
    const card = document.createElement("article");
    card.className = "story-feed-card";
    if (index === chapters.length - 1) {
      card.classList.add("is-active");
    }
    card.innerHTML = `
      <div class="story-feed-head">
        <p class="panel-label">第 ${chapter.chapterIndex} 章</p>
        <h3>${chapter.chapterTitle}</h3>
      </div>
      <p class="story-feed-recap">${chapter.recap || ""}</p>
      <div class="story-feed-body">${chapter.body || ""}</div>
      ${chapter.relationshipHints.length ? `<div class="story-feed-hints">${chapter.relationshipHints.map((hint) => `<span>${hint}</span>`).join("")}</div>` : ""}
    `;
    els.storyFeed.appendChild(card);
  });
}

function renderReplay() {
  if (!appState.replay?.event_trace?.length) {
    clearNode(els.replayTimeline, "推进几幕之后，这里会变成一条可回看的章节轨迹。");
    renderStorybook();
    return;
  }
  renderCards(
    els.replayTimeline,
    appState.replay.event_trace.map((event, index) => ({
      event,
      index,
      promises: appState.replay.promise_ledger_snapshots[index] || [],
      readerView: appState.replay.reader_views?.[index] || {},
    })),
    ({ event, index, promises, readerView }) => ({
      title: `Turn ${index + 1} · ${readerView.chapter_title || event.title}`,
      score: event.scene_function || "",
      body:
        `${readerView.recap || event.summary}\n` +
        `未解牵挂: ${promises.length}\n` +
        `Tags: ${(event.tags || []).join(", ")}`,
      active: index === appState.selectedReplayIndex,
    }),
    "推进几幕之后，这里会变成一条可回看的章节轨迹。"
  );
  renderStorybook();
}

function updateBundleSummary() {
  if (!appState.currentBundle) {
    els.worldTitle.textContent = "选择一个世界";
    els.worldDescription.textContent = "先挑一个世界，再开始一段新的命运旅程。";
    els.featuredWorldTitle.textContent = "先挑一个世界，再开始一段新的命运旅程。";
    els.featuredWorldCopy.textContent = "你会在这里看到这个世界的主命题、情绪底色，以及这一轮旅程最适合怎样推进。";
    els.featuredWorldMood.textContent = "-";
    els.featuredWorldHook.textContent = "-";
    return;
  }
  const meta = worldDisplayMeta(appState.currentBundle);
  els.worldTitle.textContent = appState.currentBundle.label;
  els.worldDescription.textContent = appState.currentBundle.description;
  els.featuredWorldTitle.textContent = appState.currentBundle.label;
  els.featuredWorldCopy.textContent = appState.currentBundle.description;
  els.featuredWorldMood.textContent = meta.mood;
  els.featuredWorldHook.textContent = meta.hook;
}

function renderAuthorDrafts() {
  clearNode(els.authorDraftList);
  if (!appState.authorDrafts.length) {
    clearNode(els.authorDraftList, "还没有 draft。先把当前世界保存为 Draft。");
    return;
  }
  const simulateAccess = appState.authorAccessSnapshot?.actions?.simulate || null;
  const submitAccess = appState.authorAccessSnapshot?.actions?.submit_draft || null;
  const validateAccess = appState.authorAccessSnapshot?.actions?.validate_draft || null;
  appState.authorDrafts.forEach((draft) => {
    const card = document.createElement("article");
    card.className = "list-card";
    if (draft.world_version_id === appState.activeDraftVersionId) {
      card.classList.add("is-active");
    }
    card.innerHTML = `
      <div class="list-card-head">
        <h3>${draft.title || draft.world_id}</h3>
        <span class="list-card-score">${draft.status}</span>
      </div>
      <p class="list-card-body">版本 ${draft.version || draft.world_version_id} · 风险 ${draft.risk_rating || "未定"}</p>
      <div class="composer-actions">
        <button class="ghost-action draft-validate">校验</button>
        <button class="ghost-action draft-simulate">模拟</button>
        <button class="primary-action draft-submit">送审</button>
      </div>
    `;
    card.querySelector(".draft-validate").addEventListener("click", () => {
      (async () => {
        try {
          await validateDraftVersion(draft.world_version_id);
        } catch (error) {
          const detail = parseErrorDetail(error);
          await refreshAuthorSurface();
          if (detail?.code === "author_entitlement_required") {
            alertAuthorGating(detail, "校验 Draft");
            return;
          }
          alert(`校验失败：${error.message}`);
        }
      })();
    });
    card.querySelector(".draft-simulate").addEventListener("click", async () => {
      try {
        await simulateDraftVersion(draft.world_version_id);
      } catch (error) {
        const detail = parseErrorDetail(error);
        await refreshAuthorSurface();
        if (detail?.code === "author_entitlement_required") {
          alert(`当前不能模拟：${accessReasonLabel(detail.reason)}。需要 ${detail.required_display_name || tierLabel(detail.required_tier)}，当前 ${detail.wallet_type || "-"} 余额 ${Number(detail.balance || 0).toFixed(0)}。`);
          return;
        }
        alert(`模拟失败：${error.message}`);
      }
    });
    if (simulateAccess && !simulateAccess.allowed) {
      const button = card.querySelector(".draft-simulate");
      button.disabled = true;
      button.title = gatingHint(simulateAccess);
    }
    if (validateAccess && !validateAccess.allowed) {
      const button = card.querySelector(".draft-validate");
      button.disabled = true;
      button.title = gatingHint(validateAccess);
    }
    card.querySelector(".draft-submit").addEventListener("click", async () => {
      try {
        await submitDraftVersion(draft.world_version_id);
      } catch (error) {
        const detail = parseErrorDetail(error);
        await refreshAuthorSurface();
        if (detail?.code === "author_entitlement_required") {
          alertAuthorGating(detail, "提交送审");
          return;
        }
        alert(`送审失败：${error.message}`);
      }
    });
    if (submitAccess && !submitAccess.allowed) {
      const button = card.querySelector(".draft-submit");
      button.disabled = true;
      button.title = gatingHint(submitAccess);
    }
    card.addEventListener("click", async () => {
      appState.activeDraftVersionId = draft.world_version_id;
      appState.activeDraftDetail = await api(`/v1/author/drafts/${draft.world_version_id}`);
      appState.selectedAuthorRevisionIndex = null;
      renderAuthorDrafts();
      renderAuthorReports();
    });
    els.authorDraftList.appendChild(card);
  });
}

function renderAuthorWorkflow() {
  clearNode(els.authorWorkflow);
  const workflow = appState.authorWorkflowSummary;
  if (!workflow) {
    clearNode(els.authorWorkflow, "这里会显示 brief -> draft -> simulate -> revise -> submit 的当前阶段与建议动作。");
    return;
  }
  const card = document.createElement("article");
  card.className = "list-card";
  card.innerHTML = `
    <div class="list-card-head">
      <h3>${workflow.draft_title || "Author Workflow"}</h3>
      <span class="list-card-score">${authorStageLabel(workflow.stage)}</span>
    </div>
    <p class="list-card-body">world_version ${workflow.world_version_id || "-"}\nrecommended ${workflow.recommended_action || "-"}\nstatus ${workflow.status || "-"}\nvalidation ${workflow.validation_summary?.status || "-"} · errors ${workflow.validation_summary?.error_count ?? 0} · warnings ${workflow.validation_summary?.warning_count ?? 0}\nsimulation ${workflow.simulation_summary?.latest_decision || "-"} · pass ${formatPercent(workflow.simulation_summary?.pass_rate)} · rewrite ${formatPercent(workflow.simulation_summary?.rewrite_rate)} · block ${formatPercent(workflow.simulation_summary?.block_rate)}\nsimulation freshness ${workflow.simulation_freshness?.status || "-"}\n\nstages:\n${(workflow.stages || []).map((item) => `${item.key} · ${item.label} · ${item.status}`).join("\n") || "-"}\n\nblockers:\n${(workflow.blockers || []).map((item) => `${item.key} · ${item.message}`).join("\n") || "-"}</p>
  `;
  els.authorWorkflow.appendChild(card);
  if ((workflow.cta_actions || []).length) {
    const actions = document.createElement("div");
    actions.className = "composer-actions";
    workflow.cta_actions.forEach((item) => {
      const button = document.createElement("button");
      button.className = item.primary ? "primary-action" : "ghost-action";
      button.textContent = item.label || item.action_id;
      button.disabled = item.enabled === false;
      if (item.reason) {
        button.title = item.reason;
      }
      button.addEventListener("click", async () => {
        try {
          await runAuthorWorkflowAction(item.action_id);
        } catch (error) {
          alert(`执行工作流动作失败：${error.message}`);
        }
      });
      actions.appendChild(button);
    });
    els.authorWorkflow.appendChild(actions);
  }
}

function renderAuthorReports() {
  renderAuthorAuthStatus();
  els.authorActiveDraft.textContent = appState.activeDraftVersionId || "-";
  els.authorValidationStatus.textContent = appState.authorValidationReport?.status || (appState.authorValidationReport?.ok ? "ok" : "未运行");
  els.authorSimulationChapters.textContent = String(appState.authorSimulationReport?.completed_chapters || 0);
  const saveDraftAccess = appState.authorAccessSnapshot?.actions?.save_draft || null;
  const briefAccess = appState.authorAccessSnapshot?.actions?.draft_from_brief || null;
  const simulateAccess = appState.authorAccessSnapshot?.actions?.simulate || null;
  if (els.authorBriefAccess) {
    els.authorBriefAccess.textContent = gatingStatusLabel(briefAccess);
    els.authorBriefAccess.title = gatingHint(briefAccess);
  }
  if (els.authorSimulateAccess) {
    els.authorSimulateAccess.textContent = gatingStatusLabel(simulateAccess);
    els.authorSimulateAccess.title = gatingHint(simulateAccess);
  }
  if (els.authorCreateDraftFromBrief) {
    els.authorCreateDraftFromBrief.disabled = Boolean(briefAccess && !briefAccess.allowed);
    els.authorCreateDraftFromBrief.title = gatingHint(briefAccess);
  }
  if (els.authorCreateDraft) {
    els.authorCreateDraft.disabled = Boolean(saveDraftAccess && !saveDraftAccess.allowed);
    els.authorCreateDraft.title = gatingHint(saveDraftAccess);
  }
  renderAuthorWorkflow();
  renderAuthorDraftDetail();
  renderAuthorRevisionPanels();
  renderAuthorCompare();
  renderAuthorCollaboration();
  clearNode(els.authorValidationReport);
  const validationPayload = appState.authorValidationReport || appState.activeDraftDetail?.validation_report || null;
  const validationDrilldown = appState.authorValidationReport?.validation_drilldown || appState.activeDraftDetail?.validation_drilldown || {};
  if (validationPayload) {
    const node = document.createElement("article");
    node.className = "list-card";
    const validation = validationPayload;
    node.innerHTML = `
      <div class="list-card-head">
        <h3>Validation / Submit 结果</h3>
        <span class="list-card-score">${validation.status || (validation.ok ? "ok" : "pending")}</span>
      </div>
      <p class="list-card-body">ok: ${validation.ok ? "true" : "false"}\nerrors: ${(validation.errors || []).length || 0}\nwarnings: ${(validation.warnings || []).length || 0}\n\nblockers:\n${(validationDrilldown.blockers || []).map((item) => `${item.category} · ${item.severity}\n${item.message}\n建议：${item.recommended_action}`).join("\n\n") || (validation.errors || []).join("\n") || "-"}\n\nwarnings:\n${(validationDrilldown.warning_groups || []).map((item) => `${item.category} · ${item.message}\n建议：${item.recommended_action}`).join("\n\n") || (validation.warnings || []).join("\n") || "-"}\n\nnext actions:\n${(validationDrilldown.next_actions || []).join("\n") || "-"}</p>
    `;
    els.authorValidationReport.appendChild(node);
  } else {
    clearNode(els.authorValidationReport, "选择一个 draft 后，这里会显示 validation report。");
  }
  clearNode(els.authorSimulationReport);
  const simulationReport = appState.authorSimulationReport || appState.activeDraftDetail?.simulation_report || null;
  const simulationDrilldown = getSimulationDrilldown();
  if (simulationReport) {
    const topIssues = simulationReport.evaluation_summary?.top_issue_categories || [];
    const failingPacks = simulationReport.top_failing_packs || appState.opsCrossPackQuality?.top_failing_packs || [];
    const metricDeltas = simulationReport.metric_deltas || {};
    const deltaSummary = simulationReport.cross_pack_summary?.delta_summary || appState.opsCrossPackQuality?.delta_summary || {};
    const currentDiagnosis = simulationReport.cross_pack_summary?.worlds?.find(
      (item) => item.world_id === appState.activeDraftDetail?.world_id
    );
    const diffSummary = buildSimulationDiffSummary(appState.authorPreviousSimulationReport, simulationReport);

    els.authorSimulationReport.appendChild(
      createListCard({
        title: "Simulation 概览",
        score: simulationReport.ok ? "ok" : "warn",
        body:
          `完成章节 ${simulationReport.completed_chapters || 0} / ${simulationDrilldown.chapter_budget || simulationReport.chapter_budget || "-"} · latest ${simulationReport.latest_decision || "-"}\n` +
          `completion ${simulationDrilldown.completion_ratio !== undefined ? Number(simulationDrilldown.completion_ratio).toFixed(3) : "-"} · stop ${simulationDrilldown.stop_reason || simulationReport.stop_reason || "-"}\n` +
          `pass ${formatPercent(simulationReport.evaluation_summary?.pass_rate)} · rewrite ${formatPercent(simulationReport.evaluation_summary?.rewrite_rate)} · block ${formatPercent(simulationReport.evaluation_summary?.block_rate)}\n` +
          `${currentDiagnosis ? `当前 Draft 诊断：${currentDiagnosis.issue_summary?.dominant_issue || "-"} · ${(currentDiagnosis.issue_summary?.weakest_dimensions || []).map((item) => `${item.name}=${Number(item.value || 0).toFixed(3)}`).join(" / ") || "-"}` : "当前 Draft 诊断：-"}\n` +
          `${Object.keys(metricDeltas).length ? `指标 delta：${Object.entries(metricDeltas).map(([key, value]) => `${key}=${Number(value).toFixed(3)}`).join(" / ")}` : "指标 delta：-"}\n` +
          `${diffSummary ? `与上次 simulation 对比：\n${diffSummary}` : "与上次 simulation 对比：-"}\n` +
          `${typeof deltaSummary.cross_pack_pass_rate_delta === "number" ? `cross-pack pass rate delta: ${deltaSummary.cross_pack_pass_rate_delta >= 0 ? "+" : ""}${deltaSummary.cross_pack_pass_rate_delta.toFixed(3)}` : "cross-pack pass rate delta: -"}`
      })
    );

    els.authorSimulationReport.appendChild(
      createListCard({
        title: "Issue / Module Drill-down",
        score: `${(simulationDrilldown.issue_histogram || []).length} 类`,
        body:
          `${(simulationDrilldown.issue_histogram || []).length ? `issue histogram:\n${simulationDrilldown.issue_histogram.map((item) => `${item.issue_code} · ${item.count} · ${item.owning_module || "-"}`).join("\n")}` : "issue histogram: -"}\n\n` +
          `${(simulationDrilldown.module_histogram || []).length ? `module histogram:\n${simulationDrilldown.module_histogram.map((item) => `${item.owning_module} · ${item.count} · ${(item.issue_codes || []).join("/") || "-"}`).join("\n")}` : "module histogram: -"}\n\n` +
          `${Object.keys(simulationDrilldown.decision_histogram || {}).length ? `decision histogram:\n${Object.entries(simulationDrilldown.decision_histogram || {}).map(([key, value]) => `${key}: ${value}`).join("\n")}` : "decision histogram: -"}\n\n` +
          `${Object.keys(simulationDrilldown.story_phase_histogram || {}).length ? `story phases:\n${Object.entries(simulationDrilldown.story_phase_histogram || {}).map(([key, value]) => `${key}: ${value}`).join("\n")}` : "story phases: -"}\n\n` +
          `${Object.keys(simulationDrilldown.scene_function_histogram || {}).length ? `scene functions:\n${Object.entries(simulationDrilldown.scene_function_histogram || {}).map(([key, value]) => `${key}: ${value}`).join("\n")}` : "scene functions: -"}\n\n` +
          `${(simulationDrilldown.next_actions || topIssues || []).length ? `next actions:\n${(simulationDrilldown.next_actions || topIssues || []).map((item, index) => `${index + 1}. ${item.issue_code} -> ${item.owning_module}\n建议：${item.fix_hint}`).join("\n\n")}` : "next actions: -"}\n\n` +
          `${simulationDrilldown.quality_pass_summary?.action_histogram?.length ? `quality pass:\nchapters touched ${simulationDrilldown.quality_pass_summary.chapters_touched}\n${simulationDrilldown.quality_pass_summary.action_histogram.map((item) => `${item.action}: ${item.count}`).join("\n")}` : "quality pass: -"}`
      })
    );

    els.authorSimulationReport.appendChild(
      createListCard({
        title: "Issue Focus Queue",
        score: `${(simulationDrilldown.issue_focus_queue || []).length} 项`,
        body:
          `${(simulationDrilldown.issue_focus_queue || []).map((item) => `${item.issue_code} · ${item.count} · ${item.owning_module || "-"}\n建议：${item.fix_hint || "-"}\n章节：${(item.chapter_targets || []).map((chapter) => `${chapter.chapter_index}.${chapter.chapter_title}(${chapter.scene_function || "-"}/${chapter.decision || "-"})`).join(" / ") || "-"}`).join("\n\n") || "暂无 issue focus queue。"}`
      })
    );
    if ((simulationDrilldown.issue_focus_queue || [])[0]?.chapter_targets?.[0]) {
      const queueActions = document.createElement("div");
      queueActions.className = "composer-actions";
      const firstTarget = simulationDrilldown.issue_focus_queue[0].chapter_targets[0];
      const button = document.createElement("button");
      button.className = "ghost-action";
      button.textContent = "评论首个问题章节";
      button.addEventListener("click", () => {
        prefillAuthorCommentAnchor("simulation", String(firstTarget.chapter_index));
      });
      queueActions.appendChild(button);
      els.authorSimulationReport.appendChild(queueActions);
    }

    els.authorSimulationReport.appendChild(
      createListCard({
        title: "Weakest Chapters",
        score: `${(simulationDrilldown.weakest_chapters || []).length} 章`,
        body:
          `${(simulationDrilldown.weakest_chapters || []).map((item) => `${item.chapter_index}. ${item.chapter_title || item.chapter_id}\n${item.decision} · score ${Number(item.overall_score || 0).toFixed(3)} · scene ${item.scene_function || "-"}\nissues ${(item.issue_codes || []).join(" / ") || "-"}\nsignals rep ${Number(item.signal_snapshot?.repetition_score || 0).toFixed(3)} · expo ${Number(item.signal_snapshot?.exposition_ratio || 0).toFixed(3)} · hook ${Number(item.signal_snapshot?.hook_quality || 0).toFixed(3)} · detail ${Number(item.signal_snapshot?.concrete_detail_density || 0).toFixed(3)}\nquality pass ${(item.quality_pass_actions || []).join(" / ") || "-"}`).join("\n\n") || "暂无章节级弱项。"}`
      })
    );

    els.authorSimulationReport.appendChild(
      createListCard({
        title: "Chapter Drill-down",
        score: `${(simulationDrilldown.chapter_breakdown || []).length} 章`,
        body:
          `${(simulationDrilldown.chapter_breakdown || []).map((item) => `${item.chapter_index}. ${item.chapter_title || item.chapter_id}\n${item.decision} · score ${Number(item.overall_score || 0).toFixed(3)} · scene ${item.scene_function || "-"}\nissues ${(item.issue_codes || []).join(" / ") || "-"}\nchoices ${(item.choices_preview || []).join(" / ") || "-"}\nquality pass ${(item.quality_pass_actions || []).join(" / ") || "-"}\ncritic signals ${item.critic_signal_count ?? 0}`).join("\n\n") || "暂无 chapter breakdown。"}`
      })
    );
  } else {
    clearNode(els.authorSimulationReport, "运行 simulation 后，这里会显示 route length、reader leak 与 cost estimate。");
  }
  const worldpack = getActiveDraftWorldpack() || {};
  const stylePack = worldpack.narrative_style_pack || {};
  const dialogueBundle = {
    dialogue_realism_policy: worldpack.dialogue_realism_policy || {},
    voice_profiles: worldpack.voice_profiles || stylePack.dialogue?.voice_profiles || {},
    response_cadence_profiles: worldpack.response_cadence_profiles || stylePack.dialogue?.response_profiles || {},
    pressure_response_styles: worldpack.pressure_response_styles || stylePack.dialogue?.pressure_styles || {},
  };
  els.authorVoiceEditor.value = JSON.stringify(dialogueBundle, null, 2);
  els.authorActionEditor.value = JSON.stringify(
    worldpack.emotion_action_policies || { default: stylePack.emotion_actions || {} },
    null,
    2
  );
  els.authorSensoryEditor.value = JSON.stringify(
    worldpack.sensory_grounding_policies || { default: stylePack.sensory_grounding || {} },
    null,
    2
  );
  els.authorSceneEditor.value = JSON.stringify(
    worldpack.scene_realization_contracts || { default: stylePack.scene_realization || {} },
    null,
    2
  );
  renderStylePacingHookControls();
  renderCharacterEditor();
  renderSceneEditor();
}

async function refreshAuthorSurface() {
  await hydrateAuthorAuthSession();
  if (!appState.authorBriefTemplate) {
    try {
      appState.authorBriefTemplate = await api("/v1/author/brief-template");
      populateAuthorBriefForm();
    } catch (error) {
      console.warn("brief template unavailable", error);
    }
  }
  const payload = await api("/v1/author/drafts");
  appState.authorDrafts = payload.drafts;
  if (!appState.activeDraftVersionId && appState.authorDrafts.length) {
    appState.activeDraftVersionId = appState.authorDrafts[0].world_version_id;
  }
  if (appState.activeDraftVersionId) {
    try {
      appState.activeDraftDetail = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`);
    } catch (error) {
      appState.activeDraftDetail = null;
      appState.activeDraftVersionId = null;
    }
  }
  if (appState.activeDraftVersionId) {
    try {
      appState.authorCollaborationSummary = await api(`/v1/author/drafts/${appState.activeDraftVersionId}/collaboration`);
      const availableThreadIds = new Set((appState.authorCollaborationSummary?.threads || []).map((item) => item.thread_id));
      if (appState.selectedAuthorThreadId && !availableThreadIds.has(appState.selectedAuthorThreadId)) {
        appState.selectedAuthorThreadId = null;
      }
      if (!appState.selectedAuthorThreadId && availableThreadIds.size) {
        appState.selectedAuthorThreadId = Array.from(availableThreadIds)[0];
      }
    } catch (error) {
      appState.authorCollaborationSummary = null;
      appState.selectedAuthorThreadId = null;
    }
  } else {
    appState.authorCollaborationSummary = null;
    appState.selectedAuthorThreadId = null;
  }
  if (els.authorApprovalReviewer?.value.trim() && !els.authorInboxReviewerId?.value.trim()) {
    els.authorInboxReviewerId.value = els.authorApprovalReviewer.value.trim();
  }
  try {
    await refreshAuthorReviewerInbox();
  } catch (error) {
    appState.authorReviewerInbox = null;
    appState.authorReviewerInboxNextCursor = null;
    appState.authorReviewerInboxHasMore = false;
  }
  try {
    await refreshAuthorNotificationPreferences();
  } catch (error) {
    appState.authorNotificationPreferences = null;
  }
  if (els.authorAccountId?.value.trim()) {
    try {
      appState.authorAccessSnapshot = await api(
        `/v1/author/access?account_id=${encodeURIComponent(els.authorAccountId.value.trim())}${
          appState.activeDraftVersionId ? `&world_version_id=${encodeURIComponent(appState.activeDraftVersionId)}` : ""
        }`
      );
    } catch (error) {
      appState.authorAccessSnapshot = null;
    }
  } else {
    appState.authorAccessSnapshot = null;
  }
  try {
    const query = new URLSearchParams();
    query.set("account_id", els.authorAccountId?.value.trim() || "web_author");
    if (appState.activeDraftVersionId) {
      query.set("world_version_id", appState.activeDraftVersionId);
    }
    appState.authorWorkflowSummary = await api(`/v1/author/workflow?${query.toString()}`);
    if (!appState.activeDraftVersionId && appState.authorWorkflowSummary?.world_version_id) {
      appState.activeDraftVersionId = appState.authorWorkflowSummary.world_version_id;
      appState.activeDraftDetail = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`);
    }
  } catch (error) {
    appState.authorWorkflowSummary = null;
  }
  if (els.authorAccountId?.value.trim()) {
    try {
      const entitlements = await api(`/v1/reader/entitlements?account_id=${encodeURIComponent(els.authorAccountId.value.trim())}`);
      els.authorStudioCredits.textContent = String(Number(entitlements.wallets?.studio_credits?.balance || 0).toFixed(0));
      if (els.authorTier) {
        els.authorTier.textContent = tierLabel(entitlements.subscription?.tier_id) || entitlements.subscription?.tier_id || "-";
      }
    } catch (error) {
      els.authorStudioCredits.textContent = "-";
      if (els.authorTier) {
        els.authorTier.textContent = "-";
      }
    }
  }
  renderAuthorDrafts();
  renderAuthorReports();
}

async function createDraftFromCurrentWorld() {
  if (!appState.worldId) {
    alert("先选择一个世界。");
    return;
  }
  try {
    const detail = await api(`/v1/library/worlds/${appState.worldId}`);
    const pack = detail.worldpack;
    pack.version = `${pack.version}-draft-${Date.now()}`;
    pack.manifest.author_id = els.authorAccountId?.value.trim() || "web_author";
    const draft = await api("/v1/author/drafts", {
      method: "POST",
      body: JSON.stringify({
        worldpack: pack,
        account_id: els.authorAccountId?.value.trim() || "web_author",
        change_context: { source: "manual_update", label: "从当前世界复制" },
      }),
    });
    appState.activeDraftVersionId = draft.world_version_id;
    appState.activeDraftDetail = await api(`/v1/author/drafts/${draft.world_version_id}`);
    appState.selectedAuthorRevisionIndex = null;
    appState.authorValidationReport = draft.validation_report;
    appState.authorSimulationReport = null;
    await refreshAuthorSurface();
    await refreshOpsSurface();
    focusAuthorPanel("draft_detail");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "创建 Draft");
      return;
    }
    alert(`创建 Draft 失败：${error.message}`);
  }
}

async function createDraftFromBrief() {
  const brief = buildAuthorBriefPayload();
  if (!brief.world_title || !brief.core_premise) {
    alert("请至少填写世界标题和故事 brief。");
    return;
  }
  try {
    const draft = await api("/v1/author/drafts/from-brief", {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
    appState.activeDraftVersionId = draft.world_version_id;
    appState.activeDraftDetail = await api(`/v1/author/drafts/${draft.world_version_id}`);
    appState.selectedAuthorRevisionIndex = null;
    appState.authorValidationReport = draft.validation_report;
    appState.authorSimulationReport = null;
    await refreshAuthorSurface();
    await refreshOpsSurface();
    focusAuthorPanel("draft_detail");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alert(`当前不能创建 Draft：${accessReasonLabel(detail.reason)}。需要 ${detail.required_display_name || tierLabel(detail.required_tier)}，当前 ${detail.wallet_type || "-"} 余额 ${Number(detail.balance || 0).toFixed(0)}。`);
      return;
    }
    alert(`生成 Draft 失败：${error.message}`);
  }
}

async function saveCapabilityAssets() {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const worldpack = structuredClone(activeWorldpack);
  worldpack.narrative_style_pack = worldpack.narrative_style_pack || {};
  try {
    const dialogueBundle = JSON.parse(els.authorVoiceEditor.value || "{}");
    worldpack.dialogue_realism_policy = dialogueBundle.dialogue_realism_policy || {};
    worldpack.voice_profiles = dialogueBundle.voice_profiles || {};
    worldpack.response_cadence_profiles = dialogueBundle.response_cadence_profiles || {};
    worldpack.pressure_response_styles = dialogueBundle.pressure_response_styles || {};
    worldpack.emotion_action_policies = JSON.parse(els.authorActionEditor.value || "{}");
    worldpack.sensory_grounding_policies = JSON.parse(els.authorSensoryEditor.value || "{}");
    worldpack.scene_realization_contracts = JSON.parse(els.authorSceneEditor.value || "{}");
    worldpack.narrative_style_pack.dialogue = {
      ...worldpack.dialogue_realism_policy,
      voice_profiles: worldpack.voice_profiles,
      response_profiles: worldpack.response_cadence_profiles,
      pressure_styles: worldpack.pressure_response_styles,
    };
    applyStylePacingHookControls(worldpack);
    worldpack.narrative_style_pack.emotion_actions = Object.values(worldpack.emotion_action_policies)[0] || {};
    worldpack.narrative_style_pack.sensory_grounding = Object.values(worldpack.sensory_grounding_policies)[0] || {};
    worldpack.narrative_style_pack.scene_realization = Object.values(worldpack.scene_realization_contracts)[0] || {};
  } catch (error) {
    alert("能力配置 JSON 解析失败，请检查格式。");
    return;
  }
  try {
    const draft = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`, {
      method: "PUT",
      body: JSON.stringify({
        worldpack,
        account_id: els.authorAccountId?.value.trim() || "web_author",
        change_context: { source: "capability_editor", label: "保存能力配置" },
      }),
    });
    appState.activeDraftVersionId = draft.world_version_id || appState.activeDraftVersionId;
    appState.activeDraftDetail = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`);
    appState.selectedAuthorRevisionIndex = null;
    appState.authorValidationReport = draft.validation_report || appState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    await refreshOpsSurface();
    focusAuthorPanel("diff");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存能力配置");
      return;
    }
    alert(`保存能力配置失败：${error.message}`);
  }
}

async function saveCharacterCard() {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const worldpack = structuredClone(activeWorldpack);
  const characters = worldpack.characters || [];
  if (!characters.length) {
    alert("当前 draft 没有可编辑角色。");
    return;
  }
  const index = Math.min(selectedCharacterIndex(), characters.length - 1);
  const character = characters[index];
  character.display_name = els.authorCharacterName.value.trim();
  character.role = els.authorCharacterRole.value.trim() || character.role;
  character.destiny_contract = character.destiny_contract || {};
  character.destiny_contract.life_theme = els.authorCharacterLifeTheme.value.trim();
  character.wound_profile = character.wound_profile || {};
  character.wound_profile.core_wound = els.authorCharacterCoreWound.value.trim();
  character.wound_profile.public_self = els.authorCharacterPublicSelf.value.trim();
  character.wound_profile.shadow_desire = els.authorCharacterShadowDesire.value.trim();
  character.vow_profile = character.vow_profile || {};
  character.vow_profile.vows = els.authorCharacterVows.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

  try {
    const draft = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`, {
      method: "PUT",
      body: JSON.stringify({
        worldpack,
        account_id: els.authorAccountId?.value.trim() || "web_author",
        change_context: { source: "character_editor", label: "保存角色卡" },
      }),
    });
    appState.activeDraftDetail = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`);
    appState.selectedAuthorRevisionIndex = null;
    appState.authorValidationReport = draft.validation_report || appState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    focusAuthorPanel("diff");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存角色卡");
      return;
    }
    alert(`保存角色卡失败：${error.message}`);
  }
}

async function saveSceneBlueprint() {
  const activeWorldpack = getActiveDraftWorldpack();
  if (!activeWorldpack || !appState.activeDraftVersionId) {
    alert("先选择一个 draft。");
    return;
  }
  const worldpack = structuredClone(activeWorldpack);
  const scenes = worldpack.scene_blueprints || [];
  if (!scenes.length) {
    alert("当前 draft 没有可编辑场景。");
    return;
  }
  const index = Math.min(selectedSceneIndex(), scenes.length - 1);
  const scene = scenes[index];
  scene.scene_id = els.authorSceneId.value.trim() || scene.scene_id;
  scene.scene_function = els.authorSceneFunction.value.trim() || scene.scene_function;
  scene.required_roles = els.authorSceneRequiredRoles.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
  scene.beats_template = els.authorSceneBeats.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

  try {
    const draft = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`, {
      method: "PUT",
      body: JSON.stringify({
        worldpack,
        account_id: els.authorAccountId?.value.trim() || "web_author",
        change_context: { source: "scene_editor", label: "保存场景蓝图" },
      }),
    });
    appState.activeDraftDetail = await api(`/v1/author/drafts/${appState.activeDraftVersionId}`);
    appState.selectedAuthorRevisionIndex = null;
    appState.authorValidationReport = draft.validation_report || appState.activeDraftDetail.validation_report;
    await refreshAuthorSurface();
    focusAuthorPanel("diff");
  } catch (error) {
    const detail = parseErrorDetail(error);
    await refreshAuthorSurface();
    if (detail?.code === "author_entitlement_required") {
      alertAuthorGating(detail, "保存场景蓝图");
      return;
    }
    alert(`保存场景蓝图失败：${error.message}`);
  }
}

async function loadExampleBundle(exampleId) {
  appState.currentBundle = await api(`/v1/examples/${exampleId}`);
  appState.worldId = appState.currentBundle.world_bible.world_id;
  appState.selectedIntentOverride = null;
  updateBundleSummary();
  renderWorldGallery();
  renderSuggestedInputs();
  await refreshSessionLibrary();
  await refreshReaderEntitlements();
  updateStatus();
}

async function refreshExamples() {
  const payload = await api("/v1/examples");
  appState.examples = payload.examples;
  const shelfPayload = await api("/v1/library/worlds");
  appState.shelfWorlds = shelfPayload.worlds;
  const selected = appState.examples.find((item) => item.example_id === "demo") || appState.examples[0];
  if (selected) {
    await loadExampleBundle(selected.example_id);
  }
}

async function refreshSessionLibrary() {
  if (!appState.currentBundle) {
    appState.sessionLibrary = [];
    renderSessionLibrary();
    return;
  }
  const payload = await api(`/v1/sessions?world_id=${encodeURIComponent(appState.currentBundle.world_bible.world_id)}`);
  appState.sessionLibrary = payload.sessions;
  renderSessionLibrary();
}

async function bootstrapWorld(triggerButton = null) {
  if (!appState.currentBundle) return;
  const restore = triggerButton ? setBusy(triggerButton, "进入中…") : () => {};
  try {
    const worldPayload = {
      world_bible: appState.currentBundle.world_bible,
      event_atoms: appState.currentBundle.event_atoms,
      metadata: { source: "frontend_bootstrap" },
    };
    const worldResult = await api("/v1/worlds", {
      method: "POST",
      body: JSON.stringify(worldPayload),
    });
    const sessionResult = await api("/v1/sessions", {
      method: "POST",
      body: JSON.stringify({
        world_id: worldResult.world_id,
        initial_state: appState.currentBundle.initial_state,
        player_profile: { surface: "app", reader_id: activeReaderId() },
        metadata: { reader_id: activeReaderId() },
      }),
    });

    appState.worldId = worldResult.world_id;
    appState.worldVersionId = sessionResult.world_version_id || null;
    appState.sessionPaywall = sessionResult.paywall || null;
    appState.sessionId = sessionResult.session_id;
    appState.currentState = sessionResult.current_state;
    appState.intentPrefill = {
      last_player_intent: "",
      current_pressure: "故事刚刚开始。",
      suggested_prefill: "我想先试探眼前这条路到底会把我带到哪一边。",
    };
    appState.latestStep = null;
    appState.latestPreview = null;
    appState.replay = null;
    appState.selectedReplayIndex = null;

    await refreshSessionLibrary();
    await refreshReaderEntitlements();
    updateStatus();
    renderRoutePreview();
    renderLatestStep();
    renderReplay();
  } catch (error) {
    alert(`开始旅程失败：${error.message}`);
  } finally {
    restore();
  }
}

async function restoreSession(sessionId, triggerButton = null) {
  if (!sessionId) return;
  const restore = triggerButton ? setBusy(triggerButton, "回到这一幕…") : () => {};
  try {
    const sessionPayload = await api(`/v1/sessions/${sessionId}`);
    const replayPayload = await api(`/v1/sessions/${sessionId}/replay`);
    appState.sessionId = sessionId;
    appState.currentState = sessionPayload.session.current_state;
    appState.sessionPaywall = sessionPayload.paywall || null;
    appState.latestStep = sessionPayload.latest_step;
    appState.replay = replayPayload;
    appState.worldId = sessionPayload.session.world_id;
    appState.worldVersionId = sessionPayload.world_version_id || sessionPayload.session.metadata?.world_version_id || null;
    appState.readerId = sessionPayload.session.metadata?.reader_id || appState.readerId;
    appState.intentPrefill = sessionPayload.intent_prefill || (await api(`/v1/sessions/${sessionId}/prefill`));
    appState.selectedReplayIndex = replayPayload.event_trace.length
      ? replayPayload.event_trace.length - 1
      : null;
    appState.activeView = "experience";
    syncViewMode();
    renderSessionLibrary();
    await refreshReaderEntitlements();
    updateStatus();
    renderLatestStep();
    renderReplay();
    spotlightChapter();
  } catch (error) {
    alert(`继续旅程失败：${error.message}`);
  } finally {
    restore();
  }
}

async function deleteSession(sessionId) {
  if (!sessionId) return;
  const confirmed = window.confirm("删除后这段旅程会从书架中移除，确定继续吗？");
  if (!confirmed) return;
  try {
    await api(`/v1/sessions/${sessionId}`, { method: "DELETE" });
    if (appState.sessionId === sessionId) {
      appState.sessionId = null;
      appState.currentState = null;
      appState.latestStep = null;
      appState.latestPreview = null;
      appState.replay = null;
      appState.selectedReplayIndex = null;
      appState.activeView = "experience";
      syncViewMode();
      renderRoutePreview();
      renderLatestStep();
      renderReplay();
    }
    await refreshSessionLibrary();
    updateStatus();
  } catch (error) {
    alert(`删除失败：${error.message}`);
  }
}

async function previewRoute() {
  if (!appState.currentBundle || !appState.currentState) return;
  const restore = setBusy(els.previewRoute, "预览中…");
  try {
    const previewState =
      typeof structuredClone === "function"
        ? structuredClone(appState.currentState)
        : JSON.parse(JSON.stringify(appState.currentState));
    if (appState.selectedIntentOverride) {
      previewState.player_intent = appState.selectedIntentOverride;
    }
    appState.latestPreview = await api("/v1/routes/preview", {
      method: "POST",
      body: JSON.stringify({
        world: appState.currentBundle.world_bible,
        state: previewState,
        candidate_events: appState.currentBundle.event_atoms,
        beam_width: 3,
        depth: 2,
      }),
    });
    renderRoutePreview();
    spotlightPreviewResult();
  } catch (error) {
    alert(`没能看到下一步：${error.message}`);
  } finally {
    restore();
  }
}

async function stepSession() {
  if (!appState.sessionId) return;
  const playerInput = els.playerInput.value.trim();
  if (!playerInput) {
    alert("先写下一句你现在真正想做的事。");
    return;
  }
  const restore = setBusy(els.stepSession, "执行中…");
  try {
    appState.latestStep = await api(`/v1/sessions/${appState.sessionId}/step?debug=true`, {
      method: "POST",
      body: JSON.stringify({
        player_input: playerInput,
        intent_override: appState.selectedIntentOverride,
        beam_width: 3,
        depth: 2,
        metadata: { reader_id: activeReaderId() },
      }),
    });
    appState.currentState = appState.latestStep.updated_state;
    appState.worldVersionId = appState.latestStep.world_version_id || appState.worldVersionId;
    appState.sessionPaywall = appState.latestStep.paywall || appState.sessionPaywall;
    appState.replay = await api(`/v1/sessions/${appState.sessionId}/replay`);
    appState.intentPrefill = await api(`/v1/sessions/${appState.sessionId}/prefill`);
    appState.selectedReplayIndex = appState.replay.event_trace.length
      ? appState.replay.event_trace.length - 1
      : null;
    await refreshSessionLibrary();
    await refreshReaderEntitlements();
    updateStatus();
    renderLatestStep();
    renderReplay();
  } catch (error) {
    alert(`这一幕没能推进：${error.message}`);
  } finally {
    restore();
  }
}

function resetOutput() {
  appState.latestStep = null;
  appState.latestPreview = null;
  appState.replay = null;
  appState.intentPrefill = null;
  appState.selectedReplayIndex = null;
  els.playerInput.value = "";
  renderRoutePreview();
  renderLatestStep();
  renderReplay();
}

async function bootstrapHealth() {
  try {
    const payload = await api("/health", { headers: {} });
    els.apiStatus.textContent = payload.status === "ok" ? "在线" : "异常";
  } catch (error) {
    els.apiStatus.textContent = "离线";
  }
}

els.previewRoute.addEventListener("click", previewRoute);
els.stepSession.addEventListener("click", stepSession);
els.resetOutput.addEventListener("click", resetOutput);
els.playerInput.addEventListener("input", () => {
  appState.selectedIntentOverride = null;
});
els.viewExperience.addEventListener("click", () => {
  appState.activeView = "experience";
  syncViewMode();
});
els.viewStorybook.addEventListener("click", () => {
  appState.activeView = "storybook";
  syncViewMode();
  renderStorybook();
});
els.viewBackstage.addEventListener("click", () => {
  appState.activeView = "backstage";
  syncViewMode();
});
els.modeReader.addEventListener("click", () => {
  appState.activeProduct = "reader";
  syncProductMode();
});
els.modeAuthor.addEventListener("click", async () => {
  appState.activeProduct = "author";
  syncProductMode();
  await refreshAuthorSurface();
});
els.modeOps.addEventListener("click", async () => {
  appState.activeProduct = "ops";
  syncProductMode();
  await refreshOpsSurface();
});
els.readerRefreshEntitlements?.addEventListener("click", refreshReaderEntitlements);
els.readerGrantEntitlement?.addEventListener("click", grantReaderEntitlement);
els.readerStartCheckout?.addEventListener("click", () => startReaderCheckout());
els.readerRetryPayment?.addEventListener("click", retryReaderSubscriptionPayment);
els.readerRenewSubscription?.addEventListener("click", renewReaderSubscription);
els.readerCancelSubscription?.addEventListener("click", cancelReaderSubscription);
els.authorGenrePreset?.addEventListener("change", applyAuthorPresetDefaults);
els.authorCharacterSelect?.addEventListener("change", renderCharacterEditor);
els.authorSceneSelect?.addEventListener("change", renderSceneEditor);
els.authorCreateDraft?.addEventListener("click", createDraftFromCurrentWorld);
els.authorCreateDraftFromBrief?.addEventListener("click", createDraftFromBrief);
els.authorRefresh?.addEventListener("click", refreshAuthorSurface);
els.authorAuthRegister?.addEventListener("click", registerAuthorAuthIdentity);
els.authorAuthLogin?.addEventListener("click", loginAuthorAuthIdentity);
els.authorAuthLogout?.addEventListener("click", logoutAuthorAuthIdentity);
els.authorSaveStyleControls?.addEventListener("click", saveCapabilityAssets);
els.authorSaveCharacter?.addEventListener("click", saveCharacterCard);
els.authorSaveScene?.addEventListener("click", saveSceneBlueprint);
els.authorSaveCapabilities?.addEventListener("click", saveCapabilityAssets);
els.authorRefreshReviewerInbox?.addEventListener("click", async () => {
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorSearchReviewerInbox?.addEventListener("click", async () => {
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorLoadMoreReviewerInbox?.addEventListener("click", async () => {
  if (!appState.authorReviewerInboxNextCursor) return;
  await refreshAuthorReviewerInbox({ append: true, cursor: appState.authorReviewerInboxNextCursor });
  renderAuthorReports();
});
els.authorInboxReviewerId?.addEventListener("change", async () => {
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorInboxStatusFilter?.addEventListener("change", async () => {
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorInboxWorldVersionFilter?.addEventListener("change", async () => {
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorInboxNotificationTypeFilter?.addEventListener("change", async () => {
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorInboxBlockingOnly?.addEventListener("change", async () => {
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorInboxSearch?.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  await refreshAuthorReviewerInbox();
  renderAuthorReports();
});
els.authorBulkReadVisible?.addEventListener("click", async () => {
  await bulkUpdateAuthorNotificationStatus("read");
});
els.authorBulkArchiveVisible?.addEventListener("click", async () => {
  await bulkUpdateAuthorNotificationStatus("archived");
});
els.authorAddDraftWatcher?.addEventListener("click", addAuthorDraftWatcher);
els.authorRemoveDraftWatcher?.addEventListener("click", removeAuthorDraftWatcher);
els.authorRefreshNotificationPreferences?.addEventListener("click", async () => {
  await refreshAuthorNotificationPreferences();
  renderAuthorReports();
});
els.authorSaveNotificationPreference?.addEventListener("click", saveAuthorNotificationPreference);
els.authorNotificationPrefType?.addEventListener("change", () => {
  syncAuthorNotificationPreferenceInputs();
});
els.authorAccountId?.addEventListener("change", () => {
  if (els.authorAuthActorId && !els.authorAuthActorId.value.trim()) {
    els.authorAuthActorId.value = els.authorAccountId.value.trim();
  }
});
els.opsAccountId?.addEventListener("change", () => {
  if (els.opsInvestigationAccountId && !els.opsInvestigationAccountId.value.trim()) {
    els.opsInvestigationAccountId.value = els.opsAccountId.value.trim();
  }
  if (els.opsAlertAccountId && !els.opsAlertAccountId.value.trim()) {
    els.opsAlertAccountId.value = els.opsAccountId.value.trim();
  }
  if (els.opsNavAccountId && !els.opsNavAccountId.value.trim()) {
    els.opsNavAccountId.value = els.opsAccountId.value.trim();
  }
});
els.authorApprovalReviewer?.addEventListener("change", () => {
  if (els.authorInboxReviewerId && !els.authorInboxReviewerId.value.trim()) {
    els.authorInboxReviewerId.value = els.authorApprovalReviewer.value.trim();
  }
});
els.opsAlertAccountId?.addEventListener("change", async () => {
  if (els.opsNavAccountId && !els.opsNavAccountId.value.trim()) {
    els.opsNavAccountId.value = els.opsAlertAccountId.value.trim();
  }
  await refreshOpsAlerts();
  renderOpsSurface();
});
els.opsAlertStatusFilter?.addEventListener("change", async () => {
  await refreshOpsAlerts();
  renderOpsSurface();
});
els.opsAlertSeverityFilter?.addEventListener("change", async () => {
  await refreshOpsAlerts();
  renderOpsSurface();
});
els.authorCreateCommentThread?.addEventListener("click", createAuthorCommentThread);
els.authorRequestApproval?.addEventListener("click", requestAuthorApproval);
els.authorApproveDraft?.addEventListener("click", () => decideAuthorApproval("approved"));
els.authorRequestChanges?.addEventListener("click", () => decideAuthorApproval("changes_requested"));
els.opsRefresh?.addEventListener("click", refreshOpsSurface);
els.opsSyncNavigation?.addEventListener("click", async () => {
  try {
    syncOpsNavigationContext(currentOpsNavigationContext(), { preserveExisting: false });
    await refreshOpsSurface({ scopes: ["account", "review_release", "alerts", "navigation"] });
  } catch (error) {
    alert(`同步 Ops context 失败：${error.message}`);
  }
});
els.opsFollowRecommendation?.addEventListener("click", async () => {
  try {
    await followOpsNavigationRecommendation();
  } catch (error) {
    alert(`执行推荐升级路径失败：${error.message}`);
  }
});
els.opsNavAccountId?.addEventListener("change", () => {
  if (els.opsAccountId) {
    els.opsAccountId.value = els.opsNavAccountId.value.trim();
  }
});
els.opsNavWorldId?.addEventListener("change", () => {
  appState.selectedOpsWorldId = (els.opsNavWorldId?.value || "").trim() || null;
  if (els.opsReleaseWorldId) {
    els.opsReleaseWorldId.value = els.opsNavWorldId.value.trim();
  }
});
els.opsNavCaseId?.addEventListener("change", () => {
  if (els.opsGovernanceCaseId) {
    els.opsGovernanceCaseId.value = els.opsNavCaseId.value.trim();
  }
});
els.opsRefreshReleaseWorkspace?.addEventListener("click", async () => {
  try {
    await refreshOpsReleaseWorkspace();
    renderOpsSurface();
  } catch (error) {
    alert(`刷新 release workspace 失败：${error.message}`);
  }
});
els.opsReleaseWorldId?.addEventListener("change", async () => {
  appState.selectedOpsWorldId = (els.opsReleaseWorldId?.value || "").trim() || null;
  if (els.opsNavWorldId) {
    els.opsNavWorldId.value = els.opsReleaseWorldId.value.trim();
  }
  await refreshOpsReleaseWorkspace();
  renderOpsSurface();
});
els.opsCreateRuntimeBackup?.addEventListener("click", createRuntimeBackup);
els.opsRestoreRuntimeBackup?.addEventListener("click", restoreRuntimeBackup);
els.opsRunRecoveryDrill?.addEventListener("click", runRecoveryDrill);
els.opsRequestRuntimeRestore?.addEventListener("click", requestRuntimeRestore);
els.opsApproveRuntimeRestore?.addEventListener("click", approveRuntimeRestore);
els.opsRevokeRuntimeRestore?.addEventListener("click", revokeRuntimeRestore);
els.opsExecuteRuntimeRestore?.addEventListener("click", executeRuntimeRestore);
els.opsRunDataIntegrityDryRun?.addEventListener("click", () => runDataIntegrityRepair(false));
els.opsApplyDataIntegrityRepair?.addEventListener("click", () => runDataIntegrityRepair(true));
els.opsRetryAsyncJob?.addEventListener("click", retryAsyncJob);
els.opsResumeAsyncJob?.addEventListener("click", resumeAsyncJob);
els.opsRecoverAsyncJobs?.addEventListener("click", recoverAsyncJobIncidents);
els.opsEnforceAsyncRetention?.addEventListener("click", enforceAsyncJobRetention);
els.opsRunColdStartDrill?.addEventListener("click", runColdStartRecoveryDrill);
els.opsExportHandoffBundle?.addEventListener("click", exportAsyncJobHandoffBundle);
els.opsAcknowledgeAsyncJob?.addEventListener("click", acknowledgeAsyncJob);
els.opsShipRemoteArtifacts?.addEventListener("click", shipRemoteArtifacts);
els.opsEscalateHandoffSla?.addEventListener("click", escalateHandoffSla);
els.opsEnqueueNotificationRetry?.addEventListener("click", enqueueNotificationRetry);
els.opsProcessNotificationRetry?.addEventListener("click", processNotificationRetry);
els.opsGrantSubscription?.addEventListener("click", grantOpsSubscription);
els.opsChangeSubscriptionState?.addEventListener("click", changeOpsSubscriptionState);
els.opsGrantWallet?.addEventListener("click", grantOpsWallet);
els.opsDebitWallet?.addEventListener("click", debitOpsWallet);
els.opsRevokeEntitlement?.addEventListener("click", revokeOpsEntitlement);
els.opsReconcileSubscription?.addEventListener("click", reconcileOpsSubscription);
els.opsRetrySubscriptionPayment?.addEventListener("click", retryOpsSubscriptionPayment);
els.opsReplayBillingEvent?.addEventListener("click", replayOpsBillingEvent);
els.opsRefreshAlerts?.addEventListener("click", async () => {
  try {
    await refreshOpsAlerts();
    renderOpsSurface();
  } catch (error) {
    alert(`刷新 alerts 失败：${error.message}`);
  }
});
els.opsAcknowledgeAlert?.addEventListener("click", async () => {
  try {
    await updateSelectedOpsAlertStatus("acknowledged");
  } catch (error) {
    alert(`ack alert 失败：${error.message}`);
  }
});
els.opsResolveAlert?.addEventListener("click", async () => {
  try {
    await updateSelectedOpsAlertStatus("resolved");
  } catch (error) {
    alert(`resolve alert 失败：${error.message}`);
  }
});
els.opsProviderCandidateCanary?.addEventListener("click", () => submitProviderRollout("candidate", "canary"));
els.opsProviderCandidateActivate?.addEventListener("click", () => submitProviderRollout("candidate", "activate"));
els.opsProviderCandidateRollback?.addEventListener("click", () => submitProviderRollout("candidate", "rollback"));
els.opsProviderRendererCanary?.addEventListener("click", () => submitProviderRollout("renderer", "canary"));
els.opsProviderRendererActivate?.addEventListener("click", () => submitProviderRollout("renderer", "activate"));
els.opsProviderRendererRollback?.addEventListener("click", () => submitProviderRollout("renderer", "rollback"));
els.opsOpenAlertInvestigation?.addEventListener("click", async () => {
  try {
    await openSelectedOpsAlertInvestigation();
  } catch (error) {
    alert(`打开 alert investigation 失败：${error.message}`);
  }
});
els.opsRunInvestigation?.addEventListener("click", async () => {
  try {
    await runOpsInvestigation();
  } catch (error) {
    alert(`运行统一排查失败：${error.message}`);
  }
});
els.opsExportInvestigationTrace?.addEventListener("click", async () => {
  try {
    await exportOpsInvestigationTrace();
  } catch (error) {
    alert(`导出 investigation trace 失败：${error.message}`);
  }
});
els.opsCreateGovernanceCase?.addEventListener("click", createGovernanceCase);
els.opsAssignGovernanceCase?.addEventListener("click", assignGovernanceCase);
els.opsAddGovernanceEvidence?.addEventListener("click", addGovernanceEvidence);
els.opsUpdateGovernanceCase?.addEventListener("click", updateGovernanceCaseStatus);
els.opsApplyGovernanceRestriction?.addEventListener("click", applyGovernanceRestriction);
els.opsReleaseGovernanceRestriction?.addEventListener("click", releaseGovernanceRestriction);
els.opsExportGovernanceAudit?.addEventListener("click", refreshGovernanceAuditExport);
els.opsSubmitReviewCapture?.addEventListener("click", submitOpsReviewCapture);
els.opsSubmitPreferenceCapture?.addEventListener("click", submitOpsPreferenceCapture);
els.opsSubmitRankingCapture?.addEventListener("click", submitOpsRankingCapture);
els.opsSubmitPreferenceCapture?.addEventListener("click", submitOpsPreferenceCapture);
els.opsSubmitRankingCapture?.addEventListener("click", submitOpsRankingCapture);
els.opsApprovePromotion?.addEventListener("click", () => submitPromotionDecision("approve"));
els.opsRevokePromotion?.addEventListener("click", () => submitPromotionDecision("revoke"));
els.opsApproveRerankerPromotion?.addEventListener("click", () => submitRerankerPromotionDecision("approve"));
els.opsRevokeRerankerPromotion?.addEventListener("click", () => submitRerankerPromotionDecision("revoke"));
els.opsSetAssistedShadow?.addEventListener("click", () => submitAssistedGateConfig("shadow_only", true));
els.opsSetAssistedActive?.addEventListener("click", () => submitAssistedGateConfig("assisted_gate", true));
els.opsDisableAssistedGate?.addEventListener("click", () => submitAssistedGateConfig("shadow_only", false));
els.opsSetAssistedRerankShadow?.addEventListener("click", () => submitAssistedRerankConfig("shadow_only", true));
els.opsSetAssistedRerankActive?.addEventListener("click", () => submitAssistedRerankConfig("assisted_rerank", true));
els.opsDisableAssistedRerank?.addEventListener("click", () => submitAssistedRerankConfig("shadow_only", false));
els.opsRunEvaluatorTraining?.addEventListener("click", () => runLearnedTraining(["evaluator"]));
els.opsRunRerankerTraining?.addEventListener("click", () => runLearnedTraining(["reranker"]));
els.opsRunBothTraining?.addEventListener("click", () => runLearnedTraining(["evaluator", "reranker"]));
for (const pill of els.tonePills) {
  pill.addEventListener("click", () => setTone(pill.dataset.tone));
}

restoreAuthorAuthSession();
renderAuthorAuthStatus();
bootstrapHealth();
if (els.readerIdInput) {
  els.readerIdInput.value = appState.readerId;
}
syncProductMode();
syncViewMode();
updateStatus();
renderLatestStep();
renderRoutePreview();
renderReplay();
renderIntentPrefill();
refreshExamples();
els.readerIdInput?.addEventListener("change", refreshReaderEntitlements);
