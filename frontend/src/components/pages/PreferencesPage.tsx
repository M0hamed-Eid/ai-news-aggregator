'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/lib/store';
import { api } from '@/lib/api';
import { toast } from 'sonner';

// Real Interest rows (web/apps/onboarding/models.py::Interest) — a curated
// 15-row vocabulary distinct from the 27-row TaxonomyTopic used for
// article/video topic chips elsewhere in this app. See
// web/apps/onboarding/api_views.py::InterestsAPIView's docstring.
interface Interest {
  id: number;
  slug: string;
  name: string;
  category: string;
}

interface InterestsResponse {
  interests: Interest[];
  selectedIds: number[];
}

export default function PreferencesPage() {
  const { navigate, isLoggedIn, sessionLoading } = useAppStore();
  const [loading, setLoading] = useState(true);
  const [interests, setInterests] = useState<Interest[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isLoggedIn) return;
    let cancelled = false;

    api.get<InterestsResponse>('/api/onboarding/interests/')
      .then(data => {
        if (cancelled) return;
        setInterests(data.interests ?? []);
        setSelectedIds(new Set(data.selectedIds ?? []));
      })
      .catch(() => {
        if (!cancelled) toast.error('Failed to load interests.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isLoggedIn]);

  // Redirect only once the real session check has resolved — isLoggedIn
  // starts false until GET /api/session/ returns, so redirecting on that
  // initial false was bouncing genuinely logged-in users to /login on every
  // fresh page load (confirmed live: also threw a React
  // "Cannot update a component while rendering" error, since navigate() was
  // being called synchronously during render, not in an effect).
  useEffect(() => {
    if (!sessionLoading && !isLoggedIn) {
      navigate('login');
    }
  }, [sessionLoading, isLoggedIn, navigate]);

  if (sessionLoading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
        <p className="text-sm text-ink-muted">Loading…</p>
      </div>
    );
  }
  if (!isLoggedIn) {
    return null;
  }

  const toggleInterest = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Group real interests by their own `category` field — same visual
  // grouping pattern the old mock TOPIC_GROUPS used, just driven by real
  // data. Every real Interest already has a category, so there's no
  // "leftover ungrouped" bucket to special-case here.
  const groupedInterests = interests.reduce<Record<string, Interest[]>>((acc, interest) => {
    (acc[interest.category] ??= []).push(interest);
    return acc;
  }, {});

  const handleSave = () => {
    setSaving(true);
    api.post('/api/onboarding/interests/', { interestIds: Array.from(selectedIds) })
      .then(() => {
        toast.success('Interests saved!');
      })
      .catch(() => {
        toast.error('Failed to save interests.');
      })
      .finally(() => {
        setSaving(false);
      });
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="space-y-8"
      >
        <div className="mb-2">
          <h2 className="text-lg font-bold text-ink">Your Interests</h2>
          <p className="text-sm text-ink-muted">Select topics to personalize your feed and digest.</p>
        </div>

        {loading ? (
          <p className="text-sm text-ink-muted">Loading your interests…</p>
        ) : (
          Object.entries(groupedInterests).map(([category, categoryInterests]) => (
            <div key={category}>
              <h3 className="mb-3 text-sm font-semibold text-ink">{category}</h3>
              <div className="flex flex-wrap gap-2">
                {categoryInterests.map(interest => {
                  const isSelected = selectedIds.has(interest.id);
                  return (
                    <button
                      key={interest.id}
                      onClick={() => toggleInterest(interest.id)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-all duration-150 ${
                        isSelected
                          ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                          : 'border border-border bg-surface text-ink-muted hover:border-primary/40 hover:text-primary'
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3" />}
                      {interest.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        )}

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving || loading}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save interests
          </Button>
        </div>
      </motion.div>
    </div>
  );
}
