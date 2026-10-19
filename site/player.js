const gameShell = document.querySelector("#game-shell");
const safeArea = document.querySelector("#safe-area");
const stage = document.querySelector("#game-stage");
const canvas = document.querySelector("#game-canvas");
const startScreen = document.querySelector("#start-screen");
const startButton = document.querySelector("#start-button");
const startHint = document.querySelector("#start-hint");
const loadStatus = document.querySelector("#load-status");
const loadProgress = document.querySelector("#load-progress");
const loadTrack = loadProgress.parentElement;
const rotateScreen = document.querySelector("#rotate-screen");
const fullscreenButton = document.querySelector("#fullscreen-button");
const errorBox = document.querySelector("#game-error");
const buildVersion = new URL(document.currentScript.src).searchParams.get("v") || "";
const uaMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
const ipadOs = /Macintosh/i.test(navigator.userAgent) && navigator.maxTouchPoints > 1;
const isMobileDevice = navigator.userAgentData?.mobile ?? (uaMobile || ipadOs);
const canFullscreen = Boolean(document.fullscreenEnabled || document.webkitFullscreenEnabled);
document.documentElement.classList.toggle("mobile-device", isMobileDevice);

// The game is drawn for landscape screens. Below 4:3 its UI camera clips the
// sides; above about 1.93:1 battle backgrounds end and white edges show (the
// battle camera is sized only when a scene starts, so a window resized during
// a battle must stay inside the art too). The stage is the largest rectangle
// in the safe area whose aspect ratio stays in this range, so the game is
// never stretched, cut off, or shown past its artwork.
const MIN_ASPECT = 4 / 3;
const MAX_ASPECT = 1.9;
// Phones report up to 3x pixel density; rendering above 2x costs a lot of GPU
// time for little visible gain.
const MAX_PIXEL_RATIO = 2;
let unityInstance = null;
let readyToPlay = false;
let gameRunning = false;

function markAudioGesture() {
  window.__epicWebGLAudioGesture = true;
  if (unityInstance) {
    try { unityInstance.SendMessage("VideoCutscene_01", "UnlockIntroAudio"); } catch (_) { /* The intro scene may not be loaded yet; Unity reads the persistent gesture flag. */ }
  }
}

function layoutStage() {
  const shell = gameShell.getBoundingClientRect();
  const insets = getComputedStyle(safeArea);
  const left = parseFloat(insets.paddingLeft) || 0;
  const right = parseFloat(insets.paddingRight) || 0;
  const top = parseFloat(insets.paddingTop) || 0;
  const bottom = parseFloat(insets.paddingBottom) || 0;
  const availableWidth = shell.width - left - right;
  const availableHeight = shell.height - top - bottom;
  if (availableWidth <= 0 || availableHeight <= 0) return;

  const aspect = Math.min(MAX_ASPECT, Math.max(MIN_ASPECT, availableWidth / availableHeight));
  let width = availableWidth;
  let height = width / aspect;
  if (height > availableHeight) {
    height = availableHeight;
    width = height * aspect;
  }
  // Whole CSS pixels keep the canvas crisp.
  width = Math.floor(width);
  height = Math.floor(height);
  const x = Math.round(left + (availableWidth - width) / 2);
  const y = Math.round(top + (availableHeight - height) / 2);
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  stage.style.transform = `translate(${x}px, ${y}px)`;
}

let layoutFrame = 0;
function scheduleLayout() {
  cancelAnimationFrame(layoutFrame);
  layoutFrame = requestAnimationFrame(() => {
    layoutStage();
    updateOrientationPrompt();
  });
}

function setButton(label) {
  startButton.firstElementChild.textContent = label;
}

function setProgress(percent) {
  loadProgress.style.width = `${percent}%`;
  loadTrack.setAttribute("aria-valuenow", String(Math.round(percent)));
}

function versionedUrl(path, base) {
  const url = new URL(path, base);
  if (buildVersion) url.searchParams.set("v", buildVersion);
  return url.href;
}

function updateOrientationPrompt() {
  const shouldPrompt = isMobileDevice && window.matchMedia("(orientation: portrait) and (max-width: 900px)").matches;
  rotateScreen.classList.toggle("is-visible", shouldPrompt && startScreen.classList.contains("is-hidden"));
}

function showError(error) {
  if (gameRunning) {
    showCrash(error);
    return;
  }
  errorBox.hidden = false;
  errorBox.textContent = `The game could not start. ${error?.message || error || "Please reload this page and try again."}`;
  loadStatus.textContent = "Game failed to load.";
  startButton.disabled = false;
  setButton("Try again");
}

// A fatal WebAssembly error stops the game loop; tell the player instead of leaving a frozen frame.
function showCrash(error) {
  if (!errorBox.hidden) return;
  console.error("Game stopped", error);
  errorBox.replaceChildren();
  const text = document.createElement("p");
  text.textContent = "The game stopped because of an unexpected error. Your progress is saved in this browser.";
  const reload = document.createElement("button");
  reload.type = "button";
  reload.className = "error-reload";
  reload.textContent = "Reload game";
  reload.addEventListener("click", () => window.location.reload());
  errorBox.append(text, reload);
  errorBox.hidden = false;
}

function isFatalRuntimeError(error, message) {
  const text = `${message || ""} ${error?.message || ""}`;
  return error instanceof WebAssembly.RuntimeError || /\babort\b|RuntimeError|unreachable|memory access out of bounds|Out of memory/i.test(text);
}

