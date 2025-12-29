#!/usr/bin/env bash
set -euo pipefail

show_stats=0
fast_stats=0
show_titles=1
vault=""
for arg in "$@"; do
  case "$arg" in
    --no-fzf|--stats)
      show_stats=1
      ;;
    --fast)
      fast_stats=1
      ;;
    --title|--titles)
      show_titles=1
      ;;
    --no-title)
      show_titles=0
      ;;
    *)
      if [[ -z "$vault" ]]; then
        vault="$arg"
      fi
      ;;
  esac
done

if [[ -z "$vault" ]]; then
  echo "Usage: tagfzf.sh [--no-fzf|--stats] [--fast] [--title|--no-title] /path/to/vault"
  exit 1
fi
if [[ ! -d "$vault" ]]; then
  echo "Error: '$vault' does not exist"
  exit 1
fi
if ! command -v rg >/dev/null 2>&1; then
  echo "Error: rg (ripgrep) not found in PATH"
  exit 1
fi
if ! command -v fzf >/dev/null 2>&1; then
  if [[ "$show_stats" -eq 0 ]]; then
    echo "Error: fzf not found in PATH"
    exit 1
  fi
fi

pattern='(?:^|[[:space:](\[\{<"'"'"'])#[A-Za-z0-9/_-]+'

preview_cmd='sed -n {2}p {1} 2>/dev/null'
if command -v bat >/dev/null 2>&1; then
  preview_cmd='bat --style=plain --color=always --highlight-line {2} {1} 2>/dev/null'
fi

