'use client';

import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ShieldCheck, ShieldAlert, ShieldOff, Database } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatDistanceToNow } from 'date-fns';
import { useAppStore } from '@/lib/store';
import { api } from '@/lib/api';

// GET /api/accounts/ops/'s real JSON shape (web/apps/accounts/api_views.py::
// OpsAPIView) — mirrors apps.accounts.ops.OpsDashboardView field-for-field
// (same is_staff gate, same Source.objects.all() query, same is_unhealthy
// computation: active + has run at least once + most recent run didn't
// succeed).
interface OpsSource {
  key: string;
  name: string;
  category: string;
  isActive: boolean;
  isUnhealthy: boolean;
  visibility: string;
  lastRunAt: string | null;
  lastSuccessAt: string | null;
}

interface OpsResponse {
  totalCount: number;
  activeCount: number;
  unhealthyCount: number;
  sources: OpsSource[];
}

export default function OpsPage() {
  const { navigate, isLoggedIn, user } = useAppStore();
  const isStaff = user?.role === 'staff';

  const { data, isLoading } = useQuery({
    queryKey: ['ops'],
    queryFn: () => api.get<OpsResponse>('/api/accounts/ops/'),
    enabled: isLoggedIn && isStaff,
  });

  if (!isLoggedIn) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center md:px-6">
        <p className="text-ink-muted">Sign in to view the ops dashboard.</p>
        <Button className="mt-4" onClick={() => navigate('login')}>Log in</Button>
      </div>
    );
  }

  if (!isStaff) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center md:px-6">
        <ShieldOff className="mx-auto mb-4 h-12 w-12 text-ink-muted" />
        <h2 className="mb-2 text-lg font-semibold text-ink">Staff access required</h2>
        <p className="text-sm text-ink-muted">This dashboard is only available to AI Compass staff.</p>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-6">
        <Skeleton className="mb-6 h-7 w-56" />
        <div className="mb-6 grid grid-cols-3 gap-3">
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-20 rounded-xl" />
        </div>
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 md:px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
            <Database className="h-4.5 w-4.5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-ink">Ops Dashboard</h1>
            <p className="text-sm text-ink-muted">Scraper health across every configured source.</p>
          </div>
        </div>

        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Total sources</p>
            <p className="mt-1 text-2xl font-bold text-ink">{data.totalCount}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Active</p>
            <p className="mt-1 text-2xl font-bold text-ink">{data.activeCount}</p>
          </div>
          <div className={`rounded-xl border p-4 ${data.unhealthyCount > 0 ? 'border-destructive/30 bg-destructive/5' : 'border-border bg-card'}`}>
            <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Unhealthy</p>
            <p className={`mt-1 text-2xl font-bold ${data.unhealthyCount > 0 ? 'text-destructive' : 'text-ink'}`}>
              {data.unhealthyCount}
            </p>
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last run</TableHead>
                <TableHead>Last success</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.sources.map(source => (
                <TableRow key={source.key}>
                  <TableCell className="font-medium text-ink">{source.name}</TableCell>
                  <TableCell className="text-ink-muted">{source.category}</TableCell>
                  <TableCell>
                    {source.isUnhealthy ? (
                      <Badge variant="destructive"><ShieldAlert className="h-3 w-3" /> Unhealthy</Badge>
                    ) : source.isActive ? (
                      <Badge className="border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                        <ShieldCheck className="h-3 w-3" /> Healthy
                      </Badge>
                    ) : (
                      <Badge variant="secondary"><ShieldOff className="h-3 w-3" /> Inactive</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-ink-muted">
                    {source.lastRunAt ? formatDistanceToNow(new Date(source.lastRunAt), { addSuffix: true }) : '—'}
                  </TableCell>
                  <TableCell className="text-ink-muted">
                    {source.lastSuccessAt ? formatDistanceToNow(new Date(source.lastSuccessAt), { addSuffix: true }) : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </motion.div>
    </div>
  );
}
