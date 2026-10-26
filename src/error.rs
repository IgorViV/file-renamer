//! Ошибки приложения.

use std::fmt;
use std::io;

/// Результат операций библиотеки.
pub type Result<T> = std::result::Result<T, Error>;

/// Ошибки переименования и работы с ярлыками.
#[derive(Debug)]
pub enum Error {
    /// Ошибка ввода-вывода.
    Io(io::Error),
    /// В имени нет даты ДД.ММ.ГГ.
    MissingDate {
        /// Исходное имя.
        name: String,
    },
    /// В имени нет корректной даты ДД.ММ.ГГ.
    InvalidDate {
        /// Исходное имя.
        name: String,
        /// Некорректный фрагмент даты.
        raw: String,
    },
    /// Ошибка разбора пути.
    InvalidPath(String),
    /// Некорректный каталог.
    Directory(String),
    /// Ошибка при работе с ярлыком.
    Shortcut(String),
    /// Ошибка журналирования.
    Logging(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(f, "{error}"),
            Self::MissingDate { name } => {
                write!(f, "в имени '{name}' нет даты ДД.ММ.ГГ")
            }
            Self::InvalidDate { name, raw } => {
                write!(f, "некорректная дата '{raw}' в имени '{name}'")
            }
            Self::InvalidPath(message) => write!(f, "некорректный путь: {message}"),
            Self::Directory(message) => write!(f, "{message}"),
            Self::Shortcut(message) => write!(f, "{message}"),
            Self::Logging(message) => write!(f, "ошибка журналирования: {message}"),
        }
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for Error {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}
