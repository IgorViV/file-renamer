//! Журналирование в файл с ротацией и запасным выводом в консоль.

use std::fmt::Display;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, PoisonError};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::date::Date;

/// Переменная окружения для переопределения каталога логов.
pub const LOG_DIR_ENV: &str = "FILE_RENAMER_LOG_DIR";

const LOG_PREFIX: &str = "renamer_";
const LOG_SUFFIX: &str = ".log";
const DEFAULT_MAX_BYTES: u64 = 1_000_000;
const DEFAULT_BACKUPS: usize = 3;
const DEFAULT_KEEP: usize = 10;

struct LogFile {
    path: PathBuf,
    file: Option<File>,
    written: u64,
}

/// Журнал приложения.
///
/// Пишет строки в отдельный файл на запуск, ротирует его по размеру и
/// ограничивает количество хранимых файлов. Потокобезопасен.
pub struct Logger {
    inner: Option<Mutex<LogFile>>,
    max_bytes: u64,
    backup_count: usize,
    console: bool,
}

impl Logger {
    /// Создает журнал в каталоге `directory`.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если каталог или файл журнала недоступны.
    pub fn open(
        directory: &Path,
        max_bytes: u64,
        backup_count: usize,
        keep: usize,
    ) -> io::Result<Self> {
        fs::create_dir_all(directory)?;
        prune_logs(directory, keep)?;

        let path = directory.join(format!(
            "{LOG_PREFIX}{}_{}{LOG_SUFFIX}",
            timestamp_compact(),
            std::process::id()
        ));
        let file = OpenOptions::new().create(true).append(true).open(&path)?;
        let written = file.metadata()?.len();

        Ok(Self {
            inner: Some(Mutex::new(LogFile {
                path,
                file: Some(file),
                written,
            })),
            max_bytes: max_bytes.max(1),
            backup_count,
            console: false,
        })
    }

    /// Включает дублирование журнала в stderr.
    #[must_use]
    pub fn with_console(mut self) -> Self {
        self.console = true;
        self
    }

    /// Создает журнал, который пишет только в stderr.
    #[must_use]
    pub fn console_only() -> Self {
        Self {
            inner: None,
            max_bytes: DEFAULT_MAX_BYTES,
            backup_count: DEFAULT_BACKUPS,
            console: true,
        }
    }

    /// Создает отключенный журнал (для тестов и библиотечного использования).
    #[must_use]
    pub fn disabled() -> Self {
        Self {
            inner: None,
            max_bytes: DEFAULT_MAX_BYTES,
            backup_count: DEFAULT_BACKUPS,
            console: false,
        }
    }

    /// Создает журнал в каталоге по умолчанию.
    ///
    /// При ошибке откатывается на вывод в stderr.
    #[must_use]
    pub fn from_environment() -> Self {
        let directory = default_logs_directory();
        Self::open(&directory, DEFAULT_MAX_BYTES, DEFAULT_BACKUPS, DEFAULT_KEEP).map_or_else(
            |error| {
                eprintln!(
                    "Не удалось открыть журнал в {}: {error}",
                    directory.display()
                );
                Self::console_only()
            },
            Logger::with_console,
        )
    }

    /// Записывает сообщение уровня INFO.
    pub fn info(&self, message: impl Display) {
        self.log("INFO", &message.to_string());
    }

    /// Записывает сообщение уровня WARN.
    pub fn warn(&self, message: impl Display) {
        self.log("WARN", &message.to_string());
    }

    /// Записывает сообщение уровня ERROR.
    pub fn error(&self, message: impl Display) {
        self.log("ERROR", &message.to_string());
    }

    fn log(&self, level: &str, message: &str) {
        let line = format!("{} {level:<5} {message}\n", timestamp_utc());

        if self.console {
            eprint!("{line}");
        }

        let Some(inner) = &self.inner else {
            return;
        };

        let mut guard = inner.lock().unwrap_or_else(PoisonError::into_inner);

        if guard.written > 0 && guard.written + line.len() as u64 > self.max_bytes {
            if let Err(error) = guard.rotate(self.backup_count) {
                if self.console {
                    eprintln!("Не удалось ротировать журнал: {error}");
                }
            }
        }

        if let Some(file) = guard.file.as_mut() {
            if let Err(error) = file.write_all(line.as_bytes()) {
                if self.console {
                    eprintln!("Не удалось записать журнал: {error}");
                }
            } else {
                guard.written += line.len() as u64;
            }
        }
    }
}

impl LogFile {
    fn rotate(&mut self, backup_count: usize) -> io::Result<()> {
        if let Some(mut file) = self.file.take() {
            file.flush()?;
        }

        if backup_count == 0 {
            let file = OpenOptions::new()
                .write(true)
                .truncate(true)
                .open(&self.path)?;
            self.file = Some(file);
            self.written = 0;
            return Ok(());
        }

        for index in (1..backup_count).rev() {
            let from = backup_path(&self.path, index);
            let to = backup_path(&self.path, index + 1);
            if from.exists() {
                let _ = fs::remove_file(&to);
                fs::rename(&from, &to)?;
            }
        }

        let first = backup_path(&self.path, 1);
        let _ = fs::remove_file(&first);
        fs::rename(&self.path, &first)?;

        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        self.file = Some(file);
        self.written = 0;
        Ok(())
    }
}

