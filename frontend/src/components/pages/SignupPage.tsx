'use client';

import { useState } from 'react';
import { Compass, Mail, Lock, User, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { useAppStore } from '@/lib/store';
import { api, ApiError, type SessionResponse } from '@/lib/api';
import { toast } from 'sonner';

interface SignupFieldErrors {
  errors: Record<string, { message: string; code?: string }[]>;
}

export default function SignupPage() {
  const { navigate, login } = useAppStore();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (!termsAccepted) {
      setError('You must accept the Terms of Use to create an account.');
      return;
    }
    setLoading(true);
    try {
      const response = await api.post<SessionResponse>('/api/accounts/signup/', {
        email,
        firstName: name,
        password1: password,
        password2: confirmPassword,
        termsAccepted,
      });
      login(response.user!);
      toast.success('Account created!');
      navigate('onboarding');
    } catch (err) {
      if (err instanceof ApiError && err.body && typeof err.body === 'object' && 'errors' in err.body) {
        const fieldErrors = (err.body as SignupFieldErrors).errors;
        const firstMessage = Object.values(fieldErrors).flat()[0]?.message;
        setError(firstMessage || 'Something went wrong. Please try again.');
      } else {
        setError('Something went wrong. Please try again.');
      }
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
        <h1 className="text-xl font-bold text-ink">Create your account</h1>
        <p className="mt-1 text-sm text-ink-muted">Start tracking AI with a personalized feed</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="name">First name <span className="text-ink-muted">(optional)</span></Label>
          <div className="relative">
            <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
            <Input
              id="name"
              type="text"
              placeholder="Alex"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

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

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
            <Input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="pl-10"
              required
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirm-password">Confirm password</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
            <Input
              id="confirm-password"
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="pl-10"
              required
            />
          </div>
        </div>

        <div className="flex items-start gap-2">
          <Checkbox
            id="terms-accepted"
            checked={termsAccepted}
            onCheckedChange={(checked) => setTermsAccepted(checked === true)}
            className="mt-0.5"
          />
          <Label htmlFor="terms-accepted" className="text-xs font-normal text-ink-muted">
            I agree to the{' '}
            <a href="/terms" target="_blank" rel="noopener noreferrer" className="font-medium text-primary hover:underline">
              Terms of Use
            </a>{' '}
            and acknowledge the{' '}
            <a href="/privacy" target="_blank" rel="noopener noreferrer" className="font-medium text-primary hover:underline">
              Privacy Policy
            </a>
            .
          </Label>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" className="w-full" disabled={loading || !termsAccepted}>
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Sign up
        </Button>
      </form>

      <p className="text-center text-sm text-ink-muted">
        Already have an account?{' '}
        <button onClick={() => navigate('login')} className="font-medium text-primary hover:underline">
          Log in
        </button>
      </p>
    </div>
  );
}