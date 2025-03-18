import os
import json
import glob
from datetime import datetime
from typing import List, Dict, Any

from app.config import GOOGLE_KEEP_PATH


def parse_timestamp(usec: int) -> str:
    """Convert microsecond timestamp to readable date."""
    if not usec:
        return "Unknown date"
    
    sec = usec / 1000000
    return datetime.fromtimestamp(sec).strftime('%Y-%m-%d %H:%M:%S')


def parse_notes() -> List[Dict[str, Any]]:
    """Parse all Google Keep notes from the export directory."""
    json_files = glob.glob(os.path.join(GOOGLE_KEEP_PATH, '*.json'))
    notes = []
    
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                note_data = json.load(f)
                
            # Skip trashed notes
            if note_data.get('isTrashed', False):
                continue
                
            # Create a clean note object
            note = {
                'id': os.path.basename(file_path),
                'title': note_data.get('title', ''),
                'content': note_data.get('textContent', ''),
                'created': parse_timestamp(note_data.get('createdTimestampUsec', 0)),
                'edited': parse_timestamp(note_data.get('userEditedTimestampUsec', 0)),
                'archived': note_data.get('isArchived', False),
                'pinned': note_data.get('isPinned', False),
                'color': note_data.get('color', 'DEFAULT'),
            }
            
            # Add annotations if present
            if note_data.get('annotations'):
                note['annotations'] = note_data.get('annotations')
            
            # Add attachments if present (usually images)
            if note_data.get('attachments'):
                note['attachments'] = note_data.get('attachments')
                
            notes.append(note)
                
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
    
    return notes