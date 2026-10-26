//! TUI на ratatui.

use std::io;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use ratatui::crossterm::cursor::{Hide, Show};
use ratatui::crossterm::event::{self, Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use ratatui::crossterm::execute;
use ratatui::layout::{Alignment, Constraint, Direction, Layout};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Wrap};
use ratatui::{DefaultTerminal, Frame};

use crate::logging::{default_logs_directory, Logger};
use crate::renamer::{FileRenamer, Outcome, RenamePlan};

const MENU_ITEMS: [&str; 4] = [
    "1. Переименование файлов и папок",
    "2. Переименование ссылок в ярлыках",
    "3. Справка",
    "4. Выход",
];

/// Запускает TUI.
///
/// # Errors
///
/// Возвращает ошибку ввода-вывода или терминала.
pub fn run(logger: Arc<Logger>) -> io::Result<()> {
    let mut terminal = match ratatui::try_init() {
        Ok(terminal) => terminal,
        Err(error) => {
            let _ = ratatui::try_restore();
            return Err(error);
        }
    };
    let mut stdout = io::stdout();
    let _ = execute!(stdout, Hide);

    let panic_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = execute!(io::stdout(), Show);
        panic_hook(info);
    }));

    let mut app = App::new(logger);
    let result = run_loop(&mut terminal, &mut app);

    let _ = execute!(stdout, Show);
    let restore = ratatui::try_restore();

    result.and(restore)
}

fn run_loop(terminal: &mut DefaultTerminal, app: &mut App) -> io::Result<()> {
    loop {
        terminal.draw(|frame| app.render(frame))?;
        if app.should_quit {
            break;
        }

        if event::poll(Duration::from_millis(250))? {
            match event::read()? {
                Event::Key(key) if key.kind == KeyEventKind::Press => {
                    app.handle_key(key);
                }
                _ => {}
            }
        }
    }

    Ok(())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Operation {
    Rename,
    Shortcuts,
}

impl Operation {
    fn title(self) -> &'static str {
        match self {
            Self::Rename => "Переименование файлов и папок",
            Self::Shortcuts => "Обновление ярлыков",
        }
    }
}

enum Screen {
    Menu,
    Path {
        operation: Operation,
        input: Vec<char>,
        cursor: usize,
        error: Option<String>,
    },
    Preview {
        operation: Operation,
        plan: Option<RenamePlan>,
        shortcuts: Vec<PathBuf>,
        scroll: usize,
        dry_run: bool,
    },
    Result {
        outcome: Outcome,
        message: String,
    },
    Help,
    Message {
        text: String,
    },
}

/// Состояние TUI.
pub struct App {
    screen: Screen,
    menu: ListState,
    logger: Arc<Logger>,
    renamer: Option<FileRenamer>,
    should_quit: bool,
}

impl App {
    /// Создает приложение с заданным журналом.
    #[must_use]
    pub fn new(logger: Arc<Logger>) -> Self {
        let mut menu = ListState::default();
        menu.select(Some(0));
        Self {
            screen: Screen::Menu,
            menu,
            logger,
            renamer: None,
            should_quit: false,
        }
    }

    /// Признак завершения работы.
    #[must_use]
    pub fn should_quit(&self) -> bool {
        self.should_quit
    }

    fn handle_key(&mut self, key: KeyEvent) {
        if key.modifiers.contains(KeyModifiers::CONTROL) && matches!(key.code, KeyCode::Char('c')) {
            self.should_quit = true;
            return;
        }

        let screen = std::mem::replace(&mut self.screen, Screen::Menu);
        self.screen = match screen {
            Screen::Menu => self.handle_menu_key(key),
            Screen::Path {
                operation,
                input,
                cursor,
                error,
            } => self.handle_path_key(key, operation, input, cursor, error),
            Screen::Preview {
                operation,
                plan,
                shortcuts,
                scroll,
                dry_run,
            } => self.handle_preview_key(key, operation, plan, shortcuts, scroll, dry_run),
            Screen::Result { outcome, message } => match key.code {
                KeyCode::Esc | KeyCode::Enter => Screen::Menu,
                _ => Screen::Result { outcome, message },
            },
            Screen::Help => match key.code {
                KeyCode::Esc | KeyCode::Enter => Screen::Menu,
                _ => Screen::Help,
            },
            Screen::Message { text } => match key.code {
                KeyCode::Esc | KeyCode::Enter => Screen::Menu,
                _ => Screen::Message { text },
            },
        };
    }

