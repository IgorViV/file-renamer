//! Разбор и форматирование дат `ДД.ММ.ГГ`.

use std::fmt;
use std::time::{SystemTime, UNIX_EPOCH};

/// Длина префикса даты в имени.
pub const DATE_PREFIX_LEN: usize = 8;

/// Календарная дата.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Date {
    /// Год.
    pub year: i32,
    /// Месяц (1-12).
    pub month: u32,
    /// День (1-31).
    pub day: u32,
}

impl Date {
    /// Форматирует дату как `ГГГГ.ММ.ДД`.
    #[must_use]
    pub fn to_yyyy_mm_dd(self) -> String {
        format!("{:04}.{:02}.{:02}", self.year, self.month, self.day)
    }

    /// Форматирует дату как `ДД.ММ.ГГ`.
    #[must_use]
    pub fn to_ddmmyy(self) -> String {
        format!(
            "{:02}.{:02}.{:02}",
            self.day,
            self.month,
            self.year.rem_euclid(100)
        )
    }

    /// Создает дату по количеству дней с 1 января 1970 года.
    #[must_use]
    pub fn from_epoch_days(days: i64) -> Self {
        let days = days + 719_468;
        let era = if days >= 0 { days } else { days - 146_096 } / 146_097;
        let day_of_era = days - era * 146_097;
        let year_of_era =
            (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
        let mut year = year_of_era + era * 400;
        let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
        let month_index = (5 * day_of_year + 2) / 153;
        let day = day_of_year - (153 * month_index + 2) / 5 + 1;
        let month = if month_index < 10 {
            month_index + 3
        } else {
            month_index - 9
        };
        if month <= 2 {
            year += 1;
        }

        Self {
            year: i32::try_from(year).unwrap_or(1970),
            month: u32::try_from(month).unwrap_or(1),
            day: u32::try_from(day).unwrap_or(1),
        }
    }
}

/// Возвращает текущие сутки как количество дней с 1 января 1970 года (UTC).
#[must_use]
pub fn today_epoch_days() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| i64::try_from(duration.as_secs() / 86_400).unwrap_or(0))
        .unwrap_or(0)
}

/// Ошибка разбора даты.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DateError {
    /// Некорректный фрагмент.
    pub raw: String,
}

impl fmt::Display for DateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "некорректная дата '{}'", self.raw)
    }
}

impl std::error::Error for DateError {}

/// Проверяет, является ли год високосным.
#[must_use]
pub fn is_leap_year(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

/// Возвращает число дней в месяце.
#[must_use]
pub fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap_year(year) => 29,
        2 => 28,
        _ => 0,
    }
}

fn is_ascii_date_shape(bytes: &[u8]) -> bool {
    bytes.len() >= DATE_PREFIX_LEN
        && bytes[0].is_ascii_digit()
        && bytes[1].is_ascii_digit()
        && bytes[2] == b'.'
        && bytes[3].is_ascii_digit()
        && bytes[4].is_ascii_digit()
        && bytes[5] == b'.'
        && bytes[6].is_ascii_digit()
        && bytes[7].is_ascii_digit()
}

/// Проверяет, что имя начинается с даты `ДД.ММ.ГГ` (без требования пробела).
#[must_use]
pub fn looks_like_date_prefix(name: &str) -> bool {
    is_ascii_date_shape(name.as_bytes())
}

/// Проверяет соответствие маске `[0-3][0-9].[0-1][0-9].[0-9][0-9] *`.
#[must_use]
pub fn matches_mask(name: &str) -> bool {
    let bytes = name.as_bytes();
    is_ascii_date_shape(bytes)
        && bytes.len() > DATE_PREFIX_LEN
        && (b'0'..=b'3').contains(&bytes[0])
        && (b'0'..=b'1').contains(&bytes[3])
        && bytes[DATE_PREFIX_LEN] == b' '
}

