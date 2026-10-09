import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        // Intelligence-console palette: near-black green-greys, restrained green accent. Token names are unchanged so every
        // existing `ink-*` / `accent` / `slate-*` class picks up the new look without touching component markup.
        ink: {
          950: '#080D0A', // app background
          900: '#0B120E', // secondary background (rails, bars)
          850: '#101913', // panel
          800: '#141F18', // elevated panel
          700: '#1A2920', // hover
          600: '#26372C', // primary border
          500: '#2F4638',
          400: '#456252',
        },
        accent: {
          DEFAULT: '#6EE7A0',
          soft: '#8FF0B8',
          cyan: '#35C978',
          dim: '#2D754A',
          glow: 'rgba(110,231,160,0.16)',
          surface: '#153624',
        },
        // Neutral text/greys re-tinted to the console palette (text-slate-* is used throughout the app for text hierarchy).
        slate: {
          50: '#F3F7F4', 100: '#E6EEE8', 200: '#CBD6CE', 300: '#A3B2A7', 400: '#8B9B90', 500: '#718077', 600: '#536158', 700: '#3A463F', 800: '#26332B', 900: '#1B2620', 950: '#101813',
        },
        // Status colours (success / warning / error / info) at the shades the app already uses for them.
        red: { 100: '#FBE3E3', 200: '#F8C9C9', 300: '#F5A3A3', 400: '#F28888', 500: '#F07171', 600: '#D95B5B', 700: '#9B3B3B', 900: '#4A1F1F' },
        amber: { 100: '#F8EBD0', 200: '#F2DBA8', 300: '#EDCB82', 400: '#E8B75A', 500: '#D9A441' },
        emerald: { 100: '#D6F5E2', 200: '#B2EBC9', 300: '#86E2AE', 400: '#55D98A', 500: '#3FC074' },
        blue: { 300: '#9ECBFF', 400: '#77B8FF', 700: '#2D5E94' },
        sev: { low: '#38BDF8', medium: '#FBBF24', high: '#FB923C', critical: '#F43F5E' },
        demo: '#C084FC',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: { '2xs': ['0.625rem', { lineHeight: '0.875rem' }], xs2: ['0.6875rem', { lineHeight: '1rem' }] },
      keyframes: {
        fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideIn: { '0%': { transform: 'translateX(8px)', opacity: '0' }, '100%': { transform: 'translateX(0)', opacity: '1' } },
        pulseDot: { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.35' } },
        scan: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(250%)' } },
      },
      animation: {
        'fade-in': 'fadeIn 0.18s ease-out',
        'slide-in': 'slideIn 0.2s ease-out',
        'pulse-dot': 'pulseDot 1.6s ease-in-out infinite',
        scan: 'scan 1.4s linear infinite',
      },
    },
  },
  plugins: [],
}
export default config
