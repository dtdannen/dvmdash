'use client'

import { useEffect, useState } from 'react'
import { fetchEventsByNaddrs, eventToArticle } from '@/lib/nostr'
import { LoadingSpinner } from '@/components/loading-spinner'

interface Article {
  title: string
  author: string
  url: string
  primalUrl?: string
  description?: string
  category?: string
  readTime?: string
  imageUrl?: string
  createdAt?: number
  naddr?: string
}

interface NoteConfig {
  naddr: string
  category?: 'tutorial' | 'news' | 'idea' | 'misc'
}

const noteConfigs: NoteConfig[] = [
  {
    naddr: 'naddr1qq8xgandvdcz6am0wf4hx6r0wqqsuamnwvaz7t6qdehhxtnvdakqygrtx7qw72tjuu7nwzuy50j3u74f4c6t7sff8rw0hkw97cajy9qkeqpsgqqqw4rs6uvppz',
    category: 'tutorial'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzq743a4atthagufhsvacq42c7yk4zmphjz2vg3mw6s055nhuwz5n4qqsyjm6594z9vnfd2d5k6atvv96x7u3d2pex76n9vd6z6ur6vajks7sa5fzxa',
    category: 'news'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzp75cf0tahv5z7plpdeaws7ex52nmnwgtwfr2g3m37r844evqrr6jqqw9x6rfwpcxjmn894fks6ts09shyepdg3ty6tthv4unxmf5n788at',
    category: 'news'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzden8qenqwphxy6rgv3576yund',
    category: 'idea'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzdenxu6nwd3sxgmryv3506t7ws',
    category: 'news'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzdejxv6nyd34xscnjd3sz05q9vc',
    category: 'news'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzp978pfzrv6n9xhq5tvenl9e74pklmskh4xw6vxxyp3j8qkke3cezqqxnzden8y6rzvfkxg6rvdphrmylpl',
    category: 'tutorial'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpwa4mkswz4t8j70s2s6q00wzqv7k7zamxrmj2y4fs88aktcfuf68qqnxx6rpd9hxjmn894j8vmtn94nx7u3ddehhxarj943kjcmy94cxjur9d35kuetn0uz742',
    category: 'idea'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qq2nq735d92hwj2wg3xrxdp5x44y7apexaxnvn96qwa',
    category: 'idea'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzde4xscryvpc8qerzwf55lgxw9',
    category: 'news'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzde4xscrzwpexyerzdes85ynm8',
    category: 'tutorial'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzde4xy6nwwf3x5cn2wfjg32j4h',
    category: 'idea'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzden8y6nqwp3xqer2vec3d8m8c',
    category: 'news'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzdenxu6nwd3sxgmryv3506t7ws',
    category: 'news'
  },
  {
    naddr: 'naddr1qvzqqqr4gupzpkscaxrqqs8nhaynsahuz6c6jy4wtfhkl2x4zkwrmc4cyvaqmxz3qqxnzdejxv6nyd34xscnjd3sz05q9v',
    category: 'news'
  }
]

const naddrs = noteConfigs.map(config => config.naddr)

export default function ArticlesPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [articles, setArticles] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedCategory, setSelectedCategory] = useState<string>('all')

  useEffect(() => {
    async function fetchNostrArticles() {
      try {
        setLoading(true)

        const events = await fetchEventsByNaddrs(naddrs)

        if (!events || events.length === 0) {
          console.warn('No events found')
          setArticles([])
          return
        }

        const articlePromises = events.map(async (event: any) => {
          const article = await eventToArticle(event)

          // Apply manual category override if specified
          const config = noteConfigs.find(c => c.naddr === article.naddr)
          if (config && config.category) {
            article.category = config.category
          }

          return article
        })

        const fetchedArticles = await Promise.all(articlePromises)

        // Sort by creation date (newest first)
        const sortedArticles = fetchedArticles.sort((a, b) => {
          const aTime = a.createdAt || 0
          const bTime = b.createdAt || 0
          return bTime - aTime
        })

        setArticles(sortedArticles)
      } catch (error) {
        console.error('Error fetching articles:', error)
        setArticles([])
      } finally {
        setLoading(false)
      }
    }

    fetchNostrArticles()
  }, [])

  const filteredArticles = articles.filter((article) => {
    const matchesSearch =
      article.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      article.author.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (article.description && article.description.toLowerCase().includes(searchQuery.toLowerCase()))

    const matchesCategory =
      selectedCategory === 'all' ||
      article.category === selectedCategory

    return matchesSearch && matchesCategory
  })

  const categories = ['all', 'tutorial', 'news', 'idea', 'misc']
  const categoryLabels: Record<string, string> = {
    all: 'All Articles',
    tutorial: 'Tutorials',
    news: 'News',
    idea: 'Ideas',
    misc: 'Miscellaneous'
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 via-gray-900 to-black">
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl md:text-5xl font-bold mb-4 bg-gradient-to-r from-purple-400 to-pink-400 text-transparent bg-clip-text">
            Articles
          </h1>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            Educational articles and guides about Data Vending Machines on Nostr
          </p>
        </div>

        {/* Search and Filter */}
        <div className="mb-8 space-y-4">
          <div className="relative">
            <input
              type="text"
              placeholder="Search articles..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 pl-12 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 transition-colors"
            />
            <svg
              className="w-5 h-5 text-gray-500 absolute left-4 top-1/2 transform -translate-y-1/2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>

          {/* Category Tabs */}
          <div className="flex flex-wrap gap-2">
            {categories.map((category) => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  selectedCategory === category
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {categoryLabels[category]}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <LoadingSpinner message="Loading articles..." />
        ) : filteredArticles.length > 0 ? (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredArticles.map((article, index) => (
              <div
                key={index}
                className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden hover:border-purple-500 transition-all duration-300 hover:scale-105"
              >
                {article.imageUrl && (
                  <img
                    src={article.imageUrl}
                    alt={article.title}
                    className="w-full h-48 object-cover"
                  />
                )}
                <div className="p-6">
                  {article.category && (
                    <span className="inline-block px-3 py-1 bg-purple-500/20 text-purple-300 text-xs font-semibold rounded-full mb-3">
                      {article.category.charAt(0).toUpperCase() + article.category.slice(1)}
                    </span>
                  )}
                  <h3 className="text-xl font-semibold text-white mb-2">{article.title}</h3>
                  {article.description && (
                    <p className="text-gray-400 text-sm mb-4 line-clamp-3">{article.description}</p>
                  )}
                  <div className="flex items-center justify-between text-sm text-gray-500 mb-4">
                    <span>By {article.author}</span>
                    {article.readTime && <span>{article.readTime}</span>}
                  </div>
                  <div className="flex gap-2">
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 text-center bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg transition-colors"
                    >
                      Read on Habla
                    </a>
                    {article.primalUrl && (
                      <a
                        href={article.primalUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
                      >
                        Primal
                      </a>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-16">
            <svg
              className="w-16 h-16 text-gray-600 mx-auto mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <h3 className="text-xl font-semibold text-gray-400 mb-2">No articles found</h3>
            <p className="text-gray-500">Try adjusting your search or filter</p>
          </div>
        )}

        {/* Footer */}
        <footer className="text-center text-gray-500 text-sm mt-16 border-t border-gray-800 pt-8">
          <p>
            Want to add an article?{' '}
            <a
              href="https://github.com/dtdannen/dvmdash/blob/main/dvmdash-lite/app/articles/page.tsx"
              target="_blank"
              rel="noopener noreferrer"
              className="text-purple-400 hover:underline"
            >
              PRs welcome!
            </a>
          </p>
        </footer>
      </div>
    </div>
  )
}
