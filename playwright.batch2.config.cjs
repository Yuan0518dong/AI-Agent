/** @type {import('@playwright/test').PlaywrightTestConfig} */
module.exports = {
  testDir: "./tests/browser",
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8015",
    browserName: "chromium",
    headless: true,
    launchOptions: {
      executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    }
  },
  reporter: [["list"]]
};