fn backup_path(path: &Path, index: usize) -> PathBuf {
    let mut name = path.as_os_str().to_os_string();
    name.push(format!(".{index}"));
    PathBuf::from(name)
}

/// Удаляет старые логи, оставляя `keep` самых новых файлов.
///
/// # Errors
///
/// Возвращает ошибку, если каталог невозможно прочитать.
pub fn prune_logs(directory: &Path, keep: usize) -> io::Result<()> {
    if keep == 0 {
        return Ok(());
    }

    let mut logs = Vec::new();
    for entry in fs::read_dir(directory)? {
        let entry = entry?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        if !name.starts_with(LOG_PREFIX) || !name.contains(LOG_SUFFIX) {
            continue;
        }
        let modified = entry
            .metadata()
            .and_then(|metadata| metadata.modified())
            .unwrap_or(UNIX_EPOCH);
        logs.push((modified, path));
    }

    logs.sort_by(|left, right| right.0.cmp(&left.0).then_with(|| right.1.cmp(&left.1)));

    for (_modified, path) in logs.into_iter().skip(keep) {
        let _ = fs::remove_file(path);
    }

    Ok(())
}

/// Возвращает каталог логов по умолчанию.
#[must_use]
pub fn default_logs_directory() -> PathBuf {
    let home = std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from);
    logs_directory_from(|key| std::env::var(key).ok(), cfg!(windows), home)
}

/// Вычисляет каталог логов по переменным окружения.
#[must_use]
pub fn logs_directory_from<F>(get_env: F, is_windows: bool, home: Option<PathBuf>) -> PathBuf
where
    F: Fn(&str) -> Option<String>,
{
    if let Some(custom) = get_env(LOG_DIR_ENV)
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
    {
        return PathBuf::from(custom);
    }

    if is_windows {
        if let Some(local_app_data) = get_env("LOCALAPPDATA")
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
        {
            return PathBuf::from(local_app_data)
                .join("file-renamer")
                .join("logs");
        }
        if let Some(home) = home {
            return home
                .join("AppData")
                .join("Local")
                .join("file-renamer")
                .join("logs");
        }
    } else {
        if let Some(state_home) = get_env("XDG_STATE_HOME")
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
        {
            return PathBuf::from(state_home).join("file-renamer").join("logs");
        }
        if let Some(home) = home {
            return home
                .join(".local")
                .join("state")
                .join("file-renamer")
                .join("logs");
        }
    }

    std::env::temp_dir().join("file-renamer").join("logs")
}

fn split_timestamp(seconds: i64) -> (Date, u32, u32, u32) {
    let days = seconds.div_euclid(86_400);
    let remainder = seconds.rem_euclid(86_400);
    let date = Date::from_epoch_days(days);
    let hour = u32::try_from(remainder / 3_600).unwrap_or(0);
    let minute = u32::try_from((remainder % 3_600) / 60).unwrap_or(0);
    let second = u32::try_from(remainder % 60).unwrap_or(0);
    (date, hour, minute, second)
}

/// Форматирует Unix-время как `ГГГГ-ММ-ДД ЧЧ:ММ:СС` (UTC).
#[must_use]
pub fn format_timestamp(seconds: i64) -> String {
    let (date, hour, minute, second) = split_timestamp(seconds);
    format!(
        "{:04}-{:02}-{:02} {hour:02}:{minute:02}:{second:02}",
        date.year, date.month, date.day
    )
}

fn timestamp_utc() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| i64::try_from(duration.as_secs()).unwrap_or(i64::MAX))
        .unwrap_or(0);
    format_timestamp(seconds)
}

