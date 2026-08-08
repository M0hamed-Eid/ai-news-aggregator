// ============================================================
// AI Compass — Core Type Definitions
// ============================================================

export type PageRoute =
  | 'home'
  | 'search'
  | 'feed'
  | 'pricing'
  | 'article-detail'
  | 'video-detail'
  | 'sources'
  | 'people'
  | 'entity-profile'
  | 'insights'
  | 'library'
  | 'profile'
  | 'billing'
  | 'preferences'
  | 'onboarding'
  | 'login'
  | 'signup'
  | 'forgot-password'
  | 'password-reset-done'
  | 'password-reset-confirm'
  | 'terms'
  | 'privacy'
  | 'password-reset-complete'
  | 'email-verify-done'
  | 'story-cluster'
  | 'ops'
  | 'trending-stories';

export type UserRole = 'visitor' | 'free' | 'pro' | 'staff';

export type Persona =
  | 'student'
  | 'researcher'
  | 'engineer'
  | 'pm'
  | 'executive'
  | 'founder'
  | 'hobbyist';

export type ContentCategory =
  | 'Research'
  | 'Open Source'
  | 'Product / Model Databases'
  | 'Developer Communities'
  | 'Government'
  | 'Funding'
  | 'Media';

export type TopicTag =
  | 'Large Language Models'
  | 'AI Agents'
  | 'Open Source Models'
  | 'NLP'
  | 'Machine Learning Research'
  | 'RAG & Vector Databases'
  | 'Computer Vision'
  | 'Reinforcement Learning'
  | 'Multimodal AI'
  | 'AI Safety & Alignment'
  | 'AI Policy & Regulation'
  | 'Robotics'
  | 'MLOps & Infrastructure'
  | 'Developer Tools'
  | 'Startups & Funding'
  | 'Anthropic'
  | 'OpenAI'
  | 'Google DeepMind'
  | 'Meta AI'
  | 'Mistral AI'
  | 'xAI'
  | 'Hugging Face'
  | 'NVIDIA'
  | 'Microsoft'
  | 'Apple Intelligence'
  | 'Stability AI'
  | 'Cohere'
  | 'AI21 Labs';

export type SourceKey =
  | 'blog_openai'
  | 'blog_anthropic'
  | 'arxiv'
  | 'github_release'
  | 'huggingface_model'
  | 'reddit'
  | 'government_uk'
  | 'government_us'
  | 'government_nist'
  | 'funding_crunchbase'
  | 'youtube';

export interface Source {
  key: SourceKey | string;
  name: string;
  category: ContentCategory;
  isActive: boolean;
  isCustom?: boolean;
  status?: 'accepted' | 'accepted_low_confidence' | 'rejected' | 'pending';
  subscriberCount?: number;
}

export interface TopicChip {
  label: string;
  followed: boolean;
}

export interface MentionedEntity {
  id: string;
  name: string;
  type: 'person' | 'company' | 'model' | 'technology';
}

export interface ArticleItem {
  id: string;
  type: 'article';
  title: string;
  summary: string;
  whyItMatters?: string;
  author?: string;
  source: SourceKey | string;
  sourceLabel: string;
  url: string;
  imageUrl?: string;
  publishedAt: string;
  category: ContentCategory;
  topics: TopicTag[];
  mentionedEntities: MentionedEntity[];
  technicalDepth?: number;
  recommendedReason?: string;
  rank?: number;
  isSaved: boolean;
  isRead: boolean;
  isHidden: boolean;
  contentType?: 'article' | 'release' | 'paper';
}

export interface VideoItem {
  id: string;
  type: 'video';
  title: string;
  summary: string;
  whyItMatters?: string;
  author?: string;
  channelName?: string;
  source: 'youtube';
  sourceLabel: string;
  url: string;
  thumbnailUrl: string;
  videoId: string;
  duration: number; // seconds
  publishedAt: string;
  category: ContentCategory;
  topics: TopicTag[];
  mentionedEntities: MentionedEntity[];
  technicalDepth?: number;
  recommendedReason?: string;
  rank?: number;
  isSaved: boolean;
  isRead: boolean;
  isHidden: boolean;
  chapters?: VideoChapter[];
  hasTranscript: boolean;
}

