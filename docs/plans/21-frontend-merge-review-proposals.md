# Task 21 — Frontend: merge + review proposals in OrganizeDashboard

## Goal
Surface task 10 gray-zone merges and task 11 review-queue assignments for one-click approval.

## Spec
In `components/Organize/`:
1. Render merge proposals: "Merge X into Y? (n + m notes)" with the existing approve/reject handlers; approval applies the tag rename via the existing API path.
2. Render review-queue assignments (low-confidence / rescued-noise notes) as proposals: note title + suggested tag(s) + confidence, approve/reject.
3. Auto-applied merges (>=0.85) shown as an informational list only — no buttons.

## Checkpoint
End-to-end: run tagging, open dashboard, approve one gray-zone merge → tags update in the notes list; reject one review assignment → note stays untagged. Both round-trips verified.

## Commit
`task 21: dashboard approval flow for tag merges and review queue`
Delete this file in the same commit.
