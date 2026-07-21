'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, SkipForward, Sparkles, Loader2, GraduationCap, FlaskConical, Wrench, Briefcase, Crown, Rocket, Gamepad2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/lib/store';
import { api, ApiError } from '@/lib/api';
import { toast } from 'sonner';

// Real backend shapes — GET /api/onboarding/wizard/. Distinct from the old
// mock Persona/TopicTag vocabularies (see cerebrum.md M15 Phase 3 notes):
// personas use the REAL Persona.slug (e.g. 'product_manager', not the mock's
// 'pm'), and interests are the separate, curated Interest table (grouped by
// their own real `category`), not the TaxonomyTopic-derived TOPIC_GROUPS.
interface WizardPersona {
  id: number;
  slug: string;
  name: string;
  description: string;
}

interface WizardInterest {
  id: number;
  slug: string;
  name: string;
  category: string;
}

interface WizardSource {
  key: string;
  name: string;
  category: string;
}

interface WizardResponse {
  onboardingCompleted: boolean;
  personas: WizardPersona[];
  selectedPersonaId: number | null;
  interests: WizardInterest[];
  selectedInterestIds: number[];
  sources: WizardSource[];
  excludedSourceKeys: string[];
}

// Icon lookup keyed by the REAL persona slug — same icon set the old
// hardcoded PERSONA_OPTIONS used, just re-keyed since the real backend's
// Product Manager slug is 'product_manager', not the mock's 'pm'. Falls back
// to Sparkles for any slug that doesn't match one of the seven seeded
// personas, so the page never crashes on an unexpected value.
const PERSONA_ICONS: Record<string, typeof GraduationCap> = {
  student: GraduationCap,
  researcher: FlaskConical,
  engineer: Wrench,
  product_manager: Briefcase,
  executive: Crown,
  founder: Rocket,
  hobbyist: Gamepad2,
};

