import { NoteColor } from '../constants/theme';

export interface Annotation {
  url?: string;
  title?: string;
}

export interface Attachment {
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
}

export interface SearchResponse {
  results: Note[];
}

export interface StatsResponse {
  total_notes: number;
  archived_notes: number;
  pinned_notes: number;
  using_cached_embeddings: boolean;
}