    fn handle_menu_key(&mut self, key: KeyEvent) -> Screen {
        match key.code {
            KeyCode::Up => {
                self.select_previous();
                Screen::Menu
            }
            KeyCode::Down => {
                self.select_next();
                Screen::Menu
            }
            KeyCode::Enter => {
                let operation = match self.menu.selected().unwrap_or(0) {
                    1 => Operation::Shortcuts,
                    2 => return Screen::Help,
                    3 => {
                        self.should_quit = true;
                        return Screen::Menu;
                    }
                    _ => Operation::Rename,
                };

                if operation == Operation::Shortcuts && !cfg!(windows) {
                    return Screen::Message {
                        text: "Обновление ярлыков поддерживается только в Windows.".to_owned(),
                    };
                }

                Screen::Path {
                    operation,
                    input: Vec::new(),
                    cursor: 0,
                    error: None,
                }
            }
            KeyCode::Esc | KeyCode::Char('q') => {
                self.should_quit = true;
                Screen::Menu
            }
            _ => Screen::Menu,
        }
    }

    fn handle_path_key(
        &mut self,
        key: KeyEvent,
        operation: Operation,
        mut input: Vec<char>,
        mut cursor: usize,
        error: Option<String>,
    ) -> Screen {
        let mut error = error;
        match key.code {
            KeyCode::Enter => return self.open_path(operation, &input),
            KeyCode::Esc => return Screen::Menu,
            KeyCode::Left => {
                cursor = cursor.saturating_sub(1);
            }
            KeyCode::Right => {
                cursor = (cursor + 1).min(input.len());
            }
            KeyCode::Home => cursor = 0,
            KeyCode::End => cursor = input.len(),
            KeyCode::Backspace => {
                if cursor > 0 {
                    cursor -= 1;
                    input.remove(cursor);
                    error = None;
                }
            }
            KeyCode::Delete => {
                if cursor < input.len() {
                    input.remove(cursor);
                    error = None;
                }
            }
            KeyCode::Char(value)
                if !key
                    .modifiers
                    .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT) =>
            {
                input.insert(cursor, value);
                cursor += 1;
                error = None;
            }
            _ => {}
        }

