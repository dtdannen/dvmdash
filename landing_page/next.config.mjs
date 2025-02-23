/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async redirects() {
    return [
      {
        source: '/metrics',
        destination: 'https://stats.dvmdash.live',
        permanent: true
      },
      {
        source: '/debug',
        destination: '/',
        permanent: true
      },
      {
        source: '/playground',
        destination: '/',
        permanent: true
      }
    ]
  }
}

export default nextConfig
