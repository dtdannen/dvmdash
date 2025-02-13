// Print environment variables at startup
const appDomain = process.env.APP_DOMAIN;
console.log(`The app's domain is: ${appDomain}`);
console.log('NEXT_PUBLIC_API_URL:', process.env.NEXT_PUBLIC_API_URL);
console.log('APP_URL:', process.env.APP_URL);

// Start Next.js
require('next/dist/server/lib/start-server').startServer({
    dir: process.cwd(),
    port: process.env.PORT || 3000,
    hostname: process.env.HOSTNAME || '0.0.0.0'
});
