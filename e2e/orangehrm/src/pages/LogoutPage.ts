import { Page, expect } from '@playwright/test';
import { waitForPageLoad, retryAction } from '../utils/helpers';
import { captureScreenshot } from '../utils/screenshotHelper';
import { logStep } from '../utils/logger';
import { LoginPage } from './LoginPage';

export class LogoutPage {
  constructor(private page: Page) {}

  async logout() {
    await retryAction(async () => {
      await this.page.locator('.oxd-userdropdown').first().click();
      await this.page.getByRole('menuitem', { name: 'Logout' }).click();
    }, 'logout');
    await waitForPageLoad(this.page);
    await captureScreenshot(this.page, 'logout');
    const login = new LoginPage(this.page);
    await login.assertLoginFormVisible();
    logStep('Logout', 'pass');
  }
}
