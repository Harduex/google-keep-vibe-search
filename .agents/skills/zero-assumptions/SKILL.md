---
name: zero-assumptions
description: Rigorous requirements interrogation methodology that refuses to proceed with vague specifications. Demands precise constraints before implementation. Applies conditional depth based on scope -- deep interrogation for system design, lightweight for simple changes. Use when scoping complex systems, defining architecture, or when requirements feel incomplete.
---

# Zero Assumptions Methodology

## Core directive

Assumptions are the root cause of systemic failures. Absolute clarity must precede implementation.

Do not provide solutions if the task is vaguely defined, lacks constraints, or misses operational context. Stop and demand precise specifications before proceeding.

## Conditional depth

Assess the scope of the request and apply proportional rigor:

### System-level (architecture, data storage, distributed systems)

Demand explicit answers to:

- **Load parameters**: Expected concurrent users, request rates, data volume
- **Performance targets**: Normal response time, worst-case acceptable latency
- **Data model**: Clarify structural relationships to determine optimal model (relational, document, graph)
- **Distribution strategy**: Replication vs. partitioning requirements
- **Failure modes**: What happens when components fail? What is the acceptable recovery time?

### Feature-level (new capabilities, integrations)

Clarify:

- **Scope boundaries**: What is included vs. explicitly excluded
- **User personas**: Who uses this and in what context
- **Edge cases**: What happens at boundaries, with invalid input, during failures
- **Success criteria**: How will we know this feature works correctly

### Localized (UI components, bug fixes, simple scripts)

Skip system-level interrogation. Proceed directly to problem-solving with clean code principles and appropriate design patterns.

## Architecture methodology

When designing systems:

- **City Planning metaphor**: Treat the architecture as clearly defined zones with strictly governed communication between boundaries.
- **Separation of concerns**: Extreme modularity. Dependency injection. No cyclic dependencies.
- **Swiss Cheese Model**: Multiple redundant layers of error mitigation so isolated failures do not cascade.

## Error management requirements

Mandate these layers:

1. **Sensibility checks**: Validate inputs for logical reasonableness and domain accuracy, not just type safety.
2. **Forcing functions**: Use type systems and architectural barriers to make invalid states unrepresentable.
3. **Checklists and fallbacks**: Systematic fallbacks for complex execution paths. No silent failures.

## Interrogation style

- Ask targeted, analytical questions. Not open-ended brainstorming.
- Persistently clarify until the picture is completely unambiguous.
- Provide 2-3 concrete options when asking for decisions.
- Never proceed with implementation until constraints are locked down.
