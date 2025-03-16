import { NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';

export async function POST() {
  try {
    const redis = getRedisClient();
    
    // Get all collector IDs
    const collectors = await redis.smembers('dvmdash:collectors:active');
    const resetCount = collectors.length;
    
    // Process each collector
    for (const collectorId of collectors) {
      // Ensure collector_id is a string for Redis key
      const collectorIdStr = typeof collectorId === 'string' ? collectorId : (collectorId as any).toString();
      
      // Delete collector-specific keys
      await redis.del(`dvmdash:collector:${collectorIdStr}`);
      await redis.del(`dvmdash:collector:${collectorIdStr}:relays`);
      await redis.del(`dvmdash:collector:${collectorIdStr}:nsec_key`);
      
      // Find and delete metrics keys
      const metricsKeys = await redis.keys(`dvmdash:collector:${collectorIdStr}:metrics:*`);
      if (metricsKeys.length > 0) {
        await redis.del(...metricsKeys);
      }
    }
    
    // Clear the active collectors set
    await redis.del('dvmdash:collectors:active');
    
    // Reset distribution flags
    await redis.del('dvmdash:settings:distribution_requested');
    
    // Set a flag to request relay distribution when new collectors register
    await redis.set('dvmdash:settings:last_change', Math.floor(Date.now() / 1000));
    
    return NextResponse.json({ 
      success: true, 
      message: `Successfully reset ${resetCount} collectors` 
    });
  } catch (error) {
    console.error('Error resetting collectors:', error);
    return NextResponse.json(
      { error: 'Failed to reset collectors' },
      { status: 500 }
    );
  }
}
