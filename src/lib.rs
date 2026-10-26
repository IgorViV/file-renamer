//! Утилита для переименования дат в именах файлов, папок и ярлыков.

pub mod date;
pub mod error;
pub mod logging;
pub mod paths;
pub mod renamer;
pub mod shortcut;
pub mod test_data;
pub mod tui;

pub use error::{Error, Result};
pub use renamer::{FileRenamer, Outcome, PlanError, PlanItem, RenamePlan};

/// Версия пакета.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
