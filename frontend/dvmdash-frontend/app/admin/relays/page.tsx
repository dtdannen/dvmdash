"use client";

import { useState, useEffect } from "react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Switch } from "../../components/ui/switch";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Loader2Icon as ReloadIcon, AlertTriangleIcon, ChevronDownIcon, ChevronUpIcon } from "lucide-react";

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
      const res = await fetch(`/api/admin/relays/${encodeURIComponent(url)}/activity`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ activity: newActivity }),
      });

      if (!res.ok) {
        throw new Error("Failed to update relay");
      }

      await fetchData();
    } catch (err) {
      setError("Failed to update relay");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const removeRelay = async (url: string) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/admin/relays/${encodeURIComponent(url)}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        throw new Error("Failed to remove relay");
      }

      await fetchData();
    } catch (err) {
      setError("Failed to remove relay");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const rebootCollectors = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/admin/collectors/reboot", {
        method: "POST",
      });

      if (!res.ok) {
        throw new Error("Failed to reboot collectors");
      }

      // Wait a few seconds then refresh data
      await new Promise(resolve => setTimeout(resolve, 5000));
      await fetchData();
    } catch (err) {
      setError("Failed to reboot collectors");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const addCollector = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/admin/collectors", {
        method: "POST",
      });

      if (!res.ok) {
        throw new Error("Failed to add collector");
      }

      await fetchData();
    } catch (err) {
      setError("Failed to add collector");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const removeCollector = async (collectorId: string) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/admin/collectors/${encodeURIComponent(collectorId)}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        throw new Error("Failed to remove collector");
      }

      await fetchData();
    } catch (err) {
      setError("Failed to remove collector");
      console.error(err);
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
      <h1 className="text-3xl font-bold mb-8">Relay Management</h1>

      {/* Configuration Status */}
      {(systemStatus?.outdated_collectors?.length ?? 0) > 0 && (
        <Alert className="mb-6 bg-yellow-50">
          <AlertTriangleIcon className="h-4 w-4" />
          <AlertDescription>
            Configuration changes pending. {systemStatus?.outdated_collectors?.length} collectors need to be rebooted.
            <Button
              variant="outline"
              size="sm"
              className="ml-4"
              onClick={rebootCollectors}
              disabled={loading}
            >
              {loading ? (
                <ReloadIcon className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                "Reboot All"
              )}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Add New Relay */}
      <div className="flex gap-4 mb-8">
        <Input
          placeholder="wss://relay.example.com"
          value={newRelayUrl}
          onChange={(e) => setNewRelayUrl(e.target.value)}
          className="max-w-md"
        />
        <Button onClick={addRelay} disabled={loading || !newRelayUrl}>
          {loading ? (
            <ReloadIcon className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            "Add Relay"
          )}
        </Button>
      </div>

      {/* Error Display */}
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Relays List */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-4 py-3 border-b">
          <h2 className="text-lg font-semibold">Configured Relays</h2>
        </div>
        <div className="divide-y">
          {relays.map((relay) => (
            <div key={relay.url} className="px-4 py-4 flex items-center justify-between">
              <div className="flex-1">
                <p className="font-mono text-sm">{relay.url}</p>
                <div className="mt-1 text-sm text-gray-500">
                  Added {new Date(relay.added_at * 1000).toLocaleString()} by {relay.added_by}
                </div>
                {relay.metrics && (
                  <div className="mt-2 text-sm">
                    {Object.entries(relay.metrics).map(([collector, metrics]) => (
                      <div key={collector} className="text-gray-600">
                        Collector {collector.slice(0, 8)}: {metrics.event_count} events, 
                        last at {new Date(parseInt(metrics.last_event) * 1000).toLocaleString()}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm">High Activity</span>
                  <Switch
                    checked={relay.activity === "high"}
                    onCheckedChange={() => toggleActivity(relay.url, relay.activity)}
                    disabled={loading}
                  />
                </div>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => removeRelay(relay.url)}
                  disabled={loading}
                >
                  Remove
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Collectors Status */}
      {systemStatus && (
        <div className="mt-8 bg-white rounded-lg shadow">
          <div className="px-4 py-3 border-b flex justify-between items-center">
            <h2 className="text-lg font-semibold">Event Collectors</h2>
            <Button onClick={addCollector} disabled={loading}>
              {loading ? (
                <ReloadIcon className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                "Add Collector"
              )}
            </Button>
          </div>
          <div className="divide-y">
            {systemStatus.collectors.map((collector) => (
              <div key={collector.id} className="px-4 py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        collector.last_heartbeat &&
                        Date.now() / 1000 - collector.last_heartbeat < 120
                          ? "bg-green-500"
                          : "bg-red-500"
                      }`}
                    />
                    <span className="font-mono">{collector.id}</span>
                    {systemStatus?.outdated_collectors?.includes(collector.id) && (
                      <span className="text-yellow-600 text-sm">
                        (Needs Reboot)
                      </span>
                    )}
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => removeCollector(collector.id)}
                    disabled={loading}
                  >
                    Remove
                  </Button>
                </div>
                <div className="mt-1 text-sm text-gray-500">
                  Last heartbeat:{" "}
                  {collector.last_heartbeat
                    ? new Date(collector.last_heartbeat * 1000).toLocaleString()
                    : "Never"}
                </div>
                <div className="mt-1 text-sm text-gray-500">
                  Assigned relays: {collector.relays.length}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Debug Panel */}
      <div className="mt-8">
        <Button 
          variant="outline" 
          onClick={() => {
            setShowDebugPanel(!showDebugPanel);
            if (!showDebugPanel) fetchRedisState();
          }}
          className="flex items-center gap-2"
        >
          {showDebugPanel ? <ChevronUpIcon className="h-4 w-4" /> : <ChevronDownIcon className="h-4 w-4" />}
          {showDebugPanel ? "Hide" : "Show"} Debug Panel
        </Button>
        
        {showDebugPanel && (
          <div className="mt-4 bg-gray-50 p-4 rounded-lg">
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
