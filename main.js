const RELEASE_BASE = "https://github.com/yvsazh/abebuilds/releases/latest/download/";
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);
const isLocalPreview = LOCAL_HOSTS.has(window.location.hostname);

const formatSize = (bytes) => {
  if (!bytes) return "Size unknown";
  const units = ["B", "KB", "MB", "GB"];
  let amount = bytes;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit > 0 && amount < 10 ? 1 : 0)} ${units[unit]}`;
};

fetch("./builds.json")
  .then((response) => {
    if (!response.ok) throw new Error("Build manifest could not be loaded");
    return response.json();
  })
  .then((builds) => {
    const dates = Object.values(builds).map((build) => build.built).filter(Boolean).sort();
    if (dates.length) {
      document.querySelector("[data-build-date]").textContent = dates[dates.length - 1];
      document.querySelector("[data-build-meta]").hidden = false;
    }
    for (const [platform, build] of Object.entries(builds)) {
      const sizeLabel = document.querySelector(`[data-size="${platform}"]`);
      if (sizeLabel) sizeLabel.textContent = formatSize(build.size);

      document.querySelectorAll(`[data-download="${platform}"]`).forEach((link) => {
        link.href = isLocalPreview
          ? `./_release-assets/${encodeURIComponent(build.file)}`
          : `${RELEASE_BASE}${encodeURIComponent(build.file)}`;
        link.setAttribute("download", build.file);
      });
    }
  })
  .catch(() => {
    document.querySelectorAll("[data-size]").forEach((label) => {
      label.textContent = "Size unknown";
    });
  });
