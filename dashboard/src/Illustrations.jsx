export function Icon({ name = "heart", ...props }) {
  const paths = {
    image: "M4 3h16v18H4ZM4 16l5-5 4 4 3-3 4 4M15 7h.01",
    heart: "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z",
    mail: "M3 5h18v14H3ZM3 5l9 8 9-8",
    calendar: "M4 5h16v16H4ZM8 3v4m8-4v4M4 11h16m-12 4h2m4 0h2",
    sparkle: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z",
    instagram: "M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4Zm9 9a4 4 0 1 1-8 0 4 4 0 0 1 8 0Zm1-5h.01",
  };
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name] || paths.heart} /></svg>;
}

export function EnvelopeIllustration() {
  return <svg className="envelope-illustration" viewBox="0 0 160 112" aria-hidden="true">
    <ellipse cx="80" cy="101" rx="48" ry="6" fill="#e9e2f1" />
    <path d="m34 48 46-31 46 31v43H34Z" fill="#dcd0ed" stroke="#b7a4cd" strokeWidth="2" />
    <rect x="49" y="21" width="62" height="63" rx="6" fill="#fffdf7" stroke="#d9cfe4" strokeWidth="2" />
    <path d="M70 41c-8-10-17 2-8 10l18 14 18-14c9-8 0-20-8-10l-10 8Z" fill="#e8a2ac" transform="translate(14 5) scale(.82)" />
    <path d="m34 48 46 29 46-29v43H34Z" fill="#eee5f7" stroke="#b7a4cd" strokeWidth="2" strokeLinejoin="round" />
    <path d="m34 91 34-25m58 25-34-25" stroke="#b7a4cd" strokeWidth="2" />
    <path d="m23 23 2-6 2 6 6 2-6 2-2 6-2-6-6-2Zm112 13 2-5 2 5 5 2-5 2-2 5-2-5-5-2Z" fill="#d4b273" />
  </svg>;
}
