# DVMDash Landing Page

This is the landing page for DVMDash built with Next.js.

## Running as a Standalone Container

The landing page is designed to be built and run as a standalone Docker container.

### Build the Container

```bash
cd landing_page
docker build -t dvmdash-landing .
```

### Run the Container

```bash
docker run -p 3000:3000 dvmdash-landing
```

This will make the landing page accessible at http://localhost:3000.

## Development

For local development without Docker, refer to the Next.js documentation for setup instructions.
