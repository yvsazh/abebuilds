const PARTS = ["Epic.data.part-001", "Epic.data.part-002"];

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "CLAIM_CLIENTS") self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  if (event.request.method !== "GET" || !requestUrl.pathname.endsWith("/Build/Epic.data")) return;

  event.respondWith((async () => {
    const partsBase = new URL("Build/", self.registration.scope);
    const stream = new ReadableStream({
      async start(controller) {
        try {
          for (const part of PARTS) {
            const response = await fetch(new URL(part, partsBase));
            if (!response.ok || !response.body) throw new Error(`Could not load ${part} (${response.status}).`);
            const reader = response.body.getReader();
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              controller.enqueue(value);
            }
          }
          controller.close();
        } catch (error) {
          controller.error(error);
        }
      }
    });
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "application/octet-stream" }
    });
  })());
});
