---
description: Skip a layer with justification (requires proof of inapplicability)
arguments:
  - name: justification
    description: Justification for skipping
    required: true
---

You are processing a request to skip a layer in the Swiss Cheese verification.

**Justification provided**: {{justification}}

## Skippable Layers

Only certain layers can be skipped:

### Layer 6: Formal Verification (Optional)

**Can skip if**:
- No `unsafe` blocks in codebase: `grep -r "unsafe" src/ | wc -l` = 0
- No safety-critical invariants documented
- Kani/Prusti not available for target platform

**Cannot skip if**:
- Contains `unsafe` code
- Safety-critical requirements exist
- Security-critical functionality

### All Other Layers

Layers 1-5 and 7-9 **cannot be skipped** - they form the core verification chain.

## Decision Process

1. Identify which layer the user wants to skip
2. Verify it's a skippable layer (only formal_verification is optional by default)
3. Validate the justification:

```bash
# Check for unsafe code
grep -r "unsafe" src/ --include="*.rs" | wc -l

# Check requirements for safety-critical flags
grep -i "safety\|critical" design.toml
```

4. Make a decision:

### If APPROVED

The Makefile target for optional layers should handle this:
```bash
# In validate-formal-verification:
# If kani not available, exit 0 (pass)
```

Report:
```
Layer Skip Approved
===================

Layer: formal_verification
Justification: {{justification}}

Validation:
- No unsafe code found: ✓
- Not safety-critical: ✓

Proceeding to next layer (dynamic_analysis).
```

### If DENIED

```
Layer Skip Denied
=================

Layer: <layer_name>
Reason: <why it cannot be skipped>

Required actions:
- <what needs to be done to pass the gate>
```

## Common Justifications

**Valid**:
- "No unsafe code in project" (verify with grep)
- "Kani not available on this platform"
- "Pure library with no safety requirements"

**Invalid**:
- "Takes too long" (not a valid reason)
- "Not needed" (requires proof)
- "Will do later" (defeats the purpose)

## Instructions

1. Determine which layer is being skipped based on context
2. Verify the justification with codebase analysis
3. Approve or deny with clear reasoning
4. If approved, proceed to next layer
5. If denied, explain what's needed
