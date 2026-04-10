interface DeleteConfirmModalProps {
  count: number;
  entityLabel: string;
  warning?: string;
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
}

export default function DeleteConfirmModal({
  count,
  entityLabel,
  warning,
  onConfirm,
  onCancel,
  deleting,
}: DeleteConfirmModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-semibold text-gray-900">
          Delete {count} {entityLabel}{count !== 1 ? "s" : ""}?
        </h2>
        <p className="mb-4 text-sm text-gray-600">
          {warning ?? `This will permanently delete ${count} ${entityLabel}${count !== 1 ? "s" : ""}. This action cannot be undone.`}
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {deleting ? "Deleting…" : `Delete ${count} ${entityLabel}${count !== 1 ? "s" : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}
