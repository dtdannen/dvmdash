import Link from "next/link"
import { ExternalLink } from "lucide-react"

interface Article {
  title: string
  author: string
  url: string
  description?: string
}

const articles: Article[] = [
  {
    title: "IoT DVM Simulator Project",
    author: "nostriot@nostriot.com",
    url: "https://habla.news/u/nostriot@nostriot.com/IoT-DVM-Simulator-Project-pzgehz",
    description: "Exploring IoT integration with DVMs through simulation"
  },
  {
    title: "Shipping Shipyard DVM",
    author: "f7z.io",
    url: "https://habla.news/u/f7z.io/Shipping-Shipyard-DVM-wey3m4",
    description: "Building and deploying DVMs with Shipyard"
  },
  {
    title: "DVM Development Guide",
    author: "dustind@dtdannen.github.io",
    url: "https://habla.news/u/dustind@dtdannen.github.io/1738308714424",
    description: "A comprehensive guide to DVM development"
  },
  {
    title: "Understanding DVM Architecture",
    author: "dustind@dtdannen.github.io",
    url: "https://habla.news/u/dustind@dtdannen.github.io/1737576026224",
    description: "Deep dive into DVM architecture and design"
  },
  {
    title: "DVM Development Best Practices",
    author: "dustind@dtdannen.github.io",
    url: "https://habla.news/u/dustind@dtdannen.github.io/1723526541960",
    description: "Best practices for developing reliable DVMs"
  },
  {
    title: "DVM Development Updates",
    author: "hodlbod@coracle.social",
    url: "https://habla.news/u/hodlbod@coracle.social/1739411624647",
    description: "Latest updates in DVM development"
  }
]

export default function LearnPage() {
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
        </nav>
      </header>

      <main className="pt-32 pb-20 px-4">
        <div className="container mx-auto">
          <h1 className="text-4xl md:text-5xl font-bold mb-8 text-center">
            Learn About DVMs
          </h1>
          <p className="text-xl text-center text-gray-400 mb-12 max-w-3xl mx-auto">
            Explore curated articles and resources about Data Vending Machines
          </p>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {articles.map((article, index) => (
              <a
                key={index}
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-gray-800 bg-opacity-50 backdrop-filter backdrop-blur-lg rounded-xl p-6 transform transition duration-500 hover:scale-105 border border-purple-500/20"
              >
                <h3 className="text-xl font-semibold mb-2">{article.title}</h3>
                <p className="text-gray-400 mb-4 text-sm">{article.description}</p>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500 text-sm">{article.author}</span>
                  <ExternalLink className="h-4 w-4 text-green-400" />
                </div>
              </a>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
