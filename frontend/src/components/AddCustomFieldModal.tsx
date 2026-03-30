import { useState } from "react";
import { createCustomFieldDefinition } from "../api/custom_fields";
import type { CustomFieldDefinition } from "../types/custom_field";

function labelToKey(label: string): string {
  const raw = label
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .replace(/^[^a-z]+/, "");
  return raw.slice(0, 100) || "";
}

interface Props {
  entityType: "lead" | "company";
  onCreated: (def: CustomFieldDefinition) => void;
  onClose: () => void;
}

export default function AddCustomFieldModal({ entityType, onCreated, onClose }: Props) {
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [type, setType] = useState<CustomFieldDefinition["field_type"]>("text");
  const [options, setOptions] = useState("");
  const [showInTable, setShowInTable] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);

  const handleLabelBlur = () => {
    if (!key) setKey(labelToKey(label));
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!label.trim()) errs.label = "Label is required";
    if (!key.trim()) {
      errs.key = "Field key is required";
    } else if (!/^[a-z][a-z0-9_]*$/.test(key)) {
      errs.key = "Must match ^[a-z][a-z0-9_]*$";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    setApiError(null);
    try {
      const opts =
        type === "select" && options.trim()
          ? options.split(",").map((o) => o.trim()).filter(Boolean)
          : null;
      const def = await createCustomFieldDefinition({
        entity_type: entityType,
        field_key: key,
        field_label: label,
        field_type: type,
        options: opts,
        show_in_table: showInTable,
      });
      onCreated(def);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-lg bg-white shadow-xl">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <h3 className="text-base font-semibold text-gray-900">Add Column</h3>
            <button
              onClick={onClose}
              className="text-xl leading-none text-gray-400 hover:text-gray-600"
            >
              &times;
            </button>
          </div>

          <div className="space-y-4 px-5 py-4">
            {apiError && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{apiError}</p>
            )}

            {/* Label */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Label <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                onBlur={handleLabelBlur}
                placeholder="Contract Value"
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              {errors.label && <p className="mt-1 text-xs text-red-500">{errors.label}</p>}
            </div>

            {/* Key */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Field Key <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="contract_value"
                className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <p className="mt-0.5 text-xs text-gray-400">Auto-generated from label · snake_case</p>
              {errors.key && <p className="mt-1 text-xs text-red-500">{errors.key}</p>}
            </div>

            {/* Type */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Type</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as typeof type)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="text">text</option>
                <option value="number">number</option>
                <option value="date">date</option>
                <option value="boolean">boolean</option>
                <option value="select">select</option>
              </select>
            </div>

            {/* Options — only for select */}
            {type === "select" && (
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Options (comma-separated)
                </label>
                <input
                  type="text"
                  value={options}
                  onChange={(e) => setOptions(e.target.value)}
                  placeholder="Hot, Warm, Cold"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            )}

            {/* Show in table */}
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="qaf_show_in_table"
                checked={showInTable}
                onChange={(e) => setShowInTable(e.target.checked)}
                className="rounded border-gray-300"
              />
              <label htmlFor="qaf_show_in_table" className="text-sm font-medium text-gray-700">
                Show in table
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-2 border-t px-5 py-4">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Add Column"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
