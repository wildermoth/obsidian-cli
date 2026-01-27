use obsidian_cli::frontmatter::{parse_cli_args, run_cli, want_field, FieldKind, Fields};
use saphyr::{LoadableYamlNode, Yaml};

fn saphyr_value_to_string(value: &Yaml) -> Option<String> {
    if let Some(s) = value.as_str() {
        let trimmed = s.trim();
        if trimmed.is_empty() {
            None
        } else if trimmed.len() == s.len() {
            Some(s.to_string())
        } else {
            Some(trimmed.to_string())
        }
    } else if let Some(i) = value.as_integer() {
        Some(i.to_string())
    } else if let Some(f) = value.as_floating_point() {
        Some(f.to_string())
    } else if let Some(b) = value.as_bool() {
        Some(b.to_string())
    } else {
        None
    }
}

fn extract_fields_min(yaml_bytes: &[u8]) -> Option<Fields> {
    if yaml_bytes.is_empty() || yaml_bytes.iter().all(|b| b.is_ascii_whitespace()) {
        return None;
    }
    let yaml_str = String::from_utf8_lossy(yaml_bytes);
    let mut docs = Yaml::load_from_str(&yaml_str).ok()?;
    let doc = docs.get_mut(0)?;
    doc.parse_representation_recursive();

    let mapping = doc.as_mapping()?;
    let mut fields = Fields {
        title: None,
        date_created: None,
        date_score: None,
        aliases: Vec::new(),
    };

    for (key, val) in mapping {
        let key = match key.as_str() {
            Some(key) => key.trim(),
            None => continue,
        };
        let Some((field, score)) = want_field(key) else {
            continue;
        };

        match field {
            FieldKind::Aliases => {
                if let Some(seq) = val.as_vec() {
                    for item in seq {
                        if let Some(value) = saphyr_value_to_string(item) {
                            fields.aliases.push(value);
                        }
                    }
                } else if let Some(value) = saphyr_value_to_string(val) {
                    fields.aliases.push(value);
                }
            }
            FieldKind::DateCreated => {
                if let Some(current_score) = fields.date_score {
                    if score < current_score {
                        continue;
                    }
                }
                if let Some(value) = saphyr_value_to_string(val) {
                    fields.date_created = Some(value);
                    fields.date_score = Some(score);
                }
            }
            FieldKind::Title => {
                if fields.title.is_none() {
                    if let Some(value) = saphyr_value_to_string(val) {
                        fields.title = Some(value);
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

    run_cli(
        "frontmatter_saphyr",
        &vault_path,
        options,
        extract_fields_min,
    );
    let _ = program;
}
