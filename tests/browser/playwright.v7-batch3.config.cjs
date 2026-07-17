module.exports = {
  testDir: ".",
  testMatch: "v7-batch3.spec.cjs",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8018",
    browserName: "chromium",
    headless: true,
    launchOptions: {
      executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    }
  },
  reporter: [["list"]]
};
