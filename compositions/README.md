# HyperFrames compositions

The workspace pins HyperFrames `0.8.152` in `package.json` and
`package-lock.json`. Run `npm ci` here before using `npx hyperframes init`,
`preview`, `validate`, or `render`.

Each composition is an HTML folder with timing attributes and a GSAP timeline.
The worker invokes `npx hyperframes preview` and `npx hyperframes render` from
the sandbox. Framework playback owns media timing; compositions do not call
`video.play()` or `video.pause()`, use random values, or animate video width or
height.
