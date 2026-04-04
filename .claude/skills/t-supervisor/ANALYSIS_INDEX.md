# Supervisor Scope Analysis — Complete Index

**Date:** 2026-04-04  
**Analysis Status:** COMPLETE — 3 new documents created, SKILL.md modifications identified  
**Scope of Work:** Clear boundary between supervisor (timer/orchestration) and tdev (project code)

---

## Overview

This analysis identifies a critical architectural issue in the supervisor's role and provides:
1. **Problem statement** — supervisor conflates timer issues with code issues
2. **Solution design** — clear scope boundary + escalation pattern
3. **Implementation plan** — specific SKILL.md modifications needed
4. **Quick reference** — one-page guide for daily use

---

## Documents Created

### 1. SUPERVISOR_SCOPE_FIX.md (Main Analysis)
**Location:** `.claude/skills/t-supervisor/SUPERVISOR_SCOPE_FIX.md`  
**Purpose:** Complete analysis and solution design  
**Contents:**
- Executive summary of the problem
- Part 1: Clear scope boundary (what supervisor owns vs tdev owns)
- Part 2: Updated Step 4 logic (classify timer vs code issues)
- Part 3: Escalation pattern (how supervisor detects and escalates code issues)
- Part 4: Example incidents (today's gate_unit violation + potential future deadlocks)
- Part 5: Subagent usage rules (when to spawn vs solve directly)
- Part 6: Updated SKILL.md sections (Step 4 check 3m, Step 5e escalation)
- Part 7: Supervisor report updates (classify issues as timer/code/unclear)
- Part 8: Summary of what changes

**Read this first if:** You want the full context and rationale.

---

### 2. SKILL_MODIFICATIONS_REQUIRED.md (Implementation Guide)
**Location:** `.claude/skills/t-supervisor/SKILL_MODIFICATIONS_REQUIRED.md`  
**Purpose:** Specific, line-by-line guidance for modifying SKILL.md  
**Contents:**
- Overall strategy
- Section-by-section review of SKILL.md
- For EACH section: current text, status, and REQUIRED CHANGE (or "no changes needed")
- Implementation order (which changes to make first)
- Testing plan after modifications (4 test scenarios)
- Rollback plan if needed

**Read this if:** You are about to modify SKILL.md and want to know exactly what to change and why.

---

### 3. SCOPE_QUICK_REFERENCE.md (One-Page Guide)
**Location:** `.claude/skills/t-supervisor/SCOPE_QUICK_REFERENCE.md`  
**Purpose:** Quick decision tree for supervisors running daily cycles  
**Contents:**
- One-page decision tree (Timer? or Code?)
- Table: "Supervisor CAN Fix" (timer issues with examples)
- Table: "Supervisor Must Escalate" (code issues with examples)
- Copy-paste ready escalation steps
- Timer issue examples (bad path, deadlock)
- Code issue examples (missing gate marker, uncomm itted changes)
- Subagent use guidelines
- Report template
- One-page flowchart

**Read this before:** Running supervisor cycle — gives you the decision logic in 2 minutes.

---

## Existing Documents (Reference)

### SUPERVISOR_DEADLOCK_FIX.md
**Status:** Already exists (created 2026-04-04)  
**Relevance:** Covers file-based deadlock detection (part of timer issue domain)  
**Use:** Reference for specific deadlock checks (eta_done age, /teta interval, log patterns)

### supervisor_enhancement_recommendations.md
**Status:** Already exists (created 2026-04-04)  
**Relevance:** Detailed deadlock prevention patterns  
**Use:** Reference for implementing deadlock detection in supervisor checks

### superv_cycle_design.md
**Status:** Already exists (core reference)  
**Relevance:** Architecture reference for timer cycle pipeline  
**Use:** Background reading, understand how timer/tdeep/tdev interact

### SKILL.md
**Status:** Needs modifications (not yet updated)  
**Relevance:** The supervisor skill itself  
**Use:** Will be updated per SKILL_MODIFICATIONS_REQUIRED.md guidance

---

## The Problem (Summary)

Today's incident (2026-04-04):
- tdeep found code violation: gate_unit.json not written by train.py
- supervisor detected this but **tried to work around it** (wrote bypass diagnostic, restarted cycle)
- correct approach: supervisor should **detect the violation, escalate to tdev, and exit**
- root cause: supervisor's role was ambiguous — did it own code-fixing authority? No.

Result: Code never actually fixed, cycle repeated, confusion about responsibility boundaries.

---

## The Solution (Summary)

**Clear, strict boundary:**

| Responsibility | Domain | Authority | When to Act |
|---|---|---|---|
| **Supervisor** | Timer/Orchestration | Session health, state management, file cleanup, deadlock resolution | Detects stuck states, classifies as TIMER → fixes directly |
| **tdev** | Project Code | Code logic, .py file changes, gate markers, config, commits | Detects stuck states classified as CODE → implements fixes |

**Key insight:** Supervisor does NOT judge whether code is "correct." Supervisor only detects that code changes are needed and escalates.

---

## How to Use These Documents

### For Understanding the Issue
1. Read **SUPERVISOR_SCOPE_FIX.md** (executive summary + rationale)
2. Read **SCOPE_QUICK_REFERENCE.md** (one-page decision tree)
3. Review **Part 5 (Example Incidents)** in SUPERVISOR_SCOPE_FIX.md

### For Implementing Changes
1. Read **SKILL_MODIFICATIONS_REQUIRED.md** (what changes and why)
2. For each section, compare "Current Text" with "REQUIRED CHANGE"
3. Apply modifications to SKILL.md
4. Run test scenarios (Section: Testing After Modifications)

### For Daily Supervisor Runs (After Implementation)
1. Read **SCOPE_QUICK_REFERENCE.md** (decision tree + copy-paste templates)
2. When stuck state detected: use flowchart to classify TIMER vs CODE
3. Execute either: FIX IT (timer) or ESCALATE IT (code)

---

## Implementation Checklist

- [ ] **Read SUPERVISOR_SCOPE_FIX.md** — understand the problem and solution
- [ ] **Read SKILL_MODIFICATIONS_REQUIRED.md** — identify all needed changes to SKILL.md
- [ ] **Modify SKILL.md Section 4** — add check 3m (Code/Timer classification)
- [ ] **Modify SKILL.md Section 5** — revise intro, add section 5e (escalation pattern)
- [ ] **Modify SKILL.md Section 8** — update report template to classify issues
- [ ] **Test on healthy pipeline** — verify supervisor runs normally with no escalations
- [ ] **Test Code Issue Detection** — create fake violation, verify supervisor escalates
- [ ] **Test Timer Issue Detection** — create stale eta_done, verify supervisor fixes it
- [ ] **Update supervisor_report.md template** — reflect new classification structure
- [ ] **Train supervisors** — share SCOPE_QUICK_REFERENCE.md with anyone running supervisor

---

## Key Takeaways

### For Supervisor
**Your job is to manage TIMER STATE, not fix CODE.**

When you detect a stuck state:
1. Classify: Is this TIMER or CODE?
2. If TIMER → Fix it directly (restart, cleanup, deadlock resolution)
3. If CODE → Escalate: write diagnostic, set next_step=2, exit
4. Let tdev handle code fixes via normal cycle (tconv → tdev → tdeep → launch)

### For tdev (When Supervisor Escalates)
**You receive escalations with full context.**

When supervisor escalates:
1. Read supervisor_diagnostics.md (what supervisor found)
2. Read deep_analysis_results.md (what tdeep found)
3. Read conviction files (what violations mean)
4. Implement code fixes (modify .py files)
5. Commit changes
6. Write launch_commands.json if needed
7. Cycle resumes automatically

### For tconv (Conviction Analysis)
**Your role is unchanged — continue analyzing convictions and violations.**

Supervisor escalation does not affect tconv's work. tconv continues to:
- Analyze convictions
- Find violations
- Assign tasks to tdev
- Propagate violations into rules

---

## Quick Decision Tree (Copy This)

```
Stuck State Detected
    ↓
Read evidence (panes, logs, deep_analysis_results.md)
    ↓
Can I fix this WITHOUT modifying .py files?
    ├─ YES → Timer issue
    │   ├─ Dead session? Restart timer
    │   ├─ Stale files? Delete them
    │   ├─ Deadlock? Delete signal file, restart timer
    │   ├─ Bad path? Find correct path, rewrite JSON
    │   └─ Go to Step 5a-5d in SKILL.md
    │
    └─ NO → Code issue
        ├─ tdeep violations? Requires .py changes
        ├─ Missing gate markers? Requires train.py
        ├─ Uncomm itted changes? Requires tdev commit
        ├─ Config wrong? Requires understanding project
        └─ Go to Step 5e in SKILL.md (escalate)
```

---

## File Locations

All analysis documents:
```
.claude/skills/t-supervisor/
├── SKILL.md                              (skill definition — needs modification)
├── SUPERVISOR_SCOPE_FIX.md               (main analysis — NEW)
├── SKILL_MODIFICATIONS_REQUIRED.md       (implementation guide — NEW)
├── SCOPE_QUICK_REFERENCE.md              (one-page guide — NEW)
├── SUPERVISOR_DEADLOCK_FIX.md            (existing, supports timer issues)
├── supervisor_enhancement_recommendations.md (existing, supports timer issues)
├── superv_cycle_design.md                (existing, architecture reference)
└── ANALYSIS_INDEX.md                     (this file — NEW)
```

---

## Next Steps

### Immediate (Today)
1. ✅ Analysis complete (this document)
2. ✅ SUPERVISOR_SCOPE_FIX.md created with full rationale
3. ✅ SKILL_MODIFICATIONS_REQUIRED.md created with specific changes
4. ✅ SCOPE_QUICK_REFERENCE.md created for daily use

### Short-Term (Next Cycle)
1. Modify SKILL.md per SKILL_MODIFICATIONS_REQUIRED.md guidance
2. Test on healthy pipeline
3. Test Code Issue detection
4. Test Timer Issue detection

### Before Next Supervisor Escalation
1. Train any supervisors on SCOPE_QUICK_REFERENCE.md
2. Have SUPERVISOR_SCOPE_FIX.md available for context
3. Execute escalation per 5e pattern (write diagnostic, set next_step=2, exit)

### For Future Incidents
- If supervisor is unsure about scope: refer to SCOPE_QUICK_REFERENCE.md decision tree
- If supervisor tries to fix code: remember "no .py file modifications" rule
- If escalation fails: check superv_cycle_design.md for state machine details

---

## Questions to Answer Before Implementation

| Question | Answer | Document |
|----------|--------|----------|
| "What's the problem?" | Supervisor conflates timer/code issues, tries to bypass code violations | SUPERVISOR_SCOPE_FIX.md intro |
| "What should supervisor do?" | Detect, classify (timer vs code), fix timer issues, escalate code issues | SCOPE_QUICK_REFERENCE.md |
| "Which SKILL.md sections change?" | Step 4 (add 3m), Step 5 (revise + add 5e), Step 8 (update report template) | SKILL_MODIFICATIONS_REQUIRED.md |
| "What exactly should I change?" | See "REQUIRED CHANGE" in each section of SKILL_MODIFICATIONS_REQUIRED.md | SKILL_MODIFICATIONS_REQUIRED.md |
| "How do I escalate to tdev?" | Write diagnostic, set next_step=2, exit. tdev reads diagnostic + deep_analysis next cycle. | SCOPE_QUICK_REFERENCE.md + SUPERVISOR_SCOPE_FIX.md 5e |
| "What if I'm not sure?" | Default to escalate. Supervisor has no authority over code logic. | SCOPE_QUICK_REFERENCE.md |
| "How do I test this?" | 4 test scenarios in SKILL_MODIFICATIONS_REQUIRED.md | SKILL_MODIFICATIONS_REQUIRED.md |

---

## Document History

| Date | Event | Documents |
|------|-------|-----------|
| 2026-04-04 20:00+ | Problem identified: supervisor tried to bypass code violations | (incident) |
| 2026-04-04 23:00+ | Root cause analysis: supervisor role ambiguous (timer vs code) | (analysis) |
| 2026-04-04 late | Full scope fix analysis with rationale and examples | SUPERVISOR_SCOPE_FIX.md |
| 2026-04-04 late | Implementation-specific guidance for modifying SKILL.md | SKILL_MODIFICATIONS_REQUIRED.md |
| 2026-04-04 late | One-page quick reference for daily supervisor use | SCOPE_QUICK_REFERENCE.md |
| 2026-04-04 late | Index document (this file) | ANALYSIS_INDEX.md |
| TBD | Modify SKILL.md per guidance | (action) |
| TBD | Test modifications | (action) |
| TBD | Deploy and train supervisors | (action) |

---

**Document Status:** ✅ Analysis complete, ready for implementation  
**Blocker:** None — all guidance in place, ready to modify SKILL.md when approved

