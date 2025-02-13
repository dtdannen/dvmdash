/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: [],
  },
  webpack: (config) => {
    config.resolve = {
      ...config.resolve,
      preferRelative: true,
      alias: {
        ...config.resolve.alias,
        '@/components': '/workspace/frontend/dvmdash-frontend/components'
      }
    };
    return config;
  }
};

export default nextConfig;
