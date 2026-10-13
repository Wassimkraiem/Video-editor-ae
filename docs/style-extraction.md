# Style extraction

Style extraction is a background job. The user supplies URLs and confirms that
they own the rights or have permission. The worker fetches only those URLs in
the sandbox, samples scenes, transcribes speech, measures loudness and tempo,
and optionally performs OCR. Source media is deleted after derived artifacts
are produced unless the user opts in.

The resulting style spec contains pacing, transitions, typography, palette,
grading, motion language, music usage, on-screen text conventions, and layout
rules. The worker writes a validated `SKILL.md`, `references/style-spec.json`,
HyperFrames templates, and FFmpeg presets. It stores URLs, timestamps, and the
extraction version but never redistributes source footage.