export default function OnboardingPage() {
  const { navigate, setOnboarding, onboarding, updateUser } = useAppStore();
  const step = (onboarding.step || 1) as 1 | 2 | 3;

  // One-time load for the whole 3-step flow — not re-fetched per step.
  const { data, isLoading } = useQuery({
    queryKey: ['onboarding-wizard'],
    queryFn: () => api.get<WizardResponse>('/api/onboarding/wizard/'),
  });

  const [selectedPersonaId, setSelectedPersonaId] = useState<number | undefined>(undefined);
  const [selectedInterestIds, setSelectedInterestIds] = useState<Set<number>>(new Set());
  const [excludedSourceKeys, setExcludedSourceKeys] = useState<Set<string>>(new Set());
  const [finishing, setFinishing] = useState(false);

  // Seed local wizard state from the backend's current selections exactly
  // once, when the initial fetch resolves — guarded so a background refetch
  // never clobbers a selection the user has already made mid-flow.
  const initialized = useRef(false);
  useEffect(() => {
    if (data && !initialized.current) {
      initialized.current = true;
      setSelectedPersonaId(data.selectedPersonaId ?? undefined);
      setSelectedInterestIds(new Set(data.selectedInterestIds));
      setExcludedSourceKeys(new Set(data.excludedSourceKeys));
    }
  }, [data]);

  // Graceful fallback on fetch failure (or while still loading): an empty
  // wizard rather than a crash — this page has no dedicated error-state UI.
  const personas = data?.personas ?? [];
  const interests = data?.interests ?? [];
  const sources = data?.sources ?? [];

  // Group interests by their real `category` field — same visual grouping
  // pattern the old mock TOPIC_GROUPS used, just driven by real data.
  const interestGroups = interests.reduce<{ category: string; items: WizardInterest[] }[]>((groups, interest) => {
    const group = groups.find(g => g.category === interest.category);
    if (group) group.items.push(interest);
    else groups.push({ category: interest.category, items: [interest] });
    return groups;
  }, []);

  const toggleInterest = (id: number) => {
    setSelectedInterestIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleExclude = (key: string) => {
    setExcludedSourceKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleNext = () => {
    if (step === 1) {
      setOnboarding({ step: 2 });
    } else if (step === 2) {
      setOnboarding({ step: 3 });
    } else {
      handleFinish();
    }
  };

  const handleFinish = async () => {
    setFinishing(true);
    try {
      await api.post('/api/onboarding/wizard/complete/', {
        personaId: selectedPersonaId ?? null,
        interestIds: Array.from(selectedInterestIds),
        excludedSourceKeys: Array.from(excludedSourceKeys),
      });
      updateUser({ onboardingComplete: true });
      setOnboarding({ step: 1, isComplete: true, interests: [], excludedSources: [] });
      toast.success('Onboarding complete! Welcome to AI Compass.');
      navigate('feed');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setFinishing(false);
    }
  };

  const handleSkip = () => {
    if (step < 3) {
      handleNext();
    } else {
      navigate('home');
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        {/* Progress */}
        <div className="mb-8 flex items-center justify-center gap-2">
          {([1, 2, 3] as const).map(s => (
            <div
              key={s}
              className={`h-1.5 flex-1 max-w-[100px] rounded-full transition-colors ${
                s <= step ? 'bg-primary' : 'bg-border'
              }`}
            />
          ))}
          <span className="ml-2 text-xs font-medium text-ink-muted">{step}/3</span>
        </div>

        <AnimatePresence mode="wait">
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              <h2 className="mb-2 text-xl font-bold text-ink text-center">Who are you?</h2>
              <p className="mb-6 text-sm text-ink-muted text-center">This helps us personalize your experience.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {personas.map(p => {
                  const Icon = PERSONA_ICONS[p.slug] ?? Sparkles;
                  const selected = selectedPersonaId === p.id;
                  return (
                    <button
                      key={p.id}
                      onClick={() => setSelectedPersonaId(p.id)}
                      className={`flex items-start gap-3 rounded-xl border-2 p-4 text-left transition-all duration-150 ${
                        selected
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/30'
                      }`}
                    >
                      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${selected ? 'bg-primary text-primary-foreground' : 'bg-muted text-ink-muted'}`}>
                        <Icon className="h-4.5 w-4.5" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-ink">{p.name}</p>
                        <p className="text-xs text-ink-muted">{p.description}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              <h2 className="mb-2 text-xl font-bold text-ink text-center">What are you into?</h2>
              <p className="mb-6 text-sm text-ink-muted text-center">Select topics you care about.</p>
              {interestGroups.map(group => (
                <div key={group.category} className="mb-5">
                  <h3 className="mb-2.5 text-sm font-semibold text-ink">{group.category}</h3>
                  <div className="flex flex-wrap gap-2">
                    {group.items.map(interest => {
                      const selected = selectedInterestIds.has(interest.id);
                      return (
                        <button
                          key={interest.id}
                          onClick={() => toggleInterest(interest.id)}
                          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-all duration-150 ${
                            selected
                              ? 'bg-primary text-primary-foreground'
                              : 'border border-border bg-surface text-ink-muted hover:border-primary/40'
                          }`}
                        >
                          {selected && <Check className="h-3 w-3" />}
                          {interest.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </motion.div>
          )}

          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              <h2 className="mb-2 text-xl font-bold text-ink text-center">Any sources to skip?</h2>
              <p className="mb-6 text-sm text-ink-muted text-center">Exclude sources you don&apos;t want in your feed.</p>
              <div className="space-y-2">
                {sources.map(s => {
                  const excluded = excludedSourceKeys.has(s.key);
                  return (
                    <button
                      key={s.key}
                      onClick={() => toggleExclude(s.key)}
                      className={`flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors ${
                        excluded ? 'border-destructive/30 bg-destructive/5' : 'border-border bg-card hover:bg-muted/50'
                      }`}
                    >
                      <span className="text-sm text-ink">{s.name}</span>
                      <span className={`text-xs ${excluded ? 'text-destructive' : 'text-ink-muted'}`}>
                        {excluded ? 'Excluded' : s.category}
                      </span>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Actions */}
        <div className="mt-8 flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={handleSkip}>
            <SkipForward className="mr-1.5 h-3.5 w-3.5" /> Skip
          </Button>
          <Button onClick={handleNext} disabled={finishing || isLoading}>
            {finishing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {step === 3 ? (
              <>
                <Sparkles className="mr-1.5 h-4 w-4" /> Finish
              </>
            ) : 'Next'}
          </Button>
        </div>

        <button
          onClick={() => { setOnboarding({ isComplete: true }); navigate('home'); }}
          className="mt-4 mx-auto block text-xs text-ink-muted hover:text-ink"
        >
          I&apos;ll finish this later
        </button>
      </motion.div>
    </div>
  );
}
