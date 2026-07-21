'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Shield, Check, Sparkles, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useAppStore } from '@/lib/store';
import { api, ApiError } from '@/lib/api';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';

const FAQ = [
  {
    q: 'Can I try Pro for free?',
    a: 'Yes! We offer a 14-day free trial of Pro. No credit card required to start.',
  },
  {
    q: 'What happens if I downgrade?',
    a: 'You keep access to Pro features until the end of your billing period. After that, excess sources and follows are paused (not deleted).',
  },
  {
    q: 'Can I cancel anytime?',
    a: 'Absolutely. Cancel from the Billing page with one click. No questions asked.',
  },
  {
    q: 'Do you offer team or enterprise plans?',
    a: 'Not yet, but they\'re on our roadmap. Contact us if you\'re interested.',
  },
];

const FREE_FEATURES = [
  'Browse Home feed',
  'Search all content',
  'My Feed (personalized ranking)',
  'Save & hide items',
  'Library',
  '3 custom sources',
  '20 topic/entity follows',
  'Digest emails',
];

const PRO_FEATURES = [
  ...FREE_FEATURES,
  'Unlimited custom sources',
  'Unlimited follows',
  'Video chapters (timestamped)',
  'Weekly Insights briefing',
  'Priority support',
];

export default function PricingPage() {
  const { navigate, isLoggedIn, user } = useAppStore();
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  const handleUpgradeClick = async () => {
    if (!isLoggedIn) {
      navigate('signup');
      return;
    }
    if (user?.plan === 'pro') return;

    setCheckoutLoading(true);
    try {
      const data = await api.post<{ url: string }>('/api/accounts/billing/checkout/');
      window.location.href = data.url;
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Something went wrong starting checkout. Please try again.';
      toast.error(message);
      setCheckoutLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="text-center"
      >
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-ink">Simple, transparent pricing</h1>
        <p className="text-ink-muted">Start free, upgrade when you need more.</p>
      </motion.div>

      <div className="mt-10 grid gap-6 md:grid-cols-2">
        {/* Free */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className="rounded-xl border border-border bg-card p-6"
        >
          <div className="mb-4">
            <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold text-ink-muted">
              Free
            </span>
          </div>
          <div className="mb-6">
            <span className="text-3xl font-bold text-ink">$0</span>
            <span className="text-sm text-ink-muted">/month</span>
          </div>
          <ul className="mb-6 space-y-2.5">
            {FREE_FEATURES.map(f => (
              <li key={f} className="flex items-center gap-2 text-sm text-ink-muted">
                <Check className="h-4 w-4 shrink-0 text-emerald-500" />
                {f}
              </li>
            ))}
          </ul>
          <Button
            variant="outline"
            className="w-full"
            disabled={isLoggedIn && user?.plan === 'free'}
            onClick={() => { if (!isLoggedIn) navigate('signup'); }}
          >
            {isLoggedIn && user?.plan === 'free' ? 'Current plan' : 'Get started free'}
          </Button>
        </motion.div>

        {/* Pro */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.15 }}
          className="relative rounded-xl border-2 border-primary bg-card p-6 shadow-lg shadow-primary/5"
        >
          <div className="absolute -top-3 left-6">
            <span className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-0.5 text-xs font-semibold text-primary-foreground">
              <Sparkles className="h-3 w-3" /> Pro
            </span>
          </div>
          <div className="mb-4 mt-2">
            <span className="text-sm text-ink-muted">For power users</span>
          </div>
          <div className="mb-6">
            <span className="text-3xl font-bold text-ink">$12</span>
            <span className="text-sm text-ink-muted">/month</span>
          </div>
          <ul className="mb-6 space-y-2.5">
            {PRO_FEATURES.map(f => (
              <li key={f} className="flex items-center gap-2 text-sm text-ink-muted">
                <Check className="h-4 w-4 shrink-0 text-primary" />
                {f}
              </li>
            ))}
          </ul>
          <Button
            className="w-full"
            disabled={(isLoggedIn && user?.plan === 'pro') || checkoutLoading}
            onClick={handleUpgradeClick}
          >
            {checkoutLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {user?.plan === 'pro' ? 'Current plan' : checkoutLoading ? 'Redirecting...' : 'Upgrade to Pro'}
          </Button>
        </motion.div>
      </div>

      {/* FAQ */}
      <div className="mt-16">
        <h2 className="mb-6 text-center text-lg font-semibold text-ink">Frequently asked questions</h2>
        <div className="mx-auto max-w-xl">
          <Accordion type="single" collapsible className="w-full">
            {FAQ.map((item, i) => (
              <AccordionItem key={i} value={`faq-${i}`}>
                <AccordionTrigger className="text-sm text-left">{item.q}</AccordionTrigger>
                <AccordionContent className="text-sm text-ink-muted">{item.a}</AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </div>
  );
}