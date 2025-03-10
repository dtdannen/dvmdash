import type { NextApiRequest, NextApiResponse } from 'next'

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    return res.status(405).json({ message: 'Method not allowed' })
  }

  const { path, ...queryParams } = req.query
  if (!path) {
    return res.status(400).json({ message: 'Path parameter is required' })
  }

  try {
    // Build the query string from all query parameters except 'path'
    const queryString = Object.entries(queryParams)
      .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value as string)}`)
      .join('&');
    
    const apiUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/${path}${queryString ? `?${queryString}` : ''}`
    console.log('Proxying request to:', apiUrl)
    
    const response = await fetch(apiUrl, {
      headers: {
        'Accept': 'application/json'
      }
    })
    
    const data = await response.json()
    res.status(200).json(data)
  } catch (error) {
    console.error('Proxy error:', error)
    res.status(500).json({ message: 'Error fetching data from API' })
  }
}
