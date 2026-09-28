/** One stroke family for every icon: 1.6 px, round caps, 20 px box. */
import type { ReactNode } from 'react'

function Icon({ children, size = 18 }: { children: ReactNode; size?: number }) {
  return (
    <svg viewBox="0 0 20 20" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  )
}

export const MicIcon = () => (
  <Icon><rect x="7.5" y="2.5" width="5" height="9.5" rx="2.5" /><path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5" /></Icon>
)
export const MicOffIcon = () => (
  <Icon><rect x="7.5" y="2.5" width="5" height="9.5" rx="2.5" /><path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5M3 3l14 14" /></Icon>
)
export const EndIcon = () => (
  <Icon><rect x="5" y="5" width="10" height="10" rx="1.5" /></Icon>
)
export const DownloadIcon = () => (
  <Icon><path d="M10 3v10M6 9.5l4 4 4-4M4 16.5h12" /></Icon>
)
export const UploadIcon = () => (
  <Icon size={16}><path d="M10 13.5V3.5M6 7l4-4 4 4M4 16.5h12" /></Icon>
)
export const CheckIcon = () => (
  <span className="check"><Icon size={16}><path d="M4.5 10.5l3.5 3.5 7.5-8" /></Icon></span>
)
export const MicLargeIcon = () => (
  <span className="dialog-icon">
    <svg viewBox="0 0 20 20" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.3"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="7.5" y="2.5" width="5" height="9.5" rx="2.5" /><path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5" />
    </svg>
  </span>
)
