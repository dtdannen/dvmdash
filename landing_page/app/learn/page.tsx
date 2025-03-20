"use client"

import Link from "next/link"
import { BookOpen, Clock, ExternalLink, GraduationCap, LayoutGrid, Lightbulb, Newspaper, Search, Tag, User } from "lucide-react"
import { useEffect, useState } from "react"

import { ThemeToggle } from "@/components/theme-toggle"
import { fetchEventsByNaddrs, eventToArticle, decodeNaddr } from "@/lib/nostr"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

interface Article {
  title: string
  author: string
  url: string
  primalUrl?: string // URL for Primal
  description?: string
  category?: string
  readTime?: string
  imageUrl?: string // Field for the article image
  createdAt?: number // Timestamp for sorting
  naddr?: string // naddr identifier
  nostrEvent?: any // Optional field for the original Nostr event
}

// Define the naddr identifiers to fetch with optional category overrides
interface NoteConfig {
  naddr: string;
  category?: 'tutorial' | 'news' | 'idea' | 'misc';
}

const noteConfigs: NoteConfig[] = [
  { 
    naddr: 'naddr1qvzqqqr4gupzq743a4atthagufhsvacq42c7yk4zmphjz2vg3mw6s055nhuwz5n4qqsyjm6594z9vnfd2d5k6atvv96x7u3d2pex76n9vd6z6ur6vajks7sa5fzxa',
    category: 'news' // Override category for this note
  },
  { 
    naddr: 'naddr1qvzqqqr4gupzp75cf0tahv5z7plpdeaws7ex52nmnwgtwfr2g3m37r844evqrr6jqqw9x6rfwpcxjmn894fks6ts09shyepdg3ty6tthv4unxmf5n788at',
    category: 'news' // Override category for this note
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
  }
];

// Extract just the naddrs for fetching
const naddrs = noteConfigs.map(config => config.naddr);

