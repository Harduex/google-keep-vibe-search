---
paths:
  - "client/**"
---

# TypeScript/React Conventions

- Format: prettier. Lint: eslint. Run `npm run fix` for both
- React 19 functional components + hooks only
- Components: PascalCase (`NoteCard.tsx`). Hooks: `use` prefix (`useSearch.ts`)
- Tests: vitest + @testing-library/react. Co-locate as `*.test.tsx`
- Named exports preferred over default
