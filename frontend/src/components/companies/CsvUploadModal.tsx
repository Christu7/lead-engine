import { useRef, useState } from "react";
import { uploadCompaniesCsv } from "../../api/companies";
import type { CompanyBulkUploadResponse } from "../../types/company";

interface CsvUploadModalProps {
  onClose: () => void;
  onUploaded: () => void;
}

// ── Field definitions ───────────────────────────────────────────────────────

const FIELD_OPTIONS: { label: string; value: string }[] = [
  { label: "Name", value: "name" },
  { label: "Domain", value: "domain" },
  { label: "Website", value: "website" },
  { label: "Industry", value: "industry" },
  { label: "Employee Count", value: "employee_count" },
  { label: "City", value: "location_city" },
  { label: "State", value: "location_state" },
  { label: "Country", value: "location_country" },
  { label: "Apollo ID", value: "apollo_id" },
  { label: "Funding Stage", value: "funding_stage" },
  { label: "-- Skip this column --", value: "__skip__" },
];

// Maps lowercased CSV header → LeadEngine field name for auto-detection
const AUTO_DETECT: Record<string, string> = {
  company: "name",
  name: "name",
  "company name": "name",
  domain: "domain",
  website: "website",
  "company website url": "website",
  industry: "industry",
  "# employees": "employee_count",
  employees: "employee_count",
  "number of employees": "employee_count",
  "employee count": "employee_count",
  city: "location_city",
  state: "location_state",
  country: "location_country",
  "apollo account id": "apollo_id",
  "account id": "apollo_id",
  "apollo id": "apollo_id",
  "apollo contact id": "apollo_id",
  "funding stage": "funding_stage",
};

function autoDetectField(header: string): string {
  return AUTO_DETECT[header.toLowerCase().trim()] ?? "__skip__";
}

// ── CSV parsing helpers ──────────────────────────────────────────────────────

function parseCsvHeaders(text: string): string[] {
  const firstLine = text.split("\n")[0] ?? "";
  // Handle both quoted and unquoted headers
  const headers: string[] = [];
  let current = "";
  let inQuotes = false;
  for (const ch of firstLine) {
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === "," && !inQuotes) {
      headers.push(current.trim());
      current = "";
    } else if (ch !== "\r") {
      current += ch;
    }
  }
  if (current.trim()) headers.push(current.trim());
  return headers;
}

function countDataRows(text: string): number {
  // Count non-empty lines after the header
  const lines = text.split("\n").slice(1);
  return lines.filter((l) => l.trim()).length;
}

// ── Template download ────────────────────────────────────────────────────────

const TEMPLATE_HEADERS = [
  "Company",
  "Domain",
  "Website",
  "Industry",
  "# Employees",
  "City",
  "State",
  "Country",
  "Apollo Account Id",
  "Funding Stage",
];

