import { NOTE_COLORS } from '@/const';

export type NoteColor = keyof typeof NOTE_COLORS;

interface Annotation {
  url?: string;
  title?: string;
}

interface Attachment {
  filePath: string;
  mimetype: string;
}

export interface Note {
  id: string;
  title: string;
  content: string;
  created: string;
  edited: string;
  archived: boolean;
  pinned: boolean;
  color: NoteColor;
  score: number;
  annotations?: Annotation[];
  attachments?: Attachment[];
  has_matching_images?: boolean;
  matched_image?: string;
  tags: string[];
}

export type ViewMode = 'list' | '3d';

export interface NoteCluster {
  id: number;
  keywords: string[];
  notes: Note[];
  size: number;
}

export interface Tag {
  name: string;
  count: number;
}

export interface TagsResponse {
  tags: Tag[];
}

export interface ExcludedTagsResponse {
  excluded_tags: string[];
}

export interface Citation {
  note_number: number;
  note_id: string;
  note_title: string;
  // Verification fields (populated after NLI check)
  claim?: string;
  support_score?: number;
  contradiction_score?: number;
  verdict?: 'supported' | 'contradicted' | 'neutral' | 'unknown';
}

export interface ConflictInfo {
  note_a_index: number;
  note_b_index: number;
  note_a_title: string;
  note_b_title: string;
  note_a_edited: string;
  note_b_edited: string;
  contradiction_score: number;
  similarity: number;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  message_count: number;
  updated_at: string;
}

export interface TagProposal {
  tag_name: string;
  note_ids: string[];
  note_count: number;
  sample_notes: { id: string; title: string; content: string }[];
  confidence: number;
}

export type ProposalAction = 'approve' | 'reject' | 'rename' | 'merge' | 'pending';

export interface ProposalState {
  proposal: TagProposal;
  action: ProposalAction;
  newName?: string;
  mergeTarget?: string;
}

export type Granularity = 'broad' | 'specific';

export interface CategorizationProgress {
  stage: string;
  message: string;
  progress: number;
  current?: number;
  total?: number;
}

export interface AgentStep {
  step_number: number;
  action: string;
  params: Record<string, unknown>;
  result_summary: string;
  notes_found: number;
  reasoning: string;
}

export interface GroundingClaim {
  text: string;
  score: number;
  verdict: 'supported' | 'contradicted' | 'neutral' | 'unsupported';
  cited_note: number | null;
}

export interface GroundingResult {
  claims: GroundingClaim[];
  overall_score: number;
  grounded_count: number;
  total_claims: number;
}
