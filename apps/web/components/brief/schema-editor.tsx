"use client";
import { fieldTypes, type Requirement } from "@/lib/api/types";
import { FilterEditor } from "./filter-editor";
export function SchemaEditor({
  value,
  onChange,
}: {
  value: Requirement;
  onChange: (value: Requirement) => void;
}) {
  const set = <K extends keyof Requirement>(key: K, next: Requirement[K]) =>
    onChange({ ...value, [key]: next });
  return (
    <>
      <div className="form-grid">
        <label>
          Dataset objective
          <input
            required
            minLength={3}
            value={value.goal}
            onChange={(e) => set("goal", e.target.value)}
          />
        </label>
        <label>
          Entity type
          <input
            required
            value={value.entity_type}
            onChange={(e) => set("entity_type", e.target.value)}
          />
        </label>
        <label>
          Geography <small>Comma separated</small>
          <input
            value={value.geography.join(", ")}
            onChange={(e) =>
              set(
                "geography",
                e.target.value.split(",").map((s) => s.trim()),
              )
            }
          />
        </label>
        <label>
          Record limit
          <input
            type="number"
            required
            min={1}
            max={500}
            value={value.limit}
            onChange={(e) => set("limit", Number(e.target.value))}
          />
        </label>
        <label>
          From
          <input
            type="date"
            value={value.time_window?.start || ""}
            onChange={(e) =>
              set("time_window", {
                start: e.target.value || null,
                end: value.time_window?.end || null,
              })
            }
          />
        </label>
        <label>
          Through
          <input
            type="date"
            value={value.time_window?.end || ""}
            onChange={(e) =>
              set("time_window", {
                end: e.target.value || null,
                start: value.time_window?.start || null,
              })
            }
          />
        </label>
      </div>
      <section className="ruled-section">
        <div className="section-heading">
          <div>
            <h2>Proposed fields</h2>
            <p className="muted">
              Edit the structure before any source is collected.
            </p>
          </div>
          <button
            type="button"
            className="button small secondary"
            onClick={() =>
              set("fields", [
                ...value.fields,
                {
                  key: `new_field_${value.fields.length + 1}`,
                  label: "New field",
                  data_type: "text",
                  required: false,
                  origin: "user",
                  description: null,
                },
              ])
            }
          >
            + Add field
          </button>
        </div>
        <div className="schema-rows">
          {value.fields.map((field, index) => (
            <div className="schema-row" key={index}>
              <div className="schema-number mono">
                {String(index + 1).padStart(2, "0")}
              </div>
              <div className="schema-main">
                <div className="schema-inputs">
                  <label>
                    Field key
                    <input
                      pattern="[a-z][a-z0-9_]{1,63}"
                      required
                      value={field.key}
                      onChange={(e) =>
                        onChange({
                          ...value,
                          fields: value.fields.map((f, i) =>
                            i === index ? { ...f, key: e.target.value } : f,
                          ),
                          filters: value.filters.map((f) =>
                            f.field_key === field.key
                              ? { ...f, field_key: e.target.value }
                              : f,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Label
                    <input
                      required
                      value={field.label}
                      onChange={(e) =>
                        set(
                          "fields",
                          value.fields.map((f, i) =>
                            i === index ? { ...f, label: e.target.value } : f,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    Type
                    <select
                      value={field.data_type}
                      onChange={(e) =>
                        set(
                          "fields",
                          value.fields.map((f, i) =>
                            i === index
                              ? {
                                  ...f,
                                  data_type: e.target
                                    .value as typeof field.data_type,
                                }
                              : f,
                          ),
                        )
                      }
                    >
                      {fieldTypes.map((type) => (
                        <option key={type}>{type}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <details>
                  <summary>Field description & origin</summary>
                  <label>
                    Description
                    <input
                      value={field.description || ""}
                      onChange={(e) =>
                        set(
                          "fields",
                          value.fields.map((f, i) =>
                            i === index
                              ? { ...f, description: e.target.value || null }
                              : f,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    Origin
                    <select
                      value={field.origin}
                      onChange={(e) =>
                        set(
                          "fields",
                          value.fields.map((f, i) =>
                            i === index
                              ? {
                                  ...f,
                                  origin: e.target.value as typeof field.origin,
                                }
                              : f,
                          ),
                        )
                      }
                    >
                      <option value="user">You</option>
                      <option value="ai_inferred">AI inferred</option>
                    </select>
                  </label>
                </details>
              </div>
              <div className="schema-flags">
                <span
                  className={
                    field.origin === "ai_inferred" ? "tag copper" : "tag"
                  }
                >
                  {field.origin === "ai_inferred" ? "AI inferred" : "You"}
                </span>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={field.required}
                    onChange={(e) =>
                      set(
                        "fields",
                        value.fields.map((f, i) =>
                          i === index
                            ? { ...f, required: e.target.checked }
                            : f,
                        ),
                      )
                    }
                  />
                  Required
                </label>
                <button
                  type="button"
                  className="text-button"
                  disabled={value.fields.length === 1}
                  onClick={() =>
                    onChange({
                      ...value,
                      fields: value.fields.filter((_, i) => i !== index),
                      filters: value.filters.filter(
                        (f) => f.field_key !== field.key,
                      ),
                    })
                  }
                  aria-label={`Remove ${field.label}`}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="ruled-section">
        <div className="section-heading">
          <h2>Filters & source scope</h2>
          <button
            type="button"
            className="button small secondary"
            onClick={() =>
              set("filters", [
                ...value.filters,
                { field_key: value.fields[0].key, operator: "eq", value: "" },
              ])
            }
          >
            + Add filter
          </button>
        </div>
        {value.filters.map((filter, index) => (
          <FilterEditor
            key={index}
            filter={filter}
            fields={value.fields}
            onChange={(filter) =>
              set(
                "filters",
                value.filters.map((f, i) => (i === index ? filter : f)),
              )
            }
            onRemove={() =>
              set(
                "filters",
                value.filters.filter((_, i) => i !== index),
              )
            }
          />
        ))}
        {!value.filters.length && (
          <p className="muted">
            No field filters. All records within the confirmed scope are
            eligible.
          </p>
        )}
        <label>
          Source hints <small>One per line</small>
          <textarea
            rows={3}
            value={value.source_hints.join("\n")}
            onChange={(e) => set("source_hints", e.target.value.split("\n"))}
          />
        </label>
        {value.refresh?.enabled && (
          <div className="notice">
            The compiled brief requests {value.refresh.frequency} refresh. This
            backend supports manual runs; no schedule will be activated.
          </div>
        )}
      </section>
    </>
  );
}
