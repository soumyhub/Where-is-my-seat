/* Original mark: a location pin with a seat inside it, in the WIMT-style blue.
   (Deliberately not a copy of the Where is my Train logo.) */
export function LogoMark({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} role="img" aria-label="Where is my Seat logo">
      <circle cx="24" cy="24" r="23" fill="#ffffff" />
      <circle cx="24" cy="24" r="20.5" fill="#2887c7" />
      <path
        d="M24 9.5c-6.3 0-11.4 4.9-11.4 11 0 8.1 11.4 19.2 11.4 19.2s11.4-11.1 11.4-19.2c0-6.1-5.1-11-11.4-11Z"
        fill="#ffffff"
      />
      <path
        d="M20.2 14.2c.9 0 1.6.7 1.6 1.6v5.6h5.5c1.2 0 2.2.9 2.3 2.1l.4 4.1h-2.3l-.3-3.6h-6.5c-1 0-1.8-.8-1.8-1.8v-6.4c0-.9.7-1.6 1.6-1.6Z"
        fill="#1b63a7"
      />
      <rect x="18.5" y="25.6" width="10.6" height="2.1" rx="1" fill="#1b63a7" />
      <circle cx="33.6" cy="12.8" r="4.1" fill="#40ae43" stroke="#ffffff" strokeWidth="1.6" />
      <path d="m31.8 12.9 1.3 1.3 2.4-2.6" fill="none" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return <span className={`text-[19px] font-medium tracking-tight ${className}`}>Where is my Seat</span>;
}
