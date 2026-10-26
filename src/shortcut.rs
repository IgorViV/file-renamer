//! Обновление целевых путей ярлыков.

use crate::error::{Error, Result};
use std::path::Path;

/// Операции с ярлыком, которые нужны переименователю.
pub trait ShortcutBackend: Send + Sync {
    /// Читает целевой путь ярлыка.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если ярлык не удалось прочитать.
    fn read_target(&self, lnk: &Path) -> Result<String>;

    /// Меняет целевой путь, сохраняя остальные свойства ярлыка.
    ///
    /// # Errors
    ///
    /// Возвращает ошибку, если ярлык не удалось обновить.
    fn update_target(&self, lnk: &Path, target: &str) -> Result<()>;
}

/// Заглушка для платформ без поддержки ярлыков.
pub struct UnsupportedShortcutBackend;

impl ShortcutBackend for UnsupportedShortcutBackend {
    fn read_target(&self, _lnk: &Path) -> Result<String> {
        Err(Error::Shortcut(
            "обновление ярлыков поддерживается только в Windows".to_owned(),
        ))
    }

    fn update_target(&self, _lnk: &Path, _target: &str) -> Result<()> {
        Err(Error::Shortcut(
            "обновление ярлыков поддерживается только в Windows".to_owned(),
        ))
    }
}

/// Возвращает бэкенд ярлыков для текущей платформы.
#[must_use]
pub fn default_backend() -> Box<dyn ShortcutBackend> {
    #[cfg(windows)]
    {
        Box::new(WindowsShortcutBackend)
    }
    #[cfg(not(windows))]
    {
        Box::new(UnsupportedShortcutBackend)
    }
}

#[cfg(windows)]
pub use windows_backend::{create_shortcut, WindowsShortcutBackend};

#[cfg(windows)]
#[allow(unsafe_code)]
mod windows_backend {
    use super::{Error, Path, Result, ShortcutBackend};
    use windows::core::{IUnknown, Interface, PCWSTR};
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoUninitialize, IPersistFile, CLSCTX_INPROC_SERVER,
        COINIT_APARTMENTTHREADED, STGM_READWRITE,
    };
    use windows::Win32::UI::Shell::{IShellLinkW, ShellLink, SLGP_RAWPATH};

    const PATH_BUFFER_LEN: usize = 32_768;

    /// Обновляет ярлыки через COM `IShellLinkW`/`IPersistFile`.
    pub struct WindowsShortcutBackend;

    impl ShortcutBackend for WindowsShortcutBackend {
        fn read_target(&self, lnk: &Path) -> Result<String> {
            let _com = ComGuard::new();
            let lnk_wide = wide_path(lnk);

            let shell: IShellLinkW =
                unsafe { CoCreateInstance(&ShellLink, None::<&IUnknown>, CLSCTX_INPROC_SERVER) }
                    .map_err(|error| com_error("CoCreateInstance", error))?;
            let persist: IPersistFile = shell
                .cast()
                .map_err(|error| com_error("IShellLinkW -> IPersistFile", error))?;

            unsafe { persist.Load(PCWSTR::from_raw(lnk_wide.as_ptr()), STGM_READWRITE) }
                .map_err(|error| com_error("IPersistFile::Load", error))?;

            let mut buffer = vec![0_u16; PATH_BUFFER_LEN];
            unsafe { shell.GetPath(&mut buffer, std::ptr::null_mut(), SLGP_RAWPATH.0 as u32) }
                .map_err(|error| com_error("IShellLinkW::GetPath", error))?;

            let len = buffer
                .iter()
                .position(|value| *value == 0)
                .unwrap_or(buffer.len());
            if len == 0 {
                return Err(Error::Shortcut(format!(
                    "у ярлыка не задан целевой путь: {}",
                    lnk.display()
                )));
            }

            Ok(String::from_utf16_lossy(&buffer[..len]))
        }

        fn update_target(&self, lnk: &Path, target: &str) -> Result<()> {
            let _com = ComGuard::new();
            let lnk_wide = wide_path(lnk);
            let target_wide = wide_str(target);

            let shell: IShellLinkW =
                unsafe { CoCreateInstance(&ShellLink, None::<&IUnknown>, CLSCTX_INPROC_SERVER) }
                    .map_err(|error| com_error("CoCreateInstance", error))?;
            let persist: IPersistFile = shell
                .cast()
                .map_err(|error| com_error("IShellLinkW -> IPersistFile", error))?;

            unsafe { persist.Load(PCWSTR::from_raw(lnk_wide.as_ptr()), STGM_READWRITE) }
                .map_err(|error| com_error("IPersistFile::Load", error))?;
            unsafe { shell.SetPath(PCWSTR::from_raw(target_wide.as_ptr())) }
                .map_err(|error| com_error("IShellLinkW::SetPath", error))?;
            unsafe { persist.Save(PCWSTR::from_raw(lnk_wide.as_ptr()), true) }
                .map_err(|error| com_error("IPersistFile::Save", error))?;

            Ok(())
        }
    }

    /// Создает новый ярлык, указывающий на `target`.
    pub fn create_shortcut(lnk: &Path, target: &str) -> Result<()> {
        let _com = ComGuard::new();
        let lnk_wide = wide_path(lnk);
        let target_wide = wide_str(target);

        let shell: IShellLinkW =
            unsafe { CoCreateInstance(&ShellLink, None::<&IUnknown>, CLSCTX_INPROC_SERVER) }
                .map_err(|error| com_error("CoCreateInstance", error))?;
        let persist: IPersistFile = shell
            .cast()
            .map_err(|error| com_error("IShellLinkW -> IPersistFile", error))?;

        unsafe { shell.SetPath(PCWSTR::from_raw(target_wide.as_ptr())) }
            .map_err(|error| com_error("IShellLinkW::SetPath", error))?;
        unsafe { persist.Save(PCWSTR::from_raw(lnk_wide.as_ptr()), true) }
            .map_err(|error| com_error("IPersistFile::Save", error))?;

        Ok(())
    }

    fn com_error(action: &str, error: windows::core::Error) -> Error {
        Error::Shortcut(format!("{action}: {error}"))
    }

    fn wide_str(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(std::iter::once(0)).collect()
    }

    fn wide_path(path: &Path) -> Vec<u16> {
        wide_str(&path.to_string_lossy())
    }

    struct ComGuard {
        uninitialize: bool,
    }

    impl ComGuard {
        fn new() -> Self {
            // SAFETY: CoInitializeEx вызывается на текущем потоке; CoUninitialize
            // выполняется только при успешной инициализации.
            let result = unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED) };
            Self {
                uninitialize: result.is_ok(),
            }
        }
    }

    impl Drop for ComGuard {
        fn drop(&mut self) {
            if self.uninitialize {
                // SAFETY: парная к успешному CoInitializeEx в new().
                unsafe { CoUninitialize() };
            }
        }
    }
}
