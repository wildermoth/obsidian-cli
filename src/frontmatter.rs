use memchr::{memchr, memmem};
use serde::Serialize;
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::Instant;

pub const FRONTMATTER_MAX_BYTES: usize = 64 * 1024;
pub const READ_CHUNK_BYTES: usize = 4 * 1024;

#[derive(Serialize)]
pub struct Note {
    pub filepath: String,
    pub title: String,
    pub date_created: Option<String>,
    pub aliases: Vec<String>,
}

#[derive(Copy, Clone)]
pub enum FieldKind {
    Title,
    Aliases,
    DateCreated,
}

pub struct Fields {
    pub title: Option<String>,
    pub date_created: Option<String>,
    pub date_score: Option<u8>,
    pub aliases: Vec<String>,
}

pub struct CliOptions {
    pub last_n: Option<usize>,
    pub show_count: bool,
}

pub struct FrontmatterReader {
    buffer: Vec<u8>,
    chunk: Vec<u8>,
}

impl FrontmatterReader {
    pub fn new() -> Self {
        Self {
            buffer: Vec::with_capacity(READ_CHUNK_BYTES * 2),
            chunk: vec![0u8; READ_CHUNK_BYTES],
        }
    }

    pub fn read_frontmatter_slice<'a>(&'a mut self, path: &Path) -> Option<&'a [u8]> {
        let mut handle = File::open(path).ok()?;
        self.buffer.clear();
        let mut read = handle.read(&mut self.chunk).ok()?;
        if read == 0 {
            return None;
        }
        self.buffer.extend_from_slice(&self.chunk[..read]);

        let mut newline_idx = memchr(b'\n', &self.buffer);
        while newline_idx.is_none() && self.buffer.len() < FRONTMATTER_MAX_BYTES {
            read = handle.read(&mut self.chunk).ok()?;
            if read == 0 {
                break;
            }
            self.buffer.extend_from_slice(&self.chunk[..read]);
            newline_idx = memchr(b'\n', &self.buffer);
        }
        let newline_idx = newline_idx?;

        let first_line = self.buffer[..newline_idx]
            .strip_suffix(b"\r")
            .unwrap_or(&self.buffer[..newline_idx]);
        if trim_ascii_whitespace(first_line) != b"---" {
            return None;
        }

        let start = newline_idx + 1;
        let mut search_from = start;
        let mut end_idx = find_frontmatter_end(&self.buffer, search_from);
        while end_idx.is_none() && self.buffer.len() < FRONTMATTER_MAX_BYTES {
            read = handle.read(&mut self.chunk).ok()?;
            if read == 0 {
                break;
            }
            let old_len = self.buffer.len();
            self.buffer.extend_from_slice(&self.chunk[..read]);
            search_from = old_len.saturating_sub(4).max(start);
            end_idx = find_frontmatter_end(&self.buffer, search_from);
        }
        let end_idx = end_idx?;
        Some(&self.buffer[start..end_idx])
    }
}

pub fn want_field(key: &str) -> Option<(FieldKind, u8)> {
    match key {
        "title" => Some((FieldKind::Title, 2)),
        "aliases" => Some((FieldKind::Aliases, 2)),
        "alias" => Some((FieldKind::Aliases, 1)),
        "date created" => Some((FieldKind::DateCreated, 2)),
        "date_created" => Some((FieldKind::DateCreated, 2)),
        "created" => Some((FieldKind::DateCreated, 1)),
        "date" => Some((FieldKind::DateCreated, 0)),
        _ => None,
    }
}

pub fn trim_ascii_whitespace(bytes: &[u8]) -> &[u8] {
    let mut start = 0;
    let mut end = bytes.len();
    while start < end && bytes[start].is_ascii_whitespace() {
        start += 1;
    }
    while end > start && bytes[end - 1].is_ascii_whitespace() {
        end -= 1;
    }
    &bytes[start..end]
}

