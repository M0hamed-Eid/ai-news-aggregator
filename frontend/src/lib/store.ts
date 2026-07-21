import { create } from 'zustand';
import { pushPath, goBackPath } from './router-bridge';
import { routeToPath } from './route-map';
import { api, type SessionUser, parseContentRef, toggleSaved, toggleHidden, toggleFollow } from './api';
import type {
  PageRoute,
  UserState,
  UserPreferences,
  FilterState,
  OnboardingState,
  ContentItem,
  TopicTag,
  SourceKey,
  Persona,
  AssistantPanelState,
  AssistantContextType,
  ChatMessage,
  AssistantConversation,
} from './types';

// ============================================================
// AI Compass — Zustand Store
// ============================================================

interface NavigationState {
  currentPage: PageRoute;
  pageParams: Record<string, string>;
  previousPage: PageRoute | null;
  navigate: (page: PageRoute, params?: Record<string, string>) => void;
  goBack: () => void;
}

interface AuthState {
  isLoggedIn: boolean;
  user: UserState | null;
  /** True until the app-load GET /api/session/ call resolves (see
   * SessionHydrator.tsx) — lets the shell avoid flashing a logged-out
   * state for one frame while the real session is still loading. */
  sessionLoading: boolean;
  login: (sessionUser: SessionUser) => void;
  logout: () => void;
  hydrateSession: (sessionUser: SessionUser | null) => void;
  updateUser: (updates: Partial<UserState>) => void;
  updatePreferences: (updates: Partial<UserPreferences>) => void;
  /** Replaces the whole user object wholesale — for GET/POST /api/accounts/
   * profile/ and GET /api/accounts/billing/, which already return a
   * complete, real UserState (unlike the minimal SessionUser login()/
   * hydrateSession() work from), so no field-by-field mapping is needed. */
  setUser: (userState: UserState) => void;
}

interface ContentState {
  savedItems: Set<string>;
  hiddenItems: Set<string>;
  followedTopics: Set<TopicTag>;
  followedEntities: Set<string>;
  /** Seeds savedItems/hiddenItems from a freshly-fetched list's real
   * isSaved/isHidden (web/apps/news/serializers.py) — call once after any
   * successful Home/Feed/Search fetch so cards reflect real saved/hidden
   * state instead of starting from an empty client-only guess. */
  hydrateContentState: (items: { id: string; isSaved: boolean; isHidden: boolean }[]) => void;
  /** Seeds followedTopics/followedEntities from GET /api/behavior/follows/
   * — called once by SessionHydrator right after a successful login, same
   * pattern as hydrateSession/hydrateContentState replacing an honest-zero
   * placeholder with real server state. */
  hydrateFollows: (entityIds: string[], topicNames: string[]) => void;
  toggleSave: (id: string) => void;
  toggleHide: (id: string) => void;
  toggleFollowTopic: (topic: TopicTag) => void;
  toggleFollowEntity: (id: string) => void;
  isItemSaved: (id: string) => boolean;
  isItemHidden: (id: string) => boolean;
  isTopicFollowed: (topic: TopicTag) => boolean;
  isEntityFollowed: (id: string) => boolean;
}

interface AppStore extends NavigationState, AuthState, ContentState {
  filterState: FilterState;
  setFilter: (filters: Partial<FilterState>) => void;
  clearFilters: () => void;
  onboarding: OnboardingState;
  setOnboarding: (updates: Partial<OnboardingState>) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  // AI Assistant
  assistantPanelState: AssistantPanelState;
  assistantContext: AssistantContextType;
  assistantConversations: AssistantConversation[];
  assistantActiveConversationId: string | null;
  assistantIsTyping: boolean;
  assistantError: string | null;
  setAssistantPanelState: (state: AssistantPanelState) => void;
  setAssistantContext: (context: AssistantContextType) => void;
  startNewAssistantConversation: (context?: AssistantContextType) => string;
  addAssistantMessage: (conversationId: string, message: ChatMessage) => void;
  updateAssistantMessage: (conversationId: string, messageId: string, updates: Partial<ChatMessage>) => void;
  setConversationBackendId: (conversationId: string, backendId: number) => void;
  setAssistantTyping: (typing: boolean) => void;
  setAssistantError: (error: string | null) => void;
}

const defaultPreferences: UserPreferences = {
  interests: ['Large Language Models', 'AI Agents', 'Developer Tools'],
  persona: 'engineer',
  technicalLevel: 'intermediate',
  itemsPerFeed: 20,
  articleVideoMix: 'balanced',
  researchIndustryLean: 'balanced',
  readingTimeBudget: undefined,
  digestFrequency: 'daily',
  digestPaused: false,
  excludedSources: [],
  excludedCategories: [],
};

