import type { NextApiRequest, NextApiResponse } from 'next'

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const apiUrl = `${API_BASE}/api/admin/relays`
  
  try {
    console.log(`Proxying ${req.method} request to: ${apiUrl}`)
    
    const fetchOptions: RequestInit = {
      method: req.method,
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    }
    
    // Add body for POST requests
    if (req.method === 'POST' && req.body) {
      fetchOptions.body = JSON.stringify(req.body)
    }
    
    const response = await fetch(apiUrl, fetchOptions)
    
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
