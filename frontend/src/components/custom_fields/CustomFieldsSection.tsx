import { useEffect, useState } from "react";
import { getCustomFieldDefinitions, updateLeadCustomFields, updateCompanyCustomFields } from "../../api/custom_fields";
import type { CustomFieldDefinition, CustomFieldValues } from "../../types/custom_field";

interface Props {
  entityType: "lead" | "company";
  entityId: number | string;
  values: CustomFieldValues;
  onSaved: (newValues: CustomFieldValues) => void;
}

function DisplayValue({ fieldType, value }: { fieldType: string; value: string | number | boolean | null }) {
  if (value == null || value === "") {
    return <span className="text-gray-400 italic">Not set</span>;
  }
  switch (fieldType) {
    case "text":
      return <span>{String(value)}</span>;
    case "number":
      return <span className="tabular-nums">{Number(value).toLocaleString()}</span>;
    case "date":
      try {
        return <span>{new Date(String(value)).toLocaleDateString()}</span>;
      } catch {
        return <span>{String(value)}</span>;
      }
    case "boolean":
      return value ? (
        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">Yes</span>
      ) : (
        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">No</span>
      );
    case "select":
      return (
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
          {String(value)}
        </span>
      );
    default:
      return <span>{String(value)}</span>;
  }
}

interface FieldRowProps {
  def: CustomFieldDefinition;
  value: string | number | boolean | null;
  entityType: "lead" | "company";
  entityId: number | string;
  onSaved: (key: string, newValue: string | number | boolean | null) => void;
}

function FieldRow({ def, value, entityType, entityId, onSaved }: FieldRowProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    if (def.field_type === "boolean") return; // boolean saves immediately on toggle
    setEditValue(value == null ? "" : String(value));
    setEditing(true);
    setError(null);
  };

  const cancelEdit = () => {
    setEditing(false);
    setError(null);
  };

  const save = async (rawValue: string | number | boolean | null) => {
    setSaving(true);
    setError(null);
    try {
      const fn = entityType === "lead" ? updateLeadCustomFields : updateCompanyCustomFields;
      await fn(entityId, { [def.field_key]: rawValue });
      onSaved(def.field_key, rawValue);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleBlurSave();
    } else if (e.key === "Escape") {
      cancelEdit();
    }
  };

  const handleBlurSave = () => {
    if (def.field_type === "number") {
      const n = editValue.trim() === "" ? null : Number(editValue);
      save(n);
    } else if (def.field_type === "date") {
      save(editValue.trim() || null);
    } else if (def.field_type === "select") {
      save(editValue || null);
    } else {
      save(editValue.trim() || null);
    }
  };

  const handleBooleanToggle = (e: React.ChangeEvent<HTMLInputElement>) => {
    save(e.target.checked);
  };

  const dateDisplayValue = (): string => {
    if (!value) return "";
    const s = String(value);
    // If already YYYY-MM-DD, return as is
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    try {
      return new Date(s).toISOString().slice(0, 10);
    } catch {
      return s;
    }
  };

  return (
    <div className="py-2">
      <div className="flex items-start justify-between gap-3">
        <span className="shrink-0 text-xs font-medium text-gray-500 w-36">{def.field_label}</span>
        <div className="flex-1 text-sm">
          {def.field_type === "boolean" ? (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={!!value}
                onChange={handleBooleanToggle}
                disabled={saving}
                className="rounded border-gray-300"
              />
              {saving && <span className="text-xs text-gray-400">Saving…</span>}
            </div>
          ) : editing ? (
            <div className="flex flex-col gap-1">
              {def.field_type === "select" ? (
                <select
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={handleBlurSave}
                  onKeyDown={handleKeyDown}
                  autoFocus
                  className="rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="">— Not set —</option>
                  {(def.options ?? []).map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={def.field_type === "number" ? "number" : def.field_type === "date" ? "date" : "text"}
                  value={def.field_type === "date" ? (editValue || dateDisplayValue()) : editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={handleBlurSave}
                  onKeyDown={handleKeyDown}
                  autoFocus
                  disabled={saving}
                  className="rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              )}
              {saving && <span className="text-xs text-gray-400">Saving…</span>}
            </div>
          ) : (
            <button
              onClick={startEdit}
              className="text-left hover:text-indigo-600 transition-colors"
            >
              <DisplayValue fieldType={def.field_type} value={value} />
            </button>
          )}
          {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
        </div>
      </div>
    </div>
  );
}

export default function CustomFieldsSection({ entityType, entityId, values, onSaved }: Props) {
  const [fieldDefs, setFieldDefs] = useState<CustomFieldDefinition[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getCustomFieldDefinitions(entityType)
      .then(setFieldDefs)
      .catch(() => {
        // silently hide on error — non-critical section
      })
      .finally(() => setLoading(false));
  }, [entityType]);

  const [localValues, setLocalValues] = useState<CustomFieldValues>(values);

  useEffect(() => {
    setLocalValues(values);
  }, [values]);

  const handleSaved = (key: string, newValue: string | number | boolean | null) => {
    const updated = { ...localValues, [key]: newValue };
    setLocalValues(updated);
    onSaved(updated);
  };

  if (loading) {
    return (
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">Custom Fields</h3>
        <p className="text-sm text-gray-400">Loading custom fields…</p>
      </section>
    );
  }

  const sorted = [...fieldDefs].sort((a, b) => {
    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
    return a.field_label.localeCompare(b.field_label);
  });

  if (sorted.length === 0) return null;

  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">Custom Fields</h3>
      <div className="divide-y divide-gray-100">
        {sorted.map((def) => (
          <FieldRow
            key={def.id}
            def={def}
            value={localValues[def.field_key] ?? null}
            entityType={entityType}
            entityId={entityId}
            onSaved={handleSaved}
          />
        ))}
      </div>
    </section>
  );
}