fn timestamp_compact() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| i64::try_from(duration.as_millis()).unwrap_or(i64::MAX))
        .unwrap_or(0);
    let seconds = millis / 1_000;
    let milliseconds = millis % 1_000;
    let (date, hour, minute, second) = split_timestamp(seconds);
    format!(
        "{:04}{:02}{:02}_{hour:02}{minute:02}{second:02}_{milliseconds:03}",
        date.year, date.month, date.day
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::fs::FileTimes;
    use std::time::Duration;

    fn env_map(values: &[(&str, &str)]) -> HashMap<String, String> {
        values
            .iter()
            .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
            .collect()
    }

    #[test]
    fn env_override_has_priority() {
        let env = env_map(&[(LOG_DIR_ENV, "/custom/logs")]);
        let directory = logs_directory_from(
            |key| env.get(key).cloned(),
            true,
            Some(PathBuf::from("/home/user")),
        );
        assert_eq!(directory, PathBuf::from("/custom/logs"));
    }

    #[test]
    fn windows_uses_local_app_data() {
        let env = env_map(&[("LOCALAPPDATA", r"C:\Users\user\AppData\Local")]);
        let directory = logs_directory_from(
            |key| env.get(key).cloned(),
            true,
            Some(PathBuf::from("/home/user")),
        );
        assert_eq!(
            directory,
            PathBuf::from(r"C:\Users\user\AppData\Local")
                .join("file-renamer")
                .join("logs")
        );
    }

    #[test]
    fn windows_falls_back_to_home() {
        let directory = logs_directory_from(|_key| None, true, Some(PathBuf::from("/home/user")));
        assert_eq!(
            directory,
            PathBuf::from("/home/user")
                .join("AppData")
                .join("Local")
                .join("file-renamer")
                .join("logs")
        );
    }

    #[test]
    fn unix_uses_xdg_state_home() {
        let env = env_map(&[("XDG_STATE_HOME", "/state")]);
        let directory = logs_directory_from(
            |key| env.get(key).cloned(),
            false,
            Some(PathBuf::from("/home/user")),
        );
        assert_eq!(
            directory,
            PathBuf::from("/state").join("file-renamer").join("logs")
        );
    }

    #[test]
    fn unix_falls_back_to_home() {
        let directory = logs_directory_from(|_key| None, false, Some(PathBuf::from("/home/user")));
        assert_eq!(
            directory,
            PathBuf::from("/home/user")
                .join(".local")
                .join("state")
                .join("file-renamer")
                .join("logs")
        );
    }

    #[test]
    fn formats_timestamp_utc() {
        assert_eq!(format_timestamp(0), "1970-01-01 00:00:00");
        assert_eq!(format_timestamp(951_782_400), "2000-02-29 00:00:00");
        assert_eq!(format_timestamp(1_700_000_000), "2023-11-14 22:13:20");
    }

    fn set_mtime(path: &Path, seconds: u64) {
        let file = OpenOptions::new()
            .write(true)
            .open(path)
            .expect("файл должен открываться");
        let times = FileTimes::new().set_modified(UNIX_EPOCH + Duration::from_secs(seconds));
        file.set_times(times).expect("mtime должен меняться");
    }

    #[test]
    fn prune_keeps_newest_logs_and_ignores_others() {
        let temp = tempfile::tempdir().expect("tempdir");
        let directory = temp.path();
        let old = directory.join("renamer_old.log");
        let middle = directory.join("renamer_middle.log");
        let new = directory.join("renamer_new.log");
        let other = directory.join("other.log");
        for (path, seconds) in [
            (&old, 1_000_u64),
            (&middle, 2_000),
            (&new, 3_000),
            (&other, 500),
        ] {
            fs::write(path, "x").expect("файл");
            set_mtime(path, seconds);
        }

        prune_logs(directory, 2).expect("prune");

        assert!(!old.exists());
        assert!(middle.exists());
        assert!(new.exists());
        assert!(other.exists());
    }

    #[test]
    fn prune_counts_backup_files() {
        let temp = tempfile::tempdir().expect("tempdir");
        let directory = temp.path();
        let first = directory.join("renamer_first.log");
        let backup = directory.join("renamer_first.log.1");
        let newest = directory.join("renamer_new.log");
        for (path, seconds) in [(&first, 1_000_u64), (&backup, 2_000), (&newest, 3_000)] {
            fs::write(path, "x").expect("файл");
            set_mtime(path, seconds);
        }

        prune_logs(directory, 2).expect("prune");

        assert!(!first.exists());
        assert!(backup.exists());
        assert!(newest.exists());
    }

    #[test]
    fn writes_to_file() {
        let temp = tempfile::tempdir().expect("tempdir");
        let logger = Logger::open(temp.path(), 1_000, 2, 10).expect("logger");
        logger.info("hello-log");

        let log = fs::read_dir(temp.path())
            .expect("read_dir")
            .filter_map(std::result::Result::ok)
            .map(|entry| entry.path())
            .find(|path| {
                path.file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| name.starts_with(LOG_PREFIX))
            })
            .expect("лог должен существовать");
        let content = fs::read_to_string(log).expect("чтение лога");
        assert!(content.contains("hello-log"));
    }

    #[test]
    fn rotates_by_size() {
        let temp = tempfile::tempdir().expect("tempdir");
        let logger = Logger::open(temp.path(), 120, 2, 10).expect("logger");
        for _ in 0..20 {
            logger.info("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx");
        }

        let backups = fs::read_dir(temp.path())
            .expect("read_dir")
            .filter_map(std::result::Result::ok)
            .filter(|entry| entry.file_name().to_string_lossy().contains(".log."))
            .count();
        assert!(backups > 0, "должен появиться архивный файл");
    }

    #[test]
    fn logger_is_send_and_sync() {
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<Logger>();
    }
}
