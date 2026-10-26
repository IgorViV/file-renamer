//! Генератор тестовых данных для проверки file-renamer.

use std::env;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::{SystemTime, UNIX_EPOCH};

use file_renamer::test_data;

const USAGE: &str = "\
Генератор тестовых каталогов, файлов и ярлыков для file-renamer.

Использование:
  create-test-data [--dir DIR] [--depth N] [--seed N] [--yes] [--force] [--no-shortcuts]

  --dir DIR        каталог для данных (по умолчанию temp_dir)
  --depth N        глубина вложенности (по умолчанию 5)
  --seed N         seed генератора
  --yes            не запрашивать подтверждение
  --force          удалить существующий каталог
  --no-shortcuts   не создавать ярлыки (Windows)
";

#[derive(Debug)]
struct Args {
    dir: PathBuf,
    depth: usize,
    seed: Option<u64>,
    yes: bool,
    force: bool,
    no_shortcuts: bool,
    help: bool,
}

impl Default for Args {
    fn default() -> Self {
        Self {
            dir: PathBuf::from("temp_dir"),
            depth: 5,
            seed: None,
            yes: false,
            force: false,
            no_shortcuts: false,
            help: false,
        }
    }
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("Ошибка: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), String> {
    let args = parse_args()?;
    if args.help {
        print!("{USAGE}");
        return Ok(());
    }

    if args.dir.exists() {
        if !args.force {
            return Err(format!(
                "каталог {} уже существует, используйте --force",
                args.dir.display()
            ));
        }
        fs::remove_dir_all(&args.dir).map_err(|error| error.to_string())?;
    }

    if !args.yes {
        print!(
            "Будут созданы тестовые данные в {}. Продолжить? [y/N]: ",
            args.dir.display()
        );
        io::stdout().flush().map_err(|error| error.to_string())?;
        let mut answer = String::new();
        io::stdin()
            .read_line(&mut answer)
            .map_err(|error| error.to_string())?;
        if !matches!(
            answer.trim().to_lowercase().as_str(),
            "y" | "yes" | "д" | "да"
        ) {
            println!("Отменено.");
            return Ok(());
        }
    }

    let seed = args.seed.unwrap_or_else(|| {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos() as u64)
            .unwrap_or(0)
    });

    let created = test_data::generate(&args.dir, args.depth, seed, !args.no_shortcuts)
        .map_err(|error| error.to_string())?;

    println!("Создано {created} объектов в {}", args.dir.display());
    Ok(())
}

fn parse_args() -> Result<Args, String> {
    let mut args = Args::default();
    let mut values = env::args().skip(1);

    while let Some(argument) = values.next() {
        match argument.as_str() {
            "--dir" => {
                args.dir = PathBuf::from(values.next().ok_or("--dir требует значение")?);
            }
            "--depth" => {
                args.depth = values
                    .next()
                    .ok_or("--depth требует значение")?
                    .parse()
                    .map_err(|_| "--depth должен быть числом")?;
            }
            "--seed" => {
                args.seed = Some(
                    values
                        .next()
                        .ok_or("--seed требует значение")?
                        .parse()
                        .map_err(|_| "--seed должен быть числом")?,
                );
            }
            "--yes" => args.yes = true,
            "--force" => args.force = true,
            "--no-shortcuts" => args.no_shortcuts = true,
            "-h" | "--help" => args.help = true,
            other => return Err(format!("неизвестный аргумент: {other}")),
        }
    }

    Ok(args)
}
