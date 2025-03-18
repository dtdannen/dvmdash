import { NextRequest, NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';
import { RelayConfigManager } from '@/lib/relay_config';

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
    const success = await RelayConfigManager.removeRelay(redis, url);
    
    if (success) {
      // Request relay redistribution from coordinator
      await RelayConfigManager.requestRelayDistribution(redis);
      return NextResponse.json({ status: 'success' });
    }
    
    return NextResponse.json(
      { error: 'Relay not found' },
      { status: 404 }
    );
  } catch (error) {
    console.error('Error removing relay:', error);
    return NextResponse.json(
      { error: 'Failed to remove relay' },
      { status: 500 }
    );
  }
}
