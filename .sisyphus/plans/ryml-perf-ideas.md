# Plan: Generate Performance Improvement Ideas for ryml Rust Parsing

## Context

### Original Request
Produce a precise plan to generate performance improvement ideas for ryml Rust parsing (no implementation yet). Expected outcome: step-by-step plan with required info, success criteria, and test plan template; include recommended category+skills delegation for follow-up implementation.

### Interview Summary
**Key Discussions**:
- This is a RESEARCH task, not an implementation task
- Focus on ryml Rust crate specifically (not Python bindings, not alternative parsers)
- Goal: identify speed improvements without quality/correctness loss
- User has existing benchmark infrastructure (`frontmatter_bench_rust.py`)

**Research Findings**:
- ryml 0.3.2 is Rust FFI bindings to rapidyaml C++ library
- Current implementation: `src/bin/frontmatter_ryml.rs` (101 lines)
- Key API: `Tree::parse_in_place(&mut yaml)` 
- Identified potential bottlenecks: String allocation, error handling overhead, no early termination
- Comparison parsers exist: yaml-rust2, saphyr, frontmatter_fast (hand-rolled)

### Gap Analysis
**Guardrails Applied**:
- Plan produces IDEAS only, no code
- Correctness must be preserved (no shortcuts that break YAML spec compliance)
- Scope limited to ryml Rust optimization (not switching libraries)
- Include "no improvement found" as valid outcome

---

## Work Objectives

### Core Objective
Research and document actionable performance improvement ideas for the ryml Rust YAML parser, validated against existing benchmarks.

### Concrete Deliverables
1. `PERFORMANCE_IDEAS.md` - Documented list of improvement opportunities with rationale
2. Baseline benchmark numbers (before any changes)
3. Estimated impact ranking for each idea
4. Implementation recommendation per idea

### Definition of Done
- [ ] At least 5 distinct improvement ideas documented
- [ ] Each idea has: description, rationale, expected impact (high/medium/low), implementation complexity
- [ ] Baseline benchmark captured with `frontmatter_bench_rust.py`
- [ ] Ideas are actionable (specific code locations or API changes identified)
- [ ] No idea compromises parsing correctness

### Must Have
- Baseline performance measurement before ideation
- Research into ryml crate API documentation
- Analysis of current implementation bottlenecks
- Impact estimation methodology

### Must NOT Have (Guardrails)
- NO actual code implementation
- NO switching away from ryml to alternative parsers
- NO ideas that sacrifice correctness for speed
- NO scope creep into Python implementation or other binaries

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (`frontmatter_bench_rust.py`)
- **User wants tests**: N/A (research task, not implementation)
- **QA approach**: Manual verification of research completeness

### Verification Approach
Each TODO is verified by examining output artifacts (documentation, benchmark results).

---

## Task Flow

```
TODO 1 (baseline) 
    ↓
TODO 2 (code analysis) ←→ TODO 3 (API research) [parallel]
    ↓
TODO 4 (bottleneck identification)
    ↓
TODO 5 (idea generation)
    ↓
TODO 6 (impact ranking)
    ↓
TODO 7 (documentation)
```

## Parallelization

| Group | Tasks | Reason |
|-------|-------|--------|
| A | 2, 3 | Independent research activities |

| Task | Depends On | Reason |
|------|------------|--------|
| 4 | 2, 3 | Needs code analysis + API knowledge |
| 5 | 4 | Ideas based on identified bottlenecks |
| 6 | 5 | Ranking requires complete idea list |
| 7 | 6 | Documentation needs final ranking |

---

## TODOs

- [ ] 1. Capture Baseline Benchmark

  **What to do**:
  - Run existing benchmark script against a representative vault
  - Record ryml performance numbers (time in ms)
  - Record comparison numbers for context (yaml-rust2, saphyr, frontmatter_fast)
  - Run multiple times (3-5) to get stable measurements
  - Document hardware/environment for reproducibility

  **Must NOT do**:
  - Modify any code
  - Optimize prematurely

  **Parallelizable**: NO (must complete first)

  **References**:
  - `frontmatter_bench_rust.py:27-33` - run_tool function showing benchmark execution
  - `frontmatter_bench_rust.py:36-44` - parse_metrics for extracting timing data

  **Acceptance Criteria**:
  - [ ] Benchmark run successfully on representative vault (500+ markdown files)
  - [ ] ryml timing recorded: `____ ms` (fill in actual number)
  - [ ] Results saved to `BASELINE.md` with timestamp and environment info
  - [ ] Command: `python3 frontmatter_bench_rust.py /path/to/vault -c` produces output

  **Commit**: NO (research artifact only)

---

