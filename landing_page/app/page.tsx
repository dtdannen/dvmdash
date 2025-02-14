import Link from "next/link"
import { Github, Mail, ExternalLink } from "lucide-react"

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-900 text-white font-inter">
      <header className="fixed w-full z-10 bg-gray-900 bg-opacity-70 backdrop-filter backdrop-blur-lg">
        <nav className="container mx-auto px-4 py-4 flex justify-between items-center">
          <Link
            href="/"
            className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-green-400"
          >
            DVMDash
          </Link>
          <div className="space-x-6">
            <Link href="#apps" className="text-gray-300 hover:text-white transition duration-300">
              Apps
            </Link>
            <Link href="#about" className="text-gray-300 hover:text-white transition duration-300">
              About
            </Link>
          </div>
        </nav>
      </header>

      <main>
        <section className="pt-32 pb-20 px-4">
          <div className="container mx-auto">
            <h1 className="text-5xl md:text-7xl font-bold mb-6 text-center">
              Welcome to{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-green-400 animate-gradient">
                DVMDash
              </span>
            </h1>
            <p className="text-xl md:text-2xl text-center text-gray-400 mb-12 max-w-3xl mx-auto">
              Monitor, debug, and test Data Vending Machines with our tools.
            </p>
            <div className="flex justify-center">
              <Link
                href="#apps"
                className="bg-gradient-to-r from-purple-500 to-green-500 text-white px-8 py-3 rounded-full font-semibold hover:from-purple-600 hover:to-green-600 transition duration-300 transform hover:scale-105"
              >
                Explore the tools
              </Link>
            </div>
          </div>
        </section>

        <section id="apps" className="py-20 px-4">
          <div className="container mx-auto">
            <h2 className="text-4xl font-bold text-center mb-16">Explore the tools</h2>
            <div className="grid md:grid-cols-3 gap-8">
              <AppCard
                title="Stats"
                description="Comprehensive metrics and analytics dashboard"
                link="https://stats.dvmdash.live/"
                isLive={true}
                icon="📊"
              />
              <AppCard
                title="Debug Tools"
                description="Advanced set of debugging tools for developers"
                link="#"
                isLive={false}
                icon="🛠️"
              />
              <AppCard
                title="Data Vending Playground"
                description="Explore and interact with data vending machines"
                link="#"
                isLive={false}
                icon="🤖"
              />
            </div>
          </div>
        </section>

        <section id="about" className="py-20 px-4 bg-gray-800">
          <div className="container mx-auto max-w-4xl">
            <h2 className="text-4xl font-bold text-center mb-12">About DVMDash</h2>
            <div className="space-y-8">
              <div className="flex items-start">
                <div className="flex-shrink-0 mt-1">
                  <div className="w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-5 w-5 text-white"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                </div>
                <p className="ml-4 text-gray-300">
                  Nostr is a radically open protocol where humans and machines connect through clients and relays to
                  form an uncensorable web of social interaction, enabling permissionless innovation and open
                  communication.
                </p>
              </div>
              <div className="flex items-start">
                <div className="flex-shrink-0 mt-1">
                  <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-5 w-5 text-white"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                </div>
                <p className="ml-4 text-gray-300">
                  <a
                    href="https://github.com/nostr-protocol/nips/blob/master/90.md"
                    className="text-purple-400 hover:text-purple-300"
                  >
                    Data Vending Machines
                  </a>{" "}
                  (DVMs) offload computationally expensive tasks from relays and clients in a decentralized, free-market
                  manner, unlocking powerful new capabilities for AI tools and algorithmic processing.
                </p>
              </div>
              <div className="flex items-start">
                <div className="flex-shrink-0 mt-1">
                  <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-5 w-5 text-white"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M3 3a1 1 0 000 2v8a2 2 0 002 2h2.586l-1.293 1.293a1 1 0 101.414 1.414L10 15.414l2.293 2.293a1 1 0 001.414-1.414L12.414 15H15a2 2 0 002-2V5a1 1 0 100-2H3zm11.707 4.707a1 1 0 00-1.414-1.414L10 9.586 8.707 8.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                </div>
                <p className="ml-4 text-gray-300">
                  DVMDash provides essential tools for monitoring, analyzing, and understanding DVM activity across
                  Nostr.
                </p>
              </div>
              <div className="flex justify-center mt-8">
                <a
                  href="https://github.com/dtdannen/dvmdash"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center bg-gradient-to-r from-purple-500 to-green-500 text-white px-8 py-3 rounded-full font-semibold hover:from-purple-600 hover:to-green-600 transition duration-300 transform hover:scale-105"
                >
                  <Github className="mr-2" />
                  Explore on GitHub
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

interface AppCardProps {
  title: string;
  description: string;
  link: string;
  isLive: boolean;
  icon: string;
}

function AppCard({ title, description, link, isLive, icon }: AppCardProps) {
  return (
    <div className="bg-gray-800 bg-opacity-50 backdrop-filter backdrop-blur-lg rounded-xl p-6 transform transition duration-500 hover:scale-105 border border-purple-500/20">
      <div className="text-4xl mb-4">{icon}</div>
      <h3 className="text-2xl font-semibold mb-2">{title}</h3>
      <p className="text-gray-400 mb-4">{description}</p>
      {isLive ? (
        <Link href={link} className="inline-flex items-center text-green-400 hover:text-green-300 font-medium">
          Launch App <ExternalLink className="ml-1 h-4 w-4" />
        </Link>
      ) : (
        <span className="text-gray-500 font-medium">Coming Soon</span>
      )}
    </div>
  )
}
