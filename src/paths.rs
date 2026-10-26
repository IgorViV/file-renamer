//! Преобразование дат в компонентах путей Windows.

use crate::date;
use crate::error::{Error, Result};

fn push_component(result: &mut String, component: &str) -> Result<()> {
    match date::convert_component(component) {
        Ok(converted) => {
            result.push_str(&converted);
            Ok(())
        }
        Err(error) => Err(Error::InvalidDate {
            name: component.to_owned(),
            raw: error.raw,
        }),
    }
}

fn is_separator(byte: u8) -> bool {
    byte == b'\\' || byte == b'/'
}

/// Заменяет `ДД.ММ.ГГ` на `ГГГГ.ММ.ДД` во всех компонентах пути.
///
/// Разделители (`\` и `/`) сохраняются, поэтому функция одинаково работает
/// с локальными, сетевыми (UNC) и смешанными путями Windows.
///
/// # Errors
///
/// Возвращает ошибку, если в пути есть компонент с некорректной датой.
pub fn update_folder_dates(path: &str) -> Result<String> {
    let bytes = path.as_bytes();
    let mut result = String::with_capacity(path.len());
    let mut start = 0;
    let mut index = 0;

    while index < bytes.len() {
        if is_separator(bytes[index]) {
            if start < index {
                push_component(&mut result, &path[start..index])?;
            }
            while index < bytes.len() && is_separator(bytes[index]) {
                result.push(char::from(bytes[index]));
                index += 1;
            }
            start = index;
        } else {
            index += 1;
        }
    }

    if start < bytes.len() {
        push_component(&mut result, &path[start..])?;
    }

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn converts_windows_file_path() {
        assert_eq!(
            update_folder_dates(r"C:\26.10.25 folder\26.10.25 file.txt").unwrap(),
            r"C:\2025.10.26 folder\2025.10.26 file.txt"
        );
    }

    #[test]
    fn preserves_unc_prefix() {
        assert_eq!(
            update_folder_dates(r"\\server\share\26.10.25 folder\file.txt").unwrap(),
            r"\\server\share\2025.10.26 folder\file.txt"
        );
    }

    #[test]
    fn supports_forward_slashes() {
        assert_eq!(
            update_folder_dates("C:/26.10.25 folder/file.txt").unwrap(),
            "C:/2025.10.26 folder/file.txt"
        );
    }

    #[test]
    fn preserves_mixed_and_repeated_separators() {
        assert_eq!(
            update_folder_dates("C:\\26.10.25 folder//26.10.25 file.txt").unwrap(),
            "C:\\2025.10.26 folder//2025.10.26 file.txt"
        );
    }

    #[test]
    fn preserves_trailing_separator() {
        assert_eq!(
            update_folder_dates("C:\\26.10.25 folder\\").unwrap(),
            "C:\\2025.10.26 folder\\"
        );
    }

    #[test]
    fn leaves_path_without_date_unchanged() {
        let path = r"C:\folder\file.txt";
        assert_eq!(update_folder_dates(path).unwrap(), path);
    }

    #[test]
    fn replaces_only_prefix_of_each_component() {
        assert_eq!(
            update_folder_dates(r"C:\26.10.25 folder\26.10.25 26.10.25.txt").unwrap(),
            r"C:\2025.10.26 folder\2025.10.26 26.10.25.txt"
        );
    }

    #[test]
    fn keeps_drive_and_empty_path() {
        assert_eq!(update_folder_dates("C:").unwrap(), "C:");
        assert_eq!(update_folder_dates("").unwrap(), "");
    }

    #[test]
    fn reports_invalid_date_with_component_name() {
        let error = update_folder_dates(r"C:\31.04.25 folder\file.txt").unwrap_err();
        assert!(matches!(
            error,
            Error::InvalidDate { ref name, ref raw }
                if name == "31.04.25 folder" && raw == "31.04.25"
        ));
    }

    #[test]
    fn handles_unicode_components() {
        assert_eq!(
            update_folder_dates(r"C:\26.10.25 папка\файл.txt").unwrap(),
            r"C:\2025.10.26 папка\файл.txt"
        );
    }
}
