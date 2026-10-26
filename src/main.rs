//! Точка входа CLI/TUI.

use std::env;
use std::process::ExitCode;
use std::sync::Arc;

use file_renamer::logging::Logger;
use file_renamer::tui;

const USAGE: &str = "\
file-renamer — переименование дат ДД.ММ.ГГ в именах файлов, папок и ярлыков.

Использование:
  file-renamer            запустить TUI
  file-renamer --help     показать справку
  file-renamer --version  показать версию

Клавиши в TUI:
  ↑/↓       навигация
  Enter     выбрать/применить
  Esc       назад
  d         переключить dry-run
  Ctrl+C    выход
";

fn main() -> ExitCode {
    if let Some(argument) = env::args().nth(1) {
        match argument.as_str() {
            "-h" | "--help" => {
                print!("{USAGE}");
                return ExitCode::SUCCESS;
            }
            "-V" | "--version" => {
                println!("file-renamer {}", file_renamer::VERSION);
                return ExitCode::SUCCESS;
            }
            other => {
                eprintln!("Неизвестный аргумент: {other}\n\n{USAGE}");
                return ExitCode::FAILURE;
            }
        }
    }

    let logger = Arc::new(Logger::from_environment().without_console());
    match tui::run(logger) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("Ошибка TUI: {error}");
            ExitCode::FAILURE
        }
    }
}
