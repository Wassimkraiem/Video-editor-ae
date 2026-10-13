# HyperFrames compositions

Compositions are deterministic HTML documents. Use `data-duration-ms`,
`data-start-ms`, and `data-end-ms` attributes plus a GSAP timeline. HyperFrames
owns media playback and mounting. Do not call `video.play()` or `pause()`, use
random/time-based values, animate video width or height, or make timeline
duration disagree with the source media.

The worker runs the pinned CLI inside the sandbox:

```text
npx hyperframes init
npx hyperframes preview <composition>
npx hyperframes render <composition> --preset 1080p30
npx hyperframes validate <composition> --json
```

Every composition write invokes validation before the agent receives a success
result. A graphics item stores only `composition_path` and `duration_ms` in the
timeline.
