import { useEffect, useRef, useState } from "react";
import { enrichLead, fetchLeadDetail, routeLead, runAiAnalysis } from "../../api/leads";
import type { LeadDetail } from "../../types/lead";
import ScoreBadge from "./ScoreBadge";

interface LeadSlideOverProps {
  leadId: number | null;
  onClose: () => void;
}

const QUALIFICATION_COLORS = {
  hot: "bg-red-100 text-red-800",
  warm: "bg-yellow-100 text-yellow-800",
  cold: "bg-blue-100 text-blue-800",
} as const;

export default function LeadSlideOver({ leadId, onClose }: LeadSlideOverProps) {
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [routing, setRouting] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => {
    if (!leadId) {
      setDetail(null);
      stopPolling();
      return;
    }
    setLoading(true);
    setFeedback(null);
    fetchLeadDetail(leadId)
      .then(setDetail)
      .finally(() => setLoading(false));

    return () => stopPolling();
  }, [leadId]);

  // Poll while ai_status === "analyzing"
  useEffect(() => {
    if (!leadId || !detail) return;

    if (detail.ai_status === "analyzing") {
      if (pollRef.current === null) {
        pollRef.current = setInterval(async () => {
          try {
            const updated = await fetchLeadDetail(leadId);
            setDetail(updated);
            if (updated.ai_status !== "analyzing") {
              stopPolling();
            }
          } catch {
            stopPolling();
          }
        }, 3000);
      }
    } else {
      stopPolling();
    }

    return () => stopPolling();
  }, [leadId, detail?.ai_status]);

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

  const handleAiAnalyze = async () => {
    setAiLoading(true);
    setFeedback(null);
    try {
      await runAiAnalysis(leadId);
      // Optimistically update status so polling starts immediately
      setDetail((prev) => prev ? { ...prev, ai_status: "analyzing" } : prev);
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "AI analysis failed");
    } finally {
      setAiLoading(false);
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

            {/* AI Analysis */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-500 uppercase">AI Analysis</h3>
                {detail.ai_status === "analyzing" && (
                  <span className="flex items-center gap-1.5 text-xs text-indigo-600">
                    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    Analyzing…
                  </span>
                )}
                {detail.ai_status === "completed" && (
                  <span className="text-xs font-medium text-green-600">✓ Complete</span>
                )}
                {detail.ai_status === "failed" && (
                  <span className="text-xs font-medium text-red-600">✗ Failed</span>
                )}
              </div>

              {/* Not yet analyzed */}
              {!detail.ai_status && (
                <button
                  onClick={handleAiAnalyze}
                  disabled={aiLoading}
                  className="rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                >
                  {aiLoading ? "Starting…" : "Run AI Analysis"}
                </button>
              )}

              {/* Failed — show retry */}
              {detail.ai_status === "failed" && (
                <button
                  onClick={handleAiAnalyze}
                  disabled={aiLoading}
                  className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {aiLoading ? "Starting…" : "Retry AI Analysis"}
                </button>
              )}

              {/* Completed — display results */}
              {detail.ai_status === "completed" && detail.ai_analysis && (
                <div className="space-y-4 text-sm">
                  {/* Company Summary */}
                  <div>
                    <p className="font-medium text-gray-700 mb-1">Company Summary</p>
                    <p className="text-gray-600 leading-relaxed">{detail.ai_analysis.company_summary}</p>
                  </div>

                  {/* Qualification */}
                  <div>
                    <p className="font-medium text-gray-700 mb-1">Qualification</p>
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
                          QUALIFICATION_COLORS[detail.ai_analysis.qualification.rating]
                        }`}
                      >
                        {detail.ai_analysis.qualification.rating}
                      </span>
                    </div>
                    <p className="text-gray-600 leading-relaxed">{detail.ai_analysis.qualification.reasoning}</p>
                  </div>

                  {/* Icebreakers */}
                  <div>
                    <p className="font-medium text-gray-700 mb-1">Icebreakers</p>
                    <ol className="list-decimal list-inside space-y-1.5 text-gray-600">
                      {detail.ai_analysis.icebreakers.map((line, i) => (
                        <li key={i} className="leading-relaxed">{line}</li>
                      ))}
                    </ol>
                  </div>

                  {/* Email Angle */}
                  <div>
                    <p className="font-medium text-gray-700 mb-1">Email Angle</p>
                    <p className="text-gray-600 leading-relaxed">{detail.ai_analysis.email_angle}</p>
                  </div>
                </div>
              )}
            </section>

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
