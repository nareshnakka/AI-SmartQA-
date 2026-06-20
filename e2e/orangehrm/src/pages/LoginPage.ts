import { Page, expect } from '@playwright/test';
import { TEST_DATA } from '../fixtures/testData';
import { waitForPageLoad, retryAction, publishLiveFrame } from '../utils/helpers';
import { logStep } from '../utils/logger';

export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto(TEST_DATA.loginUrl);
    await waitForPageLoad(this.page);
    await publishLiveFrame(this.page);
  }

  async assertLoginFormVisible() {
    await expect(this.page.getByPlaceholder('Username')).toBeVisible();
    await expect(this.page.getByPlaceholder('Password')).toBeVisible();
    await expect(this.page.getByRole('button', { name: 'Login' })).toBeVisible();
  }

  async login(username = TEST_DATA.username, password = TEST_DATA.password) {
    await retryAction(async () => {
      logStep('Enter username in input[name=username]', 'info');
      await this.page.getByPlaceholder('Username').fill(username);
      logStep('Enter username in input[name=username]', 'pass');
      logStep('Enter password', 'info');
      await this.page.getByPlaceholder('Password').fill(password);
      logStep('Enter password', 'pass');
      logStep('Click login button', 'info');
      await this.page.getByRole('button', { name: 'Login' }).click();
      logStep('Click login button', 'pass');
    }, 'login');
    await waitForPageLoad(this.page);
    await publishLiveFrame(this.page);
  }

  async assertDashboardLoaded() {
    await expect(this.page).toHaveURL(/dashboard/);
    logStep(`Post-login URL: ${this.page.url()}`, 'pass');
    await expect(this.page.locator('.oxd-main-menu').first()).toBeVisible();
    await expect(this.page.locator('.oxd-userdropdown').first()).toBeVisible();
    logStep(`Logged in — dashboard: ${await this.page.title()}`, 'pass');
  }
}
