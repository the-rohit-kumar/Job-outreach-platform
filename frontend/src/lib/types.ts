export type User = {
  id: number;
  username: string;
  created_at: string;
};

export type AuthStatus = {
  needs_setup: boolean;
  user: User | null;
};

export type Profile = {
  id: number;
  display_name: string;
  email: string;
  location: string;
  github_url?: string;
  cv_url?: string;
  portfolio_url?: string;
  about_me: string;
  skills: string[];
  do_not_mention: string[];
  tone: ProfileTone;
  updated_at: string;
};


export type ProfileTone = {
  style?: string;
  formality?: string;
  max_email_words?: number;
  max_linkedin_note_chars?: number;
  include_opt_out_line?: boolean;
  emoji?: boolean;
  exclamation_marks?: boolean;
  hard_rules?: string[];
};

export type OnboardingItem = {
  key: string;
  label: string;
  href: string;
  order_index: number;
  auto: boolean;
  done: boolean;
};

export type ApiToken = {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

export type Source = {
  key: string;
  name: string;
  kind: string;
  enabled: boolean;
  config: Record<string, any>;
  last_run_at: string | null;
  last_status: string;
  last_error: string;
  last_count: number;
  known: boolean;
};

export type SourceRun = {
  id: number;
  collector_key: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  leads_found: number;
  leads_new: number;
  error: string;
};

export type Lead = {
  id: number;
  source: string;
  title: string;
  company: string;
  company_domain: string;
  url: string;
  location: string;
  remote: boolean;
  employment_type: string;
  posted_at: string | null;
  status: string;
  stage: string;
  score: number | null;
  score_reason: string;
  channel: string;
  hook: string;
  contact: Record<string, any>;
  duplicate_of: number | null;
  opted_out: boolean;
  created_at: string;
  updated_at: string;
};

export type LeadDetail = Lead & {
  description: string;
  raw_text: string;
  enrichment: Record<string, any>;
  stage_notes: string;
  contacted_at: string | null;
  replied_at: string | null;
};

export type LeadsPageData = {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
  facets: {
    sources: string[];
    statuses: string[];
    stages: string[];
    channels: string[];
  };
};

export type LeadHistory = {
  drafts: Array<{
    id: number;
    variant: string;
    channel: string;
    subject: string;
    body: string;
    status: string;
    model: string;
    checks: Record<string, any>;
    fail_reason: string;
    created_at: string;
    reviewed_at: string | null;
  }>;
  messages: Array<{
    id: number;
    direction: string;
    channel: string;
    body: string;
    sender: string;
    received_at: string;
  }>;
  sends: Array<{
    id: number;
    channel: string;
    status: string;
    sent_at: string | null;
    error: string;
    note: string;
  }>;
};
