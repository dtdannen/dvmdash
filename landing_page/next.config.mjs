/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async redirects() {
    return [
      {
        source: '/:path+',
        destination: '/',
        permanent: true
      }
    ]
  }
}

export default nextConfig