        Screen::Path {
            operation,
            input,
            cursor,
            error,
        }
    }

    fn handle_preview_key(
        &mut self,
        key: KeyEvent,
        operation: Operation,
        plan: Option<RenamePlan>,
        shortcuts: Vec<PathBuf>,
        scroll: usize,
        dry_run: bool,
    ) -> Screen {
        let line_count = match operation {
            Operation::Rename => plan
                .as_ref()
                .map_or(0, |plan| plan.items.len() + plan.errors.len()),
            Operation::Shortcuts => shortcuts.len(),
        };
        let max_scroll = line_count.saturating_sub(1);
        let scroll = scroll.min(max_scroll);

        match key.code {
            KeyCode::Esc => Screen::Menu,
            KeyCode::Up => Screen::Preview {
                operation,
                plan,
                shortcuts,
                scroll: scroll.saturating_sub(1),
                dry_run,
            },
            KeyCode::Down => Screen::Preview {
                operation,
                plan,
                shortcuts,
                scroll: scroll.saturating_add(1).min(max_scroll),
                dry_run,
            },
            KeyCode::Char('d') | KeyCode::Char('D') => Screen::Preview {
                operation,
                plan,
                shortcuts,
                scroll,
                dry_run: !dry_run,
            },
            KeyCode::Enter => self.apply_preview(operation, plan, shortcuts, dry_run),
            _ => Screen::Preview {
                operation,
                plan,
                shortcuts,
                scroll,
                dry_run,
            },
        }
    }

    fn open_path(&mut self, operation: Operation, input: &[char]) -> Screen {
        let path: String = input.iter().collect();
        let path = path.trim();

        if path.is_empty() {
            return Screen::Path {
                operation,
                input: input.to_vec(),
                cursor: input.len(),
                error: Some("Путь не указан".to_owned()),
            };
        }

        let renamer = FileRenamer::with_logger(path, Arc::clone(&self.logger));
        if let Err(error) = renamer.validate_directory() {
            return Screen::Path {
                operation,
                input: input.to_vec(),
                cursor: input.len(),
                error: Some(error.to_string()),
            };
        }

        match operation {
            Operation::Rename => match renamer.build_plan(true) {
                Ok(plan) => {
                    self.renamer = Some(renamer);
                    Screen::Preview {
                        operation,
                        plan: Some(plan),
                        shortcuts: Vec::new(),
                        scroll: 0,
                        dry_run: false,
                    }
                }
                Err(error) => Screen::Path {
                    operation,
                    input: input.to_vec(),
                    cursor: input.len(),
                    error: Some(error.to_string()),
                },
            },
            Operation::Shortcuts => match renamer.get_shortcut_list() {
                Ok(shortcuts) => {
                    self.renamer = Some(renamer);
                    Screen::Preview {
                        operation,
                        plan: None,
                        shortcuts,
                        scroll: 0,
                        dry_run: false,
                    }
                }
                Err(error) => Screen::Path {
                    operation,
                    input: input.to_vec(),
                    cursor: input.len(),
                    error: Some(error.to_string()),
                },
            },
        }
    }

    fn apply_preview(
        &mut self,
        operation: Operation,
        plan: Option<RenamePlan>,
        shortcuts: Vec<PathBuf>,
        dry_run: bool,
    ) -> Screen {
        let Some(renamer) = self.renamer.as_ref() else {
            return Screen::Message {
                text: "Каталог не выбран".to_owned(),
            };
        };

        match operation {
            Operation::Rename => {
                let Some(plan) = plan else {
                    return Screen::Message {
                        text: "План не построен".to_owned(),
                    };
                };

                if dry_run {
                    let outcome = Outcome {
                        renamed: 0,
                        failed: plan.errors.len(),
                        planned: plan.items.len(),
                    };
                    return Screen::Result {
                        outcome,
                        message: "dry-run: изменения не применены".to_owned(),
                    };
                }

                let outcome = renamer.apply_plan(&plan);
                let message = if outcome.failed == 0 {
                    "Переименование завершено".to_owned()
                } else {
                    format!("Завершено с ошибками: {}", outcome.failed)
                };
                Screen::Result { outcome, message }
            }
            Operation::Shortcuts => {
                if dry_run {
                    return Screen::Result {
                        outcome: Outcome {
                            renamed: 0,
                            failed: 0,
                            planned: shortcuts.len(),
                        },
                        message: "dry-run: ярлыки не изменены".to_owned(),
                    };
                }

                let mut renamed = 0;
                let mut failed = 0;
                let mut first_error = None;
                for shortcut in &shortcuts {
                    match renamer.rename_shortcut_target(shortcut) {
                        Ok(()) => renamed += 1,
                        Err(error) => {
                            failed += 1;
                            self.logger.error(format!(
                                "Ошибка при модификации ярлыка {}: {error}",
                                shortcut.display()
                            ));
                            if first_error.is_none() {
                                first_error = Some(error.to_string());
                            }
                        }
                    }
                }

                self.logger.info(format!(
                    "Успешно модифицировано ярлыков: {renamed}, ошибок {failed}"
                ));
                let message = first_error.map_or_else(
                    || "Ярлыки обновлены".to_owned(),
                    |error| {
                        format!("Обновлено: {renamed}, ошибок: {failed}. Первая ошибка: {error}")
                    },
                );
                Screen::Result {
                    outcome: Outcome {
                        renamed,
                        failed,
                        planned: shortcuts.len(),
                    },
                    message,
                }
            }
        }
    }

    fn select_previous(&mut self) {
        let current = self.menu.selected().unwrap_or(0);
        let next = if current == 0 {
            MENU_ITEMS.len() - 1
        } else {
            current - 1
        };
        self.menu.select(Some(next));
    }

    fn select_next(&mut self) {
        let current = self.menu.selected().unwrap_or(0);
        self.menu.select(Some((current + 1) % MENU_ITEMS.len()));
    }

    fn render(&mut self, frame: &mut Frame) {
        match &self.screen {
            Screen::Menu => self.render_menu(frame),
            Screen::Path {
                operation,
                input,
                cursor,
                error,
            } => {
                render_path(frame, *operation, input, *cursor, error.as_deref());
            }
            Screen::Preview {
                operation,
                plan,
                shortcuts,
                scroll,
                dry_run,
            } => render_preview(
                frame,
                *operation,
                plan.as_ref(),
                shortcuts,
                *scroll,
                *dry_run,
            ),
            Screen::Result { outcome, message } => {
                render_result(frame, *outcome, message);
            }
            Screen::Help => render_help(frame),
            Screen::Message { text } => render_message(frame, text),
        }
    }

    fn render_menu(&mut self, frame: &mut Frame) {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(3),
                Constraint::Min(5),
                Constraint::Length(3),
            ])
            .split(frame.area());

        let header = Paragraph::new(Line::from(Span::styled(
            "file-renamer",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )))
        .alignment(Alignment::Center)
        .block(block("Rust + ratatui"));
        frame.render_widget(header, chunks[0]);

        let items: Vec<ListItem> = MENU_ITEMS.iter().map(|item| ListItem::new(*item)).collect();
        let list = List::new(items)
            .block(block("Меню"))
            .highlight_style(
                Style::default()
                    .bg(Color::Cyan)
                    .fg(Color::Black)
                    .add_modifier(Modifier::BOLD),
            )
            .highlight_symbol(">> ");
        frame.render_stateful_widget(list, chunks[1], &mut self.menu);

        frame.render_widget(hint("↑/↓ — выбор, Enter — открыть, q — выход"), chunks[2]);
    }
}

