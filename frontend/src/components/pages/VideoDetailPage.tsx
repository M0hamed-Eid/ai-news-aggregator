'use client';

import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowLeft, Play, ExternalLink, Bookmark, BookmarkCheck, Share2, Lightbulb, Lock, Flame } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { formatDistanceToNow } from 'date-fns';
import { api, parseContentRef } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import TopicBadge from '@/components/shared/TopicBadge';
import DepthGauge from '@/components/shared/DepthGauge';
import type { VideoItem, ContentItem } from '@/lib/types';

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatTimestamp(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  // Math.floor, not just `% 60` — chapter start_seconds is a real FloatField
  // (web/apps/catalog/models.py::ContentChunk), so an un-floored remainder
  // renders as e.g. "58.559999999999945" instead of "58". The old mock data
  // only ever used clean multiples of 60, which is why this never surfaced
  // before real chapter data existed.
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

const GRADIENTS = [
  'from-indigo-600 via-purple-600 to-pink-500',
  'from-cyan-600 via-blue-600 to-indigo-500',
  'from-emerald-600 via-teal-600 to-cyan-500',
  'from-orange-600 via-red-500 to-pink-500',
];

// GET /api/news/videos/{id}/'s real JSON shape — every field matches
// VideoItem exactly (web/apps/news serializes via the same serialize_item()
// every list page uses), plus detail-only fields: related (cross-source,
// see get_related_items), isLongVideo (replaces the old client-side
// duration >= 1200 check), and canViewChapters (a real server-side
// entitlement decision, replaces the old isPro-based client gate).
interface VideoDetailResponse extends VideoItem {
  related: ContentItem[];
  isLongVideo: boolean;
  canViewChapters: boolean;
  clusterMemberCount: number;
}

export default function VideoDetailPage() {
  const { pageParams, goBack, isItemSaved, toggleSave, navigate, hydrateContentState, setAssistantContext } = useAppStore();
  const id = pageParams.id || '';

  const ref = useMemo(() => parseContentRef(id), [id]);

  const { data: video, isLoading, isError } = useQuery({
    queryKey: ['video-detail', id],
    queryFn: () => api.get<VideoDetailResponse>(`/api/news/videos/${ref!.contentId}/`),
    enabled: !!ref && ref.contentType === 'youtube_video',
    retry: false,
  });

  useEffect(() => {
    if (video) {
      hydrateContentState([video, ...video.related]);
    }
  }, [video, hydrateContentState]);

  useEffect(() => {
    if (!video) return;
    setAssistantContext({ type: 'video', title: video.title, id: video.id });
    return () => setAssistantContext({ type: 'global' });
  }, [video, setAssistantContext]);

  const saved = isItemSaved(id);

  const notFound = !ref || ref.contentType !== 'youtube_video' || isError;

  if (notFound) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16 text-center">
        <p className="text-ink-muted">Video not found.</p>
        <Button variant="link" onClick={goBack}>Go back</Button>
      </div>
    );
  }

  if (isLoading || !video) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 text-center text-ink-muted">
        Loading video…
      </div>
    );
  }

  const gradientIdx = video.id.charCodeAt(video.id.length - 1) % GRADIENTS.length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">
      <div className="flex gap-8">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="min-w-0 flex-1"
        >
          {/* Back */}
          <button
            onClick={goBack}
            className="mb-4 flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>

          {/* Video thumbnail — real YouTube thumbnail (video.thumbnailUrl),
              clickable straight through to the original YouTube video
              (video.url) since the big Play-button overlay visually
              promises exactly that (it previously had no onClick at all —
              a real "clicking a video does nothing" bug). */}
          <a
            href={video.url}
            target="_blank"
            rel="noopener noreferrer"
            className="relative mb-6 block aspect-video overflow-hidden rounded-xl"
          >
            <div className={`absolute inset-0 bg-gradient-to-br ${GRADIENTS[gradientIdx]} opacity-80`} />
            {video.thumbnailUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={video.thumbnailUrl}
                alt=""
                loading="lazy"
                className="absolute inset-0 h-full w-full object-cover"
                onError={(e) => { e.currentTarget.style.display = 'none'; }}
              />
            )}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-black/40 backdrop-blur-sm transition-transform duration-200 hover:scale-110">
                <Play className="h-8 w-8 text-white fill-white" />
              </div>
            </div>
            <span className="absolute bottom-3 right-3 rounded-lg bg-black/70 px-2.5 py-1 text-sm font-medium text-white">
              {formatDuration(video.duration)}
            </span>
          </a>

          {/* Meta */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
              📹 {video.channelName}
            </span>
            <span className="text-xs text-ink-muted">
              {formatDistanceToNow(new Date(video.publishedAt), { addSuffix: true })}
            </span>
            {video.technicalDepth && <DepthGauge depth={video.technicalDepth} />}
          </div>

          {/* Title */}
          <h1 className="mb-4 text-2xl font-bold leading-tight tracking-tight text-ink md:text-3xl">
            {video.title}
          </h1>

          {/* Topics */}
          <div className="mb-6 flex flex-wrap gap-1.5">
            {video.topics.map(topic => (
              <TopicBadge key={topic} label={topic} topic={topic} />
            ))}
          </div>

          <Separator className="mb-6" />

          {/* Summary */}
          <div className="prose-compass mb-8">
            {video.summary ? (
              <p>{video.summary}</p>
            ) : (
              <p className="italic text-ink-muted">
                Summary unavailable for this video — it hasn&apos;t been processed yet.
              </p>
            )}
          </div>

          {/* Why it matters */}
          {video.whyItMatters && (
            <div className="mb-8 rounded-xl border border-primary/20 bg-primary/5 p-5">
              <div className="mb-2 flex items-center gap-2">
                <Lightbulb className="h-4.5 w-4.5 text-primary" />
                <h3 className="text-sm font-semibold text-ink">Why it matters</h3>
              </div>
              <p className="text-sm leading-relaxed text-ink-muted">{video.whyItMatters}</p>
            </div>
          )}

          {/* Chapters */}
          {video.chapters && video.chapters.length > 0 && (
            <div className="mb-8">
              <h3 className="mb-3 text-sm font-semibold text-ink uppercase tracking-wider">
                Chapters ({video.chapters.length})
              </h3>
              {video.canViewChapters ? (
                <div className="space-y-2">
                  {video.chapters.map((chapter, i) => (
                    <div key={i} className="flex items-start gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:bg-muted/50">
                      <button className="mt-0.5 flex shrink-0 items-center gap-1.5 text-sm font-mono font-medium text-primary hover:underline">
                        ▶ {formatTimestamp(chapter.startTime)}
                      </button>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">{chapter.title}</p>
                        <p className="mt-0.5 text-xs text-ink-muted">{chapter.summary}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-border bg-muted/50 p-6 text-center">
                  <Lock className="mx-auto mb-3 h-8 w-8 text-ink-muted" />
                  <h4 className="mb-1 text-sm font-semibold text-ink">Video chapters are a Pro feature</h4>
                  <p className="mb-4 text-xs text-ink-muted">
                    Get timestamped chapters for videos 20 minutes and longer.
                  </p>
                  <Button size="sm" onClick={() => navigate('pricing')}>Upgrade to Pro</Button>
                </div>
              )}
            </div>
          )}

          {/* Mentioned entities */}
          {video.mentionedEntities.length > 0 && (
            <div className="mb-8">
              <h3 className="mb-3 text-sm font-semibold text-ink">Mentioned:</h3>
              <div className="flex flex-wrap gap-1.5">
                {video.mentionedEntities.map(entity => (
                  <button
                    key={entity.id}
                    onClick={() => navigate('entity-profile', { id: entity.id })}
                    className="rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-primary/40 hover:text-primary"
                  >
                    {entity.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Story cluster */}
          {video.clusterMemberCount > 1 && (
            <button
              onClick={() => navigate('story-cluster', { type: 'video', id: String(ref?.contentId ?? '') })}
              className="mb-8 flex w-full items-center justify-between rounded-lg border border-border bg-card p-4 text-left transition-colors hover:border-primary/30"
            >
              <span className="flex items-center gap-1.5 text-sm text-ink">
                <Flame className="h-4 w-4 text-orange-500" />
                Part of a story with {video.clusterMemberCount - 1} related item{video.clusterMemberCount - 1 === 1 ? '' : 's'}
              </span>
              <span className="text-sm font-semibold text-primary">View all coverage →</span>
            </button>
          )}
        </motion.div>

        {/* Sidebar */}
        <aside className="hidden w-48 shrink-0 lg:block">
          <div className="sticky top-20 space-y-3">
            <Button className="w-full" asChild>
              <a href={video.url} target="_blank" rel="noopener noreferrer">
                <Play className="mr-2 h-4 w-4" /> Watch on YouTube
              </a>
            </Button>
            <Button
              variant={saved ? 'secondary' : 'outline'}
              className="w-full"
              onClick={() => toggleSave(id)}
            >
              {saved ? <BookmarkCheck className="mr-2 h-4 w-4" /> : <Bookmark className="mr-2 h-4 w-4" />}
              {saved ? 'Saved' : 'Save'}
            </Button>
            <Button variant="outline" className="w-full">
              <Share2 className="mr-2 h-4 w-4" /> Share
            </Button>
          </div>
        </aside>
      </div>

      {/* Mobile bar */}
      <div className="fixed bottom-14 left-0 right-0 z-30 flex items-center justify-center gap-2 border-t border-border bg-surface/95 p-2 backdrop-blur-md lg:hidden">
        <Button size="sm" className="flex-1" asChild>
          <a href={video.url} target="_blank" rel="noopener noreferrer">
            <Play className="mr-1.5 h-3.5 w-3.5" /> Watch
          </a>
        </Button>
        <Button size="sm" variant={saved ? 'secondary' : 'outline'} onClick={() => toggleSave(id)}>
          {saved ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
        </Button>
      </div>
    </div>
  );
}
