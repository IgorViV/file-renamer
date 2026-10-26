//! Поиск объектов, построение плана и переименование.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use crate::date;
use crate::error::{Error, Result};
use crate::logging::Logger;
use crate::paths;
use crate::shortcut::{default_backend, ShortcutBackend};

/// Один пункт плана переименования.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanItem {
    /// Исходный путь.
    pub source: PathBuf,
    /// Новый путь.
    pub target: PathBuf,
}

/// Объект, который не удалось включить в план.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanError {
    /// Путь объекта.
    pub path: PathBuf,
    /// Причина.
    pub reason: String,
}

/// План переименования.
#[derive(Debug, Default)]
pub struct RenamePlan {
    /// Объекты к переименованию.
    pub items: Vec<PlanItem>,
    /// Проблемные объекты.
    pub errors: Vec<PlanError>,
}

/// Результат операции.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Outcome {
    /// Сколько переименовано (или обновлено).
    pub renamed: usize,
    /// Сколько ошибок.
    pub failed: usize,
    /// Сколько объектов было в плане.
    pub planned: usize,
}

type PlanConfirm<'a> = &'a mut dyn FnMut(&[PlanItem]) -> Result<bool>;
type ShortcutConfirm<'a> = &'a mut dyn FnMut(&[PathBuf]) -> Result<bool>;

#[derive(Debug, Default)]
struct Contents {
    files: Vec<PathBuf>,
    directories: Vec<PathBuf>,
    shortcuts: Vec<PathBuf>,
}

/// Переименователь файлов, папок и ярлыков.
pub struct FileRenamer {
    directory: PathBuf,
    logger: Arc<Logger>,
    shortcut_backend: Box<dyn ShortcutBackend>,
}

impl FileRenamer {
    /// Создает переименователь с отключенным журналом.
    #[must_use]
    pub fn new(directory: impl AsRef<Path>) -> Self {
        Self::with_backend(directory, Arc::new(Logger::disabled()), default_backend())
    }

    /// Создает переименователь с заданным журналом.
    #[must_use]
    pub fn with_logger(directory: impl AsRef<Path>, logger: Arc<Logger>) -> Self {
        Self::with_backend(directory, logger, default_backend())
    }

    /// Создает переименователь с журналом и бэкендом ярлыков.
    #[must_use]
    pub fn with_backend(
        directory: impl AsRef<Path>,
        logger: Arc<Logger>,
        shortcut_backend: Box<dyn ShortcutBackend>,
    ) -> Self {
        Self {
            directory: normalize_directory(directory.as_ref()),
            logger,
            shortcut_backend,
        }
    }

    /// Возвращает нормализованный каталог поиска.
    #[must_use]
    pub fn directory(&self) -> &Path {
        &self.directory
    }

    /// Проверяет, что каталог задан и существует.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если путь пуст, не существует или не является каталогом.
    pub fn validate_directory(&self) -> Result<()> {
        if self.directory.as_os_str().is_empty() {
            return Err(Error::Directory("Каталог не указан".to_owned()));
        }
        if !self.directory.exists() {
            return Err(Error::Directory(format!(
                "Указанный вами каталог {} не существует",
                self.directory.display()
            )));
        }
        if !self.directory.is_dir() {
            return Err(Error::Directory(format!(
                "Указанный путь не является каталогом: {}",
                self.directory.display()
            )));
        }
        Ok(())
    }

