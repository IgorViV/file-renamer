//! Точка входа CLI.

use std::io;
use std::process::ExitCode;
use std::sync::Arc;

use file_renamer::logging::Logger;
use file_renamer::menu;

fn main() -> ExitCode {
    let logger = Arc::new(Logger::from_environment());
    let stdin = io::stdin();
    let stdout = io::stdout();

    match menu::run(stdin.lock(), stdout.lock(), logger) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("Ошибка: {error}");
            ExitCode::FAILURE
        }
    }
}
