import Link from 'next/link'

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16 max-w-6xl">
        {/* Header */}
        <header className="text-center mb-16">
          <h1 className="text-4xl md:text-5xl font-bold mb-6">
            Explore Data Vending Machines on Nostr
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            DVMs are API services over Nostr. No domain names. Innately asynchronous for long-running jobs.
          </p>
        </header>

        {/* Three Main Sections */}
        <div className="grid md:grid-cols-3 gap-6 mb-16">
          {/* History */}
          <Link
            href="/history"
            className="block bg-card border rounded-xl p-8 hover:bg-muted/50 transition-all duration-300 hover:scale-105 group"
          >
            <div className="flex items-center justify-center w-16 h-16 bg-purple-500/20 rounded-full mb-6 group-hover:bg-purple-500/30 transition-colors">
              <svg className="w-8 h-8 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold mb-3">History</h2>
            <p className="text-muted-foreground mb-4">
              Explore historical data from the DVM ecosystem. View trends, statistics,
              and the evolution of DVMs over time.
            </p>
            <div className="text-purple-400 font-medium flex items-center gap-2 group-hover:gap-3 transition-all">
              View History
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>

          {/* DVMs */}
          <Link
            href="/dvms"
            className="block bg-card border rounded-xl p-8 hover:bg-muted/50 transition-all duration-300 hover:scale-105 group"
          >
            <div className="flex items-center justify-center w-16 h-16 bg-primary/20 rounded-full mb-6 group-hover:bg-primary/30 transition-colors">
              <svg className="w-8 h-8 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold mb-3">DVMs</h2>
            <p className="text-muted-foreground mb-4">
              Browse all Data Vending Machines. Filter by type, search by name,
              and discover services across the Nostr network.
            </p>
            <div className="flex flex-wrap gap-2 mb-4">
              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded text-xs">Legacy</span>
              <span className="px-2 py-0.5 bg-pink-500/20 text-pink-300 rounded text-xs">Encrypted</span>
              <span className="px-2 py-0.5 bg-green-500/20 text-green-300 rounded text-xs">ContextVM</span>
            </div>
            <div className="text-primary font-medium flex items-center gap-2 group-hover:gap-3 transition-all">
              Explore DVMs
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>

          {/* Articles */}
          <Link
            href="/articles"
            className="block bg-card border rounded-xl p-8 hover:bg-muted/50 transition-all duration-300 hover:scale-105 group"
          >
            <div className="flex items-center justify-center w-16 h-16 bg-green-500/20 rounded-full mb-6 group-hover:bg-green-500/30 transition-colors">
              <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold mb-3">Articles</h2>
            <p className="text-muted-foreground mb-4">
              Learn about DVMs, NIPs, and the evolving standards powering
              decentralized computation on Nostr.
            </p>
            <div className="text-green-400 font-medium flex items-center gap-2 group-hover:gap-3 transition-all">
              Read Articles
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>
        </div>

        {/* Footer */}
        <footer className="text-center text-muted-foreground text-sm border-t pt-8">
          <p>
            A lightweight directory of Data Vending Machines on Nostr
          </p>
        </footer>
      </div>
    </div>
  )
}