    fn collect_all(&self) -> Result<Contents> {
        let mut contents = Contents::default();
        let mut stack = vec![self.directory.clone()];

        while let Some(directory) = stack.pop() {
            let entries = fs::read_dir(&directory).map_err(|error| io_error(&directory, error))?;

            for entry in entries {
                let entry = entry?;
                let path = entry.path();
                let file_type = entry.file_type()?;

                // Символические ссылки пропускаем: так мы не зациклимся и
                // не изменим объект за пределами выбранного каталога.
                if file_type.is_symlink() {
                    continue;
                }

                let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
                    if file_type.is_dir() {
                        stack.push(path);
                    }
                    continue;
                };

                if file_type.is_dir() {
                    if date::matches_mask(name) {
                        contents.directories.push(path.clone());
                    }
                    stack.push(path);
                } else if file_type.is_file() {
                    if date::matches_mask(name) {
                        contents.files.push(path.clone());
                    }
                    if is_shortcut(name) {
                        contents.shortcuts.push(path);
                    }
                }
            }
        }

        sort_paths(&mut contents.files);
        sort_paths(&mut contents.directories);
        sort_paths(&mut contents.shortcuts);
        Ok(contents)
    }

    /// Возвращает файлы с датой в префиксе имени.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог невозможно прочитать.
    pub fn get_files_list(&self) -> Result<Vec<PathBuf>> {
        let contents = self.collect_all()?;
        self.logger
            .info(format!("Найдено файлов: {}", contents.files.len()));
        Ok(contents.files)
    }

    /// Возвращает каталоги с датой в префиксе имени.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог невозможно прочитать.
    pub fn get_directories_list(&self) -> Result<Vec<PathBuf>> {
        let contents = self.collect_all()?;
        self.logger
            .info(format!("Найдено каталогов: {}", contents.directories.len()));
        Ok(contents.directories)
    }

    /// Возвращает объекты для переименования в порядке «сначала глубокие».
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог невозможно прочитать.
    pub fn get_rename_candidates(&self, include_directories: bool) -> Result<Vec<PathBuf>> {
        let contents = self.collect_all()?;
        let mut candidates = contents.files;
        if include_directories {
            candidates.extend(contents.directories);
        }
        sort_paths(&mut candidates);
        self.logger.info(format!(
            "Найдено объектов для переименования: {}",
            candidates.len()
        ));
        Ok(candidates)
    }

    /// Возвращает ярлыки `.lnk`.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог невозможно прочитать.
    pub fn get_shortcut_list(&self) -> Result<Vec<PathBuf>> {
        let contents = self.collect_all()?;
        self.logger
            .info(format!("Найдено ярлыков: {}", contents.shortcuts.len()));
        Ok(contents.shortcuts)
    }

    /// Возвращает новый путь с датой `ГГГГ.ММ.ДД`.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если в имени нет даты или она некорректна.
    pub fn target_path(&self, path: &Path) -> Result<PathBuf> {
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| {
                Error::InvalidPath(format!(
                    "не удалось прочитать имя файла: {}",
                    path.display()
                ))
            })?;

        if !date::looks_like_date_prefix(name) {
            return Err(Error::MissingDate {
                name: name.to_owned(),
            });
        }

        let raw = &name[..date::DATE_PREFIX_LEN];
        let parsed = date::parse_date(raw).map_err(|error| Error::InvalidDate {
            name: name.to_owned(),
            raw: error.raw,
        })?;
        let new_name = format!(
            "{}{}",
            parsed.to_yyyy_mm_dd(),
            &name[date::DATE_PREFIX_LEN..]
        );
        Ok(path.with_file_name(new_name))
    }

    /// Строит план переименования.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог невозможно прочитать.
    pub fn build_plan(&self, include_directories: bool) -> Result<RenamePlan> {
        let mut plan = RenamePlan::default();

        for path in self.get_rename_candidates(include_directories)? {
            match self.target_path(&path) {
                Ok(target) => {
                    if target == path {
                        continue;
                    }
                    if target.exists() {
                        let reason = format!("цель уже существует: {}", target.display());
                        self.logger
                            .error(format!("Пропущен {}: {reason}", path.display()));
                        plan.errors.push(PlanError { path, reason });
                    } else {
                        plan.items.push(PlanItem {
                            source: path,
                            target,
                        });
                    }
                }
                Err(error) => {
                    self.logger
                        .error(format!("Пропущен {}: {error}", path.display()));
                    plan.errors.push(PlanError {
                        path,
                        reason: error.to_string(),
                    });
                }
            }
        }

        Ok(plan)
    }

    /// Переименовывает один объект, не перезаписывая существующую цель.
    #[must_use]
    pub fn apply_rename(&self, source: &Path, target: &Path) -> bool {
        if source == target {
            self.logger
                .info(format!("{} уже имеет корректное имя", source.display()));
            return true;
        }
        if target.exists() {
            self.logger.error(format!(
                "Не переименован {}: цель уже существует {}",
                source.display(),
                target.display()
            ));
            return false;
        }

        if let Err(error) = fs::rename(source, target) {
            self.logger.error(format!(
                "Ошибка переименования файла {}: {error}",
                source.display()
            ));
            return false;
        }

        if !target.exists() || source.exists() {
            self.logger.error(format!(
                "Не удалось подтвердить переименование {} -> {}",
                source.display(),
                target.display()
            ));
            return false;
        }

        self.logger
            .info(format!("{} -> {}", source.display(), target.display()));
        true
    }

    /// Переименовывает отдельный объект.
    #[must_use]
    pub fn rename_prefix(&self, file: &Path) -> bool {
        match self.target_path(file) {
            Ok(target) => self.apply_rename(file, &target),
            Err(error) => {
                self.logger
                    .error(format!("Не переименован {}: {error}", file.display()));
                false
            }
        }
    }

    /// Переименовывает файлы и, при необходимости, каталоги.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог невозможно прочитать.
    pub fn rename_files(
        &self,
        dry_run: bool,
        confirm: Option<PlanConfirm<'_>>,
        include_directories: bool,
    ) -> Result<Outcome> {
        let plan = self.build_plan(include_directories)?;
        let failed = plan.errors.len();
        let planned = plan.items.len();

        if !plan.items.is_empty() {
            println!("\nПланируемые изменения:");
            for item in &plan.items {
                println!("{} -> {}", item.source.display(), item.target.display());
            }
        }

        if dry_run {
            self.logger.info(format!(
                "Предпросмотр (dry-run): будет переименовано {planned}, проблем {failed}"
            ));
            return Ok(Outcome {
                renamed: 0,
                failed,
                planned,
            });
        }

        if plan.items.is_empty() {
            self.logger.info("Нет файлов для переименования");
            return Ok(Outcome {
                renamed: 0,
                failed,
                planned,
            });
        }

        if let Some(confirm) = confirm {
            if !confirm(&plan.items)? {
                self.logger.info("Переименование отменено пользователем");
                return Ok(Outcome {
                    renamed: 0,
                    failed,
                    planned,
                });
            }
        }

        let mut renamed = 0;
        let mut failed = failed;
        for item in &plan.items {
            if self.apply_rename(&item.source, &item.target) {
                renamed += 1;
            } else {
                failed += 1;
            }
        }

        self.logger
            .info(format!("Успешно переименовано: {renamed}, ошибок {failed}"));
        Ok(Outcome {
            renamed,
            failed,
            planned,
        })
    }

    /// Применяет заранее построенный план.
    #[must_use]
    pub fn apply_plan(&self, plan: &RenamePlan) -> Outcome {
        let mut renamed = 0;
        let mut failed = plan.errors.len();

        for item in &plan.items {
            if self.apply_rename(&item.source, &item.target) {
                renamed += 1;
            } else {
                failed += 1;
            }
        }

        self.logger
            .info(format!("Успешно переименовано: {renamed}, ошибок {failed}"));
        Outcome {
            renamed,
            failed,
            planned: plan.items.len(),
        }
    }

    /// Обновляет целевой путь одного ярлыка.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если ярлык не удалось прочитать или обновить,
    /// либо если новая цель не существует.
    pub fn rename_shortcut_target(&self, lnk: &Path) -> Result<()> {
        let old_target = self.shortcut_backend.read_target(lnk)?;
        let new_target = paths::update_folder_dates(&old_target)?;

        if new_target == old_target {
            self.logger.info(format!(
                "Ярлык {} уже указывает на {}, изменение не требуется",
                lnk.display(),
                new_target
            ));
            return Ok(());
        }

        if !Path::new(&new_target).exists() {
            return Err(Error::Shortcut(format!(
                "Путь назначения не существует: {new_target}"
            )));
        }

        self.shortcut_backend.update_target(lnk, &new_target)?;
        self.logger.info(format!(
            "{}: {} -> {}",
            lnk.display(),
            old_target,
            new_target
        ));
        Ok(())
    }

    /// Обновляет ярлыки.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог невозможно прочитать.
    pub fn modify_shortcuts(&self, confirm: Option<ShortcutConfirm<'_>>) -> Result<Outcome> {
        let shortcuts = self.get_shortcut_list()?;
        let planned = shortcuts.len();

        if shortcuts.is_empty() {
            self.logger.info("Ярлыки не найдены");
            return Ok(Outcome::default());
        }

        println!("\nНайденные ярлыки:");
        for shortcut in &shortcuts {
            println!("ярлык -> {}", shortcut.display());
        }

        if let Some(confirm) = confirm {
            if !confirm(&shortcuts)? {
                self.logger
                    .info("Обновление ярлыков отменено пользователем");
                return Ok(Outcome {
                    renamed: 0,
                    failed: 0,
                    planned,
                });
            }
        }

        let mut renamed = 0;
        let mut failed = 0;
        for shortcut in &shortcuts {
            match self.rename_shortcut_target(shortcut) {
                Ok(()) => renamed += 1,
                Err(error) => {
                    failed += 1;
                    self.logger.error(format!(
                        "Ошибка при модификации ярлыка {}: {error}",
                        shortcut.display()
                    ));
                }
            }
        }

        self.logger.info(format!(
            "Успешно модифицировано ярлыков: {renamed}, ошибок {failed}"
        ));
        Ok(Outcome {
            renamed,
            failed,
            planned,
        })
    }
}

