import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';
import { NavigationPage } from '../pages/NavigationPage';
import { LogoutPage } from '../pages/LogoutPage';
import { TEST_DATA } from '../fixtures/testData';
import { captureScreenshot } from '../utils/screenshotHelper';
import { clearLog, getExecutionLog, logStep } from '../utils/logger';
import { assertNoJsErrors, waitForPageLoad } from '../utils/helpers';

test.describe('OrangeHRM End-to-End Navigation', () => {
  const jsErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    clearLog();
    jsErrors.length = 0;
    page.on('pageerror', (err) => jsErrors.push(err.message));
  });

  test('Flow 1-15: Login, all menus, logout with evidence', async ({ page }) => {
    const login = new LoginPage(page);
    const nav = new NavigationPage(page);
    const logout = new LogoutPage(page);

    // Flow 1 — Login
    await login.goto();
    await login.assertLoginFormVisible();
    logStep('Login page loaded', 'pass');
    await login.login();
    await login.assertDashboardLoaded();
    await captureScreenshot(page, 'dashboard-loaded');
    logStep('Login successful', 'pass');

    // Flow 2 — Dashboard
    await nav.validateDashboard();

    // Flow 3 — Admin
    await nav.navigateAndValidate('Admin', '/admin', 'Admin', 'admin', () => nav.validateAdminDeep());

    // Flow 4 — PIM
    await nav.navigateAndValidate('PIM', '/pim', 'PIM', 'pim', async () => {
      await expect(page.locator('.oxd-table-body').first()).toBeVisible();
    });

    // Flow 5 — Leave
    await nav.navigateAndValidate('Leave', '/leave', 'Leave', 'leave', async () => {
      await expect(page.getByRole('button', { name: 'Search' }).first()).toBeVisible();
    });

    // Flow 6 — Time
    await nav.navigateAndValidate('Time', '/time', 'Time', 'time', async () => {
      await expect(page.getByText('Select Employee').first()).toBeVisible();
    });

    // Flow 7 — Recruitment
    await nav.navigateAndValidate('Recruitment', '/recruitment', 'Recruitment', 'recruitment', () =>
      nav.validateRecruitmentTabs()
    );

    // Flow 8 — My Info
    await nav.navigateAndValidate('My Info', '/pim/viewMyDetails', 'PIM', 'myinfo', async () => {
      await expect(page.getByRole('link', { name: 'Personal Details' }).first()).toBeVisible();
      await expect(page.locator('.orangehrm-edit-employee-image-wrapper').first()).toBeVisible();
    });

    // Flow 9 — Performance
    await nav.navigateAndValidate('Performance', '/performance', 'Performance', 'performance', async () => {
      await expect(page.getByRole('button', { name: 'Search' }).first()).toBeVisible();
    });

    // Flow 10 — Dashboard return
    await nav.navigateAndValidate('Dashboard', '/dashboard', 'Dashboard', 'dashboard-return');

    // Flow 11 — Directory
    await nav.navigateAndValidate('Directory', '/directory', 'Directory', 'directory', async () => {
      await expect(page.getByRole('button', { name: 'Search' }).first()).toBeVisible();
    });

    // Flow 12 — Maintenance
    await nav.clickMenu('Maintenance');
    await nav.handleMaintenancePassword(TEST_DATA.password);
    await expect(page).toHaveURL(/maintenance/);
    await captureScreenshot(page, 'maintenance');
    logStep('Maintenance', 'pass');
    await nav.returnToDashboard();

    // Flow 13 — Claim (optional on some demo builds)
    const claimItem = page.locator('.oxd-main-menu-item').filter({ hasText: 'Claim' }).first();
    if (await claimItem.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await nav.navigateAndValidate('Claim', '/claim', 'Claim', 'claim');
    } else {
      logStep('Navigate Claim', 'info', 'Claim menu not available on this demo build — skipped');
    }

    // Flow 14 — Buzz (optional — removed from some OrangeHRM demo builds)
    const buzzItem = page.locator('.oxd-main-menu-item').filter({ hasText: 'Buzz' }).first();
    if (await buzzItem.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await nav.navigateAndValidate('Buzz', '/buzz', 'Buzz', 'buzz', async () => {
        const feed = page.locator('.orangehrm-buzz-module, .oxd-buzz-module, [class*="buzz"]').first();
        await expect(feed).toBeVisible({ timeout: 10_000 });
      });
    } else {
      logStep('Navigate Buzz', 'info', 'Buzz menu not available on this demo build — skipped');
    }

    // Flow 15 — Logout
    await logout.logout();

    await assertNoJsErrors(page, jsErrors);

    const log = getExecutionLog();
    expect(log.filter((e) => e.status === 'fail')).toHaveLength(0);
    expect(log.length).toBeGreaterThanOrEqual(12);
  });
});
