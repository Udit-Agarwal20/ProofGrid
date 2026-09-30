"use client";
import { useState } from "react";
import type { Field, RecordRow, TrustStatus } from "@/lib/api/types";
import { trustStates } from "@/lib/api/types";
import { formatValue, trustInfo } from "@/lib/format";
import { TrustBadge, Icon } from "@/components/ui/primitives";
export type GridControls = {
  search: string;
  sort: string;
  trust: string;
  trustField: string;
  field: string;
  operator: string;
  value: string;
};
export function GridToolbar({
  fields,
  controls,
  setControls,
}: {
  fields: Field[];
  controls: GridControls;
  setControls: (value: GridControls) => void;
}) {
  const [filters, setFilters] = useState(false);
  return (
    <>
      <div className="grid-toolbar">
        <label className="search-field">
          <Icon name="search" />
          <input
            aria-label="Search dataset"
            placeholder="Search this dataset…"
            maxLength={300}
            value={controls.search}
            onChange={(e) =>
              setControls({ ...controls, search: e.target.value })
            }
          />
        </label>
        <label className="inline-label">
          Trust
          <select
            aria-label="Trust status"
            value={controls.trust}
            onChange={(e) =>
              setControls({
                ...controls,
                trust: e.target.value,
                trustField: controls.trustField || fields[0]?.key || "",
              })
            }
          >
            <option value="">All states</option>
            {trustStates.map((state) => (
              <option key={state} value={state}>
                {trustInfo[state].label}
              </option>
            ))}
          </select>
        </label>
        {controls.trust && (
          <select
            aria-label="Field for trust filter"
            value={controls.trustField}
            onChange={(e) =>
              setControls({ ...controls, trustField: e.target.value })
            }
          >
            {fields.map((field) => (
              <option key={field.key} value={field.key}>
                {field.label}
              </option>
            ))}
          </select>
        )}
        <button
          className="button secondary small"
          aria-expanded={filters}
          onClick={() => setFilters((v) => !v)}
        >
          Field filter{controls.value ? " · 1" : ""}
        </button>
      </div>
      {filters && (
        <div className="structured-filter">
          <label>
            Field
            <select
              value={controls.field}
              onChange={(e) =>
                setControls({ ...controls, field: e.target.value })
              }
            >
              <option value="">Choose field</option>
              {fields.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Operator
            <select
              value={controls.operator}
              onChange={(e) =>
                setControls({ ...controls, operator: e.target.value })
              }
            >
              {["eq", "neq", "contains", "gt", "gte", "lt", "lte", "in"].map(
                (op) => (
                  <option key={op}>{op}</option>
                ),
              )}
            </select>
          </label>
          <label>
            Value
            <input
              placeholder="Value; comma separated for in"
              value={controls.value}
              onChange={(e) =>
                setControls({ ...controls, value: e.target.value })
              }
            />
          </label>
          <button
            className="text-button"
            onClick={() => setControls({ ...controls, field: "", value: "" })}
          >
            Clear filter
          </button>
        </div>
      )}
    </>
  );
}
export function DataGrid({
  fields,
  rows,
  offset,
  sort,
  onSort,
  onProof,
}: {
  fields: Field[];
  rows: RecordRow[];
  offset: number;
  sort: string;
  onSort: (sort: string) => void;
  onProof: (row: RecordRow, field: Field) => void;
}) {
  const [density, setDensity] = useState<"comfortable" | "compact">(
    "comfortable",
  );
  const [widths, setWidths] = useState<Record<string, number>>({});
  const [hidden, setHidden] = useState<string[]>([]);
  const visible = fields.filter(
    (f, index) => index === 0 || !hidden.includes(f.key),
  );
  function moveCell(
    event: React.KeyboardEvent<HTMLButtonElement>,
    row: number,
    column: number,
  ) {
    const delta: Record<string, [number, number]> = {
      ArrowRight: [0, 1],
      ArrowLeft: [0, -1],
      ArrowDown: [1, 0],
      ArrowUp: [-1, 0],
    };
    if (event.key.toLowerCase() === "e") {
      event.preventDefault();
      onProof(rows[row], visible[column]);
      return;
    }
    if (delta[event.key]) {
      event.preventDefault();
      const [r, c] = delta[event.key];
      document
        .getElementById(
          `cell-${Math.max(0, Math.min(rows.length - 1, row + r))}-${Math.max(0, Math.min(visible.length - 1, column + c))}`,
        )
        ?.focus();
    }
  }
  return (
    <>
      <div className="grid-options">
        <span className="hint">
          Select a value to inspect its proof. <kbd>Enter</kbd> / <kbd>E</kbd>
        </span>
        <div className="actions">
          <label className="inline-label">
            Density
            <select
              value={density}
              onChange={(e) => setDensity(e.target.value as typeof density)}
            >
              <option value="comfortable">Comfortable</option>
              <option value="compact">Compact</option>
            </select>
          </label>
          <details className="columns-menu">
            <summary>Columns</summary>
            <div>
              {fields.map((field, index) => (
                <label key={field.key} className="checkbox">
                  <input
                    type="checkbox"
                    disabled={index === 0}
                    checked={!hidden.includes(field.key)}
                    onChange={(e) =>
                      setHidden(
                        e.target.checked
                          ? hidden.filter((k) => k !== field.key)
                          : [...hidden, field.key],
                      )
                    }
                  />
                  {field.label}
                </label>
              ))}
            </div>
          </details>
        </div>
      </div>
      <div
        className={`table-scroll density-${density}`}
        tabIndex={0}
        role="region"
        aria-label="Dataset grid, scroll horizontally for additional fields"
      >
        <table className="data-grid">
          <caption className="sr-only">
            Version-pinned records with field-level trust. Select any value to
            inspect evidence.
          </caption>
          <colgroup>
            <col style={{ width: 48 }} />
            {visible.map((field) => (
              <col
                key={field.key}
                style={{
                  width:
                    widths[field.key] ||
                    (field.data_type === "entity_list" ? 240 : 210),
                }}
              />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className="row-index">
                #
              </th>
              {visible.map((field, index) => (
                <th
                  key={field.key}
                  scope="col"
                  className={index === 0 ? "frozen" : ""}
                  aria-sort={
                    sort.startsWith(field.key + ":")
                      ? sort.endsWith("asc")
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button
                    className="column-sort"
                    onClick={() =>
                      onSort(
                        `${field.key}:${sort === `${field.key}:asc` ? "desc" : "asc"}`,
                      )
                    }
                  >
                    <span>
                      {field.label}
                      <small className="mono">{field.data_type}</small>
                    </span>
                    <span aria-hidden="true">
                      {sort.startsWith(field.key + ":")
                        ? sort.endsWith("asc")
                          ? "↑"
                          : "↓"
                        : "↕"}
                    </span>
                  </button>
                  <input
                    className="column-resize"
                    type="range"
                    min={150}
                    max={500}
                    step={10}
                    value={
                      widths[field.key] ||
                      (field.data_type === "entity_list" ? 240 : 210)
                    }
                    onChange={(e) =>
                      setWidths((w) => ({
                        ...w,
                        [field.key]: Number(e.target.value),
                      }))
                    }
                    aria-label={`Width of ${field.label}`}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={row.entity_id}>
                <th scope="row" className="row-index mono">
                  {offset + rowIndex + 1}
                </th>
                {visible.map((field, index) => {
                  const status: TrustStatus = row.trust[field.key] || "MISSING";
                  return (
                    <td
                      className={`${index === 0 ? "frozen" : ""} cell-${status.toLowerCase()}`}
                      key={field.key}
                    >
                      <button
                        id={`cell-${rowIndex}-${index}`}
                        className="proof-cell"
                        onClick={() => onProof(row, field)}
                        onKeyDown={(e) => moveCell(e, rowIndex, index)}
                        aria-label={`${field.label}: ${formatValue(row.values[field.key])}. ${trustInfo[status].label}. Inspect evidence.`}
                      >
                        <span
                          className={`cell-value ${field.data_type === "money" || field.data_type === "date" ? "mono" : ""}`}
                        >
                          {formatValue(row.values[field.key])}
                        </span>
                        <TrustBadge compact status={status} />
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mobile-records">
        {rows.map((row) => (
          <article key={row.entity_id}>
            <h3>{formatValue(row.values[visible[0]?.key])}</h3>
            {visible.map((field) => (
              <button key={field.key} onClick={() => onProof(row, field)}>
                <span>
                  {field.label}
                  <strong>{formatValue(row.values[field.key])}</strong>
                </span>
                <TrustBadge
                  compact
                  status={row.trust[field.key] || "MISSING"}
                />
              </button>
            ))}
          </article>
        ))}
      </div>
    </>
  );
}
