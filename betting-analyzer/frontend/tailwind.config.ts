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
          DEFAULT: "#0c1220",
          secondary: "#0f172a",
          card: "rgba(15, 23, 42, 0.85)"
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
          glow: "rgba(14, 165, 233, 0.3)",
          cyan: "#06b6d4",
          sky: "#38bdf8",
          electric: "#3b82f6"
        },
        card: {
          DEFAULT: "#1e293b",
          hover: "#334155",
          border: "rgba(56, 189, 248, 0.1)"
        },
        success: {
          DEFAULT: "#10b981",
          glow: "rgba(16, 185, 129, 0.3)",
          muted: "rgba(16, 185, 129, 0.15)",
          bright: "#34d399"
        },
        warning: {
          DEFAULT: "#f59e0b",
          glow: "rgba(245, 158, 11, 0.3)",
          muted: "rgba(245, 158, 11, 0.15)",
          bright: "#fbbf24"
        },
        error: {
          DEFAULT: "#ef4444",
          glow: "rgba(239, 68, 68, 0.3)",
          muted: "rgba(239, 68, 68, 0.15)",
          bright: "#f87171"
        }
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"]
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
        "display": ["2.5rem", { lineHeight: "1.1", fontWeight: "700" }],
        "display-sm": ["2rem", { lineHeight: "1.15", fontWeight: "700" }]
      },
      spacing: {
        "18": "4.5rem",
        "22": "5.5rem"
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
        "4xl": "1.5rem"
      },
      boxShadow: {
        "card": "0 4px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(56, 189, 248, 0.05)",
        "card-hover": "0 8px 32px rgba(0, 0, 0, 0.4), 0 0 40px rgba(14, 165, 233, 0.15), inset 0 1px 0 rgba(56, 189, 248, 0.1)",
        "glow": "0 0 40px rgba(14, 165, 233, 0.2)",
        "glow-sm": "0 0 20px rgba(14, 165, 233, 0.12)",
        "glow-cyan": "0 0 30px rgba(6, 182, 212, 0.25)",
        "success": "0 0 20px rgba(16, 185, 129, 0.2)"
      },
      backdropBlur: {
        "xs": "2px"
      },
      transitionTimingFunction: {
        "premium": "cubic-bezier(0.4, 0, 0.2, 1)"
      },
      transitionDuration: {
        "400": "400ms"
      },
      animation: {
        "fade-in": "fadeIn 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards",
        "slide-in": "slideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards",
        "pulse-glow": "pulseGlow 3s ease-in-out infinite",
        "float": "float 3s ease-in-out infinite"
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" }
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-10px)" },
          "100%": { opacity: "1", transform: "translateX(0)" }
        },
        pulseGlow: {
          "0%, 100%": { boxShadow: "0 0 20px rgba(14, 165, 233, 0.3)" },
          "50%": { boxShadow: "0 0 35px rgba(14, 165, 233, 0.5)" }
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-5px)" }
        }
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-accent": "linear-gradient(135deg, #0ea5e9 0%, #06b6d4 100%)",
        "gradient-success": "linear-gradient(135deg, #10b981 0%, #34d399 100%)",
        "gradient-border": "linear-gradient(135deg, rgba(14, 165, 233, 0.4), rgba(6, 182, 212, 0.2))"
      }
    }
  },
  plugins: []
};

export default config;
