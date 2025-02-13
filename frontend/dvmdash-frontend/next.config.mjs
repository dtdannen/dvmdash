/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    appDir: true,
    serverComponentsExternalPackages: [],
  },
  webpack: (config) => {
    config.resolve.preferRelative = true;
    return config;
  }
};

export default nextConfig;