fn block(title: &str) -> Block<'static> {
    Block::default()
        .borders(Borders::ALL)
        .title(title.to_owned())
}

fn hint(text: &str) -> Paragraph<'static> {
    Paragraph::new(text.to_owned())
        .alignment(Alignment::Center)
        .block(Block::default().borders(Borders::ALL))
}

fn render_path(
    frame: &mut Frame,
    operation: Operation,
    input: &[char],
    cursor: usize,
    error: Option<&str>,
) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Length(3),
            Constraint::Min(3),
            Constraint::Length(3),
        ])
        .split(frame.area());

    frame.render_widget(
        Paragraph::new(operation.title()).block(block("Путь к каталогу")),
        chunks[0],
    );

    let text: String = input.iter().collect();
    let cursor_marker = if cursor <= input.len() {
        let (before, after): (String, String) = (
            text.chars().take(cursor).collect(),
            text.chars().skip(cursor).collect(),
        );
        format!("{before}|{after}")
    } else {
        format!("{text}|")
    };
    frame.render_widget(
        Paragraph::new(cursor_marker).block(Block::default().borders(Borders::ALL).title("Ввод")),
        chunks[1],
    );

    let error_text = error.unwrap_or("Введите путь и нажмите Enter. Esc — вернуться в меню.");
    let style = if error.is_some() {
        Style::default().fg(Color::Red)
    } else {
        Style::default().fg(Color::Gray)
    };
    frame.render_widget(
        Paragraph::new(error_text)
            .style(style)
            .wrap(Wrap { trim: false }),
        chunks[2],
    );

    frame.render_widget(
        hint("Enter — построить план, Esc — назад, Ctrl+C — выход"),
        chunks[3],
    );
}