if [[ "$show_stats" -eq 1 ]]; then
  tmp_matches="$(mktemp)"
  tmp_counts="$(mktemp)"
  trap 'rm -f "$tmp_matches" "$tmp_counts"' EXIT

  if [[ "$fast_stats" -eq 1 ]]; then
    rg_stats="$(mktemp)"
    trap 'rm -f "$tmp_matches" "$tmp_counts" "$rg_stats"' EXIT

    start_ns="$(date +%s%N)"
    rg --stats --no-heading --no-filename --color=never -g '*.md' -o "$pattern" "$vault" 2>&1 \
      | awk -v stats="$rg_stats" '
          /seconds spent searching/ { rg_ms=$1*1000; next }
          /files searched$/ { next }
          /bytes printed$/ { next }
          /bytes searched$/ { next }
          /^[0-9.]+ seconds$/ { next }
          { print }
          END { if (rg_ms!="") printf "%.0f\n", rg_ms > stats }
        ' \
      | sed -E 's/^[^#]*#/#/; s/[.,;:!?)]}"]+$//' \
      | LC_ALL=C sort \
      | uniq -c \
      | LC_ALL=C sort -nr > "$tmp_counts"
    end_ns="$(date +%s%N)"

    rg_time_ms="$(awk 'NR==1 {print $1}' "$rg_stats")"
    total_occ="$(awk '{s+=$1} END{print s+0}' "$tmp_counts")"
    unique_tags="$(wc -l < "$tmp_counts" | tr -d ' ')"
    notes_with_tags="NA"
    total_notes="NA"
  else
    start_ns="$(date +%s%N)"
    rg --line-number --no-heading --color=never -g '*.md' -o "$pattern" "$vault" > "$tmp_matches"
    stats_line="$(
      awk -F: '
        {
          tag=$NF
          gsub(/^[^#]*#/, "#", tag)
          gsub(/[.,;:!?)]}"]+$/, "", tag)
          if (tag !~ /^#/) next
          path=$1
          for (i=2; i<=NF-2; i++) path=path ":" $i
          count[tag]++
          total++
          notes[path]=1
          key=tag SUBSEP path
          if (!(key in seen)) { seen[key]=1; note_count[tag]++ }
        }
        END{
          for (t in count) print count[t], note_count[t], t > counts
          for (p in notes) notes_with_tags++
          for (t in count) unique_tags++
          printf "%d %d %d %d\n", total, notes_with_tags, unique_tags, 0
        }
      ' counts="$tmp_counts" "$tmp_matches"
    )"
    end_ns="$(date +%s%N)"
    read -r total_occ notes_with_tags unique_tags _ <<< "$stats_line"
    total_notes="$(rg --files -g '*.md' "$vault" | wc -l | tr -d ' ')"
  fi
  parse_ms="$(( (end_ns - start_ns) / 1000000 ))"

  echo
  echo "======================================================================"
  echo "OBSIDIAN VAULT HASHTAG STATS"
  echo "======================================================================"
  echo "Total notes: $total_notes"
  echo "Notes with hashtags: $notes_with_tags"
  echo "Unique hashtags: $unique_tags"
  echo "Total hashtag occurrences: $total_occ"
  if [[ -n "${rg_time_ms:-}" ]]; then
    echo "RG search time: ${rg_time_ms}ms"
  fi
  echo "Parse time: ${parse_ms}ms"
  echo "======================================================================"
  echo

  echo "Top 10 hashtags:"
  echo
  printf "%-30s %-10s %s\n" "Hashtag" "Count" "% of Notes"
  printf "%-30s %-10s %s\n" "------------------------------" "----------" "---------"

  if [[ "$fast_stats" -eq 1 ]]; then
    sort -nr "$tmp_counts" | head -n 10 | while read -r count tag; do
      printf "%-30s %-10s %s\n" "$tag" "$count" "NA"
    done
  else
    sort -nr "$tmp_counts" | head -n 10 | while read -r count note_count tag; do
      if [[ "$total_notes" -gt 0 ]]; then
        percent=$(awk -v n="$note_count" -v t="$total_notes" 'BEGIN{printf "%.1f%%", (n/t)*100}')
      else
        percent="0.0%"
      fi
      printf "%-30s %-10s %s\n" "$tag" "$count" "$percent"
    done
  fi
  exit 0
fi

if [[ "$show_titles" -eq 1 ]]; then
  tmp_titles="$(mktemp)"
  trap 'rm -f "$tmp_titles"' EXIT

  rg --files -g '*.md' "$vault" \
    | awk '
      function basename(path, n, a) { n=split(path,a,"/"); return a[n] }
      function get_title(file, line, in_frontmatter, t, line_no) {
        line_no=0
        while ((getline line < file) > 0) {
          line_no++
          if (line_no==1 && line != "---") { break }
          if (line == "---") { if (in_frontmatter) break; in_frontmatter=1; continue }
          if (in_frontmatter && line ~ /^title:[[:space:]]*/) {
            sub(/^title:[[:space:]]*/, "", line)
            t=line
            break
          }
        }
        close(file)
        return t
      }
      {
        t=get_title($0)
        gsub(/\t/, " ", t)
        gsub(/\r/, "", t)
        if (t=="") t=basename($0)
        print $0 "\t" t
      }
    ' > "$tmp_titles"

  if command -v bat >/dev/null 2>&1; then
    preview_cmd='bat --style=plain --color=always --highlight-line {4} {3} 2>/dev/null'
  else
    preview_cmd='sed -n {4}p {3} 2>/dev/null'
  fi

  selection="$(
    rg --column --line-number --no-heading --color=never -g '*.md' -o "$pattern" "$vault" \
      | awk -v OFS='\t' '
          FNR==NR {
            split($0, a, "\t")
            title[a[1]] = a[2]
            next
          }
          {
            n = split($0, parts, ":")
            if (n < 4) next
            m = parts[n]
            cnum = parts[n-1]
            lnum = parts[n-2]
            file = parts[1]
            for (i=2; i<=n-3; i++) file = file ":" parts[i]
            gsub(/^[[:space:]]+/, "", m)
            t = title[file]
            if (t == "") t = file
            print t, m, file, lnum, cnum
          }
        ' "$tmp_titles" - \
      | fzf --delimiter=$'\t' --with-nth=1,2 --preview "$preview_cmd"
  )"
else
  selection="$(
    rg --column --line-number --no-heading --color=never -g '*.md' -o "$pattern" "$vault" \
      | fzf --delimiter ':' --with-nth=1,4.. --preview "$preview_cmd"
  )"
fi

if [[ -z "$selection" ]]; then
  exit 0
fi

if [[ "$show_titles" -eq 1 ]]; then
  IFS=$'\t' read -r _ _ file line col <<< "$selection"
else
  file="${selection%%:*}"
  rest="${selection#*:}"
  line="${rest%%:*}"
  rest="${rest#*:}"
  col="${rest%%:*}"
fi

if [[ -z "$file" || -z "$line" || -z "$col" ]]; then
  exit 0
fi

if command -v nvim >/dev/null 2>&1; then
  nvim +"call cursor($line,$col)" "$file"
else
  "${EDITOR:-vim}" +"call cursor($line,$col)" "$file"
fi
