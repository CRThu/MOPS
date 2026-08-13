/**
 * Tauri Native Capabilities Adapter
 * Wraps Tauri 2.0 native dialog, window controls, and tray APIs with fallback for Web Browser testing environments
 */

export async function selectFile(): Promise<string | null> {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog');
    const selected = await open({
      multiple: false,
      directory: false,
      title: '选择传输文件',
    });
    if (typeof selected === 'string') {
      return selected;
    }
    return null;
  } catch (err) {
    console.warn('[Tauri API] Native dialog plugin not found or running in browser mode fallback.');
    return null;
  }
}

export async function selectFolder(): Promise<string | null> {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog');
    const selected = await open({
      multiple: false,
      directory: true,
      title: '选择文件保存路径',
    });
    if (typeof selected === 'string') {
      return selected;
    }
    return null;
  } catch (err) {
    console.warn('[Tauri API] Native directory plugin not found or running in browser mode fallback.');
    return null;
  }
}

export async function minimizeWindow(): Promise<void> {
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('minimize_window');
  } catch (err) {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      const appWindow = getCurrentWindow();
      await appWindow.hide();
    } catch {
      console.warn('[Tauri API] Window hide/minimize fallback');
    }
  }
}

export async function closeWindow(): Promise<void> {
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('close_window');
  } catch (err) {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      const appWindow = getCurrentWindow();
      await appWindow.close();
    } catch {
      console.warn('[Tauri API] Window close fallback');
    }
  }
}

export async function startDragWindow(): Promise<void> {
  try {
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    const appWindow = getCurrentWindow();
    await appWindow.startDragging();
  } catch (err) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('start_drag');
    } catch {
      // Browser fallback
    }
  }
}
