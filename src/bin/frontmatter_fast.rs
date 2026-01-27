use obsidian_cli::frontmatter::{parse_cli_args, run_cli, want_field, FieldKind, Fields};

fn strip_quotes(value: &str) -> &str {
    let trimmed = value.trim();
    if trimmed.len() >= 2 {
        let bytes = trimmed.as_bytes();
        let first = bytes[0];
        let last = bytes[bytes.len() - 1];
        if (first == b'"' && last == b'"') || (first == b'\'' && last == b'\'') {
            return &trimmed[1..trimmed.len() - 1];
        }
    }
    trimmed
}

fn parse_inline_list(value: &str, out: &mut Vec<String>) {
    let trimmed = value.trim();
    if !trimmed.starts_with('[') || !trimmed.ends_with(']') {
        return;
    }
    let inner = &trimmed[1..trimmed.len() - 1];
    for item in inner.split(',') {
        let item = strip_quotes(item).trim();
        if !item.is_empty() {
            out.push(item.to_string());
        }
    }
}

fn parse_scalar(value: &str) -> Option<String> {
    let value = strip_quotes(value).trim();
    if value.is_empty() {
        None
    } else {
        Some(value.to_string())
    }
}

fn extract_fields_min(yaml_bytes: &[u8]) -> Option<Fields> {
    if yaml_bytes.is_empty() || yaml_bytes.iter().all(|b| b.is_ascii_whitespace()) {
        return None;
    }
    let yaml_str = String::from_utf8_lossy(yaml_bytes);
    let mut fields = Fields {
        title: None,
        date_created: None,
        date_score: None,
        aliases: Vec::new(),
    };
    let mut in_alias_list = false;

    for raw_line in yaml_str.lines() {
        let line = raw_line.trim_end_matches('\r');
        if line.trim().is_empty() {
            continue;
        }
        let trimmed = line.trim_start();
        let indent = line.len() - trimmed.len();

        if indent == 0 {
            in_alias_list = false;
            let Some((key, value)) = line.split_once(':') else {
                continue;
            };
            let key = key.trim();
            let value = value.trim();
            let Some((field, score)) = want_field(key) else {
                continue;
            };

            match field {
                FieldKind::Aliases => {
                    if value.is_empty() {
                        in_alias_list = true;
                        continue;
                    }
                    if value.starts_with('[') {
                        parse_inline_list(value, &mut fields.aliases);
                    } else if let Some(item) = parse_scalar(value) {
                        fields.aliases.push(item);
                    }
                }
                FieldKind::DateCreated => {
                    if let Some(current_score) = fields.date_score {
                        if score < current_score {
                            continue;
                        }
                    }
                    if let Some(value) = parse_scalar(value) {
                        fields.date_created = Some(value);
                        fields.date_score = Some(score);
                    }
                }
                FieldKind::Title => {
                    if fields.title.is_none() {
                        if let Some(value) = parse_scalar(value) {
                            fields.title = Some(value);
                        }
                    }
                }
            }
        } else if in_alias_list && trimmed.starts_with("- ") {
            let item = parse_scalar(&trimmed[2..]);
            if let Some(value) = item {
                fields.aliases.push(value);
            }
        }
    }

    Some(fields)
}

fn main() {
    let (vault_path, options, program) = match parse_cli_args() {
        Ok(values) => values,
        Err(message) => {
            eprintln!("{message}");
            std::process::exit(2);
        }
    };

    run_cli("frontmatter_fast", &vault_path, options, extract_fields_min);
    let _ = program;
}
