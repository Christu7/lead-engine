import { useState, useEffect } from "react";
import type { ScoringRule } from "../../types/scoring";
import { VALID_OPERATORS, OPERATOR_LABELS } from "../../types/scoring";

interface Props {
  rule: ScoringRule | null;
  onSave: (data: { field: string; operator: string; value: string; points: number; is_active: boolean }) => void;
  onClose: () => void;
}

export default function RuleModal({ rule, onSave, onClose }: Props) {
  const [field, setField] = useState("");
  const [operator, setOperator] = useState("equals");
  const [value, setValue] = useState("");
  const [points, setPoints] = useState(0);
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    if (rule) {
      setField(rule.field);
      setOperator(rule.operator);
      setValue(rule.value);
      setPoints(rule.points);
      setIsActive(rule.is_active);
    }
  }, [rule]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({ field, operator, value, points, is_active: isActive });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          {rule ? "Edit Rule" : "Add Rule"}
        </h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Field</label>
            <input
              type="text"
              value={field}
              onChange={(e) => setField(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="e.g. company, title, source"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Operator</label>
            <select
              value={operator}
              onChange={(e) => setOperator(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {VALID_OPERATORS.map((op) => (
                <option key={op} value={op}>
                  {OPERATOR_LABELS[op]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Value</label>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              disabled={operator === "not_empty"}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100 disabled:text-gray-400"
              placeholder={operator === "not_empty" ? "N/A" : "e.g. Google, CEO"}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Points</label>
            <input
              type="number"
              value={points}
              onChange={(e) => setPoints(Number(e.target.value))}
              required
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_active"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="h-4 w-4 text-indigo-600 border-gray-300 rounded"
            />
            <label htmlFor="is_active" className="text-sm text-gray-700">Active</label>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
            >
              {rule ? "Update" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
