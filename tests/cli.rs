//! Интеграционный тест бинарника.

use std::io::Write;
use std::process::{Command, Stdio};

use tempfile::TempDir;

#[test]
fn binary_renames_file_after_confirmation() {
    let directory = TempDir::new().expect("tempdir");
    let logs = TempDir::new().expect("logs");
    let source = directory.path().join("26.10.25 file.txt");
    std::fs::write(&source, b"data").expect("файл");

    let mut child = Command::new(env!("CARGO_BIN_EXE_file-renamer"))
        .env("FILE_RENAMER_LOG_DIR", logs.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("бинарник должен запускаться");

    {
        let stdin = child.stdin.as_mut().expect("stdin");
        write!(stdin, "1\n{}\nn\ny\n\n4\n", directory.path().display()).expect("ввод");
    }

    let output = child.wait_with_output().expect("вывод");
    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(directory.path().join("2025.10.26 file.txt").exists());
}