pub fn find_frontmatter_end(buffer: &[u8], start: usize) -> Option<usize> {
    let mut idx = memmem::find(&buffer[start..], b"\n---").map(|pos| pos + start);
    while let Some(pos) = idx {
        let mut cursor = pos + 4;
        while cursor < buffer.len() && (buffer[cursor] == b' ' || buffer[cursor] == b'\t') {
            cursor += 1;
        }
        if cursor >= buffer.len() {
            return Some(pos);
        }
        if buffer[cursor] == b'\n' {
            return Some(pos);
        }
        if buffer[cursor] == b'\r' {
            if cursor + 1 >= buffer.len() || buffer[cursor + 1] == b'\n' {
                return Some(pos);
            }
        }
        idx = memmem::find(&buffer[pos + 1..], b"\n---").map(|p| p + pos + 1);
    }
    None
}

pub fn iter_markdown_files(root: &Path) -> Vec<PathBuf> {
    let mut stack = vec![root.to_path_buf()];
    let mut out = Vec::new();
    while let Some(current) = stack.pop() {
        let entries = match fs::read_dir(&current) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries {
            let entry = match entry {
                Ok(entry) => entry,
                Err(_) => continue,
            };
            let file_type = match entry.file_type() {
                Ok(file_type) => file_type,
                Err(_) => continue,
            };
            if file_type.is_symlink() {
                continue;
            }
            let path = entry.path();
            if file_type.is_dir() {
                stack.push(path);
            } else if file_type.is_file() {
                if path.extension().map(|ext| ext == "md").unwrap_or(false) {
                    out.push(path);
                }
            }
        }
    }
    out
}

pub fn expand_tilde(path: &str) -> PathBuf {
    if path == "~" {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home);
        }
    }
    if let Some(stripped) = path.strip_prefix("~/") {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home).join(stripped);
        }
    }
    PathBuf::from(path)
}

pub fn collect_frontmatter<F>(vault_path: &Path, mut parser: F) -> Vec<Note>
where
    F: FnMut(&[u8]) -> Option<Fields>,
{
    let paths = iter_markdown_files(vault_path);
    let mut notes = Vec::with_capacity(paths.len());
    let mut reader = FrontmatterReader::new();
    for path in paths {
        let yaml_bytes = match reader.read_frontmatter_slice(&path) {
            Some(bytes) => bytes,
            None => continue,
        };
        let fields = match parser(yaml_bytes) {
            Some(fields) => fields,
            None => continue,
        };

        let title = fields.title.unwrap_or_else(|| {
            path.file_stem()
                .and_then(|stem| stem.to_str())
                .unwrap_or("")
                .to_string()
        });

        notes.push(Note {
            filepath: path.to_string_lossy().into_owned(),
            title,
            aliases: fields.aliases,
            date_created: fields.date_created,
        });
    }
    notes
}

pub fn parse_cli_args() -> Result<(PathBuf, CliOptions, String), String> {
    let mut args = std::env::args();
    let program = args.next().unwrap_or_else(|| "frontmatter".to_string());
    let mut vault_path: Option<String> = None;
    let mut last_n: Option<usize> = None;
    let mut show_count = false;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "-n" | "--last-n" => {
                let value = args
                    .next()
                    .ok_or_else(|| format!("Usage: {program} <vault_path> [-n N] [-c]"))?;
                let parsed = value
                    .parse::<usize>()
                    .map_err(|_| format!("Usage: {program} <vault_path> [-n N] [-c]"))?;
                last_n = Some(parsed);
            }
            "-c" | "--count" => {
                show_count = true;
            }
            _ => {
                if vault_path.is_none() {
                    vault_path = Some(arg);
                }
            }
        }
    }

    let vault_path =
        vault_path.ok_or_else(|| format!("Usage: {program} <vault_path> [-n N] [-c]"))?;

    Ok((
        expand_tilde(&vault_path),
        CliOptions { last_n, show_count },
        program,
    ))
}

pub fn run_cli<F>(name: &str, vault_path: &Path, options: CliOptions, parser: F)
where
    F: FnMut(&[u8]) -> Option<Fields>,
{
    let start = Instant::now();
    let notes = collect_frontmatter(vault_path, parser);
    let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;

    println!("{name}");
    println!("total time: {elapsed_ms:.2}ms");
    if options.show_count {
        println!("count: {}", notes.len());
    }
    if let Some(last_n) = options.last_n {
        let start = notes.len().saturating_sub(last_n);
        let preview = &notes[start..];
        println!("last {last_n} results:");
        match serde_json::to_string_pretty(preview) {
            Ok(json) => println!("{json}"),
            Err(_) => println!("[]"),
        }
    }
}
