'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Mail, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { useAppStore } from '@/lib/store';
import { api, ApiError } from '@/lib/api';
import { toast } from 'sonner';
import type { UserState } from '@/lib/types';

// GET/POST /api/accounts/profile/'s real JSON shape: a complete UserState
// (see lib/types.ts) plus favoriteSources/rankingCount. preferences.interests
// and preferences.persona use the REAL Interest-slug / Persona-slug
// vocabularies (a separate curated Interest table and the real Persona
// table — NOT the mock TopicTag/Persona enums types.ts declares for other
// pages), so the response is typed locally rather than reusing UserState's
// preferences shape. setUser() is still fed the whole object — the extra
// favoriteSources/rankingCount keys are harmless on the store's UserState.
interface ProfilePreferences {
  interests: string[];
  persona: string | null;
  technicalLevel: 'beginner' | 'intermediate' | 'advanced';
  itemsPerFeed: number;
  articleVideoMix: 'balanced' | 'articles' | 'videos';
  researchIndustryLean: 'balanced' | 'research' | 'industry';
  readingTimeBudget?: number | null;
  digestFrequency: 'daily' | 'weekly';
  digestPaused: boolean;
  excludedSources: string[];
  excludedCategories: string[];
}

interface ProfileResponse {
  role: UserState['role'];
  name: string;
  email: string;
  bio: string;
  preferences: ProfilePreferences;
  customSourceCount: number;
  followCount: number;
  maxCustomSources: number;
  maxFollows: number;
  digestCount: number;
  isEmailVerified: boolean;
  onboardingComplete: boolean;
  plan?: 'free' | 'pro';
  subscriptionEnd?: string;
  favoriteSources: [string, number][];
  rankingCount: number;
}

// GET /api/onboarding/personas/'s real JSON shape — the real Persona table
// (student/researcher/engineer/product_manager/executive/founder/hobbyist),
// rendered dynamically instead of a hardcoded PERSONAS constant so a slug
// like 'product_manager' (not the old mock 'pm') always resolves correctly.
interface PersonaOption {
  id: number;
  slug: string;
  name: string;
  description: string;
}

interface PersonasResponse {
  personas: PersonaOption[];
  selectedId: number | null;
}

