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
