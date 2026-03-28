import { useEffect, useState } from "react";
import {
  getCustomFieldDefinitions,
  createCustomFieldDefinition,
  updateCustomFieldDefinition,
  deleteCustomFieldDefinition,
} from "../../api/custom_fields";
import type {
  CustomFieldDefinition,
  CustomFieldDefinitionCreate,
  CustomFieldDefinitionUpdate,
} from "../../types/custom_field";

function labelToKey(label: string): string {
  const raw = label
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .replace(/^[^a-z]+/, "");
  return raw.slice(0, 100) || "";
}

export default function CustomFieldsManager() {
  const [tab, setTab] = useState<"lead" | "company">("lead");
  const [fieldDefs, setFieldDefs] = useState<CustomFieldDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<CustomFieldDefinition | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CustomFieldDefinition | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  // Form state
  const [formLabel, setFormLabel] = useState("");
  const [formKey, setFormKey] = useState("");
  const [formType, setFormType] = useState("text");
  const [formOptions, setFormOptions] = useState("");
  const [formShowInTable, setFormShowInTable] = useState(false);
  const [formEnrichmentSource, setFormEnrichmentSource] = useState("");
  const [formEnrichmentMapping, setFormEnrichmentMapping] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [formApiError, setFormApiError] = useState<string | null>(null);

  const loadDefs = (entityType: "lead" | "company") => {
    setLoading(true);
    setListError(null);
    getCustomFieldDefinitions(entityType)
      .then(setFieldDefs)
      .catch((err) => setListError(err instanceof Error ? err.message : "Failed to load fields"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDefs(tab);
  }, [tab]);

  const openAddModal = () => {
    setEditTarget(null);
    setFormLabel("");
    setFormKey("");
    setFormType("text");
    setFormOptions("");
    setFormShowInTable(false);
    setFormEnrichmentSource("");
    setFormEnrichmentMapping("");
    setFormErrors({});
    setFormApiError(null);
    setShowModal(true);
  };

  const openEditModal = (def: CustomFieldDefinition) => {
    setEditTarget(def);
    setFormLabel(def.field_label);
    setFormKey(def.field_key);
    setFormType(def.field_type);
    setFormOptions(def.options ? def.options.join(", ") : "");
    setFormShowInTable(def.show_in_table);
    setFormEnrichmentSource(def.enrichment_source ?? "");
    setFormEnrichmentMapping(def.enrichment_mapping ?? "");
    setFormErrors({});
    setFormApiError(null);
    setShowModal(true);
  };

  const handleLabelBlur = () => {
    if (!editTarget && !formKey) {
      setFormKey(labelToKey(formLabel));
    }
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!formLabel.trim()) errors.label = "Label is required";
    if (!formKey.trim()) {
      errors.key = "Field key is required";
    } else if (!/^[a-z][a-z0-9_]*$/.test(formKey)) {
      errors.key = "Key must match ^[a-z][a-z0-9_]*$";
    }
    if (formEnrichmentMapping.trim() && !formEnrichmentSource.trim()) {
      errors.enrichment_mapping = "Enrichment source is required when mapping is set";
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSaving(true);
    setFormApiError(null);

    const options =
      formType === "select" && formOptions.trim()
        ? formOptions
            .split(",")
            .map((o) => o.trim())
            .filter(Boolean)
        : null;

    try {
      if (editTarget) {
        const payload: CustomFieldDefinitionUpdate = {
          field_label: formLabel,
          field_type: formType as CustomFieldDefinition["field_type"],
          options,
          show_in_table: formShowInTable,
          enrichment_source: formEnrichmentSource || null,
          enrichment_mapping: formEnrichmentMapping || null,
        };
        await updateCustomFieldDefinition(editTarget.id, payload);
      } else {
        const payload: CustomFieldDefinitionCreate = {
          entity_type: tab,
          field_key: formKey,
          field_label: formLabel,
          field_type: formType as CustomFieldDefinition["field_type"],
          options,
          show_in_table: formShowInTable,
          enrichment_source: formEnrichmentSource || null,
          enrichment_mapping: formEnrichmentMapping || null,
        };
        await createCustomFieldDefinition(payload);
      }
      setShowModal(false);
      loadDefs(tab);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed";
      if (msg.includes("soft-deleted") || msg.includes("restore")) {
        setFormApiError(
          "A soft-deleted field with this key already exists. Restore it from the deleted fields list.",
        );
      } else {
        setFormApiError(msg);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (def: CustomFieldDefinition) => {
    setDeleting(true);
    try {
      await deleteCustomFieldDefinition(def.id);
      setDeleteTarget(null);
      loadDefs(tab);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      {/* Tab buttons */}
      <div className="mb-4 flex gap-2 border-b border-gray-200">
        <button
          onClick={() => setTab("lead")}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "lead"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Lead Fields
        </button>
        <button
          onClick={() => setTab("company")}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "company"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Company Fields
        </button>
      </div>

      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {fieldDefs.length} field{fieldDefs.length !== 1 ? "s" : ""} defined
        </p>
        <button
          onClick={openAddModal}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Add Field
        </button>
      </div>

      {listError && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{listError}</p>
      )}

      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : fieldDefs.length === 0 ? (
        <p className="text-sm text-gray-400">No custom fields defined yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Label</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Key</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Type</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Options</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Show in Table</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Enrichment Source</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {fieldDefs.map((def) => (
                <tr key={def.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium text-gray-900">{def.field_label}</td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-600">{def.field_key}</td>
                  <td className="px-3 py-2 text-gray-700">{def.field_type}</td>
                  <td className="px-3 py-2 text-gray-600">
                    {def.options && def.options.length > 0 ? def.options.join(", ") : "—"}
                  </td>
                  <td className="px-3 py-2 text-gray-700">{def.show_in_table ? "Yes" : "No"}</td>
                  <td className="px-3 py-2 text-gray-700">
                    {def.enrichment_source
                      ? def.enrichment_source.charAt(0).toUpperCase() + def.enrichment_source.slice(1)
                      : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-1">
                      <div className="flex gap-2">
                        <button
                          onClick={() => openEditModal(def)}
                          className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                        >
                          Edit
                        </button>
                        {deleteTarget?.id !== def.id && (
                          <button
                            onClick={() => setDeleteTarget(def)}
                            className="text-xs font-medium text-red-500 hover:text-red-700"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                      {deleteTarget?.id === def.id && (
                        <div className="rounded-md bg-red-50 px-2 py-1.5 text-xs text-red-700">
                          <p className="mb-1">Delete this field? Existing data is preserved and can be restored.</p>
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleDelete(def)}
                              disabled={deleting}
                              className="rounded bg-red-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                            >
                              {deleting ? "Deleting…" : "Confirm"}
                            </button>
                            <button
                              onClick={() => setDeleteTarget(null)}
                              className="rounded border border-gray-300 bg-white px-2 py-0.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30" onClick={() => setShowModal(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
              <div className="flex items-center justify-between border-b px-5 py-4">
                <h3 className="text-base font-semibold text-gray-900">
                  {editTarget ? "Edit Custom Field" : "Add Custom Field"}
                </h3>
                <button
                  onClick={() => setShowModal(false)}
                  className="text-xl leading-none text-gray-400 hover:text-gray-600"
                >
                  &times;
                </button>
              </div>

              <div className="space-y-4 px-5 py-4">
                {formApiError && (
                  <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{formApiError}</p>
                )}

                {/* Label */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Label <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={formLabel}
                    onChange={(e) => setFormLabel(e.target.value)}
                    onBlur={handleLabelBlur}
                    placeholder="Contract Value"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  {formErrors.label && (
                    <p className="mt-1 text-xs text-red-500">{formErrors.label}</p>
                  )}
                </div>

                {/* Key */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Field Key <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={formKey}
                    onChange={(e) => setFormKey(e.target.value)}
                    disabled={!!editTarget}
                    placeholder="contract_value"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
                  />
                  <p className="mt-1 text-xs text-gray-400">Must match: ^[a-z][a-z0-9_]*$</p>
                  {formErrors.key && (
                    <p className="mt-1 text-xs text-red-500">{formErrors.key}</p>
                  )}
                </div>

                {/* Type */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Type</label>
                  <select
                    value={formType}
                    onChange={(e) => setFormType(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="text">text</option>
                    <option value="number">number</option>
                    <option value="date">date</option>
                    <option value="boolean">boolean</option>
                    <option value="select">select</option>
                  </select>
                </div>

                {/* Options (only for select) */}
                {formType === "select" && (
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Options (comma-separated)
                    </label>
                    <textarea
                      value={formOptions}
                      onChange={(e) => setFormOptions(e.target.value)}
                      placeholder="Hot,Warm,Cold"
                      rows={2}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                )}

                {/* Show in Table */}
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="show_in_table"
                    checked={formShowInTable}
                    onChange={(e) => setFormShowInTable(e.target.checked)}
                    className="rounded border-gray-300"
                  />
                  <label htmlFor="show_in_table" className="text-sm font-medium text-gray-700">
                    Show in Table
                  </label>
                </div>

                {/* Enrichment Source */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Enrichment Source
                  </label>
                  <select
                    value={formEnrichmentSource}
                    onChange={(e) => {
                      setFormEnrichmentSource(e.target.value);
                      if (!e.target.value) setFormEnrichmentMapping("");
                    }}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">None</option>
                    <option value="apollo">Apollo</option>
                    <option value="clearbit">Clearbit</option>
                    <option value="proxycurl">Proxycurl</option>
                  </select>
                </div>

                {/* Enrichment Mapping (only when source is selected) */}
                {formEnrichmentSource && (
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Enrichment Mapping
                    </label>
                    <input
                      type="text"
                      value={formEnrichmentMapping}
                      onChange={(e) => setFormEnrichmentMapping(e.target.value)}
                      placeholder="organization.phone"
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    {formErrors.enrichment_mapping && (
                      <p className="mt-1 text-xs text-red-500">{formErrors.enrichment_mapping}</p>
                    )}
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 border-t px-5 py-4">
                <button
                  onClick={() => setShowModal(false)}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={saving}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {saving ? "Saving…" : editTarget ? "Save Changes" : "Create Field"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