function downloadTemplate() {
  const csv =
    TEMPLATE_HEADERS.join(",") +
    "\nAcme Corp,acme.com,https://acme.com,SaaS,150,Austin,TX,USA,,\n";
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "companies_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// ── Component ────────────────────────────────────────────────────────────────

type Step = "select" | "map" | "done";

export default function CsvUploadModal({ onClose, onUploaded }: CsvUploadModalProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  // Step tracking
  const [step, setStep] = useState<Step>("select");

  // Step 1 state
  const [file, setFile] = useState<File | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  // Step 2 state
  const [headers, setHeaders] = useState<string[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [mapping, setMapping] = useState<Record<string, string>>({});

  // Upload state
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [result, setResult] = useState<CompanyBulkUploadResponse | null>(null);

  // ── Step 1: file selected → parse headers ──
  const handleFileChange = async (f: File | null) => {
    setFile(f);
    setParseError(null);
    if (!f) return;
    try {
      const text = await f.text();
      const hdrs = parseCsvHeaders(text);
      if (hdrs.length === 0) {
        setParseError("Could not read headers from the CSV file.");
        return;
      }
      setHeaders(hdrs);
      setRowCount(countDataRows(text));
      const initial: Record<string, string> = {};
      for (const h of hdrs) {
        initial[h] = autoDetectField(h);
      }
      setMapping(initial);
    } catch {
      setParseError("Failed to read the file.");
    }
  };

  const handleNextStep = () => {
    if (!file || headers.length === 0) return;
    setStep("map");
  };

  // ── Step 2: submit upload ──
  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setUploadError(null);
    try {
      const res = await uploadCompaniesCsv(file, mapping);
      setResult(res);
      setStep("done");
      onUploaded();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  // ── Modal width ──
  const maxW = step === "map" ? "max-w-xl" : "max-w-md";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className={`w-full ${maxW} rounded-lg bg-white shadow-xl`}>
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Upload Companies CSV</h2>
            {step === "map" && (
              <p className="text-xs text-gray-500 mt-0.5">Step 2 of 2 — Map columns</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-2xl leading-none text-gray-400 hover:text-gray-600"
          >
            &times;
          </button>
        </div>

        <div className="p-6">
          {/* ── Step: done ── */}
          {step === "done" && result && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-gray-900">Upload Complete</p>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-gray-500">Created</dt>
                <dd className="font-medium text-green-700">{result.created}</dd>
                <dt className="text-gray-500">Updated</dt>
                <dd className="font-medium text-blue-700">{result.updated}</dd>
                <dt className="text-gray-500">Skipped</dt>
                <dd className="font-medium text-gray-700">{result.skipped}</dd>
              </dl>
              {result.errors.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-red-600 mb-1">
                    Errors ({result.errors.length})
                  </p>
                  <ul className="max-h-32 overflow-y-auto rounded-md bg-red-50 p-2 text-xs text-red-700 space-y-0.5">
                    {result.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}
              <button
                onClick={onClose}
                className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Done
              </button>
            </div>
          )}

          {/* ── Step 1: select file ── */}
          {step === "select" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-600">Upload a CSV with company data.</p>
                <button
                  type="button"
                  onClick={downloadTemplate}
                  className="text-xs font-medium text-indigo-600 hover:underline"
                >
                  Download template
                </button>
              </div>

              <div
                className="cursor-pointer rounded-md border-2 border-dashed border-gray-300 p-6 text-center hover:border-indigo-400"
                onClick={() => fileRef.current?.click()}
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
                />
                {file ? (
                  <div>
                    <p className="text-sm font-medium text-gray-700">{file.name}</p>
                    {rowCount > 0 && (
                      <p className="text-xs text-gray-400 mt-0.5">{rowCount} rows detected</p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">Click to select a .csv file</p>
                )}
              </div>

              {parseError && <p className="text-sm text-red-600">{parseError}</p>}

              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleNextStep}
                  disabled={!file || headers.length === 0 || !!parseError}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  Next: Map Columns →
                </button>
              </div>
            </div>
          )}

          {/* ── Step 2: map columns ── */}
          {step === "map" && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">
                Review how your CSV columns map to LeadEngine fields. Change any that were
                detected incorrectly.
              </p>

              <div className="max-h-72 overflow-y-auto rounded-md border border-gray-200">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs uppercase text-gray-500 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">Your CSV Column</th>
                      <th className="px-3 py-2 text-left font-medium">Maps to Field</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {headers.map((header) => (
                      <tr key={header}>
                        <td className="px-3 py-2 font-mono text-gray-700">{header}</td>
                        <td className="px-3 py-2">
                          <select
                            value={mapping[header] ?? "__skip__"}
                            onChange={(e) =>
                              setMapping((prev) => ({ ...prev, [header]: e.target.value }))
                            }
                            className="w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          >
                            {FIELD_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}

              <div className="flex justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setStep("select")}
                  disabled={loading}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  ← Back
                </button>
                <button
                  type="button"
                  onClick={handleUpload}
                  disabled={loading}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? "Importing…" : `Import ${rowCount} rows`}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
