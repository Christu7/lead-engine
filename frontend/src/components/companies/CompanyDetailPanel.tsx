import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { enrichCompany, getCompany, pullContacts } from "../../api/companies";
import type { CompanyDetail } from "../../types/company";

interface CompanyDetailPanelProps {
  companyId: string | null;
  onClose: () => void;
  onEnriched?: () => void;
}

const SENIORITY_OPTIONS = [
  { value: "owner", label: "Owner" },
  { value: "founder", label: "Founder" },
  { value: "c_suite", label: "C-Suite" },
  { value: "vp", label: "VP" },
  { value: "director", label: "Director" },
  { value: "manager", label: "Manager" },
  { value: "senior", label: "Senior" },
];

function EnrichmentBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    enriched: "bg-green-100 text-green-800",
    enriching: "bg-yellow-100 text-yellow-800",
    pending: "bg-gray-100 text-gray-600",
    partial: "bg-orange-100 text-orange-800",
    failed: "bg-red-100 text-red-800",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status] ?? styles.pending}`}
    >
      {status === "enriching" && (
        <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      )}
      {status}
    </span>
  );
}

function AbmBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    target: "bg-blue-100 text-blue-800",
    active: "bg-green-100 text-green-800",
    inactive: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status] ?? styles.target}`}>
      {status}
    </span>
  );
}

