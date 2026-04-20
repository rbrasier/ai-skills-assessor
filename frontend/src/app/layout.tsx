import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Resonant',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" style={{ height: '100%' }}>
      <body style={{ margin: 0, height: '100%' }}>{children}</body>
    </html>
  )
}
