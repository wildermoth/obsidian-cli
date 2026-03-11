use obsidian_cli::frontmatter::{parse_cli_args, run_cli, want_field, FieldKind, Fields};
use ryml::Tree;
use std::borrow::Cow;

#[inline]
fn trim_val(val: &str) -> Option<String> {
    let trimmed = val.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

fn extract_fields_min(yaml_bytes: &[u8], scratch: &mut String) -> Option<Fields> {
    if yaml_bytes.is_empty() || yaml_bytes.iter().all(|b| b.is_ascii_whitespace()) {
        return None;
    }
    match String::from_utf8_lossy(yaml_bytes) {
        Cow::Borrowed(text) => {
            scratch.clear();
            scratch.push_str(text);
        }
        Cow::Owned(text) => {
            *scratch = text;
        }
    }
    let tree = Tree::parse_in_place(scratch).ok()?;
    let root_id = tree.root_id().ok()?;
    if !tree.is_map(root_id).ok()? {
        return None;
    }

    let mut fields = Fields {
        title: None,
        date_created: None,
        date_score: None,
        aliases: Vec::new(),
    };

    let mut aliases_seen = false;
    let mut child = tree.first_child(root_id).ok()?;

    while child != ryml::NONE {
        if tree.has_key(child).ok()? {
            let key = tree.key(child).ok()?;
            let key = key.trim();
            if let Some((field, score)) = want_field(key) {
                match field {
                    FieldKind::Aliases => {
                        if tree.is_seq(child).ok()? {
                            let mut item = tree.first_child(child).ok()?;
                            while item != ryml::NONE {
                                if !tree.is_container(item).ok()? {
                                    if let Ok(val) = tree.val(item) {
                                        if let Some(value) = trim_val(val) {
                                            fields.aliases.push(value);
                                        }
                                    }
                                }
                                item = tree.next_sibling(item).ok()?;
                            }
                        } else if !tree.is_container(child).ok()? {
                            if let Ok(val) = tree.val(child) {
                                if let Some(value) = trim_val(val) {
                                    fields.aliases.push(value);
                                }
                            }
                        }
                        aliases_seen = true;
                    }
                    FieldKind::DateCreated => {
                        let mut should_update = true;
                        if let Some(current_score) = fields.date_score {
                            if score < current_score {
                                should_update = false;
                            }
                        }
                        if should_update && !tree.is_container(child).ok()? {
                            if let Ok(val) = tree.val(child) {
                                if let Some(value) = trim_val(val) {
                                    fields.date_created = Some(value);
                                    fields.date_score = Some(score);
                                }
                            }
                        }
                    }
                    FieldKind::Title => {
                        if fields.title.is_none() && !tree.is_container(child).ok()? {
                            if let Ok(val) = tree.val(child) {
                                if let Some(value) = trim_val(val) {
                                    fields.title = Some(value);
                                }
                            }
                        }
                    }
                }
            }
        }

        child = tree.next_sibling(child).ok()?;

        if fields.title.is_some() && fields.date_score == Some(2) && aliases_seen {
            break;
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

    let mut scratch = String::new();
    run_cli("frontmatter_ryml", &vault_path, options, |yaml_bytes| {
        extract_fields_min(yaml_bytes, &mut scratch)
    });
    let _ = program;
}
