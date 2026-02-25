import { useEffect, useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { fetchDashboardStats } from "../api/dashboard";
import type { DashboardStats } from "../types/dashboard";

const PIE_COLORS = ["#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardStats()
      .then(setStats)
      .catch(() => setError("Failed to load dashboard data"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-gray-500 py-8">Loading dashboard...</div>;
  }
  if (error) {
    return <div className="text-red-600 py-8">{error}</div>;
  }
  if (!stats) return null;

  const metricCards = [
    { label: "Total Leads", value: stats.total_leads },
    { label: "This Week", value: stats.leads_this_week },
    { label: "This Month", value: stats.leads_this_month },
    { label: "Avg Score", value: stats.average_score !== null ? stats.average_score : "—" },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metricCards.map((card) => (
          <div key={card.label} className="bg-white rounded-lg border border-gray-200 p-5">
            <p className="text-sm text-gray-500">{card.label}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{card.value}</p>
          </div>
        ))}
      </div>

      {/* Enrichment Success Rate */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <p className="text-sm text-gray-500 mb-2">Enrichment Success Rate</p>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full"
              style={{ width: `${stats.enrichment_success_rate}%` }}
            />
          </div>
          <span className="text-lg font-semibold text-gray-900">
            {stats.enrichment_success_rate}%
          </span>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Leads by Source */}
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="text-sm font-medium text-gray-700 mb-4">Leads by Source</h2>
          {stats.leads_by_source.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={stats.leads_by_source}
                  dataKey="count"
                  nameKey="source"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={({ source }) => source}
                >
                  {stats.leads_by_source.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-400 text-sm py-10 text-center">No data yet</p>
          )}
        </div>

        {/* Score Distribution */}
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="text-sm font-medium text-gray-700 mb-4">Score Distribution</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={stats.score_distribution}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Routing Breakdown */}
      {stats.routing_breakdown.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="text-sm font-medium text-gray-700 mb-4">Routing Breakdown</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Destination</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Total</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Success</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Failed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {stats.routing_breakdown.map((row) => (
                  <tr key={row.destination}>
                    <td className="px-4 py-2 font-medium">{row.destination}</td>
                    <td className="px-4 py-2">{row.total}</td>
                    <td className="px-4 py-2 text-green-600">{row.success}</td>
                    <td className="px-4 py-2 text-red-600">{row.failed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent Activity */}
      {stats.recent_activity.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-5">
          <h2 className="text-sm font-medium text-gray-700 mb-4">Recent Activity</h2>
          <ul className="divide-y divide-gray-100">
            {stats.recent_activity.map((item, i) => (
              <li key={i} className="py-3 flex items-start gap-3">
                <span
                  className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${
                    item.type === "lead"
                      ? "bg-blue-100 text-blue-700"
                      : item.type === "enrichment"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-green-100 text-green-700"
                  }`}
                >
                  {item.type}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-900 font-medium">{item.lead_name}</p>
                  <p className="text-sm text-gray-500">{item.description}</p>
                </div>
                <time className="text-xs text-gray-400 whitespace-nowrap">
                  {new Date(item.timestamp).toLocaleString()}
                </time>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
