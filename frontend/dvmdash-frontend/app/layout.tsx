import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
}

export const metadata: Metadata = {
  metadataBase: new URL('https://stats.dvmdash.live'),
  title: {
    template: '%s | DVMDash Stats',
    default: 'DVMDash Stats',
  },
  description: "Statistics for Data Vending Machines (DVMs) on Nostr provided by DVMDash",
  openGraph: {
    type: 'website',
    locale: 'en_US',
    url: 'https://stats.dvmdash.live',
    title: 'DVMDash Stats',
    description: 'Statistics for Data Vending Machines (DVMs) on Nostr provided by DVMDash',
    siteName: 'DVMDash Stats',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'DVMDash Stats',
    description: 'Statistics for Data Vending Machines (DVMs) on Nostr provided by DVMDash',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
