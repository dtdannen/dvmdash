import { NextRequest, NextResponse } from 'next/server';
import { getRedisClient } from '@/lib/redis';
import { RelayConfigManager } from '@/lib/relay_config';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { url, activity } = body;
    
    if (!url) {
      return NextResponse.json(
        { error: 'URL is required' },
        { status: 400 }
      );
    }
    
    if (activity !== 'high' && activity !== 'normal') {
      return NextResponse.json(
        { error: 'Activity must be either "high" or "normal"' },
        { status: 400 }
      );
    }
    
    const redis = getRedisClient();
    const success = await RelayConfigManager.updateRelayActivity(redis, url, activity);
    
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
    console.error('Error updating relay activity:', error);
    return NextResponse.json(
      { error: 'Failed to update relay activity' },
      { status: 500 }
    );
  }
}
