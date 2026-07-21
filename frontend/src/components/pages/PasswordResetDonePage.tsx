'use client';

import { Compass, ArrowLeft, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/lib/store';

export default function PasswordResetDonePage() {
  const { navigate } = useAppStore();

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-100 dark:bg-emerald-950">
          <Mail className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
        </div>
        <h1 className="text-xl font-bold text-ink">Check your email</h1>
        <p className="mt-1 text-sm text-ink-muted">
          We&apos;ve sent a password reset link to your email address. Click the link to set a new password.
        </p>
      </div>

      <Button
        variant="outline"
        className="w-full"
        onClick={() => navigate('login')}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to login
      </Button>
    </div>
  );
}