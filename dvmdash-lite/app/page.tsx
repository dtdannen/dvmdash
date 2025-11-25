import Link from 'next/link'

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16 max-w-6xl">
        {/* Header */}
        <header className="text-center mb-16">
          <h1 className="text-5xl md:text-7xl font-bold mb-6">
            DVMDash Lite
          </h1>
          <p className="text-xl md:text-2xl text-muted-foreground mb-8">
            Explore Data Vending Machines (DVMs) on Nostr
          </p>
        </header>

        {/* Sunset Notice */}
        <div className="bg-yellow-900/20 border border-yellow-600/50 rounded-lg p-6 mb-12 max-w-3xl mx-auto">
          <h2 className="text-2xl font-semibold text-yellow-400 mb-3 flex items-center gap-2">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Notice: Transitioning to Lightweight Directory
          </h2>
          <p className="text-muted-foreground leading-relaxed">
            The full DVMDash monitoring service has been sunset as the ecosystem transitions to newer standards.
            This lightweight directory showcases the evolution of DVMs on Nostr, from legacy implementations to
            modern encrypted and context-aware solutions.
          </p>
        </div>

        {/* Introduction */}
        <div className="text-center mb-16 max-w-3xl mx-auto">
          <p className="text-lg text-muted-foreground leading-relaxed">
            Data Vending Machines (DVMs) are specialized services on Nostr that offload computationally
            expensive tasks from relays and clients in a decentralized manner. They power AI tools,
            algorithmic processing, and many other use cases in the Nostr ecosystem.
          </p>
        </div>

        {/* Browse DVMs Section */}
        <div className="max-w-2xl mx-auto mb-16">
          <Link
            href="/dvms"
            className="block bg-card border rounded-xl p-10 hover:bg-muted/50 transition-all duration-300 hover:scale-105 group text-center"
          >
            <div className="flex items-center justify-center w-20 h-20 bg-primary/20 rounded-full mb-6 mx-auto group-hover:bg-primary/30 transition-colors">
              <svg className="w-10 h-10 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h3 className="text-3xl font-semibold mb-4">Browse All DVMs</h3>
            <p className="text-muted-foreground mb-6 text-lg">
              Explore all Data Vending Machines across the Nostr network. Filter by type (Legacy, Encrypted, ContextVM),
              search by name or description, and toggle between grid and list views.
            </p>
            <div className="flex flex-wrap justify-center gap-3 mb-6">
              <span className="px-3 py-1 bg-purple-500/20 text-purple-300 rounded-full text-sm border border-purple-500/50">
                Legacy DVMs
              </span>
              <span className="px-3 py-1 bg-pink-500/20 text-pink-300 rounded-full text-sm border border-pink-500/50">
                Encrypted DVMs
              </span>
              <span className="px-3 py-1 bg-green-500/20 text-green-300 rounded-full text-sm border border-green-500/50">
                ContextVM Servers
              </span>
            </div>
            <div className="text-primary font-medium flex items-center justify-center gap-2 group-hover:gap-3 transition-all text-lg">
              Explore DVMs
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center mb-12">
          <Link
            href="/history"
            className="inline-flex items-center justify-center gap-3 bg-purple-600 hover:bg-purple-700 text-white px-8 py-4 rounded-lg text-lg font-semibold transition-all duration-300 hover:scale-105 shadow-lg"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            View Historical Data
          </Link>
          <Link
            href="/learn"
            className="inline-flex items-center justify-center gap-3 bg-primary hover:bg-primary/90 text-primary-foreground px-8 py-4 rounded-lg text-lg font-semibold transition-all duration-300 hover:scale-105 shadow-lg"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
            Learn About DVMs
          </Link>
        </div>

        {/* Footer */}
        <footer className="text-center text-muted-foreground text-sm mt-16 border-t pt-8">
          <p>
            DVMDash Lite - A lightweight directory of Data Vending Machines on Nostr
          </p>
          <p className="mt-2">
            Built with ❤️ for the Nostr community
          </p>
        </footer>
      </div>
    </div>
  )
}
