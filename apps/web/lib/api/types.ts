export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };
export type Resource<T> = { id: string; data: T };
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export const trustStates = [
  "VERIFIED",
  "SUPPORTED",
  "SINGLE_SOURCE",
  "CONFLICTING",
  "NEEDS_REVIEW",
  "MISSING",
] as const;
export type TrustStatus = (typeof trustStates)[number];
export const fieldTypes = [
  "text",
  "url",
  "money",
  "date",
  "location",
  "entity_ref",
  "entity_list",
  "number",
  "boolean",
] as const;
export type Field = {
  key: string;
  label: string;
  data_type: (typeof fieldTypes)[number];
  required: boolean;
  origin: "user" | "ai_inferred";
  description: string | null;
};
export type Filter = {
  field_key: string;
  operator: "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "in" | "contains";
  value: Json;
};
export type Requirement = {
  version: "1.0";
  entity_type: string;
  goal: string;
  fields: Field[];
  filters: Filter[];
  geography: string[];
  time_window: { start: string | null; end: string | null } | null;
  source_hints: string[];
  limit: number;
  refresh: {
    frequency: "daily" | "weekly" | "monthly" | "manual";
    enabled: boolean;
  } | null;
};
export type TrustContract = {
  version: "1.0";
  require_evidence_anchor: boolean;
  minimum_independent_sources: number;
  prefer_first_party: boolean;
  allow_secondary_sources: boolean;
  allow_single_source_output: boolean;
  preserve_conflicts: boolean;
  strict_required_fields: boolean;
  max_source_age_days: number | null;
  max_search_queries: number;
  max_pages: number;
  max_browser_pages: number;
  max_llm_calls: number;
  max_run_seconds: number;
  max_estimated_cost_usd: string;
};
export type Schema = {
  id: string;
  version: string;
  entity_type: string;
  fields: Field[];
  schema_hash: string;
};
export type Ambiguity = {
  code: string;
  message: string;
  blocking: boolean;
  severity: string;
  possible_interpretations: string[];
};
export type Assumption = {
  code: string;
  description: string;
  affected_field: string | null;
  reversible: boolean;
};
export type Question = {
  question_id: string;
  question: string;
  options: string[];
  impact_summary: string;
};
export type CompilerMetadata = {
  provider_name: string;
  model_name: string;
  reference_date: string;
  compiled_at: string;
};
type OutcomeBase = {
  ambiguities: Ambiguity[];
  assumptions: Assumption[];
  clarification_questions: Question[];
  metadata: CompilerMetadata;
  requires_confirmation: boolean;
};
export type Compiled = OutcomeBase & {
  status: "COMPILED";
  requirement_spec: Requirement;
  dataset_schema_proposal: Schema;
  trust_contract_proposal: TrustContract;
};
export type Clarification = OutcomeBase & {
  status: "NEEDS_CLARIFICATION";
  partial_context: {
    raw_prompt: string;
    detected_entity_type: string | null;
    detected_geography: string[];
    candidate_fields: string[];
  } | null;
};
export type CompileResponse = {
  requirement_id: string | null;
  outcome: Compiled | Clarification;
};
export type RequirementData = {
  status: string;
  original_prompt: string;
  requirement_spec: Requirement;
  schema: Schema;
  trust_contract: TrustContract;
  version: number;
  confirmed: boolean;
  compiler_metadata: {
    compiler: CompilerMetadata;
    ambiguities: Ambiguity[];
    assumptions: Assumption[];
  };
};
export type PlanNode = {
  id: string;
  operator: string;
  depends_on: string[];
  params: Record<string, Json>;
  critical: boolean;
  constraints: { timeout_seconds: number; max_retries: number };
};
export type Plan = {
  version: string;
  nodes: PlanNode[];
  rationale: string[];
  expected_pages: number;
  expected_browser_pages: number;
  expected_llm_calls: number;
};
export type PlanData = {
  workflow_version_id: string;
  version: number;
  plan: Plan;
  validated: boolean;
  schema_hash: string;
};
export type Workflow = {
  id: string;
  name: string;
  requirement_id: string;
  status: string;
};
export type RunStatus =
  | "CREATED"
  | "QUEUED"
  | "RUNNING"
  | "PARTIAL"
  | "COMPLETED"
  | "FAILED"
  | "CANCEL_REQUESTED"
  | "CANCELLED";
export const terminalRuns: RunStatus[] = [
  "PARTIAL",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];
export type Step = {
  id: string;
  node_id: string;
  operator: string;
  status: string;
  attempt: number;
  error_code: string | null;
};
export type RunData = {
  status: RunStatus;
  mode: string;
  metrics: Record<string, Json>;
  started_at: string | null;
  finished_at: string | null;
  steps: Step[];
};
export type RunSummary = {
  id: string;
  status: RunStatus;
  mode: string;
  metrics: Record<string, Json>;
  created_at: string;
};
export type RunEvent = {
  sequence: number;
  event: string;
  data: Record<string, Json>;
};
export type Dataset = { id: string; name: string; workflow_id: string };
export type Version = {
  id: string;
  version: number;
  record_count: number;
  status: string;
  workflow_run_id: string;
  created_at: string;
};
export type DatasetData = {
  name: string;
  workflow_id: string;
  latest_version: Version | null;
};
export type VersionData = {
  version: number;
  record_count: number;
  schema: Schema;
  status: string;
};
export type RecordRow = {
  entity_id: string;
  values: Record<string, Json>;
  trust: Record<string, TrustStatus>;
  row_hash: string;
};
export type Claim = {
  id: string;
  raw_value: Json;
  normalized_value: Json;
  source_id: string;
  source_url: string;
  raw_document_id: string;
  content_hash: string;
  retrieved_at: string;
  extraction_method: string;
  validation_flags: string[];
  evidence: {
    type: string;
    locator: Record<string, Json>;
    quote: string | null;
    verification_status: string;
  };
  acquisition: Record<string, Json>;
};
export type Proof = {
  dataset_version_id: string;
  entity_id: string;
  field_key: string;
  canonical_value: Json;
  trust_status: TrustStatus;
  resolution: Record<string, Json>;
  claims: Claim[];
  conflict: {
    id: string;
    status: string;
    details: Record<string, Json>;
    selected_claim_id: string | null;
  } | null;
};
export type ReviewItem =
  | {
      kind: "conflict";
      id: string;
      entity_id: string;
      field_key: string;
      dataset_version_id: string;
      details: Record<string, Json>;
    }
  | {
      kind: "entity_match";
      id: string;
      left: string;
      right: string;
      signals: Record<string, Json>;
      reason: Record<string, Json>;
    };
export type Diff = {
  entity_id: string;
  state: "ADDED" | "MISSING_LATEST" | "CHANGED" | "UNCHANGED";
  before: RecordRow | null;
  after: RecordRow | null;
  fields: { field: string; changes: string[] }[];
};
