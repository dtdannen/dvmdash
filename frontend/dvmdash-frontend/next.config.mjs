/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: [],
  },
  webpack: (config, { buildId, dev, isServer, defaultLoaders, webpack }) => {
    // Add the directory containing your components to the module resolution paths
    config.resolve.modules = [
      ...config.resolve.modules || [],
      './components',
      './lib',
      'node_modules'
    ];

    // Add path aliases
    config.resolve.alias = {
      ...config.resolve.alias,
      '@/components': './components',
      '@/lib': './lib'
    };

    return config;
  }
};

export default nextConfig;