fn normalize_directory(path: &Path) -> PathBuf {
    let text = path.to_string_lossy();
    let trimmed = text.trim().trim_matches('"').trim();
    PathBuf::from(trimmed)
}

fn is_shortcut(name: &str) -> bool {
    Path::new(name)
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("lnk"))
}

fn path_depth(path: &Path) -> usize {
    path.components().count()
}

fn sort_paths(paths: &mut [PathBuf]) {
    paths.sort_by(|left, right| {
        path_depth(right)
            .cmp(&path_depth(left))
            .then_with(|| left.to_string_lossy().cmp(&right.to_string_lossy()))
    });
}

fn io_error(path: &Path, error: io::Error) -> Error {
    Error::Io(io::Error::new(
        error.kind(),
        format!("{}: {error}", path.display()),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shortcut::ShortcutBackend;
    use std::sync::{Arc, Mutex};
    use tempfile::TempDir;

    const OLD_FILE: &str = "26.10.25 file.txt";
    const NEW_FILE: &str = "2025.10.26 file.txt";

    fn touch(path: &Path) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("каталог");
        }
        fs::write(path, b"data").expect("файл");
    }

    fn renamer(directory: &Path) -> FileRenamer {
        FileRenamer::new(directory)
    }

    #[test]
    fn validates_directory() {
        let temp = TempDir::new().expect("tempdir");
        let file = temp.path().join("file.txt");
        touch(&file);

        assert!(renamer(temp.path()).validate_directory().is_ok());
        assert!(renamer(&file).validate_directory().is_err());
        assert!(renamer(&temp.path().join("missing"))
            .validate_directory()
            .is_err());
        assert!(renamer(Path::new("")).validate_directory().is_err());
    }

    #[test]
    fn normalizes_quotes_and_spaces() {
        let temp = TempDir::new().expect("tempdir");
        let raw = format!("  \"{}\"  ", temp.path().display());
        let renamer = FileRenamer::new(raw);
        assert_eq!(renamer.directory(), temp.path());
        assert!(renamer.validate_directory().is_ok());
    }

    #[test]
    fn separates_files_and_directories() {
        let temp = TempDir::new().expect("tempdir");
        let parent = temp.path().join("26.10.25 folder");
        let child = parent.join("27.10.25 child");
        let deep_file = child.join("28.10.25 deep.txt");
        let top_file = temp.path().join("29.10.25 top.txt");
        touch(&deep_file);
        touch(&top_file);
        touch(&temp.path().join("2025.10.26 done.txt"));
        touch(&temp.path().join("readme.txt"));
        let shortcuts = temp.path().join("30.10.25 shortcuts");
        fs::create_dir_all(&shortcuts).expect("каталог");
        touch(&shortcuts.join("link.lnk"));

        let renamer = renamer(temp.path());
        let files = renamer.get_files_list().expect("files");
        let directories = renamer.get_directories_list().expect("dirs");
        let candidates = renamer.get_rename_candidates(true).expect("candidates");

        assert_eq!(
            files.into_iter().collect::<std::collections::HashSet<_>>(),
            [deep_file, top_file].into_iter().collect()
        );
        assert_eq!(
            directories
                .into_iter()
                .collect::<std::collections::HashSet<_>>(),
            [parent.clone(), child, shortcuts].into_iter().collect()
        );
        let depths: Vec<usize> = candidates.iter().map(|path| path_depth(path)).collect();
        let mut sorted = depths.clone();
        sorted.sort_unstable_by(|left, right| right.cmp(left));
        assert_eq!(depths, sorted);
        assert!(candidates.contains(&parent));
    }

    #[test]
    fn candidates_can_exclude_directories() {
        let temp = TempDir::new().expect("tempdir");
        fs::create_dir_all(temp.path().join("26.10.25 folder")).expect("dir");
        touch(&temp.path().join(OLD_FILE));

        let candidates = renamer(temp.path())
            .get_rename_candidates(false)
            .expect("candidates");
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].file_name().unwrap(), OLD_FILE);
    }

    #[test]
    fn plan_reports_invalid_date_and_collision() {
        let temp = TempDir::new().expect("tempdir");
        let bad_date = temp.path().join("39.19.99 bad.txt");
        let source = temp.path().join(OLD_FILE);
        touch(&bad_date);
        touch(&source);
        touch(&temp.path().join(NEW_FILE));

        let plan = renamer(temp.path()).build_plan(true).expect("plan");

        assert!(plan.items.is_empty());
        assert_eq!(plan.errors.len(), 2);
        let reasons = plan
            .errors
            .iter()
            .map(|error| error.reason.as_str())
            .collect::<Vec<_>>()
            .join(" | ");
        assert!(reasons.contains("некорректная дата"));
        assert!(reasons.contains("уже существует"));
    }

    #[test]
    fn dry_run_does_not_change_files() {
        let temp = TempDir::new().expect("tempdir");
        let source = temp.path().join(OLD_FILE);
        touch(&source);

        let outcome = renamer(temp.path())
            .rename_files(true, None, true)
            .expect("dry run");

        assert_eq!(
            outcome,
            Outcome {
                renamed: 0,
                failed: 0,
                planned: 1
            }
        );
        assert!(source.exists());
        assert!(!temp.path().join(NEW_FILE).exists());
    }

    #[test]
    fn declined_confirmation_changes_nothing() {
        let temp = TempDir::new().expect("tempdir");
        let source = temp.path().join(OLD_FILE);
        touch(&source);
        let mut confirm = |_items: &[PlanItem]| Ok(false);

        let outcome = renamer(temp.path())
            .rename_files(false, Some(&mut confirm), true)
            .expect("rename");

        assert_eq!(outcome.renamed, 0);
        assert!(source.exists());
    }

    #[test]
    fn accepted_confirmation_renames_file() {
        let temp = TempDir::new().expect("tempdir");
        touch(&temp.path().join(OLD_FILE));
        let mut confirm = |_items: &[PlanItem]| Ok(true);

        let outcome = renamer(temp.path())
            .rename_files(false, Some(&mut confirm), true)
            .expect("rename");

        assert_eq!(outcome.renamed, 1);
        assert!(temp.path().join(NEW_FILE).exists());
    }

    #[test]
    fn invalid_date_is_counted_as_failure() {
        let temp = TempDir::new().expect("tempdir");
        let source = temp.path().join("39.19.99 bad.txt");
        touch(&source);

        let outcome = renamer(temp.path())
            .rename_files(false, None, true)
            .expect("rename");

        assert_eq!(outcome.renamed, 0);
        assert_eq!(outcome.failed, 1);
        assert!(source.exists());
    }

    #[test]
    fn collision_is_not_overwritten() {
        let temp = TempDir::new().expect("tempdir");
        let source = temp.path().join(OLD_FILE);
        let target = temp.path().join(NEW_FILE);
        fs::write(&source, b"source").expect("source");
        fs::write(&target, b"target").expect("target");

        let outcome = renamer(temp.path())
            .rename_files(false, None, true)
            .expect("rename");

        assert_eq!(outcome.renamed, 0);
        assert_eq!(outcome.failed, 1);
        assert_eq!(fs::read(&source).unwrap(), b"source");
        assert_eq!(fs::read(&target).unwrap(), b"target");
    }

    #[test]
    fn second_run_changes_nothing() {
        let temp = TempDir::new().expect("tempdir");
        touch(&temp.path().join(OLD_FILE));
        let renamer = renamer(temp.path());

        assert_eq!(renamer.rename_files(false, None, true).unwrap().renamed, 1);
        assert_eq!(
            renamer.rename_files(false, None, true).unwrap(),
            Outcome::default()
        );
        assert!(temp.path().join(NEW_FILE).exists());
    }

    #[test]
    fn renames_directories_after_children() {
        let temp = TempDir::new().expect("tempdir");
        let folder = temp.path().join("26.10.25 folder");
        touch(&folder.join("27.10.25 inner.txt"));

        let outcome = renamer(temp.path())
            .rename_files(false, None, true)
            .expect("rename");

        assert_eq!(outcome.renamed, 2);
        let new_folder = temp.path().join("2025.10.26 folder");
        assert!(new_folder.join("2025.10.27 inner.txt").exists());
    }

    #[test]
    fn files_only_scope_keeps_directory() {
        let temp = TempDir::new().expect("tempdir");
        let folder = temp.path().join("26.10.25 folder");
        touch(&folder.join("27.10.25 inner.txt"));

        let outcome = renamer(temp.path())
            .rename_files(false, None, false)
            .expect("rename");

        assert_eq!(outcome.renamed, 1);
        assert!(folder.exists());
        assert!(folder.join("2025.10.27 inner.txt").exists());
    }

    #[test]
    fn apply_rename_refuses_existing_target() {
        let temp = TempDir::new().expect("tempdir");
        let source = temp.path().join(OLD_FILE);
        let target = temp.path().join(NEW_FILE);
        fs::write(&source, b"source").expect("source");
        fs::write(&target, b"target").expect("target");

        assert!(!renamer(temp.path()).apply_rename(&source, &target));
        assert_eq!(fs::read(&source).unwrap(), b"source");
        assert_eq!(fs::read(&target).unwrap(), b"target");
    }

    #[test]
    fn logs_before_and_after() {
        let temp = TempDir::new().expect("tempdir");
        touch(&temp.path().join(OLD_FILE));
        let log_dir = temp.path().join("logs");
        let logger = Arc::new(Logger::open(&log_dir, 10_000, 2, 5).expect("logger"));
        let renamer = FileRenamer::with_logger(temp.path(), logger);

        assert_eq!(renamer.rename_files(false, None, true).unwrap().renamed, 1);

        let log = fs::read_dir(&log_dir)
            .expect("logs")
            .filter_map(std::result::Result::ok)
            .map(|entry| entry.path())
            .find(|path| {
                path.file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| name.starts_with("renamer_"))
            })
            .expect("log file");
        let content = fs::read_to_string(log).expect("log");
        assert!(content.contains(OLD_FILE));
        assert!(content.contains(NEW_FILE));
    }

    #[derive(Default)]
    struct FakeState {
        target: String,
        updates: Vec<(PathBuf, String)>,
        fail: bool,
    }

    #[derive(Clone, Default)]
    struct FakeBackend {
        state: Arc<Mutex<FakeState>>,
    }

    impl FakeBackend {
        fn with_target(target: impl Into<String>) -> Self {
            let backend = Self::default();
            backend.state.lock().unwrap().target = target.into();
            backend
        }

        fn fail(&self) {
            self.state.lock().unwrap().fail = true;
        }

        fn target(&self) -> String {
            self.state.lock().unwrap().target.clone()
        }

        fn updates(&self) -> Vec<(PathBuf, String)> {
            self.state.lock().unwrap().updates.clone()
        }
    }

    impl ShortcutBackend for FakeBackend {
        fn read_target(&self, _lnk: &Path) -> Result<String> {
            let state = self.state.lock().unwrap();
            if state.fail {
                return Err(Error::Shortcut("ошибка чтения".to_owned()));
            }
            if state.target.is_empty() {
                return Err(Error::Shortcut("нет цели".to_owned()));
            }
            Ok(state.target.clone())
        }

        fn update_target(&self, lnk: &Path, target: &str) -> Result<()> {
            let mut state = self.state.lock().unwrap();
            if state.fail {
                return Err(Error::Shortcut("ошибка записи".to_owned()));
            }
            state.updates.push((lnk.to_path_buf(), target.to_owned()));
            state.target = target.to_owned();
            Ok(())
        }
    }

    fn shortcut_fixture(temp: &TempDir) -> (PathBuf, PathBuf, String, String) {
        let old = temp
            .path()
            .join("26.10.25 folder")
            .join("26.10.25 file.txt");
        let new = temp
            .path()
            .join("2025.10.26 folder")
            .join("2025.10.26 file.txt");
        touch(&old);
        touch(&new);
        let old_text = old.to_string_lossy().into_owned();
        let new_text = new.to_string_lossy().into_owned();
        (old, new, old_text, new_text)
    }

    #[test]
    fn shortcut_target_is_updated_in_place() {
        let temp = TempDir::new().expect("tempdir");
        let (old, new, old_text, new_text) = shortcut_fixture(&temp);
        let _ = old;
        let lnk = temp.path().join("26.10.25 link.lnk");
        touch(&lnk);
        let backend = FakeBackend::with_target(old_text);
        let renamer = FileRenamer::with_backend(
            temp.path(),
            Arc::new(Logger::disabled()),
            Box::new(backend.clone()),
        );

        renamer.rename_shortcut_target(&lnk).expect("shortcut");

        assert!(lnk.exists());
        assert_eq!(backend.target(), new_text);
        assert_eq!(backend.updates(), vec![(lnk, new_text)]);
        assert!(new.exists());
    }

    #[test]
    fn missing_target_leaves_shortcut_untouched() {
        let temp = TempDir::new().expect("tempdir");
        let old = temp
            .path()
            .join("26.10.25 folder")
            .join("26.10.25 file.txt");
        touch(&old);
        let lnk = temp.path().join("link.lnk");
        touch(&lnk);
        let backend = FakeBackend::with_target(old.to_string_lossy());
        let renamer = FileRenamer::with_backend(
            temp.path(),
            Arc::new(Logger::disabled()),
            Box::new(backend.clone()),
        );

        assert!(renamer.rename_shortcut_target(&lnk).is_err());
        assert!(lnk.exists());
        assert!(backend.updates().is_empty());
    }

    #[test]
    fn checks_target_itself_not_parent() {
        let temp = TempDir::new().expect("tempdir");
        let old = temp
            .path()
            .join("26.10.25 folder")
            .join("26.10.25 file.txt");
        touch(&old);
        fs::create_dir_all(temp.path().join("2025.10.26 folder")).expect("dir");
        let lnk = temp.path().join("link.lnk");
        touch(&lnk);
        let backend = FakeBackend::with_target(old.to_string_lossy());
        let renamer = FileRenamer::with_backend(
            temp.path(),
            Arc::new(Logger::disabled()),
            Box::new(backend.clone()),
        );

        assert!(renamer.rename_shortcut_target(&lnk).is_err());
        assert!(backend.updates().is_empty());
    }

    #[test]
    fn unchanged_target_is_not_rewritten() {
        let temp = TempDir::new().expect("tempdir");
        let target = temp.path().join("folder").join("file.txt");
        touch(&target);
        let lnk = temp.path().join("link.lnk");
        touch(&lnk);
        let backend = FakeBackend::with_target(target.to_string_lossy());
        let renamer = FileRenamer::with_backend(
            temp.path(),
            Arc::new(Logger::disabled()),
            Box::new(backend.clone()),
        );

        renamer.rename_shortcut_target(&lnk).expect("shortcut");
        assert!(backend.updates().is_empty());
    }

    #[test]
    fn backend_error_keeps_shortcut() {
        let temp = TempDir::new().expect("tempdir");
        let (_, _, old_text, _) = shortcut_fixture(&temp);
        let lnk = temp.path().join("link.lnk");
        touch(&lnk);
        let backend = FakeBackend::with_target(old_text);
        backend.fail();
        let renamer =
            FileRenamer::with_backend(temp.path(), Arc::new(Logger::disabled()), Box::new(backend));

        assert!(renamer.rename_shortcut_target(&lnk).is_err());
        assert!(lnk.exists());
    }

    #[test]
    fn modify_shortcuts_respects_confirmation() {
        let temp = TempDir::new().expect("tempdir");
        let (_, _, old_text, _) = shortcut_fixture(&temp);
        let lnk = temp.path().join("26.10.25 link.lnk");
        touch(&lnk);
        let backend = FakeBackend::with_target(old_text);
        let renamer = FileRenamer::with_backend(
            temp.path(),
            Arc::new(Logger::disabled()),
            Box::new(backend.clone()),
        );
        let mut confirm = |_items: &[PathBuf]| Ok(false);

        let outcome = renamer
            .modify_shortcuts(Some(&mut confirm))
            .expect("modify");

        assert_eq!(outcome.renamed, 0);
        assert_eq!(outcome.planned, 1);
        assert!(backend.updates().is_empty());
    }

    #[test]
    fn modify_shortcuts_updates_and_counts() {
        let temp = TempDir::new().expect("tempdir");
        let (_, _, old_text, new_text) = shortcut_fixture(&temp);
        let lnk = temp.path().join("26.10.25 link.lnk");
        touch(&lnk);
        let backend = FakeBackend::with_target(old_text.clone());
        let renamer = FileRenamer::with_backend(
            temp.path(),
            Arc::new(Logger::disabled()),
            Box::new(backend.clone()),
        );

        let outcome = renamer.modify_shortcuts(None).expect("modify");

        assert_eq!(outcome.renamed, 1);
        assert_eq!(outcome.failed, 0);
        assert_eq!(backend.target(), new_text);
    }
}
