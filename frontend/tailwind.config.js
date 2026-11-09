/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        phosphor: "#39FF88",
        cyan: { DEFAULT: "#00E5FF" },
        purple: { DEFAULT: "#A255FF" },
        amber: { DEFAULT: "#FFB000" },
        navy: "#0B1839",
        console: "#1A1030",
        danger: "#FF4D8D",
        ink: "#E8F5EE",
        muted: "#9AA8C7",
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', "monospace"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        term: ["VT323", "monospace"],
      },
    },
  },
  plugins: [],
};
