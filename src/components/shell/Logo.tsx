export function Logo({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} role="img" aria-label="GeoTrace">
      <defs>
        <linearGradient id="gt-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8FF0B8" />
          <stop offset="1" stopColor="#35C978" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="13.5" fill="none" stroke="url(#gt-g)" strokeWidth="1.6" />
      <ellipse cx="16" cy="16" rx="5.8" ry="13.5" fill="none" stroke="url(#gt-g)" strokeWidth="1" opacity="0.55" />
      <path d="M2.5 16h27M5 9.5h22M5 22.5h22" stroke="url(#gt-g)" strokeWidth="0.8" opacity="0.35" />
      <path d="M11 20.5l4-5.5 3 3.2 4.5-7" fill="none" stroke="url(#gt-g)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="22.5" cy="11.2" r="1.7" fill="#8FF0B8" />
    </svg>
  )
}
