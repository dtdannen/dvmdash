import './globals.css'

export const metadata = {
  title: 'DVMDash',
  description: 'Explore our suite of cutting-edge tools for metrics, debugging, and data vending machines.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
