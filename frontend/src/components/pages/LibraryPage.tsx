'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Bookmark, Clock } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAppStore } from '@/lib/store';
import { api } from '@/lib/api';
import ArticleCard from '@/components/shared/ArticleCard';
import VideoCard from '@/components/shared/VideoCard';
import EmptyState from '@/components/shared/EmptyState';
import SkeletonCard from '@/components/shared/SkeletonCard';
import type { ContentItem } from '@/lib/types';

// Matches GET /api/news/library/'s real response shape — both arrays are
// already fully resolved/serialized ArticleItem/VideoItem objects (by
// definition every savedItems row isSaved and every readItems row isRead),
// so no client-side savedItems.has()/item.isRead filtering is needed here
// the way the old mock-data version did.
interface LibraryResponse {
  savedItems: ContentItem[];
  readItems: ContentItem[];
}

export default function LibraryPage() {
  const { navigate, isLoggedIn, hydrateContentState } = useAppStore();
  const [tab, setTab] = useState('saved');

  // Login-gated endpoint — only ever call it once isLoggedIn is true,
  // matching the early-return gate below (calling it while logged out
  // would just fail).
  const { data, isLoading, isError } = useQuery({
    queryKey: ['library'],
    queryFn: () => api.get<LibraryResponse>('/api/news/library/'),
    enabled: isLoggedIn,
  });

  useEffect(() => {
    if (data) {
      hydrateContentState([...data.savedItems, ...data.readItems]);
    }
  }, [data, hydrateContentState]);

  if (!isLoggedIn) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <EmptyState
          icon={Bookmark}
          title="Sign in to view your library"
          description="Your saved items and reading history are waiting for you."
          action={{ label: 'Log in', onClick: () => navigate('login') }}
        />
      </div>
    );
  }

  const savedList = data?.savedItems ?? [];
  const readItems = data?.readItems ?? [];

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="saved">
              <Bookmark className="mr-1.5 h-3.5 w-3.5" /> Saved ({savedList.length})
            </TabsTrigger>
            <TabsTrigger value="history">
              <Clock className="mr-1.5 h-3.5 w-3.5" /> Read history ({readItems.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="saved">
            {isLoading ? (
              <div className="space-y-3">
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
              </div>
            ) : !isError && savedList.length > 0 ? (
              <div className="space-y-3">
                {savedList.map(item => (
                  item.type === 'video' ? (
                    <VideoCard key={item.id} item={item} />
                  ) : (
                    <ArticleCard key={item.id} item={item} />
                  )
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Bookmark}
                title="No saved items"
                description="Save articles and videos to read later. They'll appear here."
              />
            )}
          </TabsContent>

          <TabsContent value="history">
            {isLoading ? (
              <div className="space-y-3">
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
              </div>
            ) : !isError && readItems.length > 0 ? (
              <div className="space-y-3">
                {readItems.map(item => (
                  item.type === 'video' ? (
                    <VideoCard key={item.id} item={item} />
                  ) : (
                    <ArticleCard key={item.id} item={item} />
                  )
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Clock}
                title="No reading history"
                description="Articles and videos you read will appear here."
              />
            )}
          </TabsContent>
        </Tabs>
      </motion.div>
    </div>
  );
}
