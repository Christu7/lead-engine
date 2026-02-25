import type { ScoringTemplate } from "../../types/scoring";

interface Props {
  templates: ScoringTemplate[];
  onApply: (name: string) => void;
  applying: string | null;
}

export default function TemplatesSection({ templates, onApply, applying }: Props) {
  if (templates.length === 0) return null;

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Templates</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {templates.map((tpl) => (
          <div key={tpl.name} className="border border-gray-200 rounded-lg p-4 bg-white">
            <h3 className="font-medium text-gray-900">{tpl.name}</h3>
            <p className="text-sm text-gray-500 mt-1">{tpl.description}</p>
            <p className="text-xs text-gray-400 mt-2">{tpl.rules.length} rules</p>
            <button
              onClick={() => onApply(tpl.name)}
              disabled={applying === tpl.name}
              className="mt-3 w-full px-3 py-1.5 text-sm text-indigo-600 border border-indigo-300 rounded-md hover:bg-indigo-50 disabled:opacity-50"
            >
              {applying === tpl.name ? "Applying..." : "Apply Template"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