export type ContentItem = ArticleItem | VideoItem;

export interface VideoChapter {
  title: string;
  startTime: number;
  summary: string;
}

export interface TrendingTopic {
  id: string;
  label: string;
  multiplier: number;
  isHotCluster?: boolean;
}

export interface EntityProfile {
  id: string;
  name: string;
  type: 'person' | 'company' | 'model' | 'technology';
  bio?: string;
  isFollowed: boolean;
  mentionData: { date: string; count: number }[];
  ownOutput: ContentItem[];
  mentions: ContentItem[];
  related: EntityProfile[];
}

export interface InsightItem {
  id: string;
  headline: string;
  summary: string;
  sources: { title: string; url: string }[];
  weekOf: string;
}

export interface UserPreferences {
  interests: TopicTag[];
  persona: Persona;
  technicalLevel: 'beginner' | 'intermediate' | 'advanced';
  itemsPerFeed: number;
  articleVideoMix: 'balanced' | 'articles' | 'videos';
  researchIndustryLean: 'balanced' | 'research' | 'industry';
  readingTimeBudget?: number;
  digestFrequency: 'daily' | 'weekly';
  digestPaused: boolean;
  excludedSources: (SourceKey | string)[];
  excludedCategories: ContentCategory[];
}

export interface UserState {
  role: UserRole;
  name: string;
  email: string;
  bio: string;
  avatarUrl?: string;
  preferences: UserPreferences;
  customSourceCount: number;
  followCount: number;
  maxCustomSources: number;
  maxFollows: number;
  digestCount: number;
  isEmailVerified: boolean;
  onboardingComplete: boolean;
  plan?: 'free' | 'pro';
  subscriptionEnd?: string;
}

export interface StoryCluster {
  id: string;
  type: 'cluster';
  title: string;
  summary: string;
  items: ContentItem[];
}

// Navigation item for sidebar
export interface NavItem {
  id: PageRoute;
  label: string;
  icon: string; // lucide icon name
  requiresAuth?: boolean;
  requiresPro?: boolean;
  requiresStaff?: boolean;
  badge?: string | number;
}

// Filter state for Home/Search pages
export interface FilterState {
  search: string;
  category: ContentCategory | 'all';
  source: SourceKey | string | 'all';
  topic: TopicTag | 'all';
  dateFrom: string;
}

// Onboarding wizard state
export interface OnboardingState {
  step: 1 | 2 | 3;
  persona?: Persona;
  interests: TopicTag[];
  excludedSources: (SourceKey | string)[];
  isComplete: boolean;
}

// ============================================================
// AI Assistant Types (frontend-only — ready for backend integration)
// ============================================================

export type AssistantContextType =
  | { type: 'article'; title: string; id: string }
  | { type: 'video'; title: string; id: string }
  | { type: 'topic'; label: string }
  | { type: 'search'; query: string }
  | { type: 'global' };

export type MessageRole = 'user' | 'assistant';

export interface SourceReference {
  id: string;
  title: string;
  source: string;
  sourceType: 'article' | 'video' | 'summary' | 'transcript';
  time?: string;
  thumbnailUrl?: string;
  url?: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  sources?: SourceReference[];
  followUps?: string[];
  isStreaming?: boolean;
}

export type AssistantPanelState = 'closed' | 'open' | 'minimized';

export interface AssistantConversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  context: AssistantContextType;
  createdAt: number;
  updatedAt: number;
  // The real Django-side ChatConversation.id (web/apps/assistant/models.py),
  // set once the FIRST message in this conversation gets a response — every
  // later message in the same thread sends this back as conversation_id so
  // the backend keeps appending to the same real conversation instead of
  // starting a new one each turn. Undefined until then.
  backendConversationId?: number;
}

export interface AssistantState {
  panelState: AssistantPanelState;
  conversations: AssistantConversation[];
  activeConversationId: string | null;
  context: AssistantContextType;
  isTyping: boolean;
  error: string | null;
}