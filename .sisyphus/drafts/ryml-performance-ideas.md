# Draft: ryml Rust Performance Improvement Ideas

## Context Gathered

### What is ryml?
- `ryml` is a Rust crate (v0.3.2) providing bindings to the rapidyaml C++ library
- Used for parsing YAML frontmatter in Obsidian markdown files
- Located in `/home/james/obsidian_cli/src/bin/frontmatter_ryml.rs`

### Current Implementation Analysis

**File: `src/bin/frontmatter_ryml.rs` (101 lines)**
- Uses `ryml::Tree::parse_in_place(&mut yaml)` for parsing
- Converts bytes to owned String first: `String::from_utf8_lossy(yaml_bytes).into_owned()`
- Iterates over tree nodes to extract: title, aliases, date_created
- Heavy use of `.ok()?` error handling (many Result unwraps)

**Key Observations (Potential Bottlenecks):**
1. `String::from_utf8_lossy().into_owned()` - allocates new String for every file
2. `trim_val()` calls `trimmed.to_string()` - allocates on every value extraction
3. Multiple `.ok()?` calls per iteration - error handling overhead
4. No batching or parallelization at parse level

### Comparison Implementations

**frontmatter_fast.rs** - Hand-rolled line-by-line parser (no YAML library)
- Also uses `String::from_utf8_lossy(yaml_bytes)` 
- Direct string splitting, no tree construction
- Likely faster due to no tree overhead

**frontmatter_saphyr.rs** - Uses saphyr crate (pure Rust YAML)
**main.rs** - Uses yaml-rust2 crate

### Existing Benchmarking

**`frontmatter_bench_rust.py`** - Compares all 4 implementations:
- frontmatter_yaml_rust2
- frontmatter_saphyr  
- frontmatter_ryml
- frontmatter_fast

Outputs: `total time: X.XXms` per tool

### Dependencies
```toml
ryml = "0.3.2"
memchr = "2.7"
yaml-rust2 = "0.8"
saphyr = "0.0.6"
```

## Performance Investigation Categories

### 1. Allocation Reduction
- [ ] Avoid `into_owned()` if ryml supports borrowed parsing
- [ ] Reuse String buffer across files
- [ ] Use `Cow<str>` instead of `String` for extracted values
- [ ] Arena allocation for temporary strings

### 2. ryml API Optimization
- [ ] Check if ryml has streaming/SAX-style API (avoid full tree)
- [ ] Check for zero-copy value extraction
- [ ] Investigate `parse_in_place` vs other parse methods
- [ ] Check if ryml supports partial parsing (early exit)

### 3. Algorithm Improvements
- [ ] Early termination when all fields found
- [ ] Skip nodes that can't contain target fields
- [ ] Direct key lookup vs iteration (if ryml supports)

### 4. Parallelization
- [ ] Rayon for parallel file processing
- [ ] Thread pool for parsing

### 5. I/O Optimization
- [ ] Already using chunked reading (FrontmatterReader)
- [ ] Memory-mapped files?
- [ ] Async I/O?

## Open Questions

1. What are current benchmark numbers for ryml vs others?
2. Is the goal to optimize ryml specifically, or find fastest approach overall?
3. Is correctness/compatibility with full YAML spec required?
4. What's the target file count / typical frontmatter size?
5. Is memory usage a constraint, or purely speed?

## Research Needed

- [ ] ryml crate documentation and API
- [ ] rapidyaml C++ performance tips
- [ ] Rust zero-copy parsing patterns
- [ ] SIMD string search opportunities
