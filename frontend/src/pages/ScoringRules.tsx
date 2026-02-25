import { useEffect, useState } from "react";
import {
  fetchScoringRules,
  fetchTemplates,
  createScoringRule,
  updateScoringRule,
  deleteScoringRule,
  applyTemplate,
} from "../api/scoring";
import type { ScoringRule } from "../types/scoring";
import type { ScoringTemplate } from "../types/scoring";
import RulesTable from "../components/scoring/RulesTable";
import RuleModal from "../components/scoring/RuleModal";
import TemplatesSection from "../components/scoring/TemplatesSection";

export default function ScoringRules() {
  const [rules, setRules] = useState<ScoringRule[]>([]);
  const [templates, setTemplates] = useState<ScoringTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<ScoringRule | null>(null);

  // Delete confirmation
  const [deletingRule, setDeletingRule] = useState<ScoringRule | null>(null);

  // Template applying
  const [applyingTemplate, setApplyingTemplate] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [rulesRes, templatesRes] = await Promise.all([
        fetchScoringRules(),
        fetchTemplates(),
      ]);
      setRules(rulesRes.items);
      setTemplates(templatesRes);
    } catch {
      setError("Failed to load scoring rules");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const showFeedback = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(""), 3000);
  };

  const handleAdd = () => {
    setEditingRule(null);
    setModalOpen(true);
  };

  const handleEdit = (rule: ScoringRule) => {
    setEditingRule(rule);
    setModalOpen(true);
  };

  const handleSave = async (data: { field: string; operator: string; value: string; points: number; is_active: boolean }) => {
    try {
      if (editingRule) {
        const updated = await updateScoringRule(editingRule.id, data);
        setRules(rules.map((r) => (r.id === updated.id ? updated : r)));
        showFeedback("Rule updated");
      } else {
        const created = await createScoringRule(data);
        setRules([...rules, created]);
        showFeedback("Rule created");
      }
      setModalOpen(false);
    } catch {
      showFeedback("Failed to save rule");
    }
  };

  const handleDelete = (rule: ScoringRule) => {
    setDeletingRule(rule);
  };

  const confirmDelete = async () => {
    if (!deletingRule) return;
    try {
      await deleteScoringRule(deletingRule.id);
      setRules(rules.filter((r) => r.id !== deletingRule.id));
      showFeedback("Rule deleted");
    } catch {
      showFeedback("Failed to delete rule");
    } finally {
      setDeletingRule(null);
    }
  };

  const handleApplyTemplate = async (name: string) => {
    setApplyingTemplate(name);
    try {
      const newRules = await applyTemplate(name);
      setRules([...rules, ...newRules]);
      showFeedback(`Template "${name}" applied — ${newRules.length} rules added`);
    } catch {
      showFeedback("Failed to apply template");
    } finally {
      setApplyingTemplate(null);
    }
  };

  if (loading) {
    return <div className="text-gray-500 py-8">Loading scoring rules...</div>;
  }
  if (error) {
    return <div className="text-red-600 py-8">{error}</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Scoring Rules</h1>
        <button
          onClick={handleAdd}
          className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
        >
          Add Rule
        </button>
      </div>

      {feedback && (
        <div className={`text-sm px-4 py-2 rounded-md ${
          feedback.includes("Failed") ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"
        }`}>
          {feedback}
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200">
        <RulesTable rules={rules} onEdit={handleEdit} onDelete={handleDelete} />
      </div>

      <TemplatesSection
        templates={templates}
        onApply={handleApplyTemplate}
        applying={applyingTemplate}
      />

      {/* Rule Modal */}
      {modalOpen && (
        <RuleModal
          rule={editingRule}
          onSave={handleSave}
          onClose={() => setModalOpen(false)}
        />
      )}

      {/* Delete Confirmation */}
      {deletingRule && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm w-full">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete Rule</h3>
            <p className="text-sm text-gray-600 mb-4">
              Are you sure you want to delete the rule for <strong>{deletingRule.field}</strong>? This cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeletingRule(null)}
                className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="px-4 py-2 text-sm text-white bg-red-600 rounded-md hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
