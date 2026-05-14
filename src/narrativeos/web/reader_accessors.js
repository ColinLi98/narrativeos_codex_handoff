// Reader/account access helpers shared where membership, gating, and unlock labels are needed.

var ReaderAccessors = (() => {
  const TIER_LABELS = {
    play_pass: "畅读会员",
    creator_pass: "创作会员",
    studio_pass: "工作室会员",
    story_credits: "故事点数",
    world_pass: "世界通行证",
    trial: "试读",
  };

  function currentTierCatalog() {
    return (
      readerState.readerSubscription?.tiers ||
      opsState.opsSubscriptionAudit?.tiers ||
      []
    );
  }

  function tierLabel(tierId) {
    const tier = currentTierCatalog().find((item) => item.tier_id === tierId);
    return TIER_LABELS[tierId] || TIER_LABELS[tier?.tier_id] || tier?.display_name || tierId || "-";
  }

  function accessReasonLabel(reason) {
    return {
      trial_chapter: "试读章节",
      grace_window: "宽限章节",
      continue_requires_entitlement: "需要更高权限",
      subscriber_active: "会员已生效",
      subscription_active: "会员已生效",
      subscription_required: "需要创作会员或工作室会员",
      entitlement_required: "需要解锁后继续阅读",
      world_pass_active: "世界已解锁",
      credits_balance: "故事点数可用",
      credits_consumed: "已消耗故事点数",
      credits_exhausted: "故事点数已耗尽",
      studio_credits_balance: "创作点数可用",
      studio_credits_exhausted: "创作点数已耗尽",
      author_tier_required: "当前会员档位不支持创作",
      entitlement_expired: "权益已过期",
      missing_reader: "缺少 reader_id",
      missing_account: "缺少 account_id",
    }[reason] || reason || "-";
  }

  function worldUnlockLabel(paywall) {
    if (!readerState.worldId) return "-";
    if (!paywall) return "试读中";
    if (paywall.entitlement_type === "subscriber") return `${paywall.tier_id || "会员"} 已解锁`;
    if (paywall.entitlement_type === "world_pass") return "世界通行证已解锁";
    if (paywall.entitlement_type === "credits") return paywall.required ? "需消耗故事点数" : "故事点数可继续";
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

  return {
    currentTierCatalog,
    tierLabel,
    accessReasonLabel,
    worldUnlockLabel,
    gatingStatusLabel,
    gatingHint,
  };
})();