export default function CompanyDetailPanel({ companyId, onClose, onEnriched }: CompanyDetailPanelProps) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [showPullForm, setShowPullForm] = useState(false);
  const [pullTitles, setPullTitles] = useState("");
  const [pullSeniorities, setPullSeniorities] = useState<string[]>([]);
  const [pullLimit, setPullLimit] = useState(25);
  const [pulling, setPulling] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => {
    if (!companyId) {
      setDetail(null);
      stopPolling();
      return;
    }
    setLoading(true);
    setFeedback(null);
    setShowPullForm(false);
    getCompany(companyId)
      .then(setDetail)
      .catch(() => setFeedback("Failed to load company"))
      .finally(() => setLoading(false));

    return () => stopPolling();
  }, [companyId]);

  // Poll while enriching
  useEffect(() => {
    if (!companyId || !detail) return;

    if (detail.enrichment_status === "enriching") {
      if (pollRef.current === null) {
        pollRef.current = setInterval(async () => {
          try {
            const updated = await getCompany(companyId);
            setDetail(updated);
            if (updated.enrichment_status !== "enriching") {
              stopPolling();
              if (updated.enrichment_status === "enriched") {
                onEnriched?.();
              }
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
  }, [companyId, detail?.enrichment_status]);

  if (!companyId) return null;

  const handleEnrich = async () => {
    if (!companyId) return;
    setEnriching(true);
    setFeedback(null);
    try {
      await enrichCompany(companyId);
      setFeedback("Enrichment queued");
      const updated = await getCompany(companyId);
      setDetail(updated);
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "Enrichment failed");
    } finally {
      setEnriching(false);
    }
  };

  const handlePullContacts = async () => {
    if (!companyId) return;
    setPulling(true);
    setFeedback(null);
    try {
      const titles = pullTitles
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await pullContacts(companyId, {
        titles,
        seniorities: pullSeniorities,
        limit: pullLimit,
      });
      setFeedback("Contact pull queued — leads will appear shortly");
      setShowPullForm(false);
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "Contact pull failed");
    } finally {
      setPulling(false);
    }
  };

  const toggleSeniority = (val: string) => {
    setPullSeniorities((prev) =>
      prev.includes(val) ? prev.filter((s) => s !== val) : [...prev, val],
    );
  };

  const location = detail
    ? [detail.location_city, detail.location_state, detail.location_country].filter(Boolean).join(", ")
    : "";

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg overflow-y-auto bg-white shadow-xl">
        {/* Header bar */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Company Detail</h2>
          <button onClick={onClose} className="text-2xl leading-none text-gray-400 hover:text-gray-600">
            &times;
          </button>
        </div>

        {loading || !detail ? (
          <div className="p-6 text-sm text-gray-500">Loading…</div>
        ) : (
          <div className="space-y-6 p-6">
            {/* ── Section 1: Header ── */}
            <section>
              <h1 className="text-2xl font-bold text-gray-900">{detail.name}</h1>
              {detail.domain && (
                <a
                  href={`https://${detail.domain}`}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 block text-sm text-indigo-600 hover:underline"
                >
                  {detail.domain}
                </a>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <EnrichmentBadge status={detail.enrichment_status} />
                <AbmBadge status={detail.abm_status} />
                {detail.enriched_at && (
                  <span className="text-xs text-gray-400">
                    Enriched {new Date(detail.enriched_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              <div className="mt-3">
                <button
                  onClick={handleEnrich}
                  disabled={enriching || detail.enrichment_status === "enriching"}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {enriching || detail.enrichment_status === "enriching" ? "Enriching…" : "Enrich Now"}
                </button>
              </div>
            </section>

            {/* ── Section 2: Basic Info ── */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">Basic Info</h3>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-gray-500">Industry</dt>
                <dd className="text-gray-900">{detail.industry || "—"}</dd>
                <dt className="text-gray-500">Employees</dt>
                <dd className="text-gray-900">
                  {detail.employee_count != null ? detail.employee_count.toLocaleString() : "—"}
                </dd>
                <dt className="text-gray-500">Location</dt>
                <dd className="text-gray-900">{location || "—"}</dd>
                <dt className="text-gray-500">Founded</dt>
                <dd className="text-gray-900">{detail.founded_year ?? "—"}</dd>
                <dt className="text-gray-500">Funding Stage</dt>
                <dd className="text-gray-900">{detail.funding_stage || "—"}</dd>
                <dt className="text-gray-500">Annual Revenue</dt>
                <dd className="text-gray-900">{detail.annual_revenue_range || "—"}</dd>
                {detail.linkedin_url && (
                  <>
                    <dt className="text-gray-500">LinkedIn</dt>
                    <dd>
                      <a
                        href={detail.linkedin_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-600 hover:underline"
                      >
                        View Profile
                      </a>
                    </dd>
                  </>
                )}
              </dl>
            </section>

            {/* ── Section 3: Tech Stack ── */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">Tech Stack</h3>
              {detail.tech_stack && detail.tech_stack.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {detail.tech_stack.map((t) => (
                    <span key={t} className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-700">
                      {t}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400">No tech stack data</p>
              )}
            </section>

            {/* ── Section 4: Keywords ── */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">Keywords</h3>
              {detail.keywords && detail.keywords.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {detail.keywords.map((k) => (
                    <span key={k} className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs text-blue-700">
                      {k}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400">No keywords data</p>
              )}
            </section>

            {/* ── Section 5: Pull Contacts ── */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">Pull Contacts</h3>
              {!detail.apollo_id ? (
                <p className="text-sm text-gray-400">Enrich company first to pull contacts</p>
              ) : !showPullForm ? (
                <button
                  onClick={() => setShowPullForm(true)}
                  className="rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700"
                >
                  Pull Contacts from Apollo
                </button>
              ) : (
                <div className="space-y-3 rounded-md border border-gray-200 bg-gray-50 p-4">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">
                      Titles (comma-separated)
                    </label>
                    <input
                      type="text"
                      value={pullTitles}
                      onChange={(e) => setPullTitles(e.target.value)}
                      placeholder="CEO, VP of Sales"
                      className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">Seniorities</label>
                    <div className="flex flex-wrap gap-2">
                      {SENIORITY_OPTIONS.map((opt) => (
                        <label key={opt.value} className="flex cursor-pointer items-center gap-1 text-sm">
                          <input
                            type="checkbox"
                            checked={pullSeniorities.includes(opt.value)}
                            onChange={() => toggleSeniority(opt.value)}
                            className="rounded border-gray-300"
                          />
                          {opt.label}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">Limit</label>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={pullLimit}
                      onChange={(e) => setPullLimit(Math.min(100, Math.max(1, Number(e.target.value))))}
                      className="w-20 rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handlePullContacts}
                      disabled={pulling}
                      className="rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                    >
                      {pulling ? "Queuing…" : "Pull Contacts"}
                    </button>
                    <button
                      onClick={() => setShowPullForm(false)}
                      className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </section>

            {/* ── Section 6: Linked Leads ── */}
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">
                Linked Leads ({detail.lead_count})
              </h3>
              {detail.leads.length === 0 ? (
                <p className="text-sm text-gray-400">No linked leads yet</p>
              ) : (
                <div className="overflow-x-auto rounded border border-gray-200">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Name</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Title</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Score</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500">Status</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-500"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {detail.leads.map((lead) => (
                        <tr key={lead.id}>
                          <td className="px-3 py-2 font-medium text-gray-900">{lead.name}</td>
                          <td className="px-3 py-2 text-gray-600">{lead.title || "—"}</td>
                          <td className="px-3 py-2">
                            {lead.score != null ? (
                              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
                                {lead.score}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-3 py-2 text-gray-600">{lead.enrichment_status}</td>
                          <td className="px-3 py-2">
                            <button
                              onClick={() => {
                                onClose();
                                navigate("/leads");
                              }}
                              className="text-indigo-600 hover:underline"
                            >
                              View
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {feedback && (
              <p className="rounded-md bg-gray-50 px-3 py-2 text-sm text-gray-700">{feedback}</p>
            )}
          </div>
        )}
      </div>
    </>
  );
}
