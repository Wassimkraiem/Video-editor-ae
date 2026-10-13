import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { ink: "#101827", panel: "#172033", accent: "#8b5cf6" } } },
  plugins: [],
};

export default config;
