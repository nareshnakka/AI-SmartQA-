import { Page, expect } from '@playwright/test';
import { TEST_DATA } from '../fixtures/testData';
import { waitForPageLoad, retryAction } from '../utils/helpers';

export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto(TEST_DATA.loginUrl);
    await waitForPageLoad(this.page);
  }

  async assertLoginFormVisible() {
    await expect(this.page.getByPlaceholder('Username')).toBeVisible();
    await expect(this.page.getByPlaceholder('Password')).toBeVisible();
    await expect(this.page.getByRole('button', { name: 'Login' })).toBeVisible();
  }

  async login(username = TEST_DATA.username, password = TEST_DATA.password) {
    await retryAction(async () => {
      await this.page.getByPlaceholder('Username').fill(username);
      await this.page.getByPlaceholder('Password').fill(password);
      await this.page.getByRole('button', { name: 'Login' }).click();
    }, 'login');
    await waitForPageLoad(this.page);
  }

  async assertDashboardLoaded() {
    await expect(this.page).toHaveURL(/dashboard/);
    await expect(this.page.locator('.oxd-main-menu').first()).toBeVisible();
    await expect(this.page.locator('.oxd-userdropdown').first()).toBeVisible();
  }
}
