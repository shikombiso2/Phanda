import type { ListingType } from "../types/api";
import { SearchIcon } from "./icons";

export interface ListingFilterValues {
  q: string;
  type: ListingType | "";
  location: string;
  remote: boolean;
}

const TYPE_OPTIONS: { value: ListingType | ""; label: string }[] = [
  { value: "", label: "Any type" },
  { value: "job", label: "Job" },
  { value: "internship", label: "Internship" },
  { value: "learnership", label: "Learnership" },
  { value: "apprenticeship", label: "Apprenticeship" },
  { value: "bursary", label: "Bursary" },
];

export function ListingFilters({
  values,
  onChange,
}: {
  values: ListingFilterValues;
  onChange: (next: ListingFilterValues) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/40" />
        <input
          value={values.q}
          onChange={(e) => onChange({ ...values, q: e.target.value })}
          placeholder="Search job titles, companies..."
          aria-label="Search listings"
          className="w-full rounded-[10px] border border-hairline py-3 pl-10 pr-4 font-body text-[15px] text-ink outline-none placeholder:text-ink/40 focus:border-phanda-green"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <select
          value={values.type}
          onChange={(e) => onChange({ ...values, type: e.target.value as ListingType | "" })}
          aria-label="Filter by type"
          className="rounded-[10px] border border-hairline bg-paper px-3 py-2 font-body text-sm text-ink outline-none focus:border-phanda-green"
        >
          {TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <input
          value={values.location}
          onChange={(e) => onChange({ ...values, location: e.target.value })}
          placeholder="Location"
          aria-label="Filter by location"
          className="w-32 rounded-[10px] border border-hairline px-3 py-2 font-body text-sm text-ink outline-none placeholder:text-ink/40 focus:border-phanda-green sm:w-44"
        />

        <label className="flex items-center gap-2 rounded-[10px] border border-hairline px-3 py-2 font-body text-sm text-ink">
          <input
            type="checkbox"
            className="h-4 w-4 accent-phanda-green"
            checked={values.remote}
            onChange={(e) => onChange({ ...values, remote: e.target.checked })}
          />
          Remote only
        </label>
      </div>
    </div>
  );
}
