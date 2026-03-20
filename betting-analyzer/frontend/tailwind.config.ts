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
        background: "#0f0f13",
        foreground: "#f4f4f5",
        accent: "#6366f1",
        card: "#1a1a24"
      }
    }
  },
  plugins: []
};

export default config;
