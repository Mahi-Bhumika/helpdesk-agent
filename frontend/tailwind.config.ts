import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        obsidian: {
          DEFAULT: "#0B0B0C",
          surface: "#111113",   // slightly lifted panel base, under the glass layer
          border: "#232327",    // default hairline border on non-glass elements
        },
        accent: {
          indigo: "#4F46E5",
          violet: "#7C3AED",
        },
        status: {
          active: "#10B981",     // emerald
          activeSoft: "rgba(16, 185, 129, 0.14)",
          completed: "#60A5FA",  // muted blue
          completedSoft: "rgba(96, 165, 250, 0.14)",
          pending: "#F59E0B",    // amber
          pendingSoft: "rgba(245, 158, 11, 0.14)",
          declined: "#F87171",   // muted red
          declinedSoft: "rgba(248, 113, 113, 0.14)",
        },
        text: {
          primary: "#F5F5F6",
          secondary: "#A1A1AA",
          muted: "#6B6B72",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        "gradient-brand": "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)",
        "gradient-brand-soft":
          "linear-gradient(135deg, rgba(79,70,229,0.16) 0%, rgba(124,58,237,0.16) 100%)",
      },
      boxShadow: {
        glow: "0 0 24px -4px rgba(124, 58, 237, 0.35)",
        "glow-emerald": "0 0 16px -2px rgba(16, 185, 129, 0.45)",
        "glow-blue": "0 0 16px -2px rgba(96, 165, 250, 0.45)",
        "glow-amber": "0 0 16px -2px rgba(245, 158, 11, 0.45)",
        card: "0 4px 30px rgba(0, 0, 0, 0.35)",
      },
      borderRadius: {
        xl2: "1.25rem",
      },
      backdropBlur: {
        glass: "16px",
      },
    },
  },
  plugins: [],
};

export default config;
