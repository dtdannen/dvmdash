import type { NextApiRequest, NextApiResponse } from 'next'

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'DELETE') {
    return res.status(405).json({ message: 'Method not allowed' })
  }

  const { id } = req.query
  if (!id || typeof id !== 'string') {
    return res.status(400).json({ message: 'Collector ID is required' })
  }

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const apiUrl = `${API_BASE}/api/admin/collectors/${encodeURIComponent(id)}`
  
  try {
    console.log(`Proxying DELETE request to: ${apiUrl}`)
    
    const response = await fetch(apiUrl, {
      method: 'DELETE',
      headers: {
        'Accept': 'application/json'
      }
    })
    
    if (!response.ok) {
      console.error('Proxy error:', {
        status: response.status,
        statusText: response.statusText
      })
      return res.status(response.status).json({ 
        message: `Error from API: ${response.statusText}` 
      })
    }
    
    const data = await response.json()
    return res.status(200).json(data)
  } catch (error) {
    console.error('Proxy error:', error)
    return res.status(500).json({ 
      message: 'Error proxying request to API',
      error: error instanceof Error ? error.message : 'Unknown error'
    })
  }
}
