'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowLeft, User, Building2, Cpu, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { api } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import ArticleCard from '@/components/shared/ArticleCard';
import VideoCard from '@/components/shared/VideoCard';
import type { EntityProfile } from '@/lib/types';

const TYPE_ICONS = {
  person: User,
  company: Building2,
  model: Cpu,
  technology: Wrench,
};

const TYPE_COLORS = {
  person: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  company: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  model: 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300',
  technology: 'bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300',
};

export default function EntityProfilePage() {
  const { pageParams, goBack, toggleFollowEntity, isEntityFollowed, navigate, hydrateContentState } = useAppStore();
  const id = pageParams.id || '';

  // GET /api/news/entities/{id}/ — id here is a PLAIN NUMERIC STRING
  // ("10"), not type-prefixed like article/video ids (Entity has no
  // dual-model collision risk, see api.ts's parseContentRef docstring).
  // A 404 means "entity not found" — no point retrying that.
  const { data: entity, isLoading, error } = useQuery({
    queryKey: ['entity-profile', id],
    queryFn: () => api.get<EntityProfile>(`/api/news/entities/${id}/`),
    enabled: !!id,
    retry: false,
  });

  useEffect(() => {
    if (entity) {
      hydrateContentState([...entity.ownOutput, ...entity.mentions]);
    }
  }, [entity, hydrateContentState]);

  const followed = isEntityFollowed(id);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
        <div className="mb-6 flex items-start gap-4">
          <Skeleton className="h-14 w-14 shrink-0 rounded-xl" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-6 w-48 rounded" />
            <Skeleton className="h-4 w-64 rounded" />
          </div>
          <Skeleton className="h-8 w-24 rounded" />
        </div>
        <Skeleton className="mb-8 h-24 w-full rounded-xl" />
        <Skeleton className="mb-3 h-4 w-40 rounded" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </div>
    );
  }

  if (!entity || error) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16 text-center">
        <p className="text-ink-muted">Entity not found.</p>
        <Button variant="link" onClick={goBack}>Go back</Button>
      </div>
    );
  }

  const Icon = TYPE_ICONS[entity.type] || User;
  const maxMention = Math.max(...entity.mentionData.map(d => d.count), 1);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        {/* Back */}
        <button
          onClick={goBack}
          className="mb-4 flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        {/* Header */}
        <div className="mb-6 flex items-start gap-4">
          <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl ${TYPE_COLORS[entity.type]}`}>
            <Icon className="h-7 w-7" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-ink">{entity.name}</h1>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${TYPE_COLORS[entity.type]}`}>
                {entity.type}
              </span>
            </div>
            {entity.bio && (
              <p className="text-sm text-ink-muted">{entity.bio}</p>
            )}
          </div>
          <Button
            variant={followed ? 'secondary' : 'default'}
            size="sm"
            onClick={() => toggleFollowEntity(entity.id)}
          >
            {followed ? 'Following' : 'Follow'}
          </Button>
        </div>

        {/* 90-day mention sparkline */}
        <div className="mb-8 rounded-xl border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-ink">90-Day Mention Activity</h3>
          <div className="flex items-end gap-[2px]" style={{ height: 60 }}>
            {entity.mentionData.slice(-30).map((d, i) => (
              <div
                key={i}
                className="flex-1 rounded-t-sm bg-primary/70 transition-colors hover:bg-primary"
                style={{ height: `${(d.count / maxMention) * 100}%` }}
                title={`${d.count} mentions`}
              />
            ))}
          </div>
        </div>

        {/* Own output */}
        {entity.ownOutput.length > 0 && (
          <div className="mb-8">
            <h3 className="mb-3 text-sm font-semibold text-ink uppercase tracking-wider">Their Own Output</h3>
            <div className="space-y-3">
              {entity.ownOutput.map(item => (
                item.type === 'video' ? (
                  <VideoCard key={item.id} item={item} />
                ) : (
                  <ArticleCard key={item.id} item={item} />
                )
              ))}
            </div>
          </div>
        )}

        {/* Mentions */}
        {entity.mentions.length > 0 && (
          <div className="mb-8">
            <h3 className="mb-3 text-sm font-semibold text-ink uppercase tracking-wider">Mentions</h3>
            <div className="space-y-3">
              {entity.mentions.map(item => (
                item.type === 'video' ? (
                  <VideoCard key={item.id} item={item} />
                ) : (
                  <ArticleCard key={item.id} item={item} />
                )
              ))}
            </div>
          </div>
        )}

        {/* Related */}
        {entity.related && entity.related.length > 0 && (
          <div className="mb-8">
            <h3 className="mb-3 text-sm font-semibold text-ink uppercase tracking-wider">Related</h3>
            <div className="flex flex-wrap gap-2">
              {entity.related.map(r => (
                <button
                  key={r.id}
                  onClick={() => navigate('entity-profile', { id: r.id })}
                  className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/40 hover:text-primary"
                >
                  {r.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}
