//! Консольное меню.

use std::io::{BufRead, Write};
use std::sync::Arc;

use crate::error::Result;
use crate::logging::{default_logs_directory, Logger};
use crate::renamer::{FileRenamer, PlanItem};

/// Запускает меню на заданных потоках ввода-вывода.
///
/// # Errors
///
/// Возвращает ошибку ввода-вывода.
pub fn run<R: BufRead, W: Write>(mut input: R, mut output: W, logger: Arc<Logger>) -> Result<()> {
    let mut menu = Menu {
        input: &mut input,
        output: &mut output,
        logger,
    };
    menu.run()
}

struct Menu<'a, R: BufRead, W: Write> {
    input: &'a mut R,
    output: &'a mut W,
    logger: Arc<Logger>,
}

impl<R: BufRead, W: Write> Menu<'_, R, W> {
    fn run(&mut self) -> Result<()> {
        loop {
            writeln!(self.output)?;
            writeln!(self.output, "=== Утилита для переименования файлов ===")?;
            writeln!(self.output, "1. Переименование файлов и папок")?;
            writeln!(self.output, "2. Переименование ссылок в ярлыках")?;
            writeln!(self.output, "3. Справка")?;
            writeln!(self.output, "4. Выход")?;
            self.output.flush()?;

            let Some(choice) = self.prompt("\nВыберите действие (1-4): ")? else {
                break;
            };

            match choice.as_str() {
                "1" => {
                    if self.rename_flow()?.is_none() {
                        break;
                    }
                }
                "2" => {
                    if self.shortcut_flow()?.is_none() {
                        break;
                    }
                }
                "3" => {
                    self.help()?;
                    if self.pause()?.is_none() {
                        break;
                    }
                }
                "4" => {
                    writeln!(self.output, "\nПока!")?;
                    break;
                }
                _ => {
                    writeln!(self.output, "неверный выбор!")?;
                    if self.pause()?.is_none() {
                        break;
                    }
                }
            }
        }

        Ok(())
    }

    fn rename_flow(&mut self) -> Result<Option<()>> {
        writeln!(self.output, "\nПереименование файлов и папок")?;
        let Some(path) = self.prompt("Введите путь к каталогу: ")? else {
            return Ok(None);
        };
        if path.is_empty() {
            writeln!(self.output, "Путь не указан.")?;
            return self.pause();
        }

        let renamer = FileRenamer::with_logger(&path, Arc::clone(&self.logger));
        if let Err(error) = renamer.validate_directory() {
            writeln!(self.output, "{error}")?;
            return self.pause();
        }

        writeln!(
            self.output,
            "В каталоге {} выполняем поиск файлов и папок с префиксом-датой \
             в формате ДД.ММ.ГГ ...",
            renamer.directory().display()
        )?;

        let Some(dry_run) =
            self.ask_yes("Только показать план без изменений (dry-run)? [y/N]: ")?
        else {
            return Ok(None);
        };

        let mut confirm = |items: &[PlanItem]| -> Result<bool> {
            let answer = self.ask_yes(&format!(
                "\nПереименовать {} объект(ов)? [y/N]: ",
                items.len()
            ))?;
            Ok(answer.unwrap_or(false))
        };

        let outcome = renamer.rename_files(dry_run, Some(&mut confirm), true)?;
        writeln!(
            self.output,
            "\nПереименовано: {}, ошибок: {}, в плане: {}",
            outcome.renamed, outcome.failed, outcome.planned
        )?;
        self.pause()
    }

    fn shortcut_flow(&mut self) -> Result<Option<()>> {
        writeln!(self.output, "\nПереименование ссылок в ярлыках")?;

        if !cfg!(windows) {
            writeln!(
                self.output,
                "Обновление ярлыков поддерживается только в Windows."
            )?;
            return self.pause();
        }

        let Some(path) = self.prompt("Введите путь к каталогу: ")? else {
            return Ok(None);
        };
        if path.is_empty() {
            writeln!(self.output, "Путь не указан.")?;
            return self.pause();
        }

        let renamer = FileRenamer::with_logger(&path, Arc::clone(&self.logger));
        if let Err(error) = renamer.validate_directory() {
            writeln!(self.output, "{error}")?;
            return self.pause();
        }

        writeln!(
            self.output,
            "В каталоге {} выполняем поиск ярлыков ...",
            renamer.directory().display()
        )?;

        let mut confirm = |items: &[std::path::PathBuf]| -> Result<bool> {
            let answer = self.ask_yes(&format!("\nОбновить {} ярлык(ов)? [y/N]: ", items.len()))?;
            Ok(answer.unwrap_or(false))
        };

        let outcome = renamer.modify_shortcuts(Some(&mut confirm))?;
        writeln!(
            self.output,
            "\nОбновлено ярлыков: {}, ошибок: {}, найдено: {}",
            outcome.renamed, outcome.failed, outcome.planned
        )?;
        self.pause()
    }

    fn help(&mut self) -> Result<()> {
        writeln!(self.output, "\nО программе")?;
        writeln!(
            self.output,
            "Утилита для переименования файлов, папок и ярлыков, ver. {}",
            crate::VERSION
        )?;
        writeln!(
            self.output,
            "Формат даты ДД.ММ.ГГ в имени файла, папки или цели ярлыка \
             меняется на ГГГГ.ММ.ДД."
        )?;
        writeln!(
            self.output,
            "Двузначный год: 69-99 -> 1969-1999, 00-68 -> 2000-2068."
        )?;
        writeln!(
            self.output,
            "Файлы и папки переименовываются от самых глубоких; \
             перед изменениями показывается план и запрашивается подтверждение."
        )?;
        writeln!(
            self.output,
            "Сначала переименуйте файлы и папки, затем обновите ярлыки."
        )?;
        writeln!(
            self.output,
            "Журнал: {}",
            default_logs_directory().display()
        )?;
        Ok(())
    }

    fn prompt(&mut self, text: &str) -> Result<Option<String>> {
        write!(self.output, "{text}")?;
        self.output.flush()?;

        let mut line = String::new();
        if self.input.read_line(&mut line)? == 0 {
            return Ok(None);
        }
        Ok(Some(line.trim().to_owned()))
    }

    fn ask_yes(&mut self, text: &str) -> Result<Option<bool>> {
        let Some(answer) = self.prompt(text)? else {
            return Ok(None);
        };
        let normalized = answer.to_lowercase();
        Ok(Some(matches!(
            normalized.as_str(),
            "y" | "yes" | "д" | "да"
        )))
    }

    fn pause(&mut self) -> Result<Option<()>> {
        if self
            .prompt("\nНажмите Enter для продолжения ...")?
            .is_none()
        {
            return Ok(None);
        }
        Ok(Some(()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Cursor;
    use tempfile::TempDir;

    fn run_menu(input: &str) -> String {
        let mut output = Vec::new();
        run(
            Cursor::new(input.as_bytes()),
            &mut output,
            Arc::new(Logger::disabled()),
        )
        .expect("меню должно отрабатывать");
        String::from_utf8(output).expect("utf-8")
    }

    fn temp_with_file() -> (TempDir, std::path::PathBuf) {
        let temp = TempDir::new().expect("tempdir");
        let source = temp.path().join("26.10.25 file.txt");
        fs::write(&source, b"data").expect("файл");
        (temp, source)
    }

    #[test]
    fn menu_renames_file_after_confirmation() {
        let (temp, _source) = temp_with_file();
        let input = format!("1\n{}\nn\ny\n\n4\n", temp.path().display());

        let output = run_menu(&input);

        assert!(temp.path().join("2025.10.26 file.txt").exists());
        assert!(output.contains("Переименовано: 1"));
    }

    #[test]
    fn menu_declined_confirmation_changes_nothing() {
        let (temp, source) = temp_with_file();
        let input = format!("1\n{}\nn\nn\n\n4\n", temp.path().display());

        let output = run_menu(&input);

        assert!(source.exists());
        assert!(output.contains("Переименовано: 0"));
    }

    #[test]
    fn menu_reports_missing_directory() {
        let input = "1\nнесуществующая_директория\n\n4\n";

        let output = run_menu(input);

        assert!(output.contains("не существует"));
    }

    #[test]
    fn menu_exits_on_eof() {
        let output = run_menu("");
        assert!(output.contains("Утилита для переименования файлов"));
    }

    #[test]
    fn help_shows_version() {
        let output = run_menu("3\n\n4\n");
        assert!(output.contains(crate::VERSION));
    }

    #[cfg(not(windows))]
    #[test]
    fn shortcuts_are_windows_only() {
        let output = run_menu("2\n\n4\n");
        assert!(output.contains("только в Windows"));
    }
}
