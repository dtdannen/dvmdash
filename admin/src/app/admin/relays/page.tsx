"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface Relay {
  url: string;
  activity: "high" | "normal";
  added_at: number;
  added_by: string;
  metrics?: {
    [collector_id: string]: {
      last_event: string;
      event_count: string;
    };
  };
}

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
}

export default function RelaysPage() {
  // Helper function to determine status color based on collector heartbeat
  const getStatusColor = (collector: CollectorInfo) => {
    return collector.last_heartbeat && 
           Date.now() / 1000 - collector.last_heartbeat < 120 
           ? "bg-green-500" 
           : "bg-red-500";
  };
  const [newRelayUrl, setNewRelayUrl] = useState("");
  const [relays, setRelays] = useState<Relay[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [redisState, setRedisState] = useState<any>(null);

  // Fetch relays and system status
  const fetchData = async () => {
    try {
      const [relaysRes, statusRes] = await Promise.all([
        fetch("/api/admin/relays"),
        fetch("/api/admin/status"),
      ]);

      if (!relaysRes.ok || !statusRes.ok) {
        throw new Error("Failed to fetch data");
      }

      const relaysData = await relaysRes.json();
      const statusData = await statusRes.json();

      setRelays(relaysData);
      setSystemStatus(statusData);
      setError(null);
    } catch (err) {
      setError("Failed to load data");
      console.error(err);
    }
  };

  useEffect(() => {
    fetchData();
    // Poll for updates every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const addRelay = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/admin/relays", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: newRelayUrl }),
      });

      if (!res.ok) {
        throw new Error("Failed to add relay");
      }

      setNewRelayUrl("");
      await fetchData();
    } catch (err) {
      setError("Failed to add relay");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const toggleActivity = async (url: string, currentActivity: string) => {
    try {
      setLoading(true);
      const newActivity = currentActivity === "high" ? "normal" : "high";
      
      const res = await fetch("/api/admin/relays/update-activity", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          url: url,
          activity: newActivity 
        }),
      });

      if (!res.ok) {
        // Try to get more detailed error information
        let errorMessage = "Failed to update relay";
        try {
          const errorData = await res.json();
          if (errorData.message) {
            errorMessage = `${errorMessage}: ${errorData.message}`;
          }
        } catch (e) {
          // If we can't parse the error response, use the default message
        }
        throw new Error(errorMessage);
      }

      await fetchData();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to update relay";
      setError(errorMessage);
      console.error("Update relay error:", err);
    } finally {
      setLoading(false);
    }
  };

  const removeRelay = async (url: string) => {
    try {
      setLoading(true);
      const res = await fetch("/api/admin/relays/delete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url }),
      });

      if (!res.ok) {
        // Try to get more detailed error information
        let errorMessage = "Failed to remove relay";
        try {
          const errorData = await res.json();
          if (errorData.message) {
            errorMessage = `${errorMessage}: ${errorData.message}`;
          }
        } catch (e) {
          // If we can't parse the error response, use the default message
        }
        throw new Error(errorMessage);
      }

      await fetchData();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to remove relay";
      setError(errorMessage);
      console.error("Remove relay error:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchRedisState = async () => {
    try {
      const res = await fetch("/api/admin/debug/redis");
      if (!res.ok) {
        throw new Error("Failed to fetch Redis state");
      }
      const data = await res.json();
      setRedisState(data);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="container mx-auto py-8">
      <div className="mb-6">
        <Link href="/" className="text-blue-500 hover:text-blue-700">
          &larr; Back to Dashboard
        </Link>
      </div>
      
      <h1 className="text-3xl font-bold mb-8">Relay Management</h1>

      {/* Configuration Status */}
      {(systemStatus?.outdated_collectors?.length ?? 0) > 0 && (
        <div className="mb-6 bg-yellow-50 p-4 rounded-md border border-yellow-200">
          <div className="flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-yellow-500 mr-2" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <p>
              Waiting for coordinator to redistribute relays to events...
            </p>
          </div>
        </div>
      )}

      {/* Add New Relay */}
      <div className="flex gap-4 mb-8">
        <input
          type="text"
          placeholder="wss://relay.example.com"
          value={newRelayUrl}
          onChange={(e) => setNewRelayUrl(e.target.value)}
          className="flex-1 max-w-md px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button 
          onClick={addRelay} 
          disabled={loading || !newRelayUrl}
          className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        >
          {loading ? (
            <span className="flex items-center">
              <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Adding...
            </span>
          ) : (
            "Add Relay"
          )}
        </button>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mb-6 bg-red-50 p-4 rounded-md border border-red-200">
          <p className="text-red-700">{error}</p>
        </div>
      )}

      {/* Relays List */}
      <div className="bg-white rounded-lg shadow mb-8">
        <div className="px-4 py-3 border-b">
          <h2 className="text-lg font-semibold">Configured Relays</h2>
        </div>
        <div className="divide-y">
          {relays.length === 0 ? (
            <div className="px-4 py-4 text-gray-500">
              No relays configured yet. Add a relay using the form above.
            </div>
          ) : (
            relays.map((relay) => (
              <div key={relay.url} className="px-4 py-4 flex items-center justify-between">
                <div className="flex-1">
                  <p className="font-mono text-sm">{relay.url}</p>
                  <div className="mt-1 text-sm text-gray-500">
                    Added {new Date(relay.added_at * 1000).toLocaleString()} by {relay.added_by}
                  </div>
                  
                  {/* Show collectors assigned to this relay */}
                  {systemStatus && (
                    <div className="mt-2 text-sm">
                      <div className="text-gray-500">
                        <div>
                          Assigned to collectors: {systemStatus.collectors.filter(c => c.relays.includes(relay.url)).length}
                          {systemStatus.collectors.filter(c => c.relays.includes(relay.url)).length > 0 && (
                            <div className="mt-1">
                              {systemStatus.collectors.filter(c => c.relays.includes(relay.url)).map(collector => (
                                <div key={collector.id} className="text-gray-400 text-xs">
                                  Collected by {collector.id.slice(0, 8)}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* Show metrics if available */}
                  {relay.metrics && (
                    <div className="mt-2 text-sm">
                      <div className="mt-2">
                        {Object.entries(relay.metrics).map(([collector, metrics]) => (
                          <div key={collector} className="text-gray-600">
                            Collector {collector.slice(0, 8)}: {metrics.event_count} events, 
                            last at {new Date(parseInt(metrics.last_event) * 1000).toLocaleString()}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">High Activity</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={relay.activity === "high"}
                        onChange={() => toggleActivity(relay.url, relay.activity)}
                        disabled={loading}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                    </label>
                  </div>
                  <button
                    onClick={() => removeRelay(relay.url)}
                    disabled={loading}
                    className="px-3 py-1 bg-red-500 text-white text-sm rounded hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Collectors Status */}
      {systemStatus && (
        <div className="bg-white rounded-lg shadow mb-8">
          <div className="px-4 py-3 border-b">
            <h2 className="text-lg font-semibold">Event Collectors</h2>
            <p className="text-sm text-gray-500 mt-1">
              The number of event collectors is configured at startup in the docker-compose.yml file, under event_collector -> deploy -> replicas
            </p>
          </div>
          <div className="divide-y">
            {systemStatus.collectors.length === 0 ? (
              <div className="px-4 py-4 text-gray-500">
                No active collectors found.
              </div>
            ) : (
              systemStatus.collectors.map((collector) => (
                <div key={collector.id} className="px-4 py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {collector.last_heartbeat && 
                      Date.now() / 1000 - collector.last_heartbeat < 120 ? (
                        <div className="w-2 h-2 rounded-full bg-green-500"></div>
                      ) : (
                        <div className="w-2 h-2 rounded-full bg-red-500"></div>
                      )}
                      <span className="font-mono">{collector.id}</span>
                      {systemStatus?.outdated_collectors?.includes(collector.id) && (
                        <span className="text-yellow-600 text-sm">
                          (Waiting for coordinator to reassign relays...)
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="mt-1 text-sm text-gray-500">
                    Last heartbeat:{" "}
                    {collector.last_heartbeat
                      ? new Date(collector.last_heartbeat * 1000).toLocaleString()
                      : "Never"}
                  </div>
                  <div className="mt-1 text-sm text-gray-500">
                    Assigned relays: {collector.relays.length}
                    {collector.relays.length > 0 && (
                      <div className="mt-1">
                        {collector.relays.map((relay, index) => (
                          <div key={index} className="text-gray-400 text-xs">
                            Listening to {relay}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Debug Panel */}
      <div className="mt-8">
        <button 
          onClick={() => {
            setShowDebugPanel(!showDebugPanel);
            if (!showDebugPanel) fetchRedisState();
          }}
          className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className={`h-4 w-4 transition-transform ${showDebugPanel ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          {showDebugPanel ? "Hide" : "Show"} Debug Panel
        </button>
        
        {showDebugPanel && (
          <div className="mt-4 bg-gray-50 p-4 rounded-lg border border-gray-200">
            <h3 className="text-lg font-semibold mb-2">Redis State</h3>
            <div className="overflow-auto max-h-96">
              <pre className="text-xs">{JSON.stringify(redisState, null, 2)}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
