'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Rss, Settings, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/lib/store';
import { api } from '@/lib/api';
import ArticleCard from '@/components/shared/ArticleCard';
import VideoCard from '@/components/shared/VideoCard';
import EmptyState from '@/components/shared/EmptyState';
import SkeletonCard from '@/components/shared/SkeletonCard';
import type { ContentItem } from '@/lib/types';

// Matches GET /api/news/feed/'s real response shape — same ArticleItem/
// VideoItem shape as HomePage's items, but with real rank/recommendedReason
// populated once a real ranking exists (see hasRanking below).
interface FeedResponse {
  items: ContentItem[];
  hasRanking: boolean;
}

export default function FeedPage() {
  const { navigate, isLoggedIn, user, hydrateContentState } = useAppStore();

  // Login-gated endpoint — only ever call it once isLoggedIn is true,
  // matching the early-return gate below (calling it while logged out
  // would just fail).
  const { data, isLoading, isError } = useQuery({
    queryKey: ['feed'],
    queryFn: () => api.get<FeedResponse>('/api/news/feed/'),
    enabled: isLoggedIn,
  });

  useEffect(() => {
    if (data?.items) {
      hydrateContentState(data.items);
    }
  }, [data, hydrateContentState]);

  if (!isLoggedIn) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <EmptyState
          icon={Rss}
          title="Sign in to see your feed"
          description="Your personalized AI feed awaits. Log in or create an account to get started."
          action={{ label: 'Log in', onClick: () => navigate('login') }}
        />
      </div>
    );
  }

  const feedItems = data?.items ?? [];
  // Nudge toward onboarding whenever there's no personalization to show yet —
  // either the user never finished onboarding, or the backend confirms no
  // real ranking exists for them (e.g. onboarding done but no digest run
  // yet). Either signal alone should surface the same banner.
  const isNewAccount = !user?.onboardingComplete || data?.hasRanking === false;

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-ink">Your Feed</h2>
            <p className="text-sm text-ink-muted">Ranked by relevance to your interests</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('preferences')}>
            <Settings className="mr-1.5 h-3.5 w-3.5" />
            Tune my feed
          </Button>
        </div>

        {/* New account / no-ranking-yet banner */}
        {isNewAccount && (
          <div className="mb-6 rounded-lg border border-primary/20 bg-primary/5 p-4">
            <div className="flex items-start gap-3">
              <Sparkles className="mt-0.5 h-5 w-5 text-primary" />
              <div>
                <p className="text-sm font-medium text-ink">Your personalized ranking will appear after your first digest run.</p>
                <p className="mt-0.5 text-xs text-ink-muted">
                  Complete onboarding to customize your interests, or explore the home page to see all content.
                </p>
                <Button variant="link" size="sm" className="mt-1 h-auto p-0 text-xs" onClick={() => navigate('onboarding')}>
                  Complete onboarding →
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Feed items */}
        {isLoading ? (
          <div className="space-y-3">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : !isError && feedItems.length > 0 ? (
          <div className="space-y-3">
            {feedItems.map(item => (
              item.type === 'video' ? (
                <VideoCard key={item.id} item={item} showReason />
              ) : (
                <ArticleCard key={item.id} item={item} showReason />
              )
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Rss}
            title="No feed items yet"
            description="Follow topics and sources to populate your feed."
            action={{ label: 'Set preferences', onClick: () => navigate('preferences') }}
          />
        )}
      </motion.div>
    </div>
  );
}
