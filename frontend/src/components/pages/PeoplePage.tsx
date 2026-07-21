'use client';

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Search, User } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/lib/store';
import { api } from '@/lib/api';
import EmptyState from '@/components/shared/EmptyState';

const TYPE_COLORS = {
  person: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  company: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  model: 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300',
  technology: 'bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300',
};

interface PersonListItem {
  id: string;
  name: string;
  type: keyof typeof TYPE_COLORS;
  bio: string | null;
  isFollowed: boolean;
}

interface PeopleResponse {
  people: PersonListItem[];
}

export default function PeoplePage() {
  const { navigate, isLoggedIn, toggleFollowEntity, isEntityFollowed } = useAppStore();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(handle);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['people', debouncedSearch],
    queryFn: () => api.get<PeopleResponse>(`/api/news/people/?q=${encodeURIComponent(debouncedSearch)}`),
    enabled: isLoggedIn,
  });

  const filtered = data?.people ?? [];

  if (!isLoggedIn) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
        <EmptyState
          icon={User}
          title="Sign in to browse people"
          description="Explore AI people, companies, and entities after signing in."
          action={{ label: 'Log in', onClick: () => navigate('login') }}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="relative mb-6 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
          <Input
            placeholder="Search people..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-xl border border-border bg-card p-4"
              >
                <div className="h-10 w-10 shrink-0 animate-pulse rounded-lg bg-muted" />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="h-3.5 w-2/3 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-full animate-pulse rounded bg-muted" />
                </div>
              </div>
            ))}
          </div>
        ) : filtered.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {filtered.map(person => {
              const followed = isEntityFollowed(person.id);
              return (
                // A <div role="button">, not a real <button> — this card wraps an
                // actual <Button> (Follow), and <button> cannot legally contain a
                // nested <button> (was throwing a React hydration error in the
                // console with real data; the mock version had the same invalid
                // nesting, it just never got noticed before). tabIndex/onKeyDown
                // restore native-button keyboard activation (Enter/Space).
                <div
                  key={person.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate('entity-profile', { id: person.id })}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate('entity-profile', { id: person.id });
                    }
                  }}
                  className="group flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4 text-left transition-all duration-200 hover:shadow-md hover:-translate-y-[1px]"
                >
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${TYPE_COLORS[person.type]}`}>
                    <User className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-0.5 flex items-center gap-1.5">
                      <span className="text-sm font-semibold text-ink">{person.name}</span>
                      <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium capitalize ${TYPE_COLORS[person.type]}`}>
                        {person.type}
                      </span>
                    </div>
                    {person.bio && (
                      <p className="line-clamp-2 text-xs text-ink-muted">{person.bio}</p>
                    )}
                  </div>
                  <div
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleFollowEntity(person.id);
                    }}
                  >
                    <Button
                      variant={followed ? 'secondary' : 'outline'}
                      size="sm"
                      className="h-7 text-xs"
                    >
                      {followed ? 'Following' : 'Follow'}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={User}
            title="No people found"
            description="Try a different search term."
          />
        )}
      </motion.div>
    </div>
  );
}