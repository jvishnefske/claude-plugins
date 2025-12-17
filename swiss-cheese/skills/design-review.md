---
description: Use this skill when the user needs guidance on conducting upfront design reviews for production-grade Rust components, asking requirements questions, or generating design specifications.
---

# Design Review Skill

This skill provides guidance for conducting comprehensive upfront design reviews for production-grade Rust components.

## Purpose

The design review is the FIRST and MOST IMPORTANT step. All questions are asked in a single interaction before any development begins. This prevents:

1. Mid-project scope changes
2. Missed requirements
3. Incorrect safety level assumptions
4. Incompatible technical choices

## Question Categories

### 1. Functional Requirements

Establish WHAT the component does:

- **Purpose**: Single-sentence description
- **Inputs**: All data sources with types, rates, formats
- **Outputs**: All data sinks with types, rates, formats
- **Timing**: Periods, deadlines, latency budgets
- **Interfaces**: Protocols, buses, peripherals

### 2. Safety Requirements

Establish WHY safety matters:

- **Safety Level**: ASIL, SIL, DAL classification
- **Hazards**: What can go wrong (from system FMEA/FTA)
- **Mitigations**: How each hazard is addressed
- **Safe State**: What the component does on failure
- **Fault Detection**: How faults are detected

### 3. Rust Constraints

Establish HOW Rust is used:

- **Environment**: no_std, alloc, std
- **Target**: MCU, architecture, memory constraints
- **Memory Policy**: Static, bounded heap, unlimited
- **Panic Policy**: Forbidden, reset, custom handler
- **Dependencies**: Required crates

### 4. Verification Scope

Establish HOW MUCH verification:

- **Formal Tools**: Kani, Prusti, Creusot availability
- **Coverage Targets**: Line, branch, MC/DC percentages
- **Dynamic Analysis**: Miri, fuzzing, sanitizers
- **Timing Analysis**: WCET requirements
- **Hardware**: HIL testing availability

### 5. Layer Applicability

Establish WHICH layers apply:

- Request skip justifications upfront
- Validate skip criteria before approving
- Document approved skips in design spec

## Output: design.toml

After all questions are answered, generate `design.toml`:

```toml
[project]
name = "component-name"
version = "0.1.0"
description = "Component description"
max_iterations = 5
max_parallel_agents = 4

[[requirements]]
id = "REQ-001"
title = "Functional Requirement"
description = "Detailed description from design review"
priority = "critical"
acceptance_criteria = [
    "Testable criterion 1",
    "Testable criterion 2",
]

[[requirements]]
id = "REQ-002"
title = "Safety Requirement"
description = "Derived from hazard analysis"
priority = "critical"
acceptance_criteria = [
    "Safe state achieved within deadline",
    "Fault detection covers all failure modes",
]

[tasks.parse_requirements]
layer = "requirements"
description = "Formalize requirements from design review"
depends_on = []
requirements = ["REQ-001", "REQ-002"]
```

## Validation

Before proceeding, validate:

- [ ] All questions answered (no TBD in critical fields)
- [ ] Safety level matches verification scope
- [ ] Timing requirements are specific and measurable
- [ ] Hazards have corresponding safety requirements
- [ ] Rust constraints are compatible with requirements
- [ ] Skip requests have valid justifications

## Anti-Patterns

Avoid these design review failures:

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| Incremental questioning | Wastes iterations | Ask ALL questions upfront |
| Assuming defaults | May be wrong | Explicitly confirm each choice |
| Skipping safety questions | Hazards missed | Always ask about hazards |
| Vague timing | WCET undefined | Get specific numbers |
| "We'll figure it out later" | Scope creep | Resolve before starting |
