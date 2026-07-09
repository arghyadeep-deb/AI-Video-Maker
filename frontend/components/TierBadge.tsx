"use client";

// GPU tier badge — specs/04-tasks/task-15-quotas-fairness.md: "the tier
// badge truthfully tracks worker/ZeroGPU state". Polls occasionally since
// this is site-wide capacity, not something tied to one job.
import { useEffect, useState } from "react";
import { getTierState, type TierState } from "@/lib/api";

const POLL_INTERVAL_MS = 30_000;

const TIER_COLOR: Record<TierState["active_tier"], string> = {
  worker: "var(--ok)",
  zerogpu: "var(--accent)",
  cpu: "var(--text-dim)",
};

export default function TierBadge() {
  const [tier, setTier] = useState<TierState | null>(null);

  useEffect(() => {
    let cancelled = false;

    function poll() {
      getTierState()
        .then((result) => {
          if (!cancelled) setTier(result);
        })
        .catch(() => {
          // Best-effort - the badge just doesn't render if unreachable.
        });
    }

    poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (!tier) return null;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.4rem",
        padding: "0.25rem 0.65rem",
        borderRadius: 999,
        border: "1px solid var(--border)",
        fontSize: "0.75rem",
        color: "var(--text-dim)",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: TIER_COLOR[tier.active_tier],
        }}
      />
      {tier.label}
    </span>
  );
}
