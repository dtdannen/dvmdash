import type { Metadata } from 'next'

/**
 * Creates OpenGraph metadata for social media sharing
 */
export function createOpenGraphMetadata(
  title: string,
  description: string,
  imageUrl: string,
  url: string,
  imageWidth = 1200,
  imageHeight = 630
) {
  return {
    type: 'website',
    url,
    title,
    description,
    images: [
      {
        url: imageUrl,
        width: imageWidth,
        height: imageHeight,
        alt: `${title}`,
      },
    ],
    siteName: 'DVMDash Stats',
  }
}

/**
 * Creates Twitter card metadata for Twitter sharing
 */
export function createTwitterMetadata(
  title: string,
  description: string,
  imageUrl: string
) {
  return {
    card: 'summary_large_image',
    site: '@dvmdash',
    title,
    description,
    images: [imageUrl],
  }
}

/**
 * Creates structured data for better SEO
 */
export function createStructuredData(
  type: string,
  name: string,
  description: string,
  url: string
) {
  return {
    '@context': 'https://schema.org',
    '@type': type,
    'name': name,
    'description': description,
    'url': url,
    'creator': {
      '@type': 'Organization',
      'name': 'DVMDash'
    }
  }
}

/**
 * Creates a complete metadata object with all necessary fields
 */
export function createCompleteMetadata(
  title: string,
  description: string,
  imageUrl: string,
  canonicalUrl: string,
  previousImages: any[] = [],
  structuredDataType = 'Dataset',
  imageWidth = 1200,
  imageHeight = 630
): Metadata {
  return {
    title,
    description,
    openGraph: {
      ...createOpenGraphMetadata(title, description, imageUrl, canonicalUrl, imageWidth, imageHeight),
      images: [
        {
          url: imageUrl,
          width: imageWidth,
          height: imageHeight,
          alt: `${title} stats visualization`,
        },
        ...previousImages,
      ],
    },
    twitter: createTwitterMetadata(title, description, imageUrl),
    alternates: {
      canonical: canonicalUrl,
    },
    // Add structured data for better SEO
    // @ts-ignore - Next.js types don't include structuredData yet
    structuredData: createStructuredData(structuredDataType, title, description, canonicalUrl),
  }
}