- [ ] 2. Analyze Current ryml Implementation

  **What to do**:
  - Read `src/bin/frontmatter_ryml.rs` line-by-line
  - Identify all allocation points (String::new, to_string, into_owned, Vec::push)
  - Identify all error handling overhead (.ok()?, Result unwraps)
  - Identify iteration patterns and potential early-exit opportunities
  - Map hot path: bytes input → Fields output
  - Note any redundant operations

  **Must NOT do**:
  - Make code changes
  - Profile with external tools (that's implementation phase)

  **Parallelizable**: YES (with TODO 3)

  **References**:
  - `src/bin/frontmatter_ryml.rs:1-101` - Full implementation to analyze
  - `src/bin/frontmatter_ryml.rs:17` - `String::from_utf8_lossy(yaml_bytes).into_owned()` - allocation point
  - `src/bin/frontmatter_ryml.rs:9` - `trimmed.to_string()` - allocation in trim_val
  - `src/bin/frontmatter_ryml.rs:31-84` - main iteration loop with multiple .ok()? calls

  **Acceptance Criteria**:
  - [ ] List of all allocation points documented
  - [ ] List of all .ok()? / error handling sites documented
  - [ ] Hot path diagram created (text-based)
  - [ ] At least 3 potential inefficiencies identified

  **Commit**: NO (research artifact only)

---

- [ ] 3. Research ryml Crate API and Optimization Features

  **What to do**:
  - Read ryml crate documentation (docs.rs/ryml)
  - Check if zero-copy parsing is supported
  - Check for alternative parse methods (parse vs parse_in_place vs parse_in_arena)
  - Check for direct key lookup (vs iteration)
  - Check if borrowed references can be returned (avoiding .to_string())
  - Review rapidyaml C++ documentation for optimization tips
  - Search GitHub issues/discussions for performance advice

  **Must NOT do**:
  - Write experimental code
  - Benchmark alternative APIs (that's implementation phase)

  **Parallelizable**: YES (with TODO 2)

  **References**:
  - External: `https://docs.rs/ryml/0.3.2/ryml/` - Rust crate documentation
  - External: `https://github.com/biojppm/rapidyaml` - C++ library with perf docs
  - `Cargo.toml:12` - `ryml = "0.3.2"` - current version constraint

  **Acceptance Criteria**:
  - [ ] Document all parse methods available in ryml 0.3.2
  - [ ] Document whether zero-copy is possible
  - [ ] Document whether direct key lookup exists
  - [ ] At least 2 API-based optimization opportunities identified

  **Commit**: NO (research artifact only)

---

- [ ] 4. Identify and Categorize Bottlenecks

  **What to do**:
  - Synthesize findings from TODO 2 (code analysis) and TODO 3 (API research)
  - Categorize bottlenecks: Allocation, I/O, Algorithm, API misuse, Parallelization
  - For each bottleneck, estimate: frequency (per-file, per-field, once), impact (high/med/low)
  - Identify which bottlenecks are addressable within ryml vs require library changes

  **Must NOT do**:
  - Start implementing fixes
  - Use profiling tools

  **Parallelizable**: NO (depends on 2 and 3)

  **References**:
  - Output from TODO 2 (code analysis notes)
  - Output from TODO 3 (API research notes)

  **Acceptance Criteria**:
  - [ ] Bottleneck table created with columns: Location, Category, Frequency, Estimated Impact, Addressable?
  - [ ] At least 5 distinct bottlenecks identified
  - [ ] Each bottleneck has clear location reference (file:line or concept)

  **Commit**: NO (research artifact only)

---

- [ ] 5. Generate Performance Improvement Ideas

  **What to do**:
  - For each bottleneck from TODO 4, brainstorm 1-3 improvement approaches
  - Consider: API changes, algorithm changes, memory layout, parallelization, caching
  - For each idea, note: what it changes, why it helps, risks/tradeoffs
  - Include "do nothing" as valid option if cost outweighs benefit
  - Cross-reference with Rust performance best practices

  **Candidate Improvement Categories** (from initial analysis):
  1. **Allocation Reduction**: Reuse buffers, use Cow<str>, arena allocation
  2. **Error Handling**: Batch .ok()? calls, use unchecked variants if safe
  3. **Early Termination**: Exit when all fields found
  4. **Direct Lookup**: Use ryml key lookup instead of iteration (if available)
  5. **Parallelization**: Rayon for multi-file processing
  6. **Zero-Copy**: Avoid String conversion if ryml supports &[u8] input

  **Must NOT do**:
  - Implement any ideas
  - Benchmark ideas (that's follow-up work)

  **Parallelizable**: NO (depends on 4)

  **References**:
  - Output from TODO 4 (bottleneck table)
  - `src/bin/frontmatter_fast.rs` - Reference for hand-optimized approach patterns

  **Acceptance Criteria**:
  - [ ] At least 5 distinct improvement ideas documented
  - [ ] Each idea has: name, description, target bottleneck, expected benefit, complexity
  - [ ] Ideas do not compromise correctness

  **Commit**: NO (research artifact only)

---

- [ ] 6. Rank Ideas by Impact and Feasibility

  **What to do**:
  - Create 2x2 matrix: Impact (high/low) x Effort (high/low)
  - Place each idea in appropriate quadrant
  - Recommend implementation order: Quick Wins (high impact, low effort) first
  - Note any ideas that should be combined vs done separately
  - Identify ideas that require ryml upstream changes vs local-only

  **Must NOT do**:
  - Start implementation
  - Make final decisions (user will decide)

  **Parallelizable**: NO (depends on 5)

  **References**:
  - Output from TODO 5 (idea list)

  **Acceptance Criteria**:
  - [ ] Impact/Effort matrix completed
  - [ ] Priority order 1-N assigned
  - [ ] "Quick wins" clearly marked
  - [ ] Upstream vs local distinction noted

  **Commit**: NO (research artifact only)

---

- [ ] 7. Document Final Performance Ideas Report

  **What to do**:
  - Create `PERFORMANCE_IDEAS.md` in project root
  - Structure: Executive Summary, Baseline, Bottlenecks, Ideas (ranked), Recommendations, Next Steps
  - Include baseline numbers from TODO 1
  - Include implementation delegation recommendations (see below)
  - Make document actionable for follow-up implementation session

  **Document Structure**:
  ```markdown
  # ryml Rust Performance Improvement Ideas
  
  ## Executive Summary
  [1-2 paragraphs: key findings and top 3 recommendations]
  
  ## Baseline Performance
  [Numbers from TODO 1]
  
  ## Identified Bottlenecks
  [Table from TODO 4]
  
  ## Improvement Ideas (Ranked)
  [From TODO 5 + TODO 6]
  
  ## Implementation Recommendations
  [Delegation guidance below]
  
  ## Test Plan Template
  [See below]
  ```

  **Must NOT do**:
  - Include actual code implementations
  - Make changes beyond documentation

  **Parallelizable**: NO (final step)

  **References**:
  - All previous TODO outputs
  - `src/bin/frontmatter_ryml.rs` - For specific line references in recommendations

  **Acceptance Criteria**:
  - [ ] `PERFORMANCE_IDEAS.md` created and complete
  - [ ] All sections populated
  - [ ] Delegation recommendations included
  - [ ] Test plan template included
  - [ ] Document is self-contained (reader doesn't need this plan)

  **Commit**: YES
  - Message: `docs: add ryml performance improvement ideas`
  - Files: `PERFORMANCE_IDEAS.md`
  - Pre-commit: None (documentation only)

---

## Implementation Delegation Recommendations

When follow-up implementation begins, delegate tasks as follows:

| Idea Category | Agent/Skill | Rationale |
|---------------|-------------|-----------|
| Allocation reduction (Cow, arena) | `general` agent with Rust expertise | Requires careful memory management |
| API changes (zero-copy, direct lookup) | `librarian` (research) then `general` (implement) | Needs crate API verification |
| Early termination logic | `sisyphus-junior` | Straightforward algorithm change |
| Rayon parallelization | `general` agent | Requires understanding of thread safety |
| Benchmark validation | `sisyphus-junior` | Mechanical verification |

**Recommended Skills for Implementation**:
- None specific required (standard Rust tooling)
- Consider loading git-master skill for atomic commits

**Implementation Session Setup**:
```
/start-work with plan: "implement-ryml-perf-{idea-name}"
```

---

## Test Plan Template

For each implemented improvement, use this validation template:

### Pre-Implementation
```bash
# Capture baseline (run 5 times, take median)
for i in {1..5}; do
  python3 frontmatter_bench_rust.py /path/to/vault -c 2>/dev/null | grep ryml
done
```

### Post-Implementation
```bash
# Same benchmark, compare to baseline
for i in {1..5}; do
  python3 frontmatter_bench_rust.py /path/to/vault -c 2>/dev/null | grep ryml
done
```

### Correctness Verification
```bash
# Compare output between old and new implementation
# (Requires saving baseline output first)
diff <(./target/release/frontmatter_ryml_old /vault -n 1000) \
     <(./target/release/frontmatter_ryml /vault -n 1000)
```

### Acceptance Threshold
- **Performance**: Improvement must be ≥5% to be worth the complexity
- **Correctness**: Output must be byte-identical to baseline
- **Stability**: Median of 5 runs, not single measurement

---

## Success Criteria

### Verification Commands
```bash
# Check PERFORMANCE_IDEAS.md exists and has content
test -f PERFORMANCE_IDEAS.md && wc -l PERFORMANCE_IDEAS.md
# Expected: file exists, >50 lines

# Verify baseline was captured
grep -q "Baseline Performance" PERFORMANCE_IDEAS.md
# Expected: match found

# Verify ideas are ranked
grep -q "Ranked\|Priority" PERFORMANCE_IDEAS.md
# Expected: match found
```

### Final Checklist
- [ ] Baseline benchmark captured with actual numbers
- [ ] At least 5 improvement ideas documented
- [ ] Each idea has impact/effort assessment
- [ ] No implementation code written
- [ ] Test plan template included
- [ ] Delegation recommendations included
- [ ] Document is actionable for next session