fn render_preview(
    frame: &mut Frame,
    operation: Operation,
    plan: Option<&RenamePlan>,
    shortcuts: &[PathBuf],
    scroll: usize,
    dry_run: bool,
) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(4),
            Constraint::Min(5),
            Constraint::Length(3),
        ])
        .split(frame.area());

    let mode = if dry_run {
        Span::styled("dry-run", Style::default().fg(Color::Yellow))
    } else {
        Span::styled("применение", Style::default().fg(Color::Green))
    };
    let header = Paragraph::new(Text::from(vec![
        Line::from(operation.title()),
        Line::from(vec![
            Span::raw("Режим: "),
            mode,
            Span::raw(format!(
                "  Объектов: {}",
                plan.map_or(shortcuts.len(), |plan| plan.items.len())
            )),
        ]),
    ]))
    .block(block("Предпросмотр"));
    frame.render_widget(header, chunks[0]);

    let mut lines = Vec::new();
    match operation {
        Operation::Rename => {
            if let Some(plan) = plan {
                for item in &plan.items {
                    lines.push(Line::from(format!(
                        "{} -> {}",
                        item.source.display(),
                        item.target.display()
                    )));
                }
                for error in &plan.errors {
                    lines.push(Line::from(Span::styled(
                        format!("! {}: {}", error.path.display(), error.reason),
                        Style::default().fg(Color::Red),
                    )));
                }
            }
        }
        Operation::Shortcuts => {
            for shortcut in shortcuts {
                lines.push(Line::from(format!("ярлык -> {}", shortcut.display())));
            }
        }
    }

    if lines.is_empty() {
        lines.push(Line::from("Нет объектов для обработки."));
    }

    let body = Paragraph::new(Text::from(lines))
        .block(block("План"))
        .wrap(Wrap { trim: false })
        .scroll((u16::try_from(scroll).unwrap_or(u16::MAX), 0));
    frame.render_widget(body, chunks[1]);

    let footer = if dry_run {
        "Enter — применить (dry-run), d — выключить dry-run, Esc — назад"
    } else {
        "Enter — применить, d — dry-run, Esc — назад"
    };
    frame.render_widget(hint(footer), chunks[2]);
}

fn render_result(frame: &mut Frame, outcome: Outcome, message: &str) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(5), Constraint::Length(3)])
        .split(frame.area());

    let color = if outcome.failed == 0 {
        Color::Green
    } else {
        Color::Yellow
    };
    let text = Text::from(vec![
        Line::from(Span::styled(message.to_owned(), Style::default().fg(color))),
        Line::from(""),
        Line::from(format!("Успешно: {}", outcome.renamed)),
        Line::from(format!("Ошибок: {}", outcome.failed)),
        Line::from(format!("В плане: {}", outcome.planned)),
    ]);
    frame.render_widget(
        Paragraph::new(text)
            .block(block("Результат"))
            .alignment(Alignment::Center),
        chunks[0],
    );
    frame.render_widget(hint("Enter/Esc — в меню"), chunks[1]);
}

