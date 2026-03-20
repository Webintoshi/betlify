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
          DEFAULT: "#0a0a0f",
          secondary: "#0f0f13",
          card: "rgba(21, 21, 32, 0.85)"
        },
        foreground: {
          DEFAULT: "#e4e4e7",
          primary: "#ffffff",
          secondary: "#e4e4e7",
          tertiary: "#a1a1aa",
          muted: "#71717a"
        },
        accent: {
          DEFAULT: "#6366f1",
          secondary: "#8b5cf6",
          tertiary: "#a855f7",
          glow: "rgba(99, 102, 241, 0.15)"
        },
        card: {
          DEFAULT: "#151520",
          hover: "#1a1a26",
          border: "rgba(255, 255, 255, 0.06)"
        },
        success: {
          DEFAULT: "#10b981",
          glow: "rgba(16, 185, 129, 0.3)",
          muted: "rgba(16, 185, 129, 0.15)"
        },
        warning: {
          DEFAULT: "#f59e0b",
          glow: "rgba(245, 158, 11, 0.3)",
          muted: "rgba(245, 158, 11, 0.15)"
        },
        error: {
          DEFAULT: "#f43f5e",
          glow: "rgba(244, 63, 94, 0.3)",
          muted: "rgba(244, 63, 94, 0.15)"
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
        "card": "0 4px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
        "card-hover": "0 8px 32px rgba(0, 0, 0, 0.4), 0 0 40px rgba(99, 102, 241, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.08)",
        "glow": "0 0 40px rgba(99, 102, 241, 0.15)",
        "glow-sm": "0 0 20px rgba(99, 102, 241, 0.1)",
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
        "pulse-glow": "pulseGlow 3s ease-in-out infinite"
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
          "0%, 100%": { boxShadow: "0 0 20px rgba(99, 102, 241, 0.2)" },
          "50%": { boxShadow: "0 0 30px rgba(99, 102, 241, 0.35)" }
        }
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-accent": "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
        "gradient-success": "linear-gradient(135deg, #10b981 0%, #34d399 100%)",
        "gradient-border": "linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(139, 92, 246, 0.1))"
      }
    }
  },
  plugins: []
};

export default config;
