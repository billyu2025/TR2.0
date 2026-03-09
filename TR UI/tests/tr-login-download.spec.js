// @ts-check
import { test, expect } from '@playwright/test';

const UI_BASE = process.env.UI_BASE || 'http://127.0.0.1:8000';
const LOGIN_USER = process.env.TR_USERNAME || 'Henry';
const LOGIN_PASS = process.env.TR_PASSWORD || 'Henry';

function resolveCredentials(workerIndex) {
  const raw = process.env.TR_USER_LIST_JSON;
  if (!raw) {
    return { username: LOGIN_USER, password: LOGIN_PASS };
  }

  try {
    const userList = JSON.parse(raw);
    if (Array.isArray(userList) && userList.length > 0) {
      const picked = userList[workerIndex % userList.length];
      if (picked?.username && picked?.password) {
        return { username: picked.username, password: picked.password };
      }
    }
  } catch {
    // fall back to single user
  }

  return { username: LOGIN_USER, password: LOGIN_PASS };
}

test.describe('TR login and DD No download flow', () => {
  test('login -> open stockist tab -> download by DD No', async ({ page }, testInfo) => {
    test.setTimeout(300000);
    const creds = resolveCredentials(testInfo.workerIndex);

    // Auto-accept confirm/alert dialogs used by this page.
    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    async function loginOnce() {
      await page.goto(`${UI_BASE}/login.html`, { waitUntil: 'domcontentloaded' });
      await page.locator('#username').fill(creds.username);
      await page.locator('#password').fill(creds.password);
      await page.getByRole('button', { name: /登入/ }).click();
      await page.waitForTimeout(1200);

      const loginError = page.locator('.error-message');
      if (await loginError.count()) {
        const msg = (await loginError.first().textContent())?.trim();
        if (msg) {
          throw new Error(`Login failed on UI: ${msg}`);
        }
      }

      // Login page may either show success text first or redirect soon after.
      // Do not hard-fail on sessionStorage timing differences across environments.
      await Promise.race([
        page.waitForURL(/tr-records\.html/i, { timeout: 6000 }).catch(() => null),
        page.locator('.success-message').waitFor({ state: 'visible', timeout: 6000 }).catch(() => null),
      ]);
    }

    await loginOnce();

    // Always navigate to TR records explicitly (login success is token-based).
    await page.goto(`${UI_BASE}/tr-records.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle');

    // If redirected back to login, credentials/token are invalid.
    if (/login\.html/i.test(page.url())) {
      // Token may have been cleared by concurrent actions; retry login once.
      await loginOnce();
      await page.goto(`${UI_BASE}/tr-records.html`, { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle');
    }

    if (/login\.html/i.test(page.url())) {
      throw new Error(
        `Navigation redirected to login.html after retry. Verify account/session policy. ` +
        `Current worker=${testInfo.workerIndex}, username=${creds.username}`
      );
    }

    // Header is rendered by Vue after mount; allow more time.
    await expect(page.locator('h1')).toContainText('TR記錄管理', { timeout: 30000 });

    // Switch to "STOCKIST & TEST REPORT" tab.
    await page.getByRole('button', { name: /STOCKIST\s*&\s*TEST REPORT/i }).click();

    // Wait table to render and select the first record.
    const firstCheckbox = page.locator('.record-checkbox').first();
    await expect(firstCheckbox).toBeVisible({ timeout: 30000 });
    await firstCheckbox.check();

    const ddNoDownloadBtn = page.getByRole('button', { name: /按DD_No下載/ });
    await expect(ddNoDownloadBtn).toBeEnabled();

    // The page creates a blob download after background task completion.
    const downloadPromise = page.waitForEvent('download', { timeout: 300000 });
    await ddNoDownloadBtn.click();
    const download = await downloadPromise;

    const suggestedName = download.suggestedFilename();
    expect(suggestedName.toLowerCase()).toContain('.zip');
  });
});

