"use client";

interface Props {
  release: string;
  docType: string;
  k: number;
  onChange: (field: string, value: string | number) => void;
}

const RELEASES = ["All releases", "ReleaseA", "ReleaseB"];
const DOC_TYPES = ["All types", "defect", "test_execution", "metadata", "comparison"];

export default function FilterBar({ release, docType, k, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-3 text-sm">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-500 font-medium">Release</label>
        <select
          value={release}
          onChange={(e) => onChange("release", e.target.value)}
          className="rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {RELEASES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-500 font-medium">Document type</label>
        <select
          value={docType}
          onChange={(e) => onChange("docType", e.target.value)}
          className="rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {DOC_TYPES.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs text-gray-500 font-medium">Results (k)</label>
        <input
          type="number"
          min={1}
          max={20}
          value={k}
          onChange={(e) => onChange("k", parseInt(e.target.value) || 8)}
          className="w-16 rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
    </div>
  );
}
