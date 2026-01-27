use obsidian_cli::frontmatter::{parse_cli_args, run_cli, want_field, FieldKind, Fields};
use yaml_rust2::{Yaml, YamlLoader};

fn yaml_to_string(value: &Yaml) -> Option<String> {
    match value {
        Yaml::String(s) => {
            let trimmed = s.trim();
            if trimmed.is_empty() {
                None
            } else if trimmed.len() == s.len() {
                Some(s.clone())
            } else {
                Some(trimmed.to_string())
            }
        }
        Yaml::Integer(num) => Some(num.to_string()),
        Yaml::Real(s) => {
            let trimmed = s.trim();
            if trimmed.is_empty() {
                None
            } else if trimmed.len() == s.len() {
                Some(s.clone())
            } else {
                Some(trimmed.to_string())
            }
        }
        Yaml::Boolean(b) => Some(b.to_string()),
        _ => None,
    }
}

fn extract_fields_min(yaml_bytes: &[u8]) -> Option<Fields> {
    if yaml_bytes.is_empty() || yaml_bytes.iter().all(|b| b.is_ascii_whitespace()) {
        return None;
    }
    let yaml_str = String::from_utf8_lossy(yaml_bytes);
    let docs = YamlLoader::load_from_str(&yaml_str).ok()?;
    let mapping = match docs.get(0) {
        Some(Yaml::Hash(map)) => map,
        _ => return None,
    };

    let mut fields = Fields {
        title: None,
        date_created: None,
        date_score: None,
        aliases: Vec::new(),
    };

    for (key, val) in mapping {
        let key = match key {
            Yaml::String(s) => s.as_str(),
            _ => continue,
        };
        let key = key.trim();
        let Some((field, score)) = want_field(key) else {
            continue;
        };

        match field {
            FieldKind::Aliases => match val {
                Yaml::Array(seq) => {
                    for item in seq {
                        if let Some(value) = yaml_to_string(item) {
                            fields.aliases.push(value);
                        }
                    }
                }
                _ => {
                    if let Some(value) = yaml_to_string(val) {
                        fields.aliases.push(value);
                    }
                }
            },
            FieldKind::DateCreated => {
                if let Some(current_score) = fields.date_score {
                    if score < current_score {
                        continue;
                    }
                }
                if let Some(value) = yaml_to_string(val) {
                    fields.date_created = Some(value);
                    fields.date_score = Some(score);
                }
            }
            FieldKind::Title => {
                if fields.title.is_none() {
                    if let Some(value) = yaml_to_string(val) {
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
        "frontmatter_yaml_rust2",
        &vault_path,
        options,
        extract_fields_min,
    );
    let _ = program;
}
