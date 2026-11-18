# Product roadmap

Help users find the right notes, get answers they can trace to those notes, and organize or import their collections with confidence. Keep note processing local, preserve search quality in Bulgarian and English, and protect user-applied tags and source data.

Horizons show recommended sequencing. Proposed work is unscheduled. See [implementation plans](plans/PLANS.md) for active tasks and technical follow-ups.

## Now

| ID    | Outcome                                                                        | Status and next decision                                                                                                                                          |
| ----- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-01 | Find better evidence in search and chat with a local Jev-style decision model. | Research spike requested. Establish the current baseline and test local candidates before proposing a product change. [Spike](research/jev-style-search-spike.md) |

## Next

| ID    | Outcome                                                              | Status and next decision                                                                                                                                |
| ----- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-02 | Import and manage sources from the UI, including on a fresh install. | Proposed. Check the existing import API, attachment handling, and migration from `GOOGLE_KEEP_PATH`. [Import UI idea](feature-ideas/imports-ui.md)      |
| RM-03 | Restore citations when reopening a saved chat.                       | Proposed. Confirm the current restore behavior and the saved citation data available to the client. [T34 follow-up](plans/PLANS.md#proposed-follow-ups) |
| RM-04 | Make text search ready sooner on a cold start.                       | Proposed. Measure entity indexing and optional CLIP startup costs before selecting a change. [T40 follow-ups](plans/PLANS.md#proposed-follow-ups)       |

## Later

| ID    | Outcome                                                                          | Status and next decision                                                                                                                                                  |
| ----- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RM-05 | Import Apple Notes, Standard Notes, and plain-text folders.                      | Proposed. Depends on RM-02 for in-app access. Verify available export formats and choose which importer to build first. [Importer ideas](feature-ideas/more-importers.md) |
| RM-06 | Retag a selected subset of notes and optionally replace generated tags.          | Proposed. Define the tag provenance and preview or undo behavior before designing replacement. [Scoped retagging idea](feature-ideas/scoped-retagging-and-replacement.md) |
| RM-07 | Explore related tags and subtopics, with a spatial map as a possible later view. | Proposed. Validate whether related tags help users find more notes before deciding whether a map is warranted. [Tag exploration ideas](feature-ideas/tag-exploration.md)  |

## Delivered

- Tag chips filter the notes list. The tag manager links to the filtered list and previews notes for a tag. [Tag exploration history](feature-ideas/tag-exploration.md)
- Categorization rerun fixes are recorded alongside the separate proposal for scoped retagging. [Rerun fix history](feature-ideas/scoped-retagging-and-replacement.md)
