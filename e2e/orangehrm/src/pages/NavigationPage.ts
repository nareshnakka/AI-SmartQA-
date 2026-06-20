import { Page, expect } from '@playwright/test';
import { waitForPageLoad, retryAction, expectHeaderContains, timed, publishLiveFrame } from '../utils/helpers';
import { captureScreenshot } from '../utils/screenshotHelper';
import { logStep } from '../utils/logger';

export class NavigationPage {
  constructor(private page: Page) {}

  async clickMenu(label: string) {
    // Return to main app shell if stuck on maintenance/auth overlay
    if (this.page.url().includes('/maintenance')) {
      await this.page.locator('.oxd-main-menu-item').filter({ hasText: 'Dashboard' }).first().click().catch(() => {});
      await waitForPageLoad(this.page);
    }
    const sidebar = this.page.locator('.oxd-main-menu').first();
    const item = this.page.locator('.oxd-main-menu-item').filter({ hasText: label }).first();
    await retryAction(async () => {
      await sidebar.evaluate((el) => el.scrollTo(0, el.scrollHeight)).catch(() => {});
      await item.scrollIntoViewIfNeeded();
      await item.click({ timeout: 5_000 });
    }, `click menu ${label}`, 15_000);
    await waitForPageLoad(this.page);
    await publishLiveFrame(this.page);
  }

  async navigateAndValidate(
    label: string,
    urlPart: string,
    header: string,
    screenshotName: string,
    extra?: () => Promise<void>
  ) {
    const { durationMs } = await timed(async () => {
      await this.clickMenu(label);
      await expect(this.page).toHaveURL(new RegExp(urlPart.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), { timeout: 15_000 });
      await expectHeaderContains(this.page, header);
      if (extra) await extra();
      await captureScreenshot(this.page, screenshotName);
      await publishLiveFrame(this.page);
    });
    logStep(`Navigate ${label}`, 'pass', `header=${header}`, durationMs);
  }

  async validateDashboard() {
    await this.clickMenu('Dashboard');
    await expectHeaderContains(this.page, 'Dashboard');
    await expect(this.page.locator('.orangehrm-dashboard-widget').first()).toBeVisible({ timeout: 10_000 });
    await captureScreenshot(this.page, 'dashboard');
    await publishLiveFrame(this.page);
    logStep('Dashboard validation', 'pass');
  }

  async validateAdminDeep() {
    await expect(this.page.getByText('User Management').first()).toBeVisible();
    await expect(this.page.locator('.oxd-table-body').first()).toBeVisible();
    await this.page.getByText('User Management').first().click();
    await expect(this.page.getByRole('button', { name: 'Search' }).first()).toBeVisible();
    await expect(this.page.getByRole('button', { name: 'Reset' }).first()).toBeVisible();
  }

  async validateRecruitmentTabs() {
    await expect(this.page.getByRole('link', { name: 'Candidates' }).first()).toBeVisible();
    await this.page.getByRole('link', { name: 'Vacancies' }).first().click();
    await waitForPageLoad(this.page);
    await expect(this.page).toHaveURL(/viewJobVacancy|vacanc/i);
  }

  async returnToDashboard() {
    if (!this.page.url().includes('/dashboard')) {
      await this.page.goto('/web/index.php/dashboard/index');
      await waitForPageLoad(this.page);
    }
  }

  async handleMaintenancePassword(password: string) {
    const confirm = this.page.getByPlaceholder('Password');
    if (await confirm.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await confirm.fill(password);
      await this.page.getByRole('button', { name: 'Confirm' }).click();
      await waitForPageLoad(this.page);
    }
  }
}
