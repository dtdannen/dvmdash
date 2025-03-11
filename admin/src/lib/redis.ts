import Redis from 'ioredis';

let redisClient: Redis | null = null;

export function getRedisClient(): Redis {
  if (!redisClient) {
    const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379/0';
    redisClient = new Redis(redisUrl);
    
    // Log connection status
    redisClient.on('connect', () => {
      console.log('Connected to Redis');
    });
    
    redisClient.on('error', (err) => {
      console.error('Redis connection error:', err);
    });
  }
  
  return redisClient;
}

export async function closeRedisConnection(): Promise<void> {
  if (redisClient) {
    await redisClient.quit();
    redisClient = null;
    console.log('Redis connection closed');
  }
}
