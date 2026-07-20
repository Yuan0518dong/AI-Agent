const baseConfig = require("./playwright.v7-batch4.config.cjs");

module.exports = {
  ...baseConfig,
  testMatch: "v7-batch4-demo-video.spec.cjs",
  timeout: 150_000
};
