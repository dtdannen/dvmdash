import { NextRequest, NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';
import { RelayConfigManager } from '@/lib/relay_config';

export async function GET() {
  try {
    const redis = getRedisClient();
    const relaysData = await RelayConfigManager.getAllRelays(redis);
    
    // Convert the object to an array of relay entries
    const relays = Object.entries(relaysData).map(([url, config]) => ({
      url,
      activity: config.activity,
      added_at: config.added_at,
      added_by: config.added_by,
      metrics: config.metrics || null
    }));
    
    // Get metrics for each relay if available
    for (const relay of relays) {
      const collectors = await redis.smembers('dvmdash:collectors:active');
      const metrics: Record<string, Record<string, string>> = {};
      
      for (const collectorId of collectors) {
        const collectorIdStr = typeof collectorId === 'string' ? collectorId : (collectorId as any).toString();
        
        // Try both key formats - the new format with dvmdash prefix and the old format
        const metricsKeys = [
          `dvmdash:collector:${collectorIdStr}:metrics:${relay.url}`,
          `collectors:${collectorIdStr}:metrics:${relay.url}`,
          // Also try with trailing slash
          `dvmdash:collector:${collectorIdStr}:metrics:${relay.url}/`,
          `collectors:${collectorIdStr}:metrics:${relay.url}/`
        ];
        
        for (const metricsKey of metricsKeys) {
          const collectorMetrics = await redis.hgetall(metricsKey);
          
          if (Object.keys(collectorMetrics).length > 0) {
            metrics[collectorIdStr] = collectorMetrics;
            break; // Found metrics, no need to check other key formats
          }
        }
      }
      
      if (Object.keys(metrics).length > 0) {
        relay.metrics = metrics;
      }
    }
    
    return NextResponse.json(relays);
  } catch (error) {
    console.error('Error getting relays:', error);
    return NextResponse.json(
      { error: 'Failed to get relays' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { url } = body;
    
    if (!url) {
      return NextResponse.json(
        { error: 'URL is required' },
        { status: 400 }
      );
    }
    
    const redis = getRedisClient();
    const success = await RelayConfigManager.addRelay(redis, url);
    
    if (success) {
      // Request relay redistribution from coordinator
      await RelayConfigManager.requestRelayDistribution(redis);
      return NextResponse.json({ status: 'success' });
    }
    
    return NextResponse.json(
      { error: 'Relay already exists' },
      { status: 400 }
    );
  } catch (error) {
    console.error('Error adding relay:', error);
    return NextResponse.json(
      { error: 'Failed to add relay' },
      { status: 500 }
    );
  }
}
