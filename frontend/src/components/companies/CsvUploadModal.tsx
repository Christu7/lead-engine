import { useRef, useState } from "react";
import { uploadCompaniesCsv } from "../../api/companies";
import type { CompanyBulkUploadResponse } from "../../types/company";

interface CsvUploadModalProps {
  onClose: () => void;
  onUploaded: () => void;
}

const TEMPLATE_HEADERS = [
  "Company",
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
  const csv = TEMPLATE_HEADERS.join(",") + "\nAcme Corp,https://acme.com,SaaS,150,Austin,TX,USA,,\n";
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "companies_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function CsvUploadModal({ onClose, onUploaded }: CsvUploadModalProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompanyBulkUploadResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a CSV file");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await uploadCompaniesCsv(file);
      setResult(res);
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Upload Companies CSV</h2>
          <button onClick={onClose} className="text-2xl leading-none text-gray-400 hover:text-gray-600">
            &times;
          </button>
        </div>

        <div className="p-6">
          {result ? (
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
                  <p className="text-xs font-medium text-red-600 mb-1">Errors ({result.errors.length})</p>
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
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-600">
                  Upload a CSV with company data.
                </p>
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
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    setFile(f);
                    setError(null);
                  }}
                />
                {file ? (
                  <p className="text-sm text-gray-700">{file.name}</p>
                ) : (
                  <p className="text-sm text-gray-400">Click to select a .csv file</p>
                )}
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !file}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? "Uploading…" : "Upload"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