/// Разбирает дату `ДД.ММ.ГГ`.
///
/// Двузначный год: 69-99 -> 1969-1999, 00-68 -> 2000-2068.
///
/// # Errors
///
/// Возвращает ошибку, если формат или календарная дата некорректны.
pub fn parse_date(raw: &str) -> Result<Date, DateError> {
    let bytes = raw.as_bytes();
    if !is_ascii_date_shape(bytes) || bytes.len() != DATE_PREFIX_LEN {
        return Err(DateError {
            raw: raw.to_owned(),
        });
    }

    let day = u32::from(raw[0..2].parse::<u8>().unwrap_or(0));
    let month = u32::from(raw[3..5].parse::<u8>().unwrap_or(0));
    let short_year = i32::from(raw[6..8].parse::<u8>().unwrap_or(0));
    let year = if short_year >= 69 {
        1900 + short_year
    } else {
        2000 + short_year
    };

    if month == 0 || month > 12 || day == 0 || day > days_in_month(year, month) {
        return Err(DateError {
            raw: raw.to_owned(),
        });
    }

    Ok(Date { year, month, day })
}

/// Переводит префикс компонента пути из `ДД.ММ.ГГ` в `ГГГГ.ММ.ДД`.
///
/// # Errors
///
/// Возвращает ошибку, если компонент начинается с даты, но она невалидна.
pub fn convert_component(component: &str) -> Result<String, DateError> {
    if !looks_like_date_prefix(component) {
        return Ok(component.to_owned());
    }

    let raw = &component[..DATE_PREFIX_LEN];
    let date = parse_date(raw)?;
    Ok(format!(
        "{}{}",
        date.to_yyyy_mm_dd(),
        &component[DATE_PREFIX_LEN..]
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_valid_date() {
        let date = parse_date("26.10.25").expect("дата должна разбираться");
        assert_eq!(
            date,
            Date {
                year: 2025,
                month: 10,
                day: 26
            }
        );
        assert_eq!(date.to_yyyy_mm_dd(), "2025.10.26");
    }

    #[test]
    fn accepts_leap_day() {
        assert!(parse_date("29.02.24").is_ok());
        assert!(parse_date("29.02.00").is_ok());
        assert!(parse_date("29.02.2000").is_err());
    }

    #[test]
    fn rejects_invalid_calendar_dates() {
        for raw in ["29.02.25", "31.04.25", "00.00.00", "39.19.99"] {
            assert!(parse_date(raw).is_err(), "должна быть ошибка для {raw}");
        }
    }

    #[test]
    fn maps_two_digit_year_window() {
        assert_eq!(parse_date("01.01.69").unwrap().year, 1969);
        assert_eq!(parse_date("01.01.99").unwrap().year, 1999);
        assert_eq!(parse_date("01.01.00").unwrap().year, 2000);
        assert_eq!(parse_date("01.01.68").unwrap().year, 2068);
    }

    #[test]
    fn mask_requires_space_after_date() {
        assert!(matches_mask("26.10.25 file.txt"));
        assert!(!matches_mask("26.10.25file.txt"));
        assert!(!matches_mask("26.10.25"));
        assert!(!matches_mask("49.10.25 file.txt"));
        assert!(!matches_mask("46.10.25 file.txt"));
    }

    #[test]
    fn mask_accepts_impossible_calendar_date() {
        assert!(matches_mask("39.19.99 bad.txt"));
        assert!(parse_date("39.19.99").is_err());
    }

    #[test]
    fn converts_only_date_prefix() {
        assert_eq!(
            convert_component("26.10.25 26.10.25.txt").unwrap(),
            "2025.10.26 26.10.25.txt"
        );
        assert_eq!(convert_component("обычное имя").unwrap(), "обычное имя");
        assert!(convert_component("39.19.99 bad").is_err());
    }

    #[test]
    fn converts_component_without_space() {
        assert_eq!(
            convert_component("26.10.25file.txt").unwrap(),
            "2025.10.26file.txt"
        );
        assert!(!matches_mask("26.10.25file.txt"));
    }

    #[test]
    fn converts_epoch_days_and_formats_ddmmyy() {
        assert_eq!(
            Date::from_epoch_days(0),
            Date {
                year: 1970,
                month: 1,
                day: 1
            }
        );
        assert_eq!(
            Date::from_epoch_days(11_016),
            Date {
                year: 2000,
                month: 2,
                day: 29
            }
        );
        assert_eq!(
            Date::from_epoch_days(-1),
            Date {
                year: 1969,
                month: 12,
                day: 31
            }
        );
        assert_eq!(
            Date {
                year: 2025,
                month: 10,
                day: 26
            }
            .to_ddmmyy(),
            "26.10.25"
        );
    }

    #[test]
    fn handles_non_ascii_names() {
        assert!(!looks_like_date_prefix("пятница"));
        assert!(!matches_mask("пятница"));
    }
}
