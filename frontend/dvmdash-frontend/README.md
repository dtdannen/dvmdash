This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Environment Configuration

The application uses environment variables to determine API endpoints:

- `NEXT_PUBLIC_API_URL`: Used for client-side API calls from the browser
- `NEXT_PUBLIC_METADATA_API_URL`: Used for server-side API calls during SSR

### Running in Production

When running in production (separate cloud instances):

- Set `NEXT_PUBLIC_API_URL` to your public API endpoint (e.g., `https://api.dvmdash.com`)
- Set `NEXT_PUBLIC_METADATA_API_URL` to the internal API endpoint if needed

### Running with Docker Compose

When using the provided docker-compose.yml file:

- Environment variables are automatically set in the docker-compose configuration
- No additional configuration is needed

### Running Frontend Locally (Outside Docker)

When running the frontend locally but connecting to containerized backend services:

1. Create a `.env.local` file in the frontend directory with:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```
2. Adjust the port if your API is running on a different port

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
