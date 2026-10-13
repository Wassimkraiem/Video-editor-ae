import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070a12",
        panel: "#0e1422",
        "panel-raised": "#141c2e",
        line: "rgba(148, 163, 184, 0.12)",
        accent: { DEFAULT: "#2f6bff", strong: "#4a80ff", soft: "#8fb0ff" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(255,255,255,0.03) inset, 0 20px 40px -24px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(47,107,255,0.4), 0 8px 24px -8px rgba(47,107,255,0.55)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
        pulse: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
      },
      animation: { "fade-in": "fade-in 220ms ease-out both" },
    },
  },
  plugins: [],
};

export default config;
