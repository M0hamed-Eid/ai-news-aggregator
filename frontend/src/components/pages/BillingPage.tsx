'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ExternalLink, Loader2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { useAppStore } from '@/lib/store';
import { api, ApiError } from '@/lib/api';
import { toast } from 'sonner';
import type { UserState } from '@/lib/types';

// GET /api/accounts/billing/'s real JSON shape: the same complete UserState
// ProfilePage's endpoint returns, plus two Stripe-only fields. A null
// maxCustomSources/maxFollows means unlimited (Pro) — the mock UserState
// type has these as plain `number`, so they're overridden here rather than
// widened in lib/types.ts.
interface BillingResponse extends Omit<UserState, 'maxCustomSources' | 'maxFollows'> {
  maxCustomSources: number | null;
  maxFollows: number | null;
  billingConfigured: boolean;
  stripeCustomer: { subscriptionStatus: string; currentPeriodEnd: string } | null;
}

// Feeds the global store, which still models "unlimited" as a real number
// (UserState.maxFollows/maxCustomSources: number) — Infinity satisfies every
// existing `usage >= max` consumer (store.ts's free-tier follow cap, etc.)
// without ever falsely tripping it.
function toUserState(data: BillingResponse): UserState {
  const { billingConfigured, stripeCustomer, ...rest } = data;
  return {
    ...rest,
    maxCustomSources: data.maxCustomSources ?? Infinity,
    maxFollows: data.maxFollows ?? Infinity,
  };
}

function usagePercent(usage: number, max: number | null): number {
  if (max === null) return 100;
  if (max <= 0) return 0;
  return Math.min(100, (usage / max) * 100);
}

function usageLabel(usage: number, max: number | null): string {
  return max === null ? `${usage} (Unlimited)` : `${usage} of ${max}`;
}

export default function BillingPage() {
  const { navigate, isLoggedIn, sessionLoading, setUser } = useAppStore();
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  // Login-gated endpoint — only ever call it once isLoggedIn is true,
  // matching the early-return gate below (calling it while logged out
  // would just fail), same pattern as FeedPage.tsx.
  const { data, isLoading } = useQuery({
    queryKey: ['billing'],
    queryFn: () => api.get<BillingResponse>('/api/accounts/billing/'),
    enabled: isLoggedIn,
  });

  useEffect(() => {
    if (data) setUser(toUserState(data));
  }, [data, setUser]);

  // Redirect only once the real session check has resolved — see
  // PreferencesPage.tsx's identical fix for why (isLoggedIn starts false
  // until GET /api/session/ returns, so redirecting on that initial false
  // was bouncing genuinely logged-in users to /login on every fresh load).
  useEffect(() => {
    if (!sessionLoading && !isLoggedIn) {
      navigate('login');
    }
  }, [sessionLoading, isLoggedIn, navigate]);

  if (!sessionLoading && !isLoggedIn) {
    return null;
  }

  const handleUpgrade = async () => {
    setCheckoutLoading(true);
    try {
      const res = await api.post<{ url: string }>('/api/accounts/billing/checkout/', {});
      window.location.href = res.url;
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Something went wrong starting checkout. Please try again.';
      toast.error(message);
      setCheckoutLoading(false);
    }
  };

  const handleManage = async () => {
    setPortalLoading(true);
    try {
      const res = await api.post<{ url: string }>('/api/accounts/billing/portal/', {});
      window.location.href = res.url;
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Something went wrong opening the billing portal. Please try again.';
      toast.error(message);
      setPortalLoading(false);
    }
  };

  if (isLoading || !data) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6 md:px-6">
        <div className="space-y-6">
          <div className="h-[92px] animate-pulse rounded-xl border border-border bg-card" />
          <div className="h-[220px] animate-pulse rounded-xl border border-border bg-card" />
        </div>
      </div>
    );
  }

  const isPro = data.plan === 'pro';
  const sourceUsage = data.customSourceCount || 0;
  const sourceMax = data.maxCustomSources;
  const followUsage = data.followCount || 0;
  const followMax = data.maxFollows;

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="space-y-6"
      >
        {/* Current plan */}
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-ink">Current Plan</h3>
              <div className="mt-2 flex items-center gap-2">
                {isPro ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-sm font-semibold text-primary-foreground">
                    <Sparkles className="h-3.5 w-3.5" /> Pro
                  </span>
                ) : (
                  <span className="rounded-full bg-muted px-3 py-1 text-sm font-semibold text-ink-muted">
                    Free
                  </span>
                )}
              </div>
            </div>
            {isPro ? (
              <Button variant="outline" onClick={handleManage} disabled={portalLoading}>
                {portalLoading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                )}
                Manage subscription
              </Button>
            ) : (
              <Button onClick={handleUpgrade} disabled={checkoutLoading}>
                {checkoutLoading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                )}
                Upgrade to Pro
              </Button>
            )}
          </div>
        </div>

        {/* Usage */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="mb-4 text-sm font-semibold text-ink">Usage</h3>
          <div className="space-y-5">
            <div>
              <div className="mb-1.5 flex items-center justify-between text-sm">
                <span className="text-ink-muted">Custom sources</span>
                <span className="font-medium text-ink">{usageLabel(sourceUsage, sourceMax)}</span>
              </div>
              <Progress value={usagePercent(sourceUsage, sourceMax)} className="h-2" />
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between text-sm">
                <span className="text-ink-muted">Topic/entity follows</span>
                <span className="font-medium text-ink">{usageLabel(followUsage, followMax)}</span>
              </div>
              <Progress value={usagePercent(followUsage, followMax)} className="h-2" />
            </div>
            <Separator />
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink-muted">Digests received</span>
              <span className="font-medium text-ink">{data.digestCount || 0}</span>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