// Maps GET /api/session/'s minimal SessionUser (web/apps/accounts/api_views.py)
// onto the richer UserState the existing (Z.ai-authored) page components
// expect. Fields the session endpoint doesn't carry yet — bio, real
// preferences, source/follow/digest counts — stay honest placeholders
// (0 / defaults) until Phase 3 wires Profile/Preferences to real data;
// nothing here is fabricated to LOOK populated.
function mapSessionUserToUserState(sessionUser: SessionUser): UserState {
  return {
    role: sessionUser.isStaff ? 'staff' : sessionUser.plan === 'pro' ? 'pro' : 'free',
    name: sessionUser.firstName || sessionUser.email.split('@')[0],
    email: sessionUser.email,
    bio: '',
    preferences: defaultPreferences,
    customSourceCount: 0,
    followCount: 0,
    maxCustomSources: 3,
    maxFollows: 20,
    digestCount: 0,
    isEmailVerified: sessionUser.emailVerified,
    onboardingComplete: sessionUser.onboardingCompleted,
    plan: sessionUser.plan,
  };
}

const defaultFilters: FilterState = {
  search: '',
  category: 'all',
  source: 'all',
  topic: 'all',
  dateFrom: '',
};

const defaultOnboarding: OnboardingState = {
  step: 1,
  interests: [],
  excludedSources: [],
  isComplete: false,
};

