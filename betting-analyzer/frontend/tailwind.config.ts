import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: "#080c14",
          secondary: "#0d1320",
          card: "#111827",
          elevated: "#1a2332"
        },
        foreground: {
          DEFAULT: "#e2e8f0",
          primary: "#f8fafc",
          secondary: "#e2e8f0",
          tertiary: "#94a3b8",
          muted: "#64748b"
        },
        accent: {
          DEFAULT: "#0ea5e9",
          secondary: "#38bdf8",
          tertiary: "#22d3ee",
          cyan: "#06b6d4",
          sky: "#38bdf8"
        },
        card: {
          DEFAULT: "#111827",
          hover: "#1e293b",
          border: "#1e293b"
        },
        success: {
          DEFAULT: "#10b981",
          bright: "#34d399",
          muted: "#059669"
        },
        warning: {
          DEFAULT: "#f59e0b",
          bright: "#fbbf24",
          muted: "#d97706"
        },
        error: {
          DEFAULT: "#ef4444",
          bright: "#f87171",
          muted: "#dc2626"
        }
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"]
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
        "display": ["2.5rem", { lineHeight: "1.1", fontWeight: "800" }],
        "display-sm": ["2rem", { lineHeight: "1.15", fontWeight: "800" }]
      },
      spacing: {
        "18": "4.5rem",
        "22": "5.5rem"
      },
      borderRadius: {
        "2xl": "0.75rem",
        "3xl": "1rem",
        "4xl": "1.25rem"
      },
      boxShadow: {
        "card": "0 4px 6px -1px rgba(0, 0, 0, 0.6), 0 2px 4px -2px rgba(0, 0, 0, 0.5)",
        "card-hover": "0 10px 15px -3px rgba(0, 0, 0, 0.7), 0 4px 6px -4px rgba(0, 0, 0, 0.5)",
        "accent": "0 0 0 1px rgba(14, 165, 233, 0.3), 0 4px 12px rgba(14, 165, 233, 0.15)",
        "success": "0 0 0 1px rgba(16, 185, 129, 0.3), 0 4px 12px rgba(16, 185, 129, 0.15)"
      },
      transitionTimingFunction: {
        "premium": "cubic-bezier(0.4, 0, 0.2, 1)"
      },
      animation: {
        "fade-in": "fadeIn 0.4s ease-out forwards",
        "slide-in": "slideIn 0.3s ease-out forwards"
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" }
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" }
        }
      }
    }
  },
  plugins: []
};

export default config;