window.addEventListener("error", (event) => {
  if (gameRunning && isFatalRuntimeError(event.error, event.message)) showCrash(event.error || event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  if (gameRunning && isFatalRuntimeError(event.reason, "")) showCrash(event.reason);
});

function waitForServiceWorkerControl(registration, expectedScriptUrl) {
  if (navigator.serviceWorker.controller?.scriptURL === expectedScriptUrl) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      navigator.serviceWorker.removeEventListener("controllerchange", onControl);
      reject(new Error("This browser did not enable the game file loader. Try a current version of Chrome, Edge, Safari, or Firefox."));
    }, 10000);
    function onControl() {
      if (navigator.serviceWorker.controller?.scriptURL !== expectedScriptUrl) return;
      window.clearTimeout(timeout);
      navigator.serviceWorker.removeEventListener("controllerchange", onControl);
      resolve();
    }
    navigator.serviceWorker.addEventListener("controllerchange", onControl);
    registration.active?.postMessage({ type: "CLAIM_CLIENTS" });
  });
}

async function startGame() {
  errorBox.hidden = true;
  startButton.disabled = true;
  setButton("Loading…");
  loadStatus.textContent = "Starting the game engine…";
  setProgress(4);

  try {
    if (!("serviceWorker" in navigator)) throw new Error("This browser does not support the file loader needed for this WebGL build.");
    const workerUrl = versionedUrl("sw.js", new URL("./", window.location.href));
    const registration = await navigator.serviceWorker.register(workerUrl, { scope: "./" });
    await registration.update();
    await navigator.serviceWorker.ready;
    await waitForServiceWorkerControl(registration, workerUrl);

    loadStatus.textContent = "Loading the game…";
    const buildUrl = new URL("./Build/", window.location.href);
    const loader = document.createElement("script");
    loader.src = versionedUrl("Epic.loader.js", buildUrl);
    await new Promise((resolve, reject) => {
      loader.onload = resolve;
      loader.onerror = () => reject(new Error("The Unity loader file could not be downloaded."));
      document.body.appendChild(loader);
    });

    const config = {
      arguments: [],
      dataUrl: versionedUrl("Epic.data", buildUrl),
      frameworkUrl: versionedUrl("Epic.framework.js", buildUrl),
      codeUrl: versionedUrl("Epic.wasm", buildUrl),
      streamingAssetsUrl: new URL("./StreamingAssets", window.location.href).href,
      companyName: "Rovio Entertainment Ltd.",
      productName: "Epic",
      productVersion: "3.0.1",
      devicePixelRatio: Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO),
      showBanner(message, type) {
        if (type === "error") showError(message);
      }
    };

    unityInstance = await createUnityInstance(canvas, config, (progress) => {
      const percent = Math.round(progress * 100);
      setProgress(Math.max(4, percent));
      loadStatus.textContent = percent < 100 ? `Loading game files… ${percent}%` : "Starting the adventure…";
    });
    gameRunning = true;
    setProgress(100);
    loadStatus.textContent = "Ready for battle!";
    startButton.disabled = false;
    startButton.classList.add("is-ready");
    setButton("Play");
    startHint.hidden = true;
    readyToPlay = true;
  } catch (error) {
    showError(error);
  }
}

function fullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

async function enterFullscreen() {
  const root = document.documentElement;
  try {
    if (root.requestFullscreen) await root.requestFullscreen({ navigationUI: "hide" });
    else if (root.webkitRequestFullscreen) root.webkitRequestFullscreen();
  } catch (_) { /* Full screen is optional; the page already fills the viewport. */ }
}

async function exitFullscreen() {
  try {
    if (document.exitFullscreen) await document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
  } catch (_) { /* Already left full screen. */ }
}

async function requestImmersiveMode() {
  // Desktop players choose full screen themselves; phones and tablets get it on start.
  if (isMobileDevice && canFullscreen && !fullscreenElement()) await enterFullscreen();
  if (screen.orientation?.lock) {
    try { await screen.orientation.lock("landscape"); } catch (_) { /* Some browsers allow this only after a full-screen transition. */ }
  }
}

startButton.addEventListener("click", async () => {
  if (!readyToPlay) {
    await startGame();
    return;
  }
  markAudioGesture();
  await requestImmersiveMode();
  startScreen.classList.add("is-hidden");
  fullscreenButton.hidden = !canFullscreen;
  canvas.focus({ preventScroll: true });
  scheduleLayout();
});

fullscreenButton.addEventListener("click", async () => {
  if (fullscreenElement()) await exitFullscreen();
  else await enterFullscreen();
  canvas.focus({ preventScroll: true });
});

function onFullscreenChange() {
  const active = Boolean(fullscreenElement());
  document.documentElement.classList.toggle("is-fullscreen", active);
  fullscreenButton.setAttribute("aria-label", active ? "Exit full screen" : "Enter full screen");
  scheduleLayout();
}
document.addEventListener("fullscreenchange", onFullscreenChange);
document.addEventListener("webkitfullscreenchange", onFullscreenChange);

if ("ResizeObserver" in window) new ResizeObserver(scheduleLayout).observe(gameShell);
window.addEventListener("resize", scheduleLayout);
window.visualViewport?.addEventListener("resize", scheduleLayout);
// iOS reports the old size during orientationchange; measure again once it settles.
window.addEventListener("orientationchange", () => {
  scheduleLayout();
  window.setTimeout(scheduleLayout, 350);
});
layoutStage();
updateOrientationPrompt();
startGame();
