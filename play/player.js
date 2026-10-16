const canvas = document.querySelector("#game-canvas");
const startScreen = document.querySelector("#start-screen");
const startButton = document.querySelector("#start-button");
const startHint = document.querySelector("#start-hint");
const loadStatus = document.querySelector("#load-status");
const loadProgress = document.querySelector("#load-progress");
const rotateScreen = document.querySelector("#rotate-screen");
const fullscreenButton = document.querySelector("#fullscreen-button");
const errorBox = document.querySelector("#game-error");
let unityInstance = null;
let readyToPlay = false;

function updateOrientationPrompt() {
  const shouldPrompt = window.matchMedia("(orientation: portrait) and (max-width: 900px)").matches;
  rotateScreen.classList.toggle("is-visible", shouldPrompt && startScreen.classList.contains("is-hidden"));
}

function showError(error) {
  errorBox.hidden = false;
  errorBox.textContent = `The game could not start. ${error?.message || error || "Please reload this page and try again."}`;
  loadStatus.textContent = "Game failed to load.";
  startButton.disabled = false;
  startButton.textContent = "Try again";
}

function waitForServiceWorkerControl(registration) {
  if (navigator.serviceWorker.controller) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      navigator.serviceWorker.removeEventListener("controllerchange", onControl);
      reject(new Error("This browser did not enable the game file loader. Try a current version of Chrome, Edge, Safari, or Firefox."));
    }, 10000);
    function onControl() {
      clearTimeout(timeout);
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
  startButton.textContent = "Loading…";
  loadStatus.textContent = "Starting the game engine…";
  loadProgress.style.width = "8%";

  try {
    if (!("serviceWorker" in navigator)) throw new Error("This browser does not support the file loader needed for this WebGL build.");
    const registration = await navigator.serviceWorker.register("./sw.js", { scope: "./" });
    await navigator.serviceWorker.ready;
    await waitForServiceWorkerControl(registration);

    loadStatus.textContent = "Loading the game…";
    const buildUrl = new URL("./Build/", window.location.href);
    const loader = document.createElement("script");
    loader.src = new URL("Epic.loader.js", buildUrl).href;
    await new Promise((resolve, reject) => {
      loader.onload = resolve;
      loader.onerror = () => reject(new Error("The Unity loader file could not be downloaded."));
      document.body.appendChild(loader);
    });

    const config = {
      arguments: [],
      dataUrl: new URL("Epic.data", buildUrl).href,
      frameworkUrl: new URL("Epic.framework.js", buildUrl).href,
      codeUrl: new URL("Epic.wasm", buildUrl).href,
      streamingAssetsUrl: new URL("./StreamingAssets", window.location.href).href,
      companyName: "Rovio Entertainment Ltd.",
      productName: "Epic",
      productVersion: "3.0.1",
      showBanner(message, type) {
        if (type === "error") showError(message);
      }
    };

    unityInstance = await createUnityInstance(canvas, config, (progress) => {
      const percent = Math.round(progress * 100);
      loadProgress.style.width = `${Math.max(8, percent)}%`;
      loadStatus.textContent = percent < 100 ? `Loading game files… ${percent}%` : "Starting the adventure…";
    });
    loadProgress.style.width = "100%";
    loadStatus.textContent = "Ready when you are.";
    startButton.disabled = false;
    startButton.textContent = "Enter game";
    startHint.textContent = "Full screen and landscape are enabled where your browser allows them.";
    readyToPlay = true;
  } catch (error) {
    showError(error);
  }
}

async function requestImmersiveMode() {
  if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
    try { await document.documentElement.requestFullscreen({ navigationUI: "hide" }); } catch (_) { /* Full-screen is optional; the page already fills the viewport. */ }
  }
  if (screen.orientation?.lock) {
    try { await screen.orientation.lock("landscape"); } catch (_) { /* Some browsers allow this only after a full-screen transition. */ }
  }
}

startButton.addEventListener("click", async () => {
  if (!readyToPlay) {
    await startGame();
    return;
  }
  await requestImmersiveMode();
  startScreen.classList.add("is-hidden");
  canvas.focus({ preventScroll: true });
  updateOrientationPrompt();
});

fullscreenButton.addEventListener("click", requestImmersiveMode);
document.addEventListener("fullscreenchange", () => {
  fullscreenButton.setAttribute("aria-label", document.fullscreenElement ? "Exit full screen" : "Enter full screen");
  fullscreenButton.title = document.fullscreenElement ? "Full screen on" : "Enter full screen";
});
window.addEventListener("orientationchange", updateOrientationPrompt);
window.addEventListener("resize", updateOrientationPrompt);
updateOrientationPrompt();
startGame();
