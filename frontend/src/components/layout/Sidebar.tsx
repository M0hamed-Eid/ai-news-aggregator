'use client';

import { useState } from 'react';
import {
  Home, Search, Rss, CreditCard, Database, Users, Bookmark, Lightbulb, ShieldCheck, Flame,
  ChevronLeft, ChevronRight, Settings, User, LogOut, Compass, X, Sun, Moon, Monitor
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from '@/components/ui/sheet';
import { useTheme } from 'next-themes';
import { useAppStore } from '@/lib/store';
import type { PageRoute } from '@/lib/types';

type NavItemDef = {
  id: PageRoute; label: string; icon: typeof Home;
  requiresAuth?: boolean; requiresPro?: boolean; requiresStaff?: boolean; badge?: string;
};

const NAV_ITEMS: NavItemDef[] = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'feed', label: 'My Feed', icon: Rss, requiresAuth: true },
  { id: 'pricing', label: 'Pricing', icon: CreditCard },
];

const DISCOVER_ITEMS: NavItemDef[] = [
  { id: 'sources', label: 'Sources', icon: Database, requiresAuth: true },
  { id: 'people', label: 'People', icon: Users, requiresAuth: true },
  { id: 'trending-stories', label: 'Trending Stories', icon: Flame, requiresAuth: true },
  { id: 'library', label: 'Library', icon: Bookmark, requiresAuth: true },
  { id: 'insights', label: 'Insights', icon: Lightbulb, requiresAuth: true, badge: 'PRO' },
];

const STAFF_ITEMS: NavItemDef[] = [
  { id: 'ops', label: 'Ops', icon: ShieldCheck, requiresAuth: true, requiresStaff: true },
];

export default function Sidebar() {
  const { currentPage, navigate, isLoggedIn, user, logout, sidebarOpen, setSidebarOpen } = useAppStore();
  const [collapsed, setCollapsed] = useState(false);
  const { setTheme, theme } = useTheme();

  const NavItemButton = ({
    id, label, icon: Icon, requiresAuth, requiresPro, badge
  }: NavItemDef) => {
    const isActive = currentPage === id;
    const isLocked = (requiresAuth && !isLoggedIn) || (requiresPro && user?.plan !== 'pro');

    return (
      <button
        onClick={() => {
          if (isLocked) {
            if (!isLoggedIn) navigate('login');
            else navigate('pricing');
            return;
          }
          navigate(id);
          setSidebarOpen(false);
        }}
        className={`
          group relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150
          ${isActive
            ? 'sidebar-item-active bg-primary/8 text-primary'
            : 'text-ink-muted hover:bg-muted hover:text-ink'
          }
          ${collapsed ? 'justify-center px-2' : ''}
        `}
        title={collapsed ? label : undefined}
      >
        <Icon className={`h-4.5 w-4.5 shrink-0 ${isActive ? 'text-primary' : ''}`} />
        {!collapsed && (
          <>
            <span className="flex-1 text-left">{label}</span>
            {badge && (
              <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold text-primary">
                {badge}
              </span>
            )}
          </>
        )}
      </button>
    );
  };

  const sidebarContent = (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary">
          <Compass className="h-4.5 w-4.5 text-primary-foreground" />
        </div>
        {!collapsed && (
          <span className="text-base font-bold tracking-tight text-ink">
            AI Compass
          </span>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {NAV_ITEMS.map((item) => (
          <NavItemButton key={item.id} {...item} />
        ))}
        <div className="my-3 flex items-center gap-2 px-1">
          <Separator className="flex-1" />
          {!collapsed && <span className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">Discover</span>}
          <Separator className="flex-1" />
        </div>
        {DISCOVER_ITEMS.map((item) => (
          <NavItemButton key={item.id} {...item} />
        ))}
        {isLoggedIn && user?.role === 'staff' && (
          <>
            <div className="my-3 flex items-center gap-2 px-1">
              <Separator className="flex-1" />
              {!collapsed && <span className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">Staff</span>}
              <Separator className="flex-1" />
            </div>
            {STAFF_ITEMS.map((item) => (
              <NavItemButton key={item.id} {...item} />
            ))}
          </>
        )}
      </nav>

      {/* Bottom account section */}
      <div className="border-t border-border p-3">
        {isLoggedIn && user ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors duration-150 hover:bg-muted">
                <Avatar className="h-8 w-8 shrink-0">
                  <AvatarFallback className="bg-primary/10 text-sm font-semibold text-primary">
                    {user.name.split(' ').map(n => n[0]).join('')}
                  </AvatarFallback>
                </Avatar>
                {!collapsed && (
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{user.name}</p>
                    <p className="truncate text-xs text-ink-muted">{user.plan === 'pro' ? 'Pro' : 'Free'}</p>
                  </div>
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" side="top" className="w-48">
              <DropdownMenuItem onClick={() => navigate('profile')}>
                <User className="mr-2 h-4 w-4" /> Profile
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('billing')}>
                <CreditCard className="mr-2 h-4 w-4" /> Billing
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate('preferences')}>
                <Settings className="mr-2 h-4 w-4" /> Preferences
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
                {theme === 'dark' ? <Sun className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />}
                {theme === 'dark' ? 'Light mode' : 'Dark mode'}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
                <LogOut className="mr-2 h-4 w-4" /> Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <div className="flex flex-col gap-2">
            <Button size="sm" onClick={() => navigate('login')} variant="outline" className="w-full">
              Log in
            </Button>
            <Button size="sm" onClick={() => navigate('signup')} className="w-full">
              Sign up
            </Button>
          </div>
        )}
      </div>

      {/* Collapse toggle (desktop only) */}
      <div className="hidden border-t border-border lg:block">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex w-full items-center justify-center p-2 text-ink-muted transition-colors duration-150 hover:bg-muted hover:text-ink"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={`hidden lg:flex flex-col border-r border-border bg-sidebar h-screen sticky top-0 shrink-0 transition-all duration-200 ${collapsed ? 'w-[68px]' : 'w-[260px]'}`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile sidebar (sheet) */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-[280px] p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          {sidebarContent}
        </SheetContent>
      </Sheet>
    </>
  );
}