export default function LearnPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [articles, setArticles] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)

  // Fetch Nostr events
  useEffect(() => {
    async function fetchNostrArticles() {
      try {
        setLoading(true)
        
        // Fetch events with error handling
        let events: any[] = [];
        try {
          events = await fetchEventsByNaddrs(naddrs);
        } catch (fetchError) {
          console.error('Error fetching events by naddrs:', fetchError);
          events = []; // Use empty array if fetch fails
        }
        
        if (!events || events.length === 0) {
          console.warn('No events found or error occurred during fetch');
          setArticles([]);
          return;
        }
        
        // Convert events to Article format and apply any manual category overrides
        const articlePromises = events.map(async (event: any) => {
          try {
            // Find the config for this event
            const eventCoordinates = {
              kind: event.kind,
              pubkey: event.pubkey,
              identifier: event.tags?.find((t: string[]) => t[0] === 'd')?.[1] || ''
            };
            
            // Find the matching naddr config
            const config = noteConfigs.find(config => {
              try {
                const decoded = decodeNaddr(config.naddr);
                if (!decoded) return false;
                
                return decoded.kind === eventCoordinates.kind && 
                      decoded.pubkey === eventCoordinates.pubkey && 
                      decoded.identifier === eventCoordinates.identifier;
              } catch (decodeError) {
                console.error('Error decoding naddr in config matching:', decodeError);
                return false;
              }
            });
            
            // Get the article data (now async)
            const article = await eventToArticle(event);
            
            // Apply manual category override if specified
            if (config?.category) {
              article.category = config.category;
            }
            
            return article;
          } catch (eventError) {
            console.error('Error processing event:', eventError, event);
            // Return a minimal article to avoid breaking the UI
            return {
              title: 'Error loading article',
              author: 'Unknown',
              url: '#',
              description: 'There was an error loading this article.',
              category: 'misc',
              readTime: '1 min',
              createdAt: 0
            };
          }
        });
        
        // Wait for all article promises to resolve
        let nostrArticles: Article[] = [];
        try {
          nostrArticles = await Promise.all(articlePromises);
        } catch (promiseError) {
          console.error('Error resolving article promises:', promiseError);
          nostrArticles = []; // Use empty array if promises fail
        }
        
        // Sort articles by creation date (newest first)
        const sortedArticles = nostrArticles.sort((a: Article, b: Article) => {
          // If createdAt is missing for either article, put it at the end
          if (!a.createdAt) return 1;
          if (!b.createdAt) return -1;
          return b.createdAt - a.createdAt;
        });
        
        setArticles(sortedArticles);
      } catch (error) {
        console.error('Error fetching Nostr articles:', error);
        setArticles([]); // Set empty array on error
      } finally {
        setLoading(false);
      }
    }
    
    fetchNostrArticles();
  }, []);

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
      case "idea":
        return "bg-purple-100 text-purple-800 hover:bg-purple-200"
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
      case "idea":
        return <Lightbulb className="h-4 w-4" />
      case "news":
        return <Newspaper className="h-4 w-4" />
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
            Discover the latest news, ideas, and tutorials from the DVM community
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
              <TabsTrigger value="idea">Ideas</TabsTrigger>
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
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800 transition-all hover:shadow-md">
                    <div className="flex flex-col md:flex-row">
                      {article.imageUrl && (
                        <div className="md:w-1/3 h-48 md:h-auto overflow-hidden border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-800">
                          <img 
                            src={article.imageUrl} 
                            alt={article.title} 
                            className="w-full h-full object-contain transition-transform hover:scale-105"
                            onError={(e) => {
                              // Hide the image container if loading fails
                              const target = e.target as HTMLImageElement;
                              if (target.parentElement) {
                                target.parentElement.style.display = 'none';
                              }
                              // Make the content take full width
                              const contentDiv = target.parentElement?.nextElementSibling;
                              if (contentDiv) {
                                contentDiv.className = 'w-full';
                              }
                            }}
                          />
                        </div>
                      )}
                      <div className={article.imageUrl ? "md:w-2/3" : "w-full"}>
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
                        <CardFooter className="pt-2 flex justify-end gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <Link href={article.url} target="_blank" rel="noopener noreferrer">
                              Read on Habla.news
                              <ExternalLink className="ml-2 h-3 w-3" />
                            </Link>
                          </Button>
                          {article.primalUrl && (
                            <Button variant="outline" size="sm" asChild>
                              <Link href={article.primalUrl} target="_blank" rel="noopener noreferrer">
                                Read on Primal
                                <ExternalLink className="ml-2 h-3 w-3" />
                              </Link>
                            </Button>
                          )}
                        </CardFooter>
                      </div>
                    </div>
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
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800 transition-all hover:shadow-md">
                    <div className="flex flex-col md:flex-row">
                      {article.imageUrl && (
                        <div className="md:w-1/3 h-48 md:h-auto overflow-hidden border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-800">
                          <img 
                            src={article.imageUrl} 
                            alt={article.title} 
                            className="w-full h-full object-contain transition-transform hover:scale-105"
                            onError={(e) => {
                              // Hide the image container if loading fails
                              const target = e.target as HTMLImageElement;
                              if (target.parentElement) {
                                target.parentElement.style.display = 'none';
                              }
                              // Make the content take full width
                              const contentDiv = target.parentElement?.nextElementSibling;
                              if (contentDiv) {
                                contentDiv.className = 'w-full';
                              }
                            }}
                          />
                        </div>
                      )}
                      <div className={article.imageUrl ? "md:w-2/3" : "w-full"}>
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
                        <CardFooter className="pt-2 flex justify-end gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <Link href={article.url} target="_blank" rel="noopener noreferrer">
                              Read on Habla.news
                              <ExternalLink className="ml-2 h-3 w-3" />
                            </Link>
                          </Button>
                          {article.primalUrl && (
                            <Button variant="outline" size="sm" asChild>
                              <Link href={article.primalUrl} target="_blank" rel="noopener noreferrer">
                                Read on Primal
                                <ExternalLink className="ml-2 h-3 w-3" />
                              </Link>
                            </Button>
                          )}
                        </CardFooter>
                      </div>
                    </div>
                  </Card>
                ))}
            </div>
          </TabsContent>

          <TabsContent value="news">
            <div className="grid gap-6">
              {filteredArticles
                .filter((article) => article.category?.toLowerCase() === "news")
                .map((article, index) => (
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800 transition-all hover:shadow-md">
                    <div className="flex flex-col md:flex-row">
                      {article.imageUrl && (
                        <div className="md:w-1/3 h-48 md:h-auto overflow-hidden border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-800">
                          <img 
                            src={article.imageUrl} 
                            alt={article.title} 
                            className="w-full h-full object-contain transition-transform hover:scale-105"
                            onError={(e) => {
                              // Hide the image container if loading fails
                              const target = e.target as HTMLImageElement;
                              if (target.parentElement) {
                                target.parentElement.style.display = 'none';
                              }
                              // Make the content take full width
                              const contentDiv = target.parentElement?.nextElementSibling;
                              if (contentDiv) {
                                contentDiv.className = 'w-full';
                              }
                            }}
                          />
                        </div>
                      )}
                      <div className={article.imageUrl ? "md:w-2/3" : "w-full"}>
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
                        <CardFooter className="pt-2 flex justify-end gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <Link href={article.url} target="_blank" rel="noopener noreferrer">
                              Read on Habla.news
                              <ExternalLink className="ml-2 h-3 w-3" />
                            </Link>
                          </Button>
                          {article.primalUrl && (
                            <Button variant="outline" size="sm" asChild>
                              <Link href={article.primalUrl} target="_blank" rel="noopener noreferrer">
                                Read on Primal
                                <ExternalLink className="ml-2 h-3 w-3" />
                              </Link>
                            </Button>
                          )}
                        </CardFooter>
                      </div>
                    </div>
                  </Card>
                ))}
            </div>
          </TabsContent>

          <TabsContent value="idea">
            <div className="grid gap-6">
              {filteredArticles
                .filter((article) => article.category?.toLowerCase() === "idea")
                .map((article, index) => (
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800 transition-all hover:shadow-md">
                    <div className="flex flex-col md:flex-row">
                      {article.imageUrl && (
                        <div className="md:w-1/3 h-48 md:h-auto overflow-hidden border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-800">
                          <img 
                            src={article.imageUrl} 
                            alt={article.title} 
                            className="w-full h-full object-contain transition-transform hover:scale-105"
                            onError={(e) => {
                              // Hide the image container if loading fails
                              const target = e.target as HTMLImageElement;
                              if (target.parentElement) {
                                target.parentElement.style.display = 'none';
                              }
                              // Make the content take full width
                              const contentDiv = target.parentElement?.nextElementSibling;
                              if (contentDiv) {
                                contentDiv.className = 'w-full';
                              }
                            }}
                          />
                        </div>
                      )}
                      <div className={article.imageUrl ? "md:w-2/3" : "w-full"}>
                        <CardHeader className="pb-4">
                          <div className="flex justify-between items-start">
                            <div className="flex items-center gap-2 mb-2">
                              {getCategoryIcon(article.category)}
                              <Badge className="bg-purple-100 text-purple-800 hover:bg-purple-200 border-0">
                                Idea
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
                        <CardFooter className="pt-2 flex justify-end gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <Link href={article.url} target="_blank" rel="noopener noreferrer">
                              Read on Habla.news
                              <ExternalLink className="ml-2 h-3 w-3" />
                            </Link>
                          </Button>
                          {article.primalUrl && (
                            <Button variant="outline" size="sm" asChild>
                              <Link href={article.primalUrl} target="_blank" rel="noopener noreferrer">
                                Read on Primal
                                <ExternalLink className="ml-2 h-3 w-3" />
                              </Link>
                            </Button>
                          )}
                        </CardFooter>
                      </div>
                    </div>
                  </Card>
                ))}
            </div>
          </TabsContent>

          <TabsContent value="misc">
            <div className="grid gap-6">
              {filteredArticles
                .filter((article) => article.category?.toLowerCase() === "misc" || !article.category)
                .map((article, index) => (
                  <Card key={index} className="overflow-hidden border border-gray-200 dark:border-gray-800 transition-all hover:shadow-md">
                    <div className="flex flex-col md:flex-row">
                      {article.imageUrl && (
                        <div className="md:w-1/3 h-48 md:h-auto overflow-hidden border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-800">
                          <img 
                            src={article.imageUrl} 
                            alt={article.title} 
                            className="w-full h-full object-contain transition-transform hover:scale-105"
                            onError={(e) => {
                              // Hide the image container if loading fails
                              const target = e.target as HTMLImageElement;
                              if (target.parentElement) {
                                target.parentElement.style.display = 'none';
                              }
                              // Make the content take full width
                              const contentDiv = target.parentElement?.nextElementSibling;
                              if (contentDiv) {
                                contentDiv.className = 'w-full';
                              }
                            }}
                          />
                        </div>
                      )}
                      <div className={article.imageUrl ? "md:w-2/3" : "w-full"}>
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
                        <CardFooter className="pt-2 flex justify-end gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <Link href={article.url} target="_blank" rel="noopener noreferrer">
                              Read on Habla.news
                              <ExternalLink className="ml-2 h-3 w-3" />
                            </Link>
                          </Button>
                          {article.primalUrl && (
                            <Button variant="outline" size="sm" asChild>
                              <Link href={article.primalUrl} target="_blank" rel="noopener noreferrer">
                                Read on Primal
                                <ExternalLink className="ml-2 h-3 w-3" />
                              </Link>
                            </Button>
                          )}
                        </CardFooter>
                      </div>
                    </div>
                  </Card>
                ))}
            </div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}
