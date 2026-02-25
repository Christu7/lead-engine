import type { ScoringRule } from "../../types/scoring";
import { OPERATOR_LABELS } from "../../types/scoring";

interface Props {
  rules: ScoringRule[];
  onEdit: (rule: ScoringRule) => void;
  onDelete: (rule: ScoringRule) => void;
}

export default function RulesTable({ rules, onEdit, onDelete }: Props) {
  if (rules.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No scoring rules yet. Add one to get started.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Field</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Operator</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Value</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Points</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Active</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {rules.map((rule) => (
            <tr key={rule.id}>
              <td className="px-4 py-3 text-sm font-medium text-gray-900">{rule.field}</td>
              <td className="px-4 py-3 text-sm text-gray-500">
                {OPERATOR_LABELS[rule.operator] || rule.operator}
              </td>
              <td className="px-4 py-3 text-sm text-gray-500">{rule.value || "—"}</td>
              <td className="px-4 py-3 text-sm">
                <span className={rule.points >= 0 ? "text-green-600 font-medium" : "text-red-600 font-medium"}>
                  {rule.points > 0 ? `+${rule.points}` : rule.points}
                </span>
              </td>
              <td className="px-4 py-3 text-sm">
                <span
                  className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${
                    rule.is_active
                      ? "bg-green-100 text-green-800"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {rule.is_active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="px-4 py-3 text-sm space-x-2">
                <button
                  onClick={() => onEdit(rule)}
                  className="text-indigo-600 hover:text-indigo-800"
                >
                  Edit
                </button>
                <button
                  onClick={() => onDelete(rule)}
                  className="text-red-600 hover:text-red-800"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