export const useAppStore = create<AppStore>((set, get) => ({
  // Navigation
  currentPage: 'home',
  pageParams: {},
  previousPage: null,
  navigate: (page, params = {}) => {
    set((state) => ({
      previousPage: state.currentPage,
      currentPage: page,
      pageParams: params,
    }));
    // Real URL change — PageSync on the destination route re-syncs this
    // same state back in on mount, so this is a no-op loop-breaker, not a
    // second source of truth.
    pushPath(routeToPath(page, params));
  },
  goBack: () => goBackPath(),

  // Auth — starts honestly logged-out; SessionHydrator (mounted in
  // layout.tsx, same pattern as RouterBridge) calls GET /api/session/ once
  // on app load and reconciles this via hydrateSession().
  isLoggedIn: false,
  user: null,
  sessionLoading: true,
  login: (sessionUser) => set({ isLoggedIn: true, user: mapSessionUserToUserState(sessionUser), sessionLoading: false }),
  logout: () => {
    api.post('/api/accounts/logout/').catch(() => {});
    set({ isLoggedIn: false, user: null, currentPage: 'home' });
  },
  hydrateSession: (sessionUser) =>
    set({
      isLoggedIn: sessionUser !== null,
      user: sessionUser ? mapSessionUserToUserState(sessionUser) : null,
      sessionLoading: false,
    }),
  setUser: (userState) => set({ user: userState }),
  updateUser: (updates) =>
    set((state) => ({
      user: state.user ? { ...state.user, ...updates } : null,
    })),
  updatePreferences: (updates) =>
    set((state) => ({
      user: state.user
        ? {
            ...state.user,
            preferences: { ...state.user.preferences, ...updates },
          }
        : null,
    })),

  // Content interactions — savedItems/hiddenItems are a CLIENT-SIDE CACHE
  // of real apps.behavior.SavedItem state, not invented data: hydrated from
  // each list fetch's real isSaved/isHidden (hydrateContentState, called by
  // Home/Feed/Search after a successful fetch) and kept in sync by
  // toggleSave/toggleHide's real API calls below. followedTopics/
  // followedEntities are the same pattern (real GET /api/behavior/follows/
  // seeds them via hydrateFollows, real POST /api/behavior/follow/ keeps
  // them in sync via toggleFollowTopic/toggleFollowEntity below) — M15
  // Phase 5 replaced what used to be local-only mock state here.
  savedItems: new Set<string>(),
  hiddenItems: new Set<string>(),
  followedTopics: new Set<TopicTag>(),
  followedEntities: new Set<string>(),

  hydrateContentState: (items) =>
    set((state) => {
      const savedItems = new Set(state.savedItems);
      const hiddenItems = new Set(state.hiddenItems);
      for (const item of items) {
        if (item.isSaved) savedItems.add(item.id);
        if (item.isHidden) hiddenItems.add(item.id);
      }
      return { savedItems, hiddenItems };
    }),
  hydrateFollows: (entityIds, topicNames) =>
    set({
      followedEntities: new Set(entityIds),
      followedTopics: new Set(topicNames as TopicTag[]),
    }),

  toggleSave: (id) => {
    const ref = parseContentRef(id);
    if (!ref) return;
    set((state) => {
      const next = new Set(state.savedItems);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { savedItems: next };
    });
    toggleSaved(ref.contentType, ref.contentId).catch(() => {
      // Revert the optimistic flip on failure (network error, 403 not
      // logged in, etc.) — the server never confirmed the new state.
      set((state) => {
        const next = new Set(state.savedItems);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return { savedItems: next };
      });
    });
  },
  toggleHide: (id) => {
    const ref = parseContentRef(id);
    if (!ref) return;
    set((state) => {
      const next = new Set(state.hiddenItems);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { hiddenItems: next };
    });
    toggleHidden(ref.contentType, ref.contentId).catch(() => {
      set((state) => {
        const next = new Set(state.hiddenItems);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return { hiddenItems: next };
      });
    });
  },
  // Optimistic flip + real POST /api/behavior/follow/, reverted on failure
  // (network error, or a real 403 from the server's FREE_FOLLOW_LIMIT cap —
  // the client-side maxFollows pre-check below just avoids the round-trip
  // in the common case; the server's response is what's authoritative).
  // Matches toggleSave/toggleHide's exact optimistic-update pattern above.
  toggleFollowTopic: (topic) => {
    const wasFollowing = get().followedTopics.has(topic);
    const user = get().user;
    if (!wasFollowing && user && user.role === 'free' && get().followedTopics.size + get().followedEntities.size >= user.maxFollows) return;

    set((state) => {
      const next = new Set(state.followedTopics);
      if (wasFollowing) next.delete(topic);
      else next.add(topic);
      const newCount = state.followedEntities.size + next.size;
      return { followedTopics: next, user: state.user ? { ...state.user, followCount: newCount } : null };
    });
    toggleFollow('topic', topic).catch(() => {
      set((state) => {
        const next = new Set(state.followedTopics);
        if (wasFollowing) next.add(topic);
        else next.delete(topic);
        const newCount = state.followedEntities.size + next.size;
        return { followedTopics: next, user: state.user ? { ...state.user, followCount: newCount } : null };
      });
    });
  },
  toggleFollowEntity: (id) => {
    const wasFollowing = get().followedEntities.has(id);
    const user = get().user;
    if (!wasFollowing && user && user.role === 'free' && get().followedEntities.size + get().followedTopics.size >= user.maxFollows) return;

    set((state) => {
      const next = new Set(state.followedEntities);
      if (wasFollowing) next.delete(id);
      else next.add(id);
      const newCount = state.followedTopics.size + next.size;
      return { followedEntities: next, user: state.user ? { ...state.user, followCount: newCount } : null };
    });
    toggleFollow('entity', id).catch(() => {
      set((state) => {
        const next = new Set(state.followedEntities);
        if (wasFollowing) next.add(id);
        else next.delete(id);
        const newCount = state.followedTopics.size + next.size;
        return { followedEntities: next, user: state.user ? { ...state.user, followCount: newCount } : null };
      });
    });
  },
  isItemSaved: (id) => get().savedItems.has(id),
  isItemHidden: (id) => get().hiddenItems.has(id),
  isTopicFollowed: (topic) => get().followedTopics.has(topic),
  isEntityFollowed: (id) => get().followedEntities.has(id),

  // Filters
  filterState: defaultFilters,
  setFilter: (filters) =>
    set((state) => ({
      filterState: { ...state.filterState, ...filters },
    })),
  clearFilters: () => set({ filterState: defaultFilters }),

  // Onboarding
  onboarding: defaultOnboarding,
  setOnboarding: (updates) =>
    set((state) => ({
      onboarding: { ...state.onboarding, ...updates },
    })),

  // Sidebar
  sidebarOpen: false,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  // AI Assistant
  assistantPanelState: 'closed',
  assistantContext: { type: 'global' },
  assistantConversations: [],
  assistantActiveConversationId: null,
  assistantIsTyping: false,
  assistantError: null,
  setAssistantPanelState: (state) => set({ assistantPanelState: state }),
  setAssistantContext: (context) => set({ assistantContext: context }),
  startNewAssistantConversation: (context) => {
    const id = `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const ctx = context || get().assistantContext;
    const newConv: AssistantConversation = {
      id,
      title: '',
      messages: [],
      context: ctx,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    set((state) => ({
      assistantConversations: [newConv, ...state.assistantConversations],
      assistantActiveConversationId: id,
      assistantError: null,
    }));
    return id;
  },
  addAssistantMessage: (conversationId, message) =>
    set((state) => ({
      assistantConversations: state.assistantConversations.map((c) =>
        c.id === conversationId
          ? { ...c, messages: [...c.messages, message], updatedAt: Date.now(), title: c.title || (message.role === 'user' ? message.content.slice(0, 50) : c.title) }
          : c
      ),
    })),
  // Mutates one message in place (by id) rather than appending — used by the
  // real SSE stream to grow an assistant message's content token-by-token,
  // then attach citations/followUps/isStreaming:false once the stream ends.
  updateAssistantMessage: (conversationId, messageId, updates) =>
    set((state) => ({
      assistantConversations: state.assistantConversations.map((c) =>
        c.id === conversationId
          ? {
              ...c,
              messages: c.messages.map((m) => (m.id === messageId ? { ...m, ...updates } : m)),
              updatedAt: Date.now(),
            }
          : c
      ),
    })),
  setConversationBackendId: (conversationId, backendId) =>
    set((state) => ({
      assistantConversations: state.assistantConversations.map((c) =>
        c.id === conversationId ? { ...c, backendConversationId: backendId } : c
      ),
    })),
  setAssistantTyping: (typing) => set({ assistantIsTyping: typing }),
  setAssistantError: (error) => set({ assistantError: error }),
}));