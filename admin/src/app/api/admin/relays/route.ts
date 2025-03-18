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
        
        // Try both with and without trailing slash
        const metricsKeys = [
          `dvmdash:collector:${collectorIdStr}:metrics:${relay.url}`,
          `dvmdash:collector:${collectorIdStr}:metrics:${relay.url}/`
        ];
        
        let foundMetrics = false;
        
        for (const metricsKey of metricsKeys) {
          const rawMetrics = await redis.hgetall(metricsKey);
          
          // Convert Redis hash to a regular JavaScript object with string keys and values
          if (Object.keys(rawMetrics).length > 0) {
            const processedMetrics: Record<string, string> = {};
            
            // Process each key-value pair in the Redis hash
            for (const key in rawMetrics) {
              if (Object.prototype.hasOwnProperty.call(rawMetrics, key)) {
                const value = rawMetrics[key];
                // Convert to string if needed
                const keyStr = String(key);
                const valueStr = String(value);
                processedMetrics[keyStr] = valueStr;
              }
            }
            
            metrics[collectorIdStr] = processedMetrics;
            foundMetrics = true;
            console.log(`Found metrics for collector ${collectorIdStr} at key ${metricsKey}`);
            break; // Found metrics, no need to check other key formats
          }
        }
        
        if (!foundMetrics) {
          console.log(`No metrics found for collector ${collectorIdStr} and relay ${relay.url}`);
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
