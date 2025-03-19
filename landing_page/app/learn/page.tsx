"use client"

import Link from "next/link"
import { BookOpen, Clock, ExternalLink, GraduationCap, LayoutGrid, Lightbulb, Search, Tag, User } from "lucide-react"
import { useEffect, useState } from "react"

import { ThemeToggle } from "@/components/theme-toggle"
import { fetchEventsByIds, eventToArticle, decodeNoteId } from "@/lib/nostr"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

interface Article {
  title: string
  author: string
  url: string
  description?: string
  category?: string
  readTime?: string
  nostrEvent?: any // Optional field for the original Nostr event
}

// Define the note IDs to fetch with optional category overrides
interface NoteConfig {
  id: string;
  category?: 'tutorial' | 'news' | 'misc';
}

const noteConfigs: NoteConfig[] = [
  { 
    id: 'note1ksn2amfu3pwjr0l28ucgrrg3aahejc3dphvcxvjjzt6fm8k09j4q2mlhwm',
    category: 'tutorial' // Override category for this note
  },
  { 
    id: 'note1l5y82ws076zsfrpvuse0g50zzstcxq832f63834u9zyexl95q7zq9wcvtr',
    category: 'news' // Override category for this note
  },
  { 
    id: 'note19nnafqx7rxwjkagnmqdff3wvjzkxmhgpc3jl4j0m4s87y4vjzshshmmxsw',
    // No category override, will use the one detected from the note's tags
  }
];

// Extract just the IDs for fetching
const noteIds = noteConfigs.map(config => config.id);

