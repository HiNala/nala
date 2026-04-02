//! Action confirmation workflow.
//!
//! Handles the confirm/skip/apply-all cycle when the AI proposes
//! inline edits requiring user approval.

use crossterm::event::KeyCode;

use crate::app::{App, AppMode, BackgroundEvent, Message};

impl App {
    pub(crate) fn handle_confirm_key(&mut self, code: KeyCode) {
        match code {
            KeyCode::Char('y') | KeyCode::Enter => self.apply_next_action(),
            KeyCode::Char('n') => self.skip_next_action(),
            KeyCode::Char('a') => {
                self.apply_all = true;
                self.apply_next_action();
            }
            KeyCode::Char('q') | KeyCode::Esc => self.skip_all_actions(),
            _ => {}
        }
    }

    fn apply_next_action(&mut self) {
        let Some(action) = self.pending_actions.first().cloned() else {
            self.show_next_pending_action();
            return;
        };
        let Some(bridge) = self.python_bridge.clone() else {
            self.push_message(Message::error("Bridge not available."));
            self.mode = AppMode::Ready;
            return;
        };
        let tx = self.bg_tx.clone();
        let id = action.action_id.clone();
        self.pending_actions.remove(0);
        tokio::spawn(async move {
            if let Err(e) = bridge.apply_action(id).await {
                let _ = tx
                    .send(BackgroundEvent::AssistantError(e.to_string()))
                    .await;
            }
        });
        self.show_next_pending_action();
    }

    fn skip_next_action(&mut self) {
        let Some(action) = self.pending_actions.first().cloned() else {
            self.mode = AppMode::Ready;
            return;
        };
        let Some(bridge) = self.python_bridge.clone() else {
            self.pending_actions.clear();
            self.mode = AppMode::Ready;
            return;
        };
        let id = action.action_id.clone();
        self.pending_actions.remove(0);
        let tx = self.bg_tx.clone();
        tokio::spawn(async move {
            let _ = bridge.skip_action(id).await;
            drop(tx);
        });
        self.push_message(Message::system("Skipped."));
        self.show_next_pending_action();
    }

    fn skip_all_actions(&mut self) {
        let bridge = self.python_bridge.clone();
        let ids: Vec<String> = self
            .pending_actions
            .drain(..)
            .map(|a| a.action_id)
            .collect();
        if let Some(bridge) = bridge {
            tokio::spawn(async move {
                for id in ids {
                    let _ = bridge.skip_action(id).await;
                }
            });
        }
        self.push_message(Message::system("Skipped all proposed actions."));
        self.apply_all = false;
        self.mode = AppMode::Ready;
    }

    pub(crate) fn show_next_pending_action(&mut self) {
        if let Some(next) = self.pending_actions.first() {
            if self.apply_all {
                self.apply_next_action();
            } else {
                self.push_message(Message::assistant(format!(
                    "**[{} — {}]**\n{}\n\n[y] Apply  [n] Skip  [a] Apply all  [q] Skip all",
                    next.action_type, next.description, next.preview,
                )));
                self.mode = AppMode::Confirming;
            }
        } else {
            self.apply_all = false;
            self.mode = AppMode::Ready;
        }
    }
}
