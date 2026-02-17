import { useEffect, useState } from "react";
import { enrichLead, fetchLeadDetail, routeLead } from "../../api/leads";
import type { LeadDetail } from "../../types/lead";
import ScoreBadge from "./ScoreBadge";

interface LeadSlideOverProps {
  leadId: number | null;
  onClose: () => void;
}

export default function LeadSlideOver({ leadId, onClose }: LeadSlideOverProps) {
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [routing, setRouting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!leadId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setFeedback(null);
    fetchLeadDetail(leadId)
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [leadId]);

  if (!leadId) return null;

  const handleEnrich = async () => {
    setEnriching(true);
    setFeedback(null);
    try {
      await enrichLead(leadId);
      setFeedback("Enrichment queued");
      const updated = await fetchLeadDetail(leadId);
      setDetail(updated);
    } catch {
      setFeedback("Enrichment failed");
    } finally {
      setEnriching(false);
    }
  };

  const handleRoute = async () => {
    setRouting(true);
    setFeedback(null);
    try {
      await routeLead(leadId);
      setFeedback("Routed successfully");
      const updated = await fetchLeadDetail(leadId);
      setDetail(updated);
    } catch {
      setFeedback("Routing failed");
    } finally {
      setRouting(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg overflow-y-auto bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Lead Detail</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        {loading || !detail ? (
          <div className="p-6 text-sm text-gray-500">Loading...</div>
        ) : (
          <div className="space-y-6 p-6">
            {/* Contact Info */}
            <section>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Contact</h3>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-gray-500">Name</dt><dd className="text-gray-900">{detail.name}</dd>
                <dt className="text-gray-500">Email</dt><dd className="text-gray-900">{detail.email}</dd>
                <dt className="text-gray-500">Phone</dt><dd className="text-gray-900">{detail.phone || "—"}</dd>
                <dt className="text-gray-500">Company</dt><dd className="text-gray-900">{detail.company || "—"}</dd>
                <dt className="text-gray-500">Title</dt><dd className="text-gray-900">{detail.title || "—"}</dd>
                <dt className="text-gray-500">Source</dt><dd className="text-gray-900">{detail.source || "—"}</dd>
                <dt className="text-gray-500">Status</dt><dd className="text-gray-900">{detail.status}</dd>
              </dl>
            </section>

            {/* Score */}
            <section>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Score</h3>
              <div className="flex items-center gap-3 mb-2">
                <ScoreBadge score={detail.score} />
                <span className="text-sm text-gray-600">Enrichment: {detail.enrichment_status}</span>
              </div>
              {detail.score_details && (
                <pre className="rounded bg-gray-50 p-3 text-xs text-gray-700 overflow-x-auto">
                  {JSON.stringify(detail.score_details, null, 2)}
                </pre>
              )}
            </section>

            {/* Enrichment Data */}
            {detail.enrichment_data && (
              <section>
                <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Enrichment Data</h3>
                <pre className="rounded bg-gray-50 p-3 text-xs text-gray-700 overflow-x-auto">
                  {JSON.stringify(detail.enrichment_data, null, 2)}
                </pre>
              </section>
            )}

            {/* Actions */}
            <section>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Actions</h3>
              <div className="flex gap-3">
                <button
                  onClick={handleEnrich}
                  disabled={enriching}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {enriching ? "Enriching..." : "Re-Enrich"}
                </button>
                <button
                  onClick={handleRoute}
                  disabled={routing}
                  className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  {routing ? "Routing..." : "Route to GHL"}
                </button>
              </div>
              {feedback && <p className="mt-2 text-sm text-gray-600">{feedback}</p>}
            </section>

            {/* Enrichment Logs */}
            <section>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Enrichment Logs</h3>
              {detail.enrichment_logs.length === 0 ? (
                <p className="text-sm text-gray-400">No logs</p>
              ) : (
                <div className="overflow-x-auto rounded border border-gray-200">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Provider</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Success</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Date</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {detail.enrichment_logs.map((log) => (
                        <tr key={log.id}>
                          <td className="px-3 py-2">{log.provider}</td>
                          <td className="px-3 py-2">{log.success ? "Yes" : "No"}</td>
                          <td className="px-3 py-2">{new Date(log.created_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* Routing Logs */}
            <section>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Routing Logs</h3>
              {detail.routing_logs.length === 0 ? (
                <p className="text-sm text-gray-400">No logs</p>
              ) : (
                <div className="overflow-x-auto rounded border border-gray-200">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Destination</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Status</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Success</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Date</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {detail.routing_logs.map((log) => (
                        <tr key={log.id}>
                          <td className="px-3 py-2">{log.destination}</td>
                          <td className="px-3 py-2">{log.response_code ?? "—"}</td>
                          <td className="px-3 py-2">{log.success ? "Yes" : "No"}</td>
                          <td className="px-3 py-2">{new Date(log.created_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </>
  );
}
