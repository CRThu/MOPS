import { test, expect } from '@playwright/test';

test.describe('MOPS GUI E2E End-to-End Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the backend REST API endpoints for E2E browser environment
    await page.route('**/api/v1/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          message: 'success',
          data: {
            hostname: 'E2E-PC',
            client_port: 10081,
            server_port: 10080,
            api_port: 10082,
            client_enabled: true,
            server_enabled: true,
            system_proxy: { enabled: true, proxy_server: '127.0.0.1:10081' },
            speed_up: 1536.0,
            speed_down: 4096.0,
            total_nodes: 2,
            online_nodes: 2,
            download_dir: './downloads',
          },
        }),
      });
    });

    await page.route('**/api/v1/nodes', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          message: 'success',
          data: [
            {
              id: 'E2E-PC@127.0.0.1:10080',
              hostname: 'E2E-PC',
              ip: '127.0.0.1',
              port: 10080,
              is_me: true,
              status: 'ONLINE',
            },
            {
              id: 'Remote-Mac@192.168.1.88:10080',
              hostname: 'Remote-Mac',
              ip: '192.168.1.88',
              port: 10080,
              is_me: false,
              status: 'ONLINE',
            },
          ],
        }),
      });
    });

    await page.route('**/api/v1/files/progress', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          message: 'success',
          data: null,
        }),
      });
    });
  });

  test('should load compact popover header, node list and professional copy', async ({ page }) => {
    await page.goto('http://localhost:1420');

    // Header assertions with professional copy
    await expect(page.getByText('MOPS Proxy')).toBeVisible();
    await expect(page.getByText('上行 UPLOAD')).toBeVisible();
    await expect(page.getByText('下行 DOWNLOAD')).toBeVisible();
    await expect(page.getByText('系统代理 System Proxy')).toBeVisible();

    // System Proxy IP:Port input & confirm button assertions
    const proxyInput = page.getByRole('textbox', { name: '系统代理地址' });
    await expect(proxyInput).toBeVisible();
    await expect(proxyInput).toHaveValue('127.0.0.1:10081');
    await expect(page.getByRole('button', { name: '确定保存代理地址' })).toBeVisible();

    // Node list assertions
    await expect(page.getByText('E2E-PC')).toBeVisible();
    await expect(page.getByText('Remote-Mac')).toBeVisible();
    await expect(page.getByRole('button', { name: '传输文件' })).toBeVisible();
  });

  test('should render window control buttons for desktop widget mode', async ({ page }) => {
    await page.goto('http://localhost:1420');

    // Verify minimize to tray and close buttons are visible
    const minimizeBtn = page.getByRole('button', { name: '最小化到托盘' });
    const closeBtn = page.getByRole('button', { name: '关闭应用' });

    await expect(minimizeBtn).toBeVisible();
    await expect(closeBtn).toBeVisible();
  });
});

