import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        // GeoTrace console palette: near-black blue-greys with a restrained teal/cyan accent.
        ink: {
          950: '#04070C',
          900: '#070B12',
          850: '#0A0F18',
          800: '#0D1420',
          700: '#131C2B',
          600: '#1B2638',
          500: '#27364D',
          400: '#3A4C68',
        },
        accent: {
          DEFAULT: '#2DD4BF',
          soft: '#5EEAD4',
          cyan: '#22D3EE',
          dim: '#0F766E',
          glow: 'rgba(45,212,191,0.18)',
        },
        sev: { low: '#38BDF8', medium: '#FBBF24', high: '#FB923C', critical: '#F43F5E' },
        demo: '#C084FC',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
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
