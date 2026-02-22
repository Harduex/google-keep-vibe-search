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
  tag?: string;
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

/** Legacy citation format (Note #N). */
export interface Citation {
  note_number: number;
  note_id: string;
  note_title: string;
}

/** Grounded context item from the retrieval pipeline. */
export interface GroundedContext {
  citation_id: string;
  note_id: string;
  note_title: string;
  text: string;
  start_char_idx: number | null;
  end_char_idx: number | null;
  relevance_score: number;
  source_type: string;
  heading_trail: string[];
}

/** Grounded citation extracted from the LLM response. */
export interface GroundedCitation {
  citation_id: string;
  note_id: string;
  note_title: string;
  start_char_idx: number | null;
  end_char_idx: number | null;
  text_snippet: string;
}

/** A parsed segment of text, either plain or a citation reference. */
export interface ContentSegment {
  type: 'text' | 'citation';
  text: string;
  citationId?: string;
}

/** Result of parsing an LLM response for citations. */
export interface ParsedContent {
  cleanText: string;
  citations: GroundedCitation[];
  segments: ContentSegment[];
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  message_count: number;
  updated_at: string;
}
