/** Tailwind configuration — AapaatSathi design tokens. */
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Risk scale follows the India Met / NDMA colour convention.
        risk: {
          green: "#16a34a",
          blue: "#0ea5e9",
          yellow: "#eab308",
          orange: "#f97316",
          red: "#dc2626",
        },
        ink: {
          950: "#070b14",
          900: "#0b1220",
          800: "#121a2b",
          700: "#1b2537",
          600: "#27334a",
          400: "#5b6b86",
          300: "#8ea0bd",
          200: "#c3d0e4",
          100: "#e6ecf5",
        },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "Noto Sans Devanagari", "sans-serif"],
        deva: ["Noto Sans Devanagari", "Mangal", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      keyframes: {
        pulseRing: {
          "0%": { transform: "scale(.6)", opacity: "0.85" },
          "80%,100%": { transform: "scale(2.2)", opacity: "0" },
        },
        slideIn: {
          from: { transform: "translateY(-8px)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        ticker: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
      },
      animation: {
        ring: "pulseRing 2.2s cubic-bezier(0.2,0.6,0.4,1) infinite",
        slide: "slideIn .28s ease-out",
        ticker: "ticker 38s linear infinite",
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,.04) inset, 0 18px 40px -24px rgba(0,0,0,.7)",
      },
    },
  },
  plugins: [],
} satisfies Config;
