import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)",
        paper: "var(--paper)",
        surface: {
          DEFAULT: "var(--surface)",
          muted: "var(--surface-muted)",
        },
        ink: {
          DEFAULT: "var(--ink)",
          muted: "var(--ink-muted)",
        },
        border: "var(--border)",
        grid: "var(--grid)",
        copper: {
          DEFAULT: "var(--copper)",
          accent: "var(--copper-accent)",
        },
        link: "var(--link)",
        trust: {
          verified: "var(--trust-verified)",
          supported: "var(--trust-supported)",
          "single-source": "var(--trust-single-source)",
          conflicting: "var(--trust-conflicting)",
          "needs-review": "var(--trust-needs-review)",
          missing: "var(--trust-missing)",
        },
      },
      fontFamily: {
        sans: ["var(--font-plex-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "monospace"],
        serif: ["var(--font-plex-serif)", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
