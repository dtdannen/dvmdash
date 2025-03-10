import type { NextApiRequest, NextApiResponse } from 'next'

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).json({ message: 'Method not allowed' })
  }

  const { url, activity } = req.body
  if (!url) {
    return res.status(400).json({ message: 'Relay URL is required' })
  }
  if (!activity || (activity !== 'high' && activity !== 'normal')) {
    return res.status(400).json({ message: 'Activity must be "high" or "normal"' })
  }

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  // Try to normalize the URL to avoid encoding issues
  const normalizedUrl = url.replace(/:/g, '%3A').replace(/\//g, '%2F')
  const apiUrl = `${API_BASE}/api/admin/relays/${normalizedUrl}/activity`
  
  try {
    console.log(`Proxying PUT request to: ${apiUrl}`)
    
    const response = await fetch(apiUrl, {
      method: 'PUT',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ activity })
    })
    
    if (!response.ok) {
      console.error('Proxy error:', {
        status: response.status,
        statusText: response.statusText,
        url: apiUrl
      })
      
      // Try to get more detailed error information from the response
      let errorDetail;
      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorData.message || response.statusText;
      } catch (e) {
        errorDetail = response.statusText;
      }
      
      return res.status(response.status).json({ 
        message: `Error from API: ${errorDetail}`,
        url: apiUrl
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
