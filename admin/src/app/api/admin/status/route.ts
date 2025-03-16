import { NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';
import { RelayConfigManager } from '@/lib/relay_config';

interface CollectorInfo {
  id: string;
  last_heartbeat: number | null;
  config_version: number | null;
  relays: string[];
}

interface SystemStatus {
  collectors: CollectorInfo[];
  outdated_collectors: string[];
  config_version: number;
  last_change: number | null;
  redis_host: string;
  redis_connected: boolean;
}

export async function GET() {
  try {
    const redis = getRedisClient();
    const collectors: CollectorInfo[] = [];
    
    // Get current time in seconds
    const currentTime = Math.floor(Date.now() / 1000);
    
    // Get all active collectors
    const collectorsSet = await redis.smembers('dvmdash:collectors:active');
    
    for (const collectorId of collectorsSet) {
      // Ensure collector_id is a string for Redis key
      const collectorIdStr = typeof collectorId === 'string' ? collectorId : (collectorId as any).toString();
      
      // Get collector information from hash
      const rawCollectorData = await redis.hgetall(`dvmdash:collector:${collectorIdStr}`);
      const rawRelaysJson = await redis.get(`dvmdash:collector:${collectorIdStr}:relays`);
      
      // Convert hash data to regular strings
      const collectorData: Record<string, string> = {};
      for (const key in rawCollectorData) {
        if (Object.prototype.hasOwnProperty.call(rawCollectorData, key)) {
          const keyStr = String(key);
          const valueStr = String(rawCollectorData[key]);
          collectorData[keyStr] = valueStr;
        }
      }
      
      // Convert relays JSON to string if it's a Buffer
      const relaysJson = rawRelaysJson ? String(rawRelaysJson) : null;
      
      let relaysList: string[] = [];
      if (relaysJson) {
        try {
          const relaysDict = JSON.parse(relaysJson);
          relaysList = Object.keys(relaysDict);
        } catch (e) {
          console.error(`Error parsing relays JSON for collector ${collectorIdStr}:`, e);
        }
      }
      
      collectors.push({
        id: collectorIdStr,
        last_heartbeat: collectorData.heartbeat ? parseInt(collectorData.heartbeat) : null,
        config_version: collectorData.config_version ? parseInt(collectorData.config_version) : null,
        relays: relaysList
      });
    }
    
    // Get configuration version and last change
    const rawConfigVersion = await redis.get('dvmdash:settings:config_version');
    const rawLastChange = await redis.get('dvmdash:settings:last_change');
    
    // Convert to strings if they're Buffers
    const configVersion = rawConfigVersion ? String(rawConfigVersion) : null;
    const lastChange = rawLastChange ? String(rawLastChange) : null;
    
    // Get outdated collectors
    const outdatedCollectors = await RelayConfigManager.getOutdatedCollectors(redis);
    
    // Get Redis connection info
    const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379/0';
    let redisHost = 'localhost';
    
    try {
      // Extract host from Redis URL
      const url = new URL(redisUrl);
      redisHost = url.hostname;
    } catch (e) {
      console.error('Error parsing Redis URL:', e);
    }
    
    // Check Redis connection
    let redisConnected = false;
    try {
      // Ping Redis to check connection
      await redis.ping();
      redisConnected = true;
    } catch (e) {
      console.error('Redis connection check failed:', e);
    }
    
    const status: SystemStatus = {
      collectors,
      outdated_collectors: outdatedCollectors,
      config_version: configVersion ? parseInt(configVersion) : 0,
      last_change: lastChange ? parseInt(lastChange) : null,
      redis_host: redisHost,
      redis_connected: redisConnected
    };
    
    return NextResponse.json(status);
  } catch (error) {
    console.error('Error getting system status:', error);
    return NextResponse.json(
      { error: 'Failed to get system status' },
      { status: 500 }
    );
  }
}
