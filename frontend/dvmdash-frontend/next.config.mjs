/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: [],
  },
  eslint: {
    // Warning: This allows production builds to successfully complete even if
    // your project has ESLint errors.
    ignoreDuringBuilds: true,
  },
  typescript: {
    // !! WARN !!
    // Dangerously allow production builds to successfully complete even if
    // your project has type errors.
    ignoreBuildErrors: true,
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
