import { createPreset } from "@basicbar/ui/tailwind-preset";
import typography from "@tailwindcss/typography";

/**
 * Ausleihbar design tokens (see DESIGN.md).
 *
 * Structure and conventions (shade semantics, dark mode, font, motion) come
 * from the shared @basicbar/ui preset; the OKLCH color ramps below are
 * Ausleihbar's identity and stay in the tool:
 *
 * - `slate` is a warm-tinted neutral ramp (hue ~91) so the whole app inherits
 *   the warm neutrals. Values are tuned for WCAG AA: slate-400 on white
 *   already reaches ≥4.5:1, so even meta text stays readable.
 * - `brand` is the single accent: honey-gold. CTAs use brand-400 with dark ink
 *   text (≈8.6:1); brand-600 is the focus/selection color (≥3:1 non-text on
 *   white); brand-700 is accent text on white (≥4.5:1).
 */

/** @type {import('tailwindcss').Config} */
export default {
  presets: [
    createPreset({
      colors: {
        // The `/ <alpha-value>` placeholder lets Tailwind's opacity modifier
        // (e.g. `bg-slate-900/90`, `dark:bg-slate-800/50`) work on these custom
        // OKLCH colors; without it those utilities silently render transparent.
        slate: {
          50: "oklch(0.985 0.003 91 / <alpha-value>)",
          100: "oklch(0.962 0.004 91 / <alpha-value>)",
          200: "oklch(0.922 0.006 91 / <alpha-value>)",
          300: "oklch(0.868 0.008 91 / <alpha-value>)",
          400: "oklch(0.577 0.012 91 / <alpha-value>)",
          500: "oklch(0.498 0.014 91 / <alpha-value>)",
          600: "oklch(0.43 0.015 91 / <alpha-value>)",
          700: "oklch(0.36 0.014 91 / <alpha-value>)",
          800: "oklch(0.28 0.012 91 / <alpha-value>)",
          900: "oklch(0.215 0.012 91 / <alpha-value>)",
          950: "oklch(0.16 0.01 91 / <alpha-value>)",
        },
        brand: {
          50: "oklch(0.975 0.02 95 / <alpha-value>)",
          100: "oklch(0.945 0.045 95 / <alpha-value>)",
          200: "oklch(0.9 0.08 93 / <alpha-value>)",
          300: "oklch(0.865 0.115 92 / <alpha-value>)",
          400: "oklch(0.84 0.15 91 / <alpha-value>)",
          500: "oklch(0.78 0.145 88 / <alpha-value>)",
          600: "oklch(0.65 0.13 80 / <alpha-value>)",
          700: "oklch(0.52 0.105 75 / <alpha-value>)",
          800: "oklch(0.43 0.085 70 / <alpha-value>)",
          900: "oklch(0.36 0.065 65 / <alpha-value>)",
        },
      },
    }),
  ],
  // The @basicbar/ui components carry Tailwind classes of their own — scan
  // the package dist so those classes reach the generated CSS.
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./node_modules/@basicbar/ui/dist/**/*.js",
  ],
  plugins: [typography],
};
