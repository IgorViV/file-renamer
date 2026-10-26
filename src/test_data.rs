//! Генератор тестовых каталогов, файлов и ярлыков.

use std::fs;
use std::path::{Path, PathBuf};

use crate::date::{today_epoch_days, Date};
use crate::error::Result;

/// Генерирует тестовые данные и возвращает число созданных объектов.
///
/// # Errors
///
/// Возвращает ошибку, если не удалось создать каталог, файл или ярлык.
pub fn generate(base: &Path, depth: usize, seed: u64, create_shortcuts: bool) -> Result<usize> {
    fs::create_dir_all(base)?;
    if depth == 0 {
        return Ok(0);
    }

    #[cfg(not(windows))]
    let _ = create_shortcuts;

    let mut rng = Lcg::new(seed);
    let today = today_epoch_days();
    let mut created = 0;
    create_level(base, depth, &mut rng, today, create_shortcuts, &mut created)?;
    Ok(created)
}

#[cfg_attr(not(windows), allow(clippy::only_used_in_recursion))]
fn create_level(
    base: &Path,
    depth_left: usize,
    rng: &mut Lcg,
    today: i64,
    create_shortcuts: bool,
    created: &mut usize,
) -> Result<()> {
    if depth_left == 0 {
        return Ok(());
    }

    let offset = i64::try_from(rng.range(0, 365)).unwrap_or(0);
    let date = Date::from_epoch_days(today + offset);
    let prefix = date.to_ddmmyy();

    let shortcuts_dir = base.join(format!("{prefix} shortcuts"));
    fs::create_dir_all(&shortcuts_dir)?;
    *created += 1;

    for folder_index in 0..rng.range(1, 3) {
        let folder = base.join(format!("{prefix} folder-{folder_index}"));
        fs::create_dir_all(&folder)?;
        *created += 1;

        for file_index in 0..rng.range(1, 3) {
            let file = folder.join(format!("{prefix} file-{file_index}.txt"));
            fs::write(
                &file,
                format!("Этот файл {file_index} создан для проверки file-renamer"),
            )?;
            *created += 1;

            #[cfg(windows)]
            if create_shortcuts {
                let cut = shortcuts_dir.join(format!("{prefix} shortcut_to_file_{file_index}.lnk"));
                let target = std::path::absolute(&file).unwrap_or_else(|_| file.clone());
                crate::shortcut::create_shortcut(&cut, &target.to_string_lossy())?;
                *created += 1;
            }
        }

        create_level(
            &folder,
            depth_left - 1,
            rng,
            today,
            create_shortcuts,
            created,
        )?;
    }

    Ok(())
}

struct Lcg(u64);

impl Lcg {
    fn new(seed: u64) -> Self {
        Self(seed ^ 0x9E37_79B9_7F4A_7C15)
    }

    fn next(&mut self) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        self.0
    }

    fn range(&mut self, min: u64, max: u64) -> u64 {
        min + self.next() % (max - min + 1)
    }
}

/// Возвращает все относительные пути внутри каталога.
///
/// # Errors
///
/// Возвращает ошибку, если каталог невозможно прочитать.
pub fn relative_entries(base: &Path) -> Result<Vec<PathBuf>> {
    let mut entries = Vec::new();
    let mut stack = vec![base.to_path_buf()];

    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            let path = entry.path();
            if entry.file_type()?.is_dir() {
                stack.push(path.clone());
            }
            if let Ok(relative) = path.strip_prefix(base) {
                entries.push(relative.to_path_buf());
            }
        }
    }

    entries.sort();
    Ok(entries)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::date::matches_mask;
    use std::collections::HashSet;
    use tempfile::TempDir;

    fn entry_names(temp: &TempDir) -> Vec<String> {
        relative_entries(temp.path())
            .expect("entries")
            .into_iter()
            .filter_map(|path| {
                path.file_name()
                    .map(|name| name.to_string_lossy().into_owned())
            })
            .collect()
    }

    #[test]
    fn creates_dated_entries() {
        let temp = TempDir::new().expect("tempdir");

        let created = generate(temp.path(), 2, 7, false).expect("generate");
        let names = entry_names(&temp);

        assert_eq!(created, names.len());
        assert!(!names.is_empty());
        for name in names {
            assert!(matches_mask(&name), "неожиданное имя: {name}");
        }
    }

    #[test]
    fn generation_is_reproducible() {
        let first = TempDir::new().expect("tempdir");
        let second = TempDir::new().expect("tempdir");

        generate(first.path(), 2, 42, false).expect("first");
        generate(second.path(), 2, 42, false).expect("second");

        assert_eq!(
            relative_entries(first.path()).unwrap(),
            relative_entries(second.path()).unwrap()
        );
    }

    #[test]
    fn zero_depth_creates_nothing() {
        let temp = TempDir::new().expect("tempdir");
        let created = generate(temp.path(), 0, 1, false).expect("generate");
        assert_eq!(created, 0);
        assert!(relative_entries(temp.path()).unwrap().is_empty());
    }

    #[cfg(not(windows))]
    #[test]
    fn no_shortcuts_outside_windows() {
        let temp = TempDir::new().expect("tempdir");
        generate(temp.path(), 1, 1, true).expect("generate");
        let shortcuts: Vec<_> = relative_entries(temp.path())
            .unwrap()
            .into_iter()
            .filter(|path| {
                path.extension()
                    .is_some_and(|extension| extension.eq_ignore_ascii_case("lnk"))
            })
            .collect();
        assert!(shortcuts.is_empty());
    }

    #[test]
    fn relative_entries_are_unique() {
        let temp = TempDir::new().expect("tempdir");
        generate(temp.path(), 1, 3, false).expect("generate");
        let entries = relative_entries(temp.path()).unwrap();
        let unique: HashSet<_> = entries.iter().collect();
        assert_eq!(entries.len(), unique.len());
    }
}
