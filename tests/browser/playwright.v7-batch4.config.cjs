const fs = require("fs");
const path = require("path");

const edgePath = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const launchOptions = process.platform === "win32" && fs.existsSync(edgePath)
  ? { executablePath: edgePath }
  : {};

/** @type {import('@playwright/test').PlaywrightTestConfig} */
module.exports = {
  testDir: ".",
  testMatch: "v7-batch4.spec.cjs",
  timeout: 90_000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8019",
    browserName: "chromium",
    headless: true,
    launchOptions
  },
  webServer: {
    command: "python -c \"from pathlib import Path; Path('test-results/v7-batch4-browser.db').unlink(missing_ok=True)\" && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8019",
    cwd: path.resolve(__dirname, "../.."),
    url: "http://127.0.0.1:8019/api/health",
    reuseExistingServer: !process.env.CI,
    timeout: 90_000,
    env: {
      APP_ENV: "development",
      CORS_ORIGINS: "http://127.0.0.1:8019",
      LLM_PROVIDER: "mock",
      EMBEDDING_PROVIDER: "mock",
      LLM_ENV_FILE: ".missing-v7-batch4-browser.env",
      EMBEDDING_ENV_FILE: ".missing-v7-batch4-browser.env",
      SQLITE_DATABASE_PATH: "test-results/v7-batch4-browser.db"
    }
  },
  reporter: [["list"], ["html", { outputFolder: "test-results/playwright-report", open: "never" }]]
};
