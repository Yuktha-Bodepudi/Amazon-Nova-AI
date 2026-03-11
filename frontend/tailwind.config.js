/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono:    ["'IBM Plex Mono'", "monospace"],
        display: ["'DM Sans'", "sans-serif"],
      },
      colors: {
        brand: { DEFAULT: "#00E5FF", dim: "#0097A7", dark: "#001F26" },
        warn:  { DEFAULT: "#FF6B35", dim: "#BF4A20" },
        ok:    { DEFAULT: "#00E676", dim: "#007A3D" },
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in":    "fadeIn 0.4s ease-out both",
        "slide-up":   "slideUp 0.4s ease-out both",
      },
      keyframes: {
        fadeIn:  { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: "translateY(12px)" }, to: { opacity: 1, transform: "translateY(0)" } },
      }
    }
  },
  plugins: []
};