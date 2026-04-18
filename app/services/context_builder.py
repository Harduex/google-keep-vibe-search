from typing import Any, Dict, List, Optional

from app.prompts.system_prompts import NO_NOTES_SYSTEM_PROMPT, NOTES_CHAT_SYSTEM_PROMPT


class ContextBuilder:
    """Formats notes and builds LLM message lists with system prompts."""

    def format_notes(self, notes: List[Dict[str, Any]]) -> str:
        """Format notes into a string for system prompt injection."""
        formatted = []
        for i, note in enumerate(notes, 1):
            title = note.get("title", "Untitled Note")
            content = note.get("content", "")
            created = note.get("created", "Unknown")
            edited = note.get("edited", "Unknown")
            tag = note.get("tag", "")
            tags = note.get("tags", [tag] if tag else [])

            block = f"--- Note #{i} ---\nTitle: {title}\nCreated: {created} | Last edited: {edited}"
            if tags:
                block += f"\nTags: {', '.join(tags)}"
            block += f"\n\n{content}\n--- End Note #{i} ---"
            formatted.append(block)

        return "\n\n".join(formatted)

    def build_messages(
        self,
        messages: List[Dict[str, str]],
        notes: List[Dict[str, Any]],
        conflicts: Optional[List[Dict[str, Any]]] = None,
        gap_status: str = "sufficient",
    ) -> List[Dict[str, str]]:
        """Build the full message list with system prompt, notes context, and warnings."""
        prepared = [m for m in messages if m.get("role") != "system"]

        if notes:
            formatted_notes = self.format_notes(notes)
            system_content = NOTES_CHAT_SYSTEM_PROMPT.format(
                note_count=len(notes),
                formatted_notes=formatted_notes,
            )

            # Inject pre-computed conflict warnings
            if conflicts:
                conflict_lines = []
                for c in conflicts:
                    a_label = c["note_a_title"] or f"Note #{c['note_a_index']}"
                    b_label = c["note_b_title"] or f"Note #{c['note_b_index']}"
                    line = (
                        f"- Note #{c['note_a_index']} ({a_label}) and "
                        f"Note #{c['note_b_index']} ({b_label}) "
                        f"contain conflicting information "
                        f"(confidence: {c['contradiction_score']:.0%})."
                    )
                    if c["note_a_edited"] and c["note_b_edited"]:
                        line += (
                            f" Edited: #{c['note_a_index']} on {c['note_a_edited']}, "
                            f"#{c['note_b_index']} on {c['note_b_edited']}."
                        )
                    conflict_lines.append(line)

                system_content += (
                    "\n\nIMPORTANT — CONFLICTING NOTES DETECTED:\n"
                    + "\n".join(conflict_lines)
                    + "\nPlease acknowledge these conflicts in your response "
                    "and prefer the most recently edited note."
                )
        else:
            system_content = NO_NOTES_SYSTEM_PROMPT

        # Gap analysis warning
        if gap_status == "best_effort":
            system_content += (
                "\n\nNote: Your notes may not contain complete information "
                "about this topic. Be honest about gaps in the available information."
            )

        prepared.insert(0, {"role": "system", "content": system_content})
        return prepared
