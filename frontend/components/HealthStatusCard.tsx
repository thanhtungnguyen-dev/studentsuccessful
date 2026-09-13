"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, RefreshCw, Server, Database, HardDrive } from "lucide-react";
import { apiClient, type HealthLiveResponse, type HealthReadyResponse } from "../lib/api/client";

export function HealthStatusCard() {
  const [live, setLive] = useState<HealthLiveResponse | null>(null);
  const [ready, setReady] = useState<HealthReadyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const [liveData, readyData] = await Promise.all([
        apiClient.getHealthLive(),
        apiClient.getHealthReady(),
      ]);
      setLive(liveData);
      setReady(readyData);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to fetch health status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div id="health-status-card" className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-8">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Infrastructure Health & Readiness</h2>
          <p className="text-sm text-slate-500">Real-time status of backend service, database, and storage adapter</p>
        </div>
        <button
          id="refresh-health-btn"
          onClick={fetchHealth}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-amber-800">
            <span className="font-medium">Backend Connection Note:</span> {error}
            <div className="mt-1 text-xs text-amber-700">
              In development, ensure the FastAPI backend is running (`uvicorn backend.app.main:app --port 8000`). Next.js proxies `/health/*` directly to it.
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        {/* Process Liveness */}
        <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 flex items-center gap-3.5">
          <div className={`p-2.5 rounded-md ${live?.status === "ok" ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>
            <Server className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">FastAPI Process</div>
            <div className="text-sm font-medium text-slate-900 flex items-center gap-1.5 mt-0.5">
              {live?.status === "ok" ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Alive (/health/live)</span>
                </>
              ) : (
                <span className="text-slate-500">Checking...</span>
              )}
            </div>
          </div>
        </div>

        {/* Database Connectivity */}
        <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 flex items-center gap-3.5">
          <div className={`p-2.5 rounded-md ${ready?.dependencies?.database ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
            <Database className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">PostgreSQL 16 Engine</div>
            <div className="text-sm font-medium text-slate-900 flex items-center gap-1.5 mt-0.5">
              {ready?.dependencies?.database ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Connected (SELECT 1)</span>
                </>
              ) : (
                <span className="text-amber-700">Disconnected</span>
              )}
            </div>
          </div>
        </div>

        {/* Storage Adapter */}
        <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 flex items-center gap-3.5">
          <div className={`p-2.5 rounded-md ${ready?.dependencies?.storage ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
            <HardDrive className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Storage Adapter</div>
            <div className="text-sm font-medium text-slate-900 flex items-center gap-1.5 mt-0.5">
              {ready?.dependencies?.storage ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Ready (LocalStorage)</span>
                </>
              ) : (
                <span className="text-amber-700">Storage Unavailable</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
