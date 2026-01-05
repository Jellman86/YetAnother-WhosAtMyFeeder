
const { chromium } = require('playwright-core');

(async () => {
  let browser;
  try {
    console.log('Connecting to Playwright service...');
    browser = await chromium.connect('ws://playwright-service:3000');
    const page = await browser.newPage();
    
    console.log('Navigating to frontend...');
    await page.goto('http://yawamf-frontend', { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(5000); // Wait for animations
    
    console.log('Capturing screenshot...');
    await page.screenshot({ path: 'ui_state.png', fullPage: true });
    
    console.log('Collecting console logs...');
    page.on('console', msg => console.log(`BROWSER [${msg.type()}] ${msg.text()}`));
    
    await browser.close();
    console.log('Inspection complete.');
  } catch (err) {
    console.error('Inspection failed:', err);
    if (browser) await browser.close();
    process.exit(1);
  }
})();
