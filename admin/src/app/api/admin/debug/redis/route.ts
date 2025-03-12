import { NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';

export async function GET() {
  try {
    const redis = getRedisClient();
    const result: Record<string, any> = {
      collectors: {},
      config: {}
    };
    
    // Get collector information
    const collectors = await redis.smembers('dvmdash:collectors:active');
    for (const collectorId of collectors) {
      // Ensure collector_id is a string for Redis key
      const collectorIdStr = typeof collectorId === 'string' ? collectorId : (collectorId as any).toString();
      
      const heartbeat = await redis.get(`dvmdash:collector:${collectorIdStr}:heartbeat`);
      const configVersion = await redis.get(`dvmdash:collector:${collectorIdStr}:config_version`);
      const relaysJson = await redis.get(`dvmdash:collector:${collectorIdStr}:relays`);
      
      result.collectors[collectorIdStr] = {
        heartbeat,
        config_version: configVersion,
        relays: relaysJson ? JSON.parse(relaysJson) : {}
      };
      
      // Get metrics for each relay
      result.collectors[collectorIdStr].metrics = {};
      
      if (relaysJson) {
        const relays = JSON.parse(relaysJson);
        for (const relayUrl of Object.keys(relays)) {
          const metricsKey = `dvmdash:collector:${collectorIdStr}:metrics:${relayUrl}`;
          const metrics = await redis.hgetall(metricsKey);
          
          if (Object.keys(metrics).length > 0) {
            result.collectors[collectorIdStr].metrics[relayUrl] = metrics;
          }
        }
      }
    }
    
    // Get configuration
    const relaysJson = await redis.get('dvmdash:settings:relays');
    const configVersion = await redis.get('dvmdash:settings:config_version');
    const lastChange = await redis.get('dvmdash:settings:last_change');
    
    result.config.relays = relaysJson ? JSON.parse(relaysJson) : {};
    result.config.config_version = configVersion;
    result.config.last_change = lastChange;
    
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error getting Redis debug info:', error);
    return NextResponse.json(
      { error: 'Failed to get Redis debug info' },
      { status: 500 }
    );
  }
}