fn render_help(frame: &mut Frame) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(5), Constraint::Length(3)])
        .split(frame.area());

    let text = Text::from(vec![
        Line::from(Span::styled(
            format!("file-renamer {}", crate::VERSION),
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
        Line::from("Меняет дату ДД.ММ.ГГ на ГГГГ.ММ.ДД в именах файлов,"),
        Line::from("папок и целей ярлыков Windows."),
        Line::from(""),
        Line::from("Двузначный год: 69-99 -> 1969-1999, 00-68 -> 2000-2068."),
        Line::from("Сначала переименуйте файлы и папки, затем ярлыки."),
        Line::from("Перед изменениями показывается план и запрашивается подтверждение."),
        Line::from(""),
        Line::from("Клавиши: ↑/↓ — навигация, Enter — выбор, Esc — назад,"),
        Line::from("d — dry-run, Ctrl+C — выход."),
        Line::from(""),
        Line::from(format!("Журнал: {}", default_logs_directory().display())),
    ]);
    frame.render_widget(
        Paragraph::new(text)
            .block(block("Справка"))
            .wrap(Wrap { trim: false }),
        chunks[0],
    );
    frame.render_widget(hint("Enter/Esc — в меню"), chunks[1]);
}

fn render_message(frame: &mut Frame, text: &str) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(5), Constraint::Length(3)])
        .split(frame.area());
    frame.render_widget(
        Paragraph::new(text.to_owned())
            .block(block("Сообщение"))
            .wrap(Wrap { trim: false }),
        chunks[0],
    );
    frame.render_widget(hint("Enter/Esc — в меню"), chunks[1]);
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;
    use std::fs;
    use tempfile::TempDir;

    fn app() -> App {
        App::new(Arc::new(Logger::disabled()))
    }

    fn press(app: &mut App, code: KeyCode) {
        app.handle_key(KeyEvent::new(code, KeyModifiers::NONE));
    }

    fn type_text(app: &mut App, text: &str) {
        for character in text.chars() {
            press(app, KeyCode::Char(character));
        }
    }

    fn render_text(app: &mut App) -> String {
        let backend = TestBackend::new(120, 40);
        let mut terminal = Terminal::new(backend).expect("terminal");
        terminal.draw(|frame| app.render(frame)).expect("draw");
        terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(ratatui::buffer::Cell::symbol)
            .collect()
    }

    fn temp_with_file() -> (TempDir, PathBuf) {
        let temp = TempDir::new().expect("tempdir");
        let source = temp.path().join("26.10.25 file.txt");
        fs::write(&source, b"data").expect("файл");
        (temp, source)
    }

    #[test]
    fn menu_is_rendered() {
        let mut app = app();
        let text = render_text(&mut app);
        assert!(text.contains("Переименование файлов и папок"));
        assert!(text.contains("Выход"));
    }

    #[test]
    fn menu_navigates_with_arrows() {
        let mut app = app();
        press(&mut app, KeyCode::Down);
        assert_eq!(app.menu.selected(), Some(1));
        press(&mut app, KeyCode::Up);
        assert_eq!(app.menu.selected(), Some(0));
    }

    #[test]
    fn path_input_supports_editing() {
        let mut app = app();
        press(&mut app, KeyCode::Enter);
        type_text(&mut app, "abc");
        press(&mut app, KeyCode::Backspace);
        let text = render_text(&mut app);
        assert!(text.contains("ab|"));
    }

    #[test]
    fn rename_flow_applies_plan() {
        let (temp, _source) = temp_with_file();
        let mut app = app();

        press(&mut app, KeyCode::Enter);
        type_text(&mut app, &temp.path().display().to_string());
        press(&mut app, KeyCode::Enter);

        let preview = render_text(&mut app);
        assert!(preview.contains("2025.10.26 file.txt"));
        assert!(preview.contains("Предпросмотр"));

        press(&mut app, KeyCode::Enter);

        let result = render_text(&mut app);
        assert!(result.contains("Результат"));
        assert!(temp.path().join("2025.10.26 file.txt").exists());
    }

    #[test]
    fn dry_run_does_not_rename() {
        let (temp, source) = temp_with_file();
        let mut app = app();

        press(&mut app, KeyCode::Enter);
        type_text(&mut app, &temp.path().display().to_string());
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Char('d'));
        press(&mut app, KeyCode::Enter);

        let result = render_text(&mut app);
        assert!(result.contains("dry-run"));
        assert!(source.exists());
        assert!(!temp.path().join("2025.10.26 file.txt").exists());
    }

    #[test]
    fn escape_returns_to_menu() {
        let mut app = app();
        press(&mut app, KeyCode::Enter);
        press(&mut app, KeyCode::Esc);
        assert!(matches!(app.screen, Screen::Menu));
    }

    #[test]
    fn help_contains_version() {
        let mut app = app();
        press(&mut app, KeyCode::Down);
        press(&mut app, KeyCode::Down);
        press(&mut app, KeyCode::Enter);
        let text = render_text(&mut app);
        assert!(text.contains(crate::VERSION));
    }

    #[cfg(not(windows))]
    #[test]
    fn shortcuts_are_windows_only() {
        let mut app = app();
        press(&mut app, KeyCode::Down);
        press(&mut app, KeyCode::Enter);
        let text = render_text(&mut app);
        assert!(text.contains("только в Windows"));
    }
}
