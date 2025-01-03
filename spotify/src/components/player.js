const puppeteer = require("puppeteer");
const config = require("config");
const { launch, getStream } = require("puppeteer-stream");

let browser = null;
let page = null;
let access_token = null;

// Read config
const deviceName = config.get("deviceName");
const restartOnError = config.get("restartOnError");

const firefox = {
  headless: true,
  extraPrefsFirefox: {
    "media.gmp-manager.updateEnabled": true,
    "media.eme.enabled": true,
    "media.autoplay.default": 0,
  },
  protocol: "webDriverBiDi",
  browser: "firefox",
};

const chrome = {
  args: ["--headless=new"],
  ignoreDefaultArgs: ["--mute-audio", "--disable-component-update"],
  channel: "chrome",
};

const raspberry = {
  headless: true,
  dumpio: true,
  extraPrefsFirefox: {
    "media.gmp-manager.updateEnabled": true,
    "media.eme.enabled": true,
    "media.autoplay.default": 0,
  },
  protocol: "webDriverBiDi",
  browser: "firefox",
  executablePath: "/usr/bin/firefox",
};

const raspberry_chromium = {
  headless: "new",
  dumpio: true,
  ignoreDefaultArgs: ["--mute-audio"],
  args: ["--disable-gpu"],
  executablePath: "/usr/bin/chromium-browser",
};

const start = async () => {
  const selected = config.get("browser");
  let browserConf = chrome;
  switch (selected) {
    case "firefox":
      browserConf = firefox;
      break;
    case "raspberry":
      browserConf = raspberry;
      break;
    case "raspberry_chromium":
      browserConf = raspberry_chromium;
      break;
  }
  browser = await launch(chrome);
  page = await browser.newPage();
  page.on("pageerror", (err) => {
    // page error
    if (restartOnError) {
      reset();
    }
  });
  // About logging errors, see this: https://github.com/puppeteer/puppeteer/issues/1512
};

const connect = async (getToken) => {
  // Start system first but only once
  if (page == null || page == undefined) {
    await start();
  } else {
    return;
  }

  access_token = getToken();
  await page.goto("http://localhost:5000/play");
  await page.waitForSelector(".ready");

  // Do not use static token
  await page.exposeFunction("getToken", getToken);

  await page.evaluate(async (deviceName) => {
    window.player = new window.Spotify.Player({
      name: deviceName,
      getOAuthToken: (cb) => {
        window.getToken().then((access_token) => {
          cb(access_token);
        });
      },
      volume: 0.5,
    });
  }, deviceName);

  await page.evaluate(async () => {
    window.player.addListener("ready", ({ device_id }) => {});

    window.player.addListener("not_ready", ({ device_id }) => {});

    window.player.addListener("initialization_error", ({ message }) => {
      console.error(message);
    });

    window.player.addListener("authentication_error", ({ message }) => {
      console.error(message);
    });

    window.player.addListener("account_error", ({ message }) => {
      console.error(message);
    });

    window.player.addListener("playback_error", ({ message }) => {
      console.error(message);
    });

    window.player.addListener("autoplay_failed", ({ message }) => {
      console.error(message);
    });

    window.player.connect().then((success) => {
      if (success) {
      } else {
        console.error("The Web Playback SDK could not connect to Spotify.");
      }
    });
  });
  const stream = await getStream(page, { audio: true, video: true });

  stream.pipe(process.stdout);
};

// Toggle play/pause
const playPause = async () => {
  return await page.evaluate(async () => await window.player.togglePlay());
};

// Previous track
const prevTrack = async () => {
  await page.evaluate(async () => await window.player.previousTrack());
};

// Next track
const nextTrack = async () => {
  await page.evaluate(async () => await window.player.nextTrack());
};

// Stop the instance
const stop = async () => {
  await browser.close();
};

const reset = async () => {
  return await page.evaluate(async () => {
    await window.player.disconnect();
    window.player.connect().then((success) => {});
  });
};

// Get status info
const status = async () => {
  return await page.evaluate(async () => await window.player.getCurrentState());
};

exports.connect = connect;
exports.stop = stop;
exports.playPause = playPause;
exports.prevTrack = prevTrack;
exports.nextTrack = nextTrack;
exports.status = status;
exports.reset = reset;
