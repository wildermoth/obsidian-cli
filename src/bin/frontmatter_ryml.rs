use obsidian_cli::frontmatter::{parse_cli_args, run_cli, want_field, FieldKind, Fields};
use ryml::Tree;

fn trim_val(val: &str) -> Option<String> {
    let trimmed = val.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

fn extract_fields_min(yaml_bytes: &[u8]) -> Option<Fields> {
    if yaml_bytes.is_empty() || yaml_bytes.iter().all(|b| b.is_ascii_whitespace()) {
        return None;
    }
    let mut yaml = String::from_utf8_lossy(yaml_bytes).into_owned();
    let tree = Tree::parse_in_place(&mut yaml).ok()?;
    let root = tree.root_ref().ok()?;
    if !root.is_map().ok()? {
        return None;
    }

    let mut fields = Fields {
        title: None,
        date_created: None,
        date_score: None,
        aliases: Vec::new(),
    };

    for child in root.iter().ok()? {
        if !child.has_key().ok()? {
            continue;
        }
        let key = child.key().ok()?;
        let key = key.trim();
        let Some((field, score)) = want_field(key) else {
            continue;
        };

        match field {
            FieldKind::Aliases => {
                if child.is_seq().ok()? {
                    for item in child.iter().ok()? {
                        if let Ok(val) = item.val() {
                            if let Some(value) = trim_val(val) {
                                fields.aliases.push(value);
                            }
                        }
                    }
                } else if child.has_val().ok()? {
                    if let Ok(val) = child.val() {
                        if let Some(value) = trim_val(val) {
                            fields.aliases.push(value);
                        }
                    }
                }
            }
            FieldKind::DateCreated => {
                if let Some(current_score) = fields.date_score {
                    if score < current_score {
                        continue;
                    }
                }
                if child.has_val().ok()? {
                    if let Ok(val) = child.val() {
                        if let Some(value) = trim_val(val) {
                            fields.date_created = Some(value);
                            fields.date_score = Some(score);
                        }
                    }
                }
            }
            FieldKind::Title => {
                if fields.title.is_none() && child.has_val().ok()? {
                    if let Ok(val) = child.val() {
                        if let Some(value) = trim_val(val) {
                            fields.title = Some(value);
                        }
                    }
                }
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

    run_cli("frontmatter_ryml", &vault_path, options, extract_fields_min);
    let _ = program;
}
