// scripts/start.js
console.log('Environment variables at startup:');
console.log('NODE_ENV:', process.env.NODE_ENV);
console.log('REDIS_URL:', process.env.REDIS_URL);
console.log('POSTGRES_HOST:', process.env.POSTGRES_HOST);

// Start Next.js
require('next/dist/server/lib/start-server').startServer({
    dir: process.cwd(),
    port: process.env.PORT || 3000,
    hostname: process.env.HOSTNAME || '0.0.0.0'
});
