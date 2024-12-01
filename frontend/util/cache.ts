// util/cache.ts
import { LRUCache } from 'lru-cache'

const options = {
  // Maximum number of items to store in cache
  max: 500,

  // Maximum age in milliseconds. Items will expire after this time
  ttl: 1000 * 60 * 5, // 5 minutes

  // Return stale items before removing them from cache?
  allowStale: false,

  // Update TTL when item is retrieved?
  updateAgeOnGet: false,

  // Update TTL when item is stored?
  updateAgeOnHas: false,
}

// Create cache instance
const cache = new LRUCache(options)

// Type for the function being memoized
type AsyncFunction = (...args: any[]) => Promise<any>

export function withCache<T extends AsyncFunction>(fn: T): T {
  return (async (...args: Parameters<T>) => {
    // Create a key from the function name and arguments
    const key = `${fn.name}-${JSON.stringify(args)}`

    // Check if we have a cached value
    const cached = cache.get(key)
    if (cached !== undefined) {
      return cached
    }

    // If not cached, execute function
    const result = await fn(...args)

    // Store in cache
    cache.set(key, result)

    return result
  }) as T
}

// Example usage with your API calls:
export async function fetchWithCache<T>(url: string): Promise<T> {
  const cachedFetch = withCache(async (url: string) => {
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  })

  return await cachedFetch(url)
}