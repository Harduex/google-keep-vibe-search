# Code Quality Standards

- Write self-documenting code. Use intention-revealing names for variables, functions, and classes.
- Comments only where logic is genuinely non-obvious. Never add comments explaining what changed (`// <- added this`, `// fix applied`).
- Follow DRY: extract duplication only when the pattern is stable and repeated. Three similar lines are better than a premature abstraction.
- Follow SOLID principles. Single responsibility for classes and functions.
- Maintain separation of concerns: UI, business logic, and data access in distinct layers.
- Handle errors explicitly at system boundaries. No swallowed exceptions. Fail noisily with context.
- Validate all external inputs. Parameterize queries. Escape output. Never log secrets.
- All output must be production-ready. No TODOs, no placeholders, no half-finished implementations.
