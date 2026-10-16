# Generic fast engine: how to write the composition

The style document above says how the edit should look and feel. It may describe scripts,
sub-agents or multi-step workflows: none of them run here. Reproduce the look yourself in ONE
self-contained `index.html` that the studio lints and renders as is.

## Contract (HyperFrames)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { width: 1080px; height: 1920px; overflow: hidden; background: #000; }
      #root { position: relative; width: 100%; height: 100%; overflow: hidden; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="DURATION" data-width="1080" data-height="1920">
      <video id="footage" src="assets/source.mp4" playsinline data-has-audio="true" data-start="0" data-duration="DURATION" data-track-index="0"></video>
      <!-- timed overlays: any element with data-start + data-duration (+ class="clip") -->
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
      // tl.fromTo("#card-1", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.5 }, 3.2);
      tl.to({}, { duration: DURATION }, 0);
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
```

- Root: `data-composition-id="main"`, `data-width`/`data-height` (1080x1920 for vertical footage,
  otherwise the clip's size), `data-duration` = the footage duration given in the request.
- Footage (when there is a clip): the `<video>` above, `id` required, `data-has-audio="true"`,
  full frame (`width: 100%; height: 100%; object-fit: cover`). Never trim or reorder it.
- Every timed element has a unique `id`, `data-start` and `data-duration` (seconds). Visibility
  is `[start, start + duration)`: finish exit animations slightly before the end.
- ONE paused GSAP timeline registered as `window.__timelines["main"]`, deterministic: no
  `Math.random`, `Date`, timers, `requestAnimationFrame` or network calls besides the GSAP script.
  Zooms/punch-ins animate a wrapper around the video (`transform`), never the video's timing.
- Sounds: `<audio id="..." src="..." data-start data-duration data-volume>` (ids required).
  Bundled effects can't be loaded here; only use files the user attached.
- Fonts: only these three, declared exactly like this in the `<style>` (the build puts the files
  in `fonts/`; any other family renders as a fallback and fails lint). No web fonts or external images.
  ```css
  @font-face { font-family: "Studio Arabic"; src: url("fonts/arabic.ttf"); font-weight: 700; font-display: block; }
  @font-face { font-family: "Studio Arabic Display"; src: url("fonts/arabic-display.ttf"); font-weight: 700; font-display: block; }
  @font-face { font-family: "Studio Latin"; src: url("fonts/inter.woff2") format("woff2"); font-weight: 700; font-display: block; }
  ```
  Body/captions: `"Studio Arabic", "Studio Latin", sans-serif`; headlines: `"Studio Arabic Display"`
  for Arabic, `"Studio Latin"` for French/English. All are bold (700).
- Attached files are under `assets/resources/` (listed in the request) and may be used as
  `<img>`, `<video muted>` or `<audio>`.

## Captions and timing

- Captions use the transcript words exactly as given (never respell, translate or drop words),
  grouped into short phrases, each shown from its first word's start to just before the next
  phrase. Arabic text is `direction: rtl`; Latin words inside it keep their own direction.
- Every card, keyword, graphic and sound starts on a word onset from the transcript and shows
  what is said at that moment. Keep faces clear: overlays in the band the style specifies, or
  else the middle/lower third.
- Keep the file compact: CSS classes for repeated elements, small helper functions in the
  script for repeated tweens, data arrays + a loop for caption phrases.
