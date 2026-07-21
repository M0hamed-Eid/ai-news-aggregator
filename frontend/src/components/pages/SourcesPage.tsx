'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Plus, X, Check, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { useAppStore } from '@/lib/store';
import { api, ApiError } from '@/lib/api';
import { toast } from 'sonner';
import EmptyState from '@/components/shared/EmptyState';
import SourceIcon from '@/components/shared/SourceIcon';

// The real 7 source categories, as key <-> display-label pairs. GET
// /api/onboarding/sources/ returns categories/excludedCategories/
// sources[].category as display LABELS only — the two POST endpoints below
// expect the backend KEY instead, so this is the reverse-lookup map the
// Add-source Select and the Save-preferences call both need.
const CATEGORY_KEY_TO_LABEL: Record<string, string> = {
  research: 'Research',
  open_source: 'Open Source',
  product_model_databases: 'Product / Model Databases',
  developer_communities: 'Developer Communities',
  government: 'Government',
  funding: 'Funding',
  media: 'Media',
};
const CATEGORY_LABEL_TO_KEY: Record<string, string> = Object.fromEntries(
  Object.entries(CATEGORY_KEY_TO_LABEL).map(([key, label]) => [label, key])
);

interface SourceRow {
  key: string;
  name: string;
  category: string; // display label
  isExcluded: boolean;
}

interface SourceSubmission {
  key: string;
  name: string;
  category: string; // display label
  status: 'accepted' | 'pending';
}

// Matches GET /api/onboarding/sources/'s real response shape.
interface SourcesResponse {
  sources: SourceRow[];
  categories: string[]; // display labels
  excludedCategories: string[]; // display labels
  mySubmissions: SourceSubmission[];
}

// Matches POST /api/onboarding/sources/add/'s real response shape.
interface AddSourceResponse {
  ok: boolean;
  status?: string;
  message: string;
  score?: number;
}

