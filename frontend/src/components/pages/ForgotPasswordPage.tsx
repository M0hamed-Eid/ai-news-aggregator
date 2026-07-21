'use client';

import { useState } from 'react';
import { Compass, Mail, Loader2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAppStore } from '@/lib/store';
import { api } from '@/lib/api';
import { toast } from 'sonner';

export default function ForgotPasswordPage() {
  const { navigate } = useAppStore();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);

  // POST /api/accounts/password-reset/ always returns {ok: true} whether or
  // not the address has an account (web/apps/accounts/api_views.py::
  // PasswordResetRequestAPIView) -- same information-disclosure posture as
  // Django's own PasswordResetForm, so there's no error branch to show here.
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/api/accounts/password-reset/', { email });
      toast.success('Reset link sent!');
      navigate('password-reset-done');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary">
          <Compass className="h-6 w-6 text-primary-foreground" />
        </div>
        <h1 className="text-xl font-bold text-ink">Reset your password</h1>
        <p className="mt-1 text-sm text-ink-muted">We&apos;ll send you a reset link</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="pl-10"
              required
            />
          </div>
        </div>

        <Button type="submit" className="w-full" disabled={loading}>
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Send reset link
        </Button>
      </form>

      <button
        onClick={() => navigate('login')}
        className="mx-auto flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to login
      </button>
    </div>
  );
}