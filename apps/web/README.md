# Web studio

This is the Next.js client for the API. It keeps provider keys out of the
browser, uses the generated API client boundary, and reconnects to API SSE
streams with `Last-Event-ID`.

Install with `npm ci` and run `npm run dev`. The workspace shell includes
authentication, project creation, streamed uploads, timeline/version display,
agent chat with SSE events, storyboard approval, memory editing, and preview
render controls. HyperFrames' pinned player package is loaded only in the
browser.
