import './globals.css'
import { ThemeProvider } from '@/components/theme-provider'
import { Navbar } from '@/components/navbar'

export const metadata = {
  title: 'DVMDash Lite - Nostr DVM Directory',
  description: 'Explore Data Vending Machines (DVMs) on Nostr: Legacy DVMs, ContextVMs, and Encrypted DVMs.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <Navbar />
          {children}
        </ThemeProvider>
      </body>
    </html>
  )
}
