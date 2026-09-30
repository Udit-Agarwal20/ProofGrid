"use client";
import type { Field, Filter, Json } from "@/lib/api/types";
export function FilterEditor({
  filter,
  fields,
  onChange,
  onRemove,
}: {
  filter: Filter;
  fields: Field[];
  onChange: (filter: Filter) => void;
  onRemove: () => void;
}) {
  const field = fields.find((f) => f.key === filter.field_key);
  const object =
    filter.value &&
    typeof filter.value === "object" &&
    !Array.isArray(filter.value)
      ? filter.value
      : null;
  const money = field?.data_type === "money";
  const display = Array.isArray(filter.value)
    ? filter.value
        .map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v)))
        .join(", ")
    : object
      ? String(object.amount ?? object.value ?? JSON.stringify(object))
      : String(filter.value ?? "");
  function changeValue(text: string) {
    let value: Json = text;
    if (filter.operator === "in") value = text.split(",").map((v) => v.trim());
    else if (money)
      value = { amount: text, currency: object?.currency || "USD" };
    else if (field?.data_type === "boolean") value = text === "true";
    else if (object && "value" in object) value = { ...object, value: text };
    onChange({ ...filter, value });
  }
  return (
    <div className="filter-edit">
      <label>
        Field
        <select
          value={filter.field_key}
          onChange={(e) =>
            onChange({ ...filter, field_key: e.target.value, value: "" })
          }
        >
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
          value={filter.operator}
          onChange={(e) =>
            onChange({
              ...filter,
              operator: e.target.value as Filter["operator"],
            })
          }
        >
          {["eq", "neq", "gt", "gte", "lt", "lte", "in", "contains"].map(
            (op) => (
              <option key={op}>{op}</option>
            ),
          )}
        </select>
      </label>
      <div className="filter-value">
        <label>
          {money ? "Amount" : "Value"}
          {field?.data_type === "boolean" ? (
            <select
              value={String(filter.value)}
              onChange={(e) => changeValue(e.target.value)}
            >
              <option value="true">True</option>
              <option value="false">False</option>
            </select>
          ) : (
            <input
              value={display}
              onChange={(e) => changeValue(e.target.value)}
            />
          )}
        </label>
        {money && (
          <label>
            Currency
            <input
              aria-label="Filter currency"
              maxLength={3}
              pattern="[A-Z]{3}"
              value={String(object?.currency || "USD")}
              onChange={(e) =>
                onChange({
                  ...filter,
                  value: {
                    amount: object?.amount ?? display,
                    currency: e.target.value.toUpperCase(),
                  },
                })
              }
            />
          </label>
        )}
      </div>
      <button type="button" className="text-button" onClick={onRemove}>
        Remove
      </button>
    </div>
  );
}
