// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent,
};

struct DaemonState(Mutex<Option<Child>>);

fn is_daemon_running() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:10082".parse().unwrap(),
        Duration::from_millis(500),
    )
    .is_ok()
}

fn resolve_mops_executable() -> Option<PathBuf> {
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(dir) = exe_path.parent() {
            let mops_same = dir.join("mops.exe");
            if mops_same.exists() {
                return Some(mops_same);
            }
            let mops_bin = dir.join("bin").join("mops.exe");
            if mops_bin.exists() {
                return Some(mops_bin);
            }
            if let Some(parent) = dir.parent() {
                let mops_parent = parent.join("mops.exe");
                if mops_parent.exists() {
                    return Some(mops_parent);
                }
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        let mops_cwd = cwd.join("bin").join("mops.exe");
        if mops_cwd.exists() {
            return Some(mops_cwd);
        }
        let mops_direct = cwd.join("mops.exe");
        if mops_direct.exists() {
            return Some(mops_direct);
        }
    }
    None
}

fn start_daemon_if_needed(app_handle: &tauri::AppHandle) {
    if is_daemon_running() {
        return;
    }

    if let Some(exe_path) = resolve_mops_executable() {
        let mut cmd = Command::new(&exe_path);
        cmd.arg("run");

        if let Some(parent_dir) = exe_path.parent() {
            cmd.current_dir(parent_dir);
            let log_dir = parent_dir.join("logs");
            let _ = std::fs::create_dir_all(&log_dir);
            if let Ok(f) = std::fs::File::create(log_dir.join("mops-daemon.log")) {
                if let Ok(f_err) = f.try_clone() {
                    cmd.stdout(f);
                    cmd.stderr(f_err);
                }
            }
        }

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        if let Ok(child) = cmd.spawn() {
            let state = app_handle.state::<DaemonState>();
            let mut lock = state.0.lock().unwrap();
            *lock = Some(child);
            
            // Poll for daemon readiness (up to 3 seconds)
            for _ in 0..15 {
                if is_daemon_running() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(200));
            }
        } else {
            use tauri_plugin_dialog::{DialogExt, MessageDialogKind};
            app_handle
                .dialog()
                .message("启动 mops.exe 后端守护进程失败！\n请检查文件权限或是否有安全软件拦截。")
                .title("MOPS 启动失败")
                .kind(MessageDialogKind::Error)
                .show(|_| {});
        }
    } else {
        use tauri_plugin_dialog::{DialogExt, MessageDialogKind};
        app_handle
            .dialog()
            .message("未找到 mops.exe 后端内核文件！\n\n请确认已将 mops.exe 与 MOPS Desktop.exe 放置在同一个文件夹（或 bin/ 目录下）。")
            .title("MOPS 后端未找到")
            .kind(MessageDialogKind::Error)
            .show(|_| {});
    }
}

fn cleanup_daemon(app_handle: &tauri::AppHandle) {
    let state = app_handle.state::<DaemonState>();
    let mut lock = state.0.lock().unwrap();
    if let Some(mut child) = lock.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[tauri::command]
fn minimize_window(window: tauri::Window) {
    let _ = window.hide();
}

#[tauri::command]
fn close_window(window: tauri::Window) {
    let _ = window.close();
}

#[tauri::command]
fn start_drag(window: tauri::Window) {
    let _ = window.start_dragging();
}

fn main() {
    let app = tauri::Builder::default()
        .manage(DaemonState(Mutex::new(None)))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .invoke_handler(tauri::generate_handler![
            minimize_window,
            close_window,
            start_drag
        ])
        .setup(|app| {
            // Build Tray Menu
            let show_item = MenuItemBuilder::with_id("show", "显示主界面").build(app)?;
            let quit_item = MenuItemBuilder::with_id("quit", "退出 MOPS").build(app)?;
            let menu = MenuBuilder::new(app)
                .items(&[&show_item, &quit_item])
                .build()?;

            // Build Tray Icon using app default window icon
            let icon = app.default_window_icon().cloned().expect("no default app icon");
            let _tray = TrayIconBuilder::new()
                .icon(icon)
                .menu(&menu)
                .on_menu_event(|app_handle, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(window) = app_handle.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => {
                        cleanup_daemon(app_handle);
                        app_handle.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| match event {
                    TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } => {
                        let app_handle = tray.app_handle();
                        if let Some(window) = app_handle.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                            }
                        }
                    }
                    _ => {}
                })
                .build(app)?;

            // Auto-start backend daemon if needed
            start_daemon_if_needed(app.handle());

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| match event {
        RunEvent::ExitRequested { .. } => {
            cleanup_daemon(app_handle);
        }
        _ => {}
    });
}