// "large-language-models" -> "Large Language Models", "blog_openai" ->
// "Blog Openai" — good enough display transform for real Interest slugs
// (hyphens) and real Source keys (underscores) alike; don't overthink it.
function formatSlugLabel(slug: string): string {
  return slug.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ProfilePage() {
  const { navigate, isLoggedIn, sessionLoading, setUser } = useAppStore();

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get<ProfileResponse>('/api/accounts/profile/'),
    enabled: isLoggedIn,
  });

  const { data: personasData } = useQuery({
    queryKey: ['onboarding-personas'],
    queryFn: () => api.get<PersonasResponse>('/api/onboarding/personas/'),
    enabled: isLoggedIn,
  });

  const [name, setName] = useState('');
  const [bio, setBio] = useState('');
  const [persona, setPersona] = useState('');
  const [digestFrequency, setDigestFrequency] = useState<string>('daily');
  const [digestPaused, setDigestPaused] = useState(false);
  const [technicalLevel, setTechnicalLevel] = useState<string>('intermediate');
  const [itemsPerFeed, setItemsPerFeed] = useState(20);
  const [articleVideoMix, setArticleVideoMix] = useState<string>('balanced');
  const [researchIndustryLean, setResearchIndustryLean] = useState<string>('balanced');
  const [readingTimeBudget, setReadingTimeBudget] = useState('');
  const [saving, setSaving] = useState(false);
  const [seeded, setSeeded] = useState(false);
  const [resending, setResending] = useState(false);

  // Once per successful fetch: replace the ENTIRE global user object with
  // the real one (setUser), and seed this page's local form state from the
  // same fetched data — not from the store's previously-placeholder user.
  useEffect(() => {
    if (!profile) return;
    setUser(profile as unknown as UserState);
    setName(profile.name);
    setBio(profile.bio);
    setPersona(profile.preferences.persona || '');
    setDigestFrequency(profile.preferences.digestFrequency);
    setDigestPaused(profile.preferences.digestPaused);
    setTechnicalLevel(profile.preferences.technicalLevel);
    setItemsPerFeed(profile.preferences.itemsPerFeed);
    setArticleVideoMix(profile.preferences.articleVideoMix);
    setResearchIndustryLean(profile.preferences.researchIndustryLean);
    setReadingTimeBudget(profile.preferences.readingTimeBudget?.toString() ?? '');
    setSeeded(true);
  }, [profile, setUser]);

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

  if (sessionLoading || profileLoading || !profile || !seeded) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">
        <p className="text-sm text-ink-muted">Loading profile…</p>
      </div>
    );
  }

  const topInterests = profile.preferences.interests.slice(0, 3);
  const topSources = profile.favoriteSources.slice(0, 3);
  const personaOptions = personasData?.personas ?? [];

  const handleResendVerification = async () => {
    setResending(true);
    try {
      const response = await api.post<{ ok: boolean; alreadyVerified: boolean }>('/api/accounts/verify/resend/');
      toast.success(response.alreadyVerified ? 'Your email is already verified.' : 'Verification email sent!');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to send verification email.');
    } finally {
      setResending(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await api.post<ProfileResponse>('/api/accounts/profile/', {
        name,
        bio,
        persona: persona || null,
        digestFrequency,
        digestPaused,
        technicalLevel,
        itemsPerFeed,
        articleVideoMix,
        researchIndustryLean,
        readingTimeBudget: readingTimeBudget ? parseInt(readingTimeBudget, 10) : null,
      });
      setUser(response as unknown as UserState);
      toast.success('Profile saved!');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to save profile.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">
      <div className="flex gap-8">
        {/* Left sidebar — At a glance */}
        <motion.aside
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3 }}
          className="hidden w-56 shrink-0 lg:block"
        >
          <div className="sticky top-20 rounded-xl border border-border bg-card p-4">
            <h3 className="mb-4 text-sm font-semibold text-ink">At a glance</h3>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-ink-muted">Digests received</dt>
                <dd className="font-semibold text-ink">{profile.digestCount || 0}</dd>
              </div>
              <div>
                <dt className="text-ink-muted">Interests followed</dt>
                <dd className="font-semibold text-ink">{profile.followCount || 0}</dd>
              </div>
              <div>
                <dt className="text-ink-muted">Onboarding</dt>
                <dd className="font-semibold text-ink">{profile.onboardingComplete ? '✓ Complete' : 'Incomplete'}</dd>
              </div>
              <Separator />
              <div>
                <dt className="mb-1.5 text-ink-muted">Top interests</dt>
                <div className="flex flex-wrap gap-1">
                  {topInterests.map(t => (
                    <span key={t} className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">{formatSlugLabel(t)}</span>
                  ))}
                </div>
              </div>
              <div>
                <dt className="mb-1.5 text-ink-muted">Top sources</dt>
                <div className="flex flex-col gap-1">
                  {topSources.map(([key]) => (
                    <span key={key} className="text-xs text-ink-muted">{formatSlugLabel(key)}</span>
                  ))}
                </div>
              </div>
            </dl>
          </div>
        </motion.aside>

        {/* Main form */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="min-w-0 flex-1 space-y-8"
        >
          {/* Account info */}
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="mb-4 text-sm font-semibold text-ink">Account</h3>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>Name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>Bio</Label>
                <Textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={3} />
              </div>
              <div className="space-y-1.5">
                <Label>Email</Label>
                <div className="flex items-center gap-2">
                  <Input value={profile.email} disabled className="bg-muted" />
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
                  </div>
                </div>
                {profile.isEmailVerified ? (
                  <p className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Verified
                  </p>
                ) : (
                  <div className="flex items-center gap-2">
                    <p className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                      <AlertCircle className="h-3.5 w-3.5" /> Not verified
                    </p>
                    <button
                      onClick={handleResendVerification}
                      disabled={resending}
                      className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
                    >
                      {resending ? 'Sending…' : 'Resend verification email'}
                    </button>
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <Label>Persona</Label>
                <Select value={persona} onValueChange={setPersona}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {personaOptions.map(p => (
                      <SelectItem key={p.slug} value={p.slug}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Digest settings */}
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="mb-4 text-sm font-semibold text-ink">Digest</h3>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Frequency</Label>
                <RadioGroup value={digestFrequency} onValueChange={setDigestFrequency} className="flex gap-4">
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="daily" id="daily" />
                    <Label htmlFor="daily" className="font-normal">Daily</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="weekly" id="weekly" />
                    <Label htmlFor="weekly" className="font-normal">Weekly</Label>
                  </div>
                </RadioGroup>
              </div>
              <div className="flex items-center justify-between">
                <Label>Pause digest emails</Label>
                <Switch checked={digestPaused} onCheckedChange={setDigestPaused} />
              </div>
            </div>
          </div>

          {/* Ranking preferences */}
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="mb-4 text-sm font-semibold text-ink">Ranking Preferences</h3>
            <div className="space-y-5">
              <div className="space-y-2">
                <Label>Technical level</Label>
                <RadioGroup value={technicalLevel} onValueChange={setTechnicalLevel} className="flex gap-4">
                  {['beginner', 'intermediate', 'advanced'].map(level => (
                    <div key={level} className="flex items-center gap-2">
                      <RadioGroupItem value={level} id={level} />
                      <Label htmlFor={level} className="font-normal capitalize">{level}</Label>
                    </div>
                  ))}
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Items per feed</Label>
                  <span className="text-sm font-medium text-primary">{itemsPerFeed}</span>
                </div>
                <Slider
                  value={[itemsPerFeed]}
                  onValueChange={([v]) => setItemsPerFeed(v)}
                  min={5}
                  max={50}
                  step={1}
                />
                <div className="flex justify-between text-[11px] text-ink-muted">
                  <span>5</span>
                  <span>50</span>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Article vs video mix</Label>
                <RadioGroup value={articleVideoMix} onValueChange={setArticleVideoMix} className="flex gap-4">
                  {['balanced', 'articles', 'videos'].map(v => (
                    <div key={v} className="flex items-center gap-2">
                      <RadioGroupItem value={v} id={`mix-${v}`} />
                      <Label htmlFor={`mix-${v}`} className="font-normal capitalize">{v}</Label>
                    </div>
                  ))}
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <Label>Research vs industry lean</Label>
                <RadioGroup value={researchIndustryLean} onValueChange={setResearchIndustryLean} className="flex gap-4">
                  {['balanced', 'research', 'industry'].map(v => (
                    <div key={v} className="flex items-center gap-2">
                      <RadioGroupItem value={v} id={`lean-${v}`} />
                      <Label htmlFor={`lean-${v}`} className="font-normal capitalize">{v}</Label>
                    </div>
                  ))}
                </RadioGroup>
              </div>

              <div className="space-y-1.5">
                <Label>Reading time budget <span className="text-ink-muted">(minutes, optional)</span></Label>
                <Input
                  type="number"
                  min={1}
                  max={120}
                  value={readingTimeBudget}
                  onChange={(e) => setReadingTimeBudget(e.target.value)}
                  placeholder="e.g. 30"
                />
              </div>
            </div>
          </div>

          {/* Save */}
          <div className="flex justify-end">
            <Button onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save changes
            </Button>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
