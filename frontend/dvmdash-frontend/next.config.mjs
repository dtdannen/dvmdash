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
      modules: [
        ...config.resolve.modules || [],
        'frontend/dvmdash-frontend',
        'node_modules'
      ],
      alias: {
        ...config.resolve.alias,
        '@/components': './components',
        '@/lib': './lib'
      }
    };
    return config;
  }
};

export default nextConfig;