export default function SourcesPage() {
  const { navigate, isLoggedIn } = useAppStore();
  const [sourceType, setSourceType] = useState<'rss' | 'youtube'>('rss');
  const [feedUrl, setFeedUrl] = useState('');
  const [channelUrl, setChannelUrl] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [categoryKey, setCategoryKey] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [excludedSources, setExcludedSources] = useState<Set<string>>(new Set());
  const [excludedCategories, setExcludedCategories] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['onboarding-sources'],
    queryFn: () => api.get<SourcesResponse>('/api/onboarding/sources/'),
    enabled: isLoggedIn,
  });

  // Local UI state initializes from the real fetch, then mutates locally
  // (checkbox/category toggles) until "Save preferences" persists it.
  useEffect(() => {
    if (!data) return;
    setExcludedSources(new Set(data.sources.filter(s => s.isExcluded).map(s => s.key)));
    setExcludedCategories(new Set(data.excludedCategories));
  }, [data]);

  if (!isLoggedIn) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <EmptyState
          icon={Plus}
          title="Sign in to manage sources"
          description="Manage your sources and subscriptions after signing in."
          action={{ label: 'Log in', onClick: () => navigate('login') }}
        />
      </div>
    );
  }

  const urlValue = sourceType === 'youtube' ? channelUrl : feedUrl;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlValue.trim() || !categoryKey) return;
    setSubmitting(true);
    setSubmitResult(null);
    try {
      // A real Celery round-trip with a relevance-gate check — can take a
      // few seconds, unlike the old Math.random() mock. sourceType/
      // channelUrl restore the old app's "RSS feed OR YouTube channel"
      // choice (AddSourceAPIView has always supported both — only this
      // form's UI was missing the YouTube option).
      const response = await api.post<AddSourceResponse>('/api/onboarding/sources/add/', {
        sourceType,
        feedUrl: sourceType === 'rss' ? feedUrl : undefined,
        channelUrl: sourceType === 'youtube' ? channelUrl : undefined,
        name: displayName,
        category: categoryKey,
      });
      setSubmitResult({ ok: response.ok, message: response.message });
      if (response.ok) {
        setFeedUrl('');
        setChannelUrl('');
        setDisplayName('');
        setCategoryKey('');
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Something went wrong. Please try again.';
      setSubmitResult({ ok: false, message });
    } finally {
      setSubmitting(false);
      setTimeout(() => setSubmitResult(null), 5000);
    }
  };

  const toggleExcludeSource = (key: string) => {
    setExcludedSources(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleExcludeCategory = (cat: string) => {
    setExcludedCategories(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.post('/api/onboarding/sources/', {
        excludedSourceKeys: Array.from(excludedSources),
        excludedCategoryKeys: Array.from(excludedCategories).map(label => CATEGORY_LABEL_TO_KEY[label] ?? label),
      });
      toast.success('Source preferences saved!');
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Something went wrong. Please try again.';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const sources = data?.sources ?? [];
  const categories = data?.categories ?? [];
  const mySubmissions = data?.mySubmissions ?? [];

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        {/* Add source form */}
        <div className="mb-8 rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-sm font-semibold text-ink">Add a source</h3>
          <form onSubmit={handleSubmit} className="space-y-3">
            {/* RSS vs YouTube toggle — restores the source-type choice the
                old app's add-source form had (AddSourceAPIView has always
                supported sourceType: 'rss'|'youtube'; only this form's UI
                was RSS-only). */}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setSourceType('rss')}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  sourceType === 'rss' ? 'bg-primary text-primary-foreground' : 'bg-muted text-ink-muted hover:text-ink'
                }`}
              >
                RSS / Atom Feed
              </button>
              <button
                type="button"
                onClick={() => setSourceType('youtube')}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  sourceType === 'youtube' ? 'bg-primary text-primary-foreground' : 'bg-muted text-ink-muted hover:text-ink'
                }`}
              >
                YouTube Channel
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {sourceType === 'rss' ? (
                <div className="space-y-1.5">
                  <Label className="text-xs">Feed URL</Label>
                  <Input
                    placeholder="https://example.com/feed.xml"
                    value={feedUrl}
                    onChange={(e) => setFeedUrl(e.target.value)}
                    required
                  />
                </div>
              ) : (
                <div className="space-y-1.5">
                  <Label className="text-xs">Channel URL</Label>
                  <Input
                    placeholder="youtube.com/@handle"
                    value={channelUrl}
                    onChange={(e) => setChannelUrl(e.target.value)}
                    required
                  />
                </div>
              )}
              <div className="space-y-1.5">
                <Label className="text-xs">Display name {sourceType === 'youtube' && <span className="text-ink-muted">(optional)</span>}</Label>
                <Input
                  placeholder="My Blog"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                />
              </div>
            </div>
            <div className="flex items-end gap-3">
              <div className="flex-1 space-y-1.5">
                <Label className="text-xs">Category</Label>
                <Select value={categoryKey} onValueChange={setCategoryKey}>
                  <SelectTrigger><SelectValue placeholder="Select category" /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(CATEGORY_KEY_TO_LABEL).map(([key, label]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" disabled={!urlValue.trim() || !categoryKey || submitting}>
                {submitting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plus className="mr-1.5 h-4 w-4" />}
                {submitting ? 'Submitting...' : 'Submit'}
              </Button>
            </div>
          </form>

          {submitResult && submitResult.ok && (
            <div className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4" />
              {submitResult.message}
            </div>
          )}
          {submitResult && !submitResult.ok && (
            <div className="mt-3 flex items-center gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" />
              {submitResult.message}
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-ink-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading sources...
          </div>
        ) : (
          <>
            {/* Categories */}
            <div className="mb-8">
              <h3 className="mb-3 text-sm font-semibold text-ink">Categories</h3>
              <div className="flex flex-wrap gap-2">
                {categories.map(cat => {
                  const excluded = excludedCategories.has(cat);
                  return (
                    <button
                      key={cat}
                      onClick={() => toggleExcludeCategory(cat)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                        excluded
                          ? 'bg-destructive/10 text-destructive line-through'
                          : 'bg-primary/10 text-primary hover:bg-primary/20'
                      }`}
                    >
                      {excluded ? <X className="h-3 w-3" /> : <Check className="h-3 w-3" />}
                      {cat}
                    </button>
                  );
                })}
              </div>
            </div>

            <Separator className="my-6" />

            {/* Individual sources table */}
            <div className="mb-8">
              <h3 className="mb-3 text-sm font-semibold text-ink">All Sources</h3>
              <div className="space-y-2">
                {sources.map(s => {
                  const excluded = excludedSources.has(s.key);
                  return (
                    <div
                      key={s.key}
                      className={`flex items-center gap-3 rounded-lg border p-3 transition-colors ${
                        excluded ? 'border-destructive/20 bg-destructive/5 opacity-60' : 'border-border bg-card'
                      }`}
                    >
                      <Checkbox
                        checked={!excluded}
                        onCheckedChange={() => toggleExcludeSource(s.key)}
                      />
                      <SourceIcon sourceKey={s.key} className="h-6 w-6" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-ink">{s.name}</p>
                        <p className="text-xs text-ink-muted">{s.category}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <Separator className="my-6" />

            {/* Sources you've submitted */}
            {mySubmissions.length > 0 && (
              <div className="mb-8">
                <h3 className="mb-3 text-sm font-semibold text-ink">Sources You&apos;ve Submitted</h3>
                <div className="space-y-2">
                  {mySubmissions.map(sub => (
                    <div key={sub.key} className="flex items-center gap-3 rounded-lg border border-border bg-card p-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-ink">{sub.name}</p>
                        <p className="text-xs text-ink-muted">{sub.category}</p>
                      </div>
                      <Badge
                        variant={sub.status === 'accepted' ? 'default' : 'secondary'}
                        className="text-[11px] shrink-0"
                      >
                        {sub.status === 'accepted' ? '✓ Accepted' : '⏳ Pending'}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Save button */}
            <div className="flex justify-end">
              <Button onClick={handleSave} disabled={saving}>
                {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Save preferences
              </Button>
            </div>
          </>
        )}
      </motion.div>
    </div>
  );
}
