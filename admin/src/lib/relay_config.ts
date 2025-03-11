import { Redis } from 'ioredis';
import { getRedisClient } from './redis';

export interface RelayEntry {
  url: string;
  activity: 'high' | 'normal';
  added_at: number;
  added_by: string;
  metrics?: Record<string, Record<string, string>>;
}

export class RelayConfigManager {
  /**
   * Get all configured relays and their settings
   */
  static async getAllRelays(redis: Redis): Promise<Record<string, RelayEntry>> {
    try {
      const relaysJson = await redis.get('dvmdash:settings:relays');
      return relaysJson ? JSON.parse(relaysJson) : {};
    } catch (error) {
      console.error('Error getting relays:', error);
      return {};
    }
  }

  /**
   * Add a new relay to the configuration
   */
  static async addRelay(redis: Redis, relayUrl: string, activity: 'high' | 'normal' = 'normal'): Promise<boolean> {
    try {
      // Use pipeline to ensure atomic operations
      const pipeline = redis.pipeline();
      
      // Get current relays
      const currentRelays = await this.getAllRelays(redis);
      
      // Check if relay already exists
      if (relayUrl in currentRelays) {
        return false;
      }
      
      // Add the new relay
      currentRelays[relayUrl] = {
        url: relayUrl,
        activity,
        added_at: Math.floor(Date.now() / 1000),
        added_by: 'admin'
      };
      
      // Update settings and increment config version
      pipeline.set('dvmdash:settings:relays', JSON.stringify(currentRelays));
      pipeline.incr('dvmdash:settings:config_version');
      pipeline.set('dvmdash:settings:last_change', Math.floor(Date.now() / 1000));
      
      await pipeline.exec();
      return true;
    } catch (error) {
      console.error('Error adding relay:', error);
      return false;
    }
  }

  /**
   * Update a relay's activity level
   */
  static async updateRelayActivity(redis: Redis, relayUrl: string, activity: 'high' | 'normal'): Promise<boolean> {
    try {
      // Get current relays
      const currentRelays = await this.getAllRelays(redis);
      
      // Try to find the relay URL in the relays dictionary
      // First try exact match
      let matchedUrl = relayUrl;
      
      if (!(relayUrl in currentRelays)) {
        // Try to normalize URLs for comparison
        const normalizedInput = relayUrl.toLowerCase().replace('%3A', ':');
        const foundUrl = Object.keys(currentRelays).find(url => {
          const normalizedUrl = url.toLowerCase().replace('%3A', ':');
          return normalizedUrl === normalizedInput;
        });
        
        if (!foundUrl) {
          console.error(`Relay not found for activity update: ${relayUrl}`);
          return false;
        }
        
        matchedUrl = foundUrl;
      }
      
      console.log(`Updating relay activity: ${matchedUrl} to ${activity}`);
      
      // Use pipeline to ensure atomic operations
      const pipeline = redis.pipeline();
      
      // Update the relay activity
      currentRelays[matchedUrl].activity = activity;
      
      // Update settings and increment config version
      pipeline.set('dvmdash:settings:relays', JSON.stringify(currentRelays));
      pipeline.incr('dvmdash:settings:config_version');
      pipeline.set('dvmdash:settings:last_change', Math.floor(Date.now() / 1000));
      
      await pipeline.exec();
      return true;
    } catch (error) {
      console.error('Error updating relay activity:', error);
      return false;
    }
  }

  /**
   * Remove a relay from the configuration
   */
  static async removeRelay(redis: Redis, relayUrl: string): Promise<boolean> {
    try {
      // Get current relays
      const currentRelays = await this.getAllRelays(redis);
      
      // Try to find the relay URL in the relays dictionary
      // First try exact match
      let matchedUrl = relayUrl;
      
      if (!(relayUrl in currentRelays)) {
        // Try to normalize URLs for comparison
        const normalizedInput = relayUrl.toLowerCase().replace('%3A', ':');
        const foundUrl = Object.keys(currentRelays).find(url => {
          const normalizedUrl = url.toLowerCase().replace('%3A', ':');
          return normalizedUrl === normalizedInput;
        });
        
        if (!foundUrl) {
          console.error(`Relay not found: ${relayUrl}`);
          return false;
        }
        
        matchedUrl = foundUrl;
      }
      
      console.log(`Removing relay: ${matchedUrl}`);
      
      // Use pipeline to ensure atomic operations
      const pipeline = redis.pipeline();
      
      // Remove the relay
      delete currentRelays[matchedUrl];
      
      // Update settings and increment config version
      pipeline.set('dvmdash:settings:relays', JSON.stringify(currentRelays));
      pipeline.incr('dvmdash:settings:config_version');
      pipeline.set('dvmdash:settings:last_change', Math.floor(Date.now() / 1000));
      
      await pipeline.exec();
      return true;
    } catch (error) {
      console.error('Error removing relay:', error);
      return false;
    }
  }

  /**
   * Get list of collector IDs that need to be rebooted
   */
  static async getOutdatedCollectors(redis: Redis): Promise<string[]> {
    try {
      const currentVersion = await redis.get('dvmdash:settings:config_version');
      if (!currentVersion) {
        return [];
      }
      
      const collectorsSet = await redis.smembers('dvmdash:collectors:active');
      const outdated: string[] = [];
      
      for (const collectorId of collectorsSet) {
        // Ensure collector_id is a string for Redis key
        const collectorIdStr = typeof collectorId === 'string' ? collectorId : collectorId.toString();
        
        // Check if collector is outdated based on config version
        const collectorVersion = await redis.get(`dvmdash:collector:${collectorIdStr}:config_version`);
        if (!collectorVersion || parseInt(collectorVersion) !== parseInt(currentVersion)) {
          outdated.push(collectorIdStr);
        }
      }
      
      return outdated;
    } catch (error) {
      console.error('Error checking outdated collectors:', error);
      return [];
    }
  }

  /**
   * Set a flag in Redis to request relay distribution from the coordinator
   */
  static async requestRelayDistribution(redis: Redis): Promise<boolean> {
    try {
      // Set the last_change timestamp to trigger redistribution
      await redis.set('dvmdash:settings:last_change', Math.floor(Date.now() / 1000));
      // Set a specific flag to request distribution
      await redis.set('dvmdash:settings:distribution_requested', '1', 'EX', 300); // Expire after 5 minutes
      return true;
    } catch (error) {
      console.error('Error requesting relay distribution:', error);
      return false;
    }
  }
}