export default function LearnPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [articles, setArticles] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)

  // Fetch Nostr events
  useEffect(() => {
    async function fetchNostrArticles() {
      try {
        setLoading(true)
        
        const events = await fetchEventsByIds(noteIds)
        
        // Convert events to Article format and apply any manual category overrides
        const nostrArticles = events.map(event => {
          // Find the config for this event
          const config = noteConfigs.find(config => {
            const hexId = decodeNoteId(config.id);
            return hexId === event.id;
          });
          
          // Get the article data
          const article = eventToArticle(event);
          
          // Apply manual category override if specified
          if (config?.category) {
            article.category = config.category;
          }
          
          return article;
        });
        
        setArticles(nostrArticles)
      } catch (error) {
        console.error('Error fetching Nostr articles:', error)
      } finally {
        setLoading(false)
      }
    }
    
    fetchNostrArticles()
  }, [])

  const filteredArticles = articles.filter(
    (article) =>
      article.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      article.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      article.category?.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const getCategoryColor = (category?: string) => {
    switch (category?.toLowerCase()) {
      case "tutorial":
        return "bg-green-100 text-green-800 hover:bg-green-200"
      case "news":
        return "bg-blue-100 text-blue-800 hover:bg-blue-200"
      case "misc":
        return "bg-gray-100 text-gray-800 hover:bg-gray-200"
      default:
        return "bg-gray-100 text-gray-800 hover:bg-gray-200"
    }
  }

  const getCategoryIcon = (category?: string) => {
    switch (category?.toLowerCase()) {
      case "tutorial":
        return <BookOpen className="h-4 w-4" />
      case "news":
        return <Lightbulb className="h-4 w-4" />
      case "misc":
        return <Tag className="h-4 w-4" />
      default:
        return <Tag className="h-4 w-4" />
    }
  }

  return (
    <div className="min-h-screen bg-white dark:bg-gray-950">
      <header className="sticky top-0 z-10 bg-white dark:bg-gray-950 border-b border-gray-200 dark:border-gray-800">
        <div className="container mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <Link href="/" className="text-2xl font-bold text-gray-900 dark:text-white">
              DVMDash <span className="text-primary text-lg">Learn</span>
            </Link>
            <div className="flex items-center">
              <nav className="hidden md:flex space-x-6 mr-4">
                <Link href="#" className="text-gray-600 dark:text-gray-300 hover:text-primary dark:hover:text-primary">
                  Home
                </Link>
                <Link href="#" className="text-primary font-medium">
                  Learn
                </Link>
                <Link href="#" className="text-gray-600 dark:text-gray-300 hover:text-primary dark:hover:text-primary">
                  Community
                </Link>
                <Link href="#" className="text-gray-600 dark:text-gray-300 hover:text-primary dark:hover:text-primary">
                  Documentation
                </Link>
              </nav>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto mb-12 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 dark:text-white mb-4">
            Learn About Data Vending Machines
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400 mb-8">
            Explore curated resources to master DVM concepts from beginner to advanced
          </p>

          <div className="relative max-w-md mx-auto">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
            <Input
              type="search"
              placeholder="Search articles, topics, or authors..."
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <Tabs defaultValue="all" className="max-w-4xl mx-auto">
          <div className="flex justify-between items-center mb-6">
            <TabsList>
              <TabsTrigger value="all">All Resources</TabsTrigger>
              <TabsTrigger value="tutorial">Tutorials</TabsTrigger>
              <TabsTrigger value="news">News</TabsTrigger>
              <TabsTrigger value="misc">Misc</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="all" className="mt-0">
            {loading ? (
              <div className="text-center py-12">
                <p className="text-gray-500 dark:text-gray-400">Loading articles from Nostr relays...</p>
              </div>
            ) : filteredArticles.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-gray-500 dark:text-gray-400">No articles found matching your search.</p>
              </div>
            ) : (
              <div className="grid gap-6">
                {filteredArticles.map((article, index) => (
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800">
                    <CardHeader className="pb-4">
                      <div className="flex justify-between items-start">
                        <div className="flex items-center gap-2 mb-2">
                          {getCategoryIcon(article.category)}
                          <Badge className={`${getCategoryColor(article.category)} border-0`}>
                            {article.category || "misc"}
                          </Badge>
                        </div>
                        <div className="flex items-center text-gray-500 text-sm">
                          <Clock className="h-3 w-3 mr-1" />
                          {article.readTime}
                        </div>
                      </div>
                      <CardTitle className="text-xl hover:text-primary transition-colors">
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          {article.title}
                        </Link>
                      </CardTitle>
                      <CardDescription className="text-base">{article.description}</CardDescription>
                    </CardHeader>
                    <CardContent className="pb-2">
                      <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
                        <User className="h-3 w-3 mr-1" />
                        <span>Author: {article.author}</span>
                      </div>
                    </CardContent>
                    <CardFooter className="pt-2 flex justify-between">
                      <div></div>
                      <Button variant="outline" size="sm" asChild>
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          Read Article
                          <ExternalLink className="ml-2 h-3 w-3" />
                        </Link>
                      </Button>
                    </CardFooter>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="tutorial">
            <div className="grid gap-6">
              {filteredArticles
                .filter((article) => article.category?.toLowerCase() === "tutorial")
                .map((article, index) => (
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800">
                    <CardHeader className="pb-4">
                      <div className="flex justify-between items-start">
                        <div className="flex items-center gap-2 mb-2">
                          {getCategoryIcon(article.category)}
                          <Badge className="bg-green-100 text-green-800 hover:bg-green-200 border-0">
                            Tutorial
                          </Badge>
                        </div>
                        <div className="flex items-center text-gray-500 text-sm">
                          <Clock className="h-3 w-3 mr-1" />
                          {article.readTime}
                        </div>
                      </div>
                      <CardTitle className="text-xl hover:text-primary transition-colors">
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          {article.title}
                        </Link>
                      </CardTitle>
                      <CardDescription className="text-base">{article.description}</CardDescription>
                    </CardHeader>
                    <CardContent className="pb-2">
                      <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
                        <User className="h-3 w-3 mr-1" />
                        <span>Author: {article.author}</span>
                      </div>
                    </CardContent>
                    <CardFooter className="pt-2 flex justify-between">
                      <div></div>
                      <Button variant="outline" size="sm" asChild>
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          Read Article
                          <ExternalLink className="ml-2 h-3 w-3" />
                        </Link>
                      </Button>
                    </CardFooter>
                  </Card>
                ))}
            </div>
          </TabsContent>

          <TabsContent value="news">
            <div className="grid gap-6">
              {filteredArticles
                .filter((article) => article.category?.toLowerCase() === "news")
                .map((article, index) => (
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800">
                    <CardHeader className="pb-4">
                      <div className="flex justify-between items-start">
                        <div className="flex items-center gap-2 mb-2">
                          {getCategoryIcon(article.category)}
                          <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-200 border-0">
                            News
                          </Badge>
                        </div>
                        <div className="flex items-center text-gray-500 text-sm">
                          <Clock className="h-3 w-3 mr-1" />
                          {article.readTime}
                        </div>
                      </div>
                      <CardTitle className="text-xl hover:text-primary transition-colors">
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          {article.title}
                        </Link>
                      </CardTitle>
                      <CardDescription className="text-base">{article.description}</CardDescription>
                    </CardHeader>
                    <CardContent className="pb-2">
                      <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
                        <User className="h-3 w-3 mr-1" />
                        <span>Author: {article.author}</span>
                      </div>
                    </CardContent>
                    <CardFooter className="pt-2 flex justify-between">
                      <div></div>
                      <Button variant="outline" size="sm" asChild>
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          Read Article
                          <ExternalLink className="ml-2 h-3 w-3" />
                        </Link>
                      </Button>
                    </CardFooter>
                  </Card>
                ))}
            </div>
          </TabsContent>

          <TabsContent value="misc">
            <div className="grid gap-6">
              {filteredArticles
                .filter((article) => article.category?.toLowerCase() === "misc" || !article.category)
                .map((article, index) => (
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800">
                    <CardHeader className="pb-4">
                      <div className="flex justify-between items-start">
                        <div className="flex items-center gap-2 mb-2">
                          {getCategoryIcon(article.category)}
                          <Badge className="bg-gray-100 text-gray-800 hover:bg-gray-200 border-0">
                            Misc
                          </Badge>
                        </div>
                        <div className="flex items-center text-gray-500 text-sm">
                          <Clock className="h-3 w-3 mr-1" />
                          {article.readTime}
                        </div>
                      </div>
                      <CardTitle className="text-xl hover:text-primary transition-colors">
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          {article.title}
                        </Link>
                      </CardTitle>
                      <CardDescription className="text-base">{article.description}</CardDescription>
                    </CardHeader>
                    <CardContent className="pb-2">
                      <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
                        <User className="h-3 w-3 mr-1" />
                        <span>Author: {article.author}</span>
                      </div>
                    </CardContent>
                    <CardFooter className="pt-2 flex justify-between">
                      <div></div>
                      <Button variant="outline" size="sm" asChild>
                        <Link href={article.url} target="_blank" rel="noopener noreferrer">
                          Read Article
                          <ExternalLink className="ml-2 h-3 w-3" />
                        </Link>
                      </Button>
                    </CardFooter>
                  </Card>
                ))}
            </div>
          </TabsContent>
        </Tabs>

        <div className="max-w-4xl mx-auto mt-16 text-center">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Ready to start building?</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            Join our community and start creating your own Data Vending Machines
          </p>
          <div className="flex justify-center gap-4">
            <Button>Get Started</Button>
            <Button variant="outline">Join Community</Button>
          </div>
        </div>
      </main>

      <footer className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-12">
        <div className="container mx-auto px-4">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="mb-6 md:mb-0">
              <Link href="/" className="text-xl font-bold text-gray-900 dark:text-white">
                DVMDash
              </Link>
              <p className="text-gray-600 dark:text-gray-400 mt-2">Building the future of Data Vending Machines</p>
            </div>
            <div className="flex gap-8">
              <div className="grid gap-2">
                <h3 className="font-medium text-gray-900 dark:text-white">Resources</h3>
                <Link href="#" className="text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary">
                  Documentation
                </Link>
                <Link href="#" className="text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary">
                  Tutorials
                </Link>
                <Link href="#" className="text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary">
                  API Reference
                </Link>
              </div>
              <div className="grid gap-2">
                <h3 className="font-medium text-gray-900 dark:text-white">Community</h3>
                <Link href="#" className="text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary">
                  GitHub
                </Link>
                <Link href="#" className="text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary">
                  Discord
                </Link>
                <Link href="#" className="text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary">
                  Twitter
                </Link>
              </div>
            </div>
          </div>
          <div className="mt-8 pt-8 border-t border-gray-200 dark:border-gray-800 text-center text-gray-600 dark:text-gray-400">
            <p>© {new Date().getFullYear()} DVMDash. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
