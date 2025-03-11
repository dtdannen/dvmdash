/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Disable API routes being exposed to the frontend
  experimental: {
    serverComponentsExternalPackages: ['pg', 'ioredis', 'docker-cli-js']
  }
}

module.exports = nextConfig
