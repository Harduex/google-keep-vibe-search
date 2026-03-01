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
