/** Hack RND 2026 cashflow contract, revision 2.0.0.
 * v1 is implemented; v2 is the target specification, NOT a capability claim.
 * JSON: snake_case. Dates: company-local YYYY-MM-DD. Timestamps: UTC ISO 8601.
 * Money: RUB decimal major units, rounded to 2 places by server-side Decimal.
 * Probability: [0,1]; null means unavailable, never zero. IDs: opaque strings.
 * Runtime constraints and business invariants: ../ARCH_PLAN.md, sections 3 and 5.
 */
export type LocalDate = string;
export type UtcTimestamp = string;
export type EntityId = string;
export type Money = number;
export type Probability = number;
export type Direction = 'income' | 'expense';
export type RiskLevel = 'low' | 'medium' | 'critical';
export type Currency = 'RUB';

// Existing wire shapes. Never add required fields to these v1 interfaces.
export interface TransactionPoint { date: LocalDate; income: number; expense: number }
export interface ForecastRequest {
  /** Closing balance on the last history day. */
  initial_balance: Money;
  /** Client uses 30, 60 or 90; legacy backend defaults to 14. */
  horizon_days: number;
  history: TransactionPoint[];
}
export interface ForecastResult {
  predicted_dates: LocalDate[];
  predicted_income: Money[];
  predicted_expense: Money[];
  predicted_balance: Money[];
  cashflow_gap_detected: boolean;
  gap_dates: LocalDate[];
  minimum_expected_balance: Money;
  risk_level: RiskLevel;
}
export interface AdvisorRequest { forecast: ForecastResult; business_type: string }
export interface AdvisorResponse { analysis: string; recommendations: string[]; urgent_action_required: boolean }
export interface HealthResponse { status: string; app: string }
export interface ApiError {
  code: 'validation_error' | 'unauthorized' | 'forbidden' | 'not_found' | 'conflict'
    | 'insufficient_data' | 'too_large' | 'rate_limited' | 'unavailable' | 'internal_error';
  message: string;
  request_id: string;
  details: { field: string; message: string }[];
}
/** v1 may return the default FastAPI HTTPValidationError. */
export interface LegacyValidationError { detail: { loc: (string | number)[]; msg: string; type: string }[] }
export interface PageQuery { limit?: number; cursor?: string }
export interface DateRangeQuery { from_date?: LocalDate; to_date?: LocalDate }
export interface LoginRequest { email: string; password: string }
export interface SessionResponse {
  user: { id: EntityId; display_name: string; company_ids: EntityId[] };
  expires_at: UtcTimestamp;
}
export interface LogoutResponse { signed_out: boolean }
export interface CapabilitiesResponse {
  contract_version: string;
  features: ('imports' | 'categorization' | 'recurring' | 'forecast_v2' | 'probability'
    | 'events' | 'scenarios' | 'plan_actual' | 'evaluation' | 'integrations' | 'advice')[];
}
export interface Company {
  id: EntityId;
  name: string;
  business_type: string;
  currency: Currency;
  timezone: string;
  /** Last observed closing balance, not an estimated live bank balance. */
  closing_balance: Money | null;
  balance_date: LocalDate | null;
  data_revision: number;
}
export interface CompanyListResponse { items: Company[] }
export interface CompanyCreateRequest { name: string; business_type: string; timezone: string }
export type CategoryId = 'sales' | 'other_income' | 'payroll' | 'rent' | 'suppliers'
  | 'taxes' | 'loan' | 'fees' | 'equipment' | 'transfer' | 'other_expense' | 'uncategorized';
export interface Category { id: CategoryId; name: string; direction: Direction | 'both' }
export interface CategoryListResponse { items: Category[] }
export type IntegrationKind = 'invoice' | 'contract' | 'tax'
  | 'bank' | 'accounting' | 'cash_register' | 'marketplace' | 'registry';
export type SourceKind = 'statement' | 'manual' | IntegrationKind;
export interface SourceReference { kind: SourceKind; source_id: EntityId | null; external_id: string | null; label: string }
export interface StatementOperationInput {
  date: LocalDate;
  /** Positive absolute amount; direction carries the sign. */
  amount: Money;
  direction: Direction;
  counterparty_name: string;
  /** Anonymized dataset token, not required to match real INN syntax. */
  counterparty_inn: string;
  purpose: string;
  closing_balance: Money;
  external_id?: string;
}
export interface Transaction extends StatementOperationInput {
  id: EntityId;
  company_id: EntityId;
  category_id: CategoryId;
  category_method: 'rule' | 'model' | 'manual' | 'unknown';
  category_confidence: Probability | null;
  source: SourceReference;
  matched_event_id: EntityId | null;
}
export interface TransactionQuery extends PageQuery, DateRangeQuery { direction?: Direction; category_id?: CategoryId; search?: string }
export interface TransactionListResponse { items: Transaction[]; next_cursor: string | null; total: number }
export interface CategoryUpdateRequest { category_id: CategoryId }
export interface DailyActual {
  date: LocalDate;
  income: Money | null;
  expense: Money | null;
  closing_balance: Money | null;
  transaction_count: number;
  observation: 'observed' | 'confirmed_no_activity' | 'missing';
}
export interface CategoryTotal { category_id: CategoryId; direction: Direction; amount: Money; count: number }
export interface ActualsResponse { company_id: EntityId; data_revision: number; days: DailyActual[]; category_totals: CategoryTotal[] }
export interface ActualsQuery extends DateRangeQuery { granularity?: 'day' | 'week' }
/** Multipart field description; file is binary, column_mapping is JSON-serialized ColumnMapping. */
export interface StatementImportForm { file: string; format: 'csv' | 'xlsx' | '1c'; column_mapping: string; balance_policy: 'reject_conflicts' | 'use_last_row' }
export interface ColumnMapping {
  date: string; amount: string; direction: string; counterparty_name: string;
  counterparty_inn: string; purpose: string; closing_balance: string; external_id?: string;
}
export interface ImportIssue { row: number | null; field: string | null; code: string; message: string }
export interface ImportResponse {
  id: EntityId; company_id: EntityId; status: 'ready' | 'rejected';
  accepted_rows: number; duplicate_rows: number; rejected_rows: number;
  period_start: LocalDate | null; period_end: LocalDate | null; issues: ImportIssue[]; data_revision: number;
}
export interface RecurringPattern {
  id: EntityId; direction: Direction; category_id: CategoryId; counterparty_name: string;
  cadence: 'weekly' | 'monthly' | 'quarterly'; expected_amount: Money; next_date: LocalDate;
  confidence: Probability; sample_count: number; transaction_ids: EntityId[];
}
export interface RecurringListResponse { items: RecurringPattern[] }
export type EventKind = 'manual' | 'invoice' | 'contract' | 'tax' | 'loan' | 'payroll' | 'recurring';
export type EventStatus = 'planned' | 'partial' | 'paid' | 'overdue' | 'cancelled';
export interface PlannedEventInput {
  title: string; kind: EventKind; direction: Direction; amount: Money; due_date: LocalDate;
  category_id: CategoryId; counterparty_name: string | null;
  /** Chance of arrival on due_date, nullable when unknown. */
  on_time_probability: Probability | null;
  source: SourceReference;
}
export interface PlannedEvent extends PlannedEventInput {
  id: EntityId; company_id: EntityId; status: EventStatus; paid_amount: Money;
  matched_transaction_ids: EntityId[]; recurrence_id: EntityId | null; updated_at: UtcTimestamp;
}
export interface EventQuery extends PageQuery, DateRangeQuery { status?: EventStatus; kind?: EventKind }
export interface EventListResponse { items: PlannedEvent[]; next_cursor: string | null }
/** Full replacement of editable fields; reconciliation fields are server-owned. */
export interface EventUpdateRequest extends PlannedEventInput { cancelled: boolean; expected_data_revision?: number | null; }
export interface InvoiceInput {
  external_id: string; number: string; issued_date: LocalDate; due_date: LocalDate;
  amount: Money; direction: Direction; counterparty_name: string; category_id: CategoryId; on_time_probability: Probability | null;
}
export interface ContractInput {
  external_id: string; title: string; counterparty_name: string; direction: Direction;
  category_id: CategoryId; signed_date: LocalDate; payment_terms: string;
  schedule: { due_date: LocalDate; amount: Money; on_time_probability: Probability | null }[];
}
export interface TaxPaymentInput {
  external_id: string; title: string; due_date: LocalDate; amount: Money; period: string;
  authority_source_url: string | null; confirmed_by_user: boolean;
}
export interface ExternalEventsRequest { source: SourceReference; invoices: InvoiceInput[]; contracts: ContractInput[]; taxes: TaxPaymentInput[] }
export interface ExternalEventsResponse { created_events: PlannedEvent[]; updated_count: number; duplicate_count: number; data_revision: number }
export type ModelId = 'seasonal_naive' | 'weekday_mean' | 'ridge_calendar';
export interface CreateForecastRequest {
  as_of_date: LocalDate; horizon_days: 30 | 60 | 90;
  /** null uses last verified closing balance; non-null is explicit user override. */
  initial_balance: Money | null;
  include_planned_events: boolean; model: ModelId | 'auto'; expected_data_revision: number;
}
export interface ForecastDay {
  date: LocalDate; predicted_income: Money; predicted_expense: Money; predicted_balance: Money;
  balance_lower: Money | null; balance_upper: Money | null; gap_probability: Probability | null; planned_event_ids: EntityId[];
}
export interface CashGap {
  start_date: LocalDate; end_date: LocalDate; minimum_balance_date: LocalDate;
  shortage_amount: Money; probability: Probability | null; contributing_event_ids: EntityId[]; explanation: string;
}
export interface ForecastWarning {
  id: EntityId;
  code: 'cash_gap' | 'low_balance' | 'overdue_income' | 'missing_data' | 'short_history'
    | 'unreconciled_balance' | 'uncertain_probability' | 'outlier';
  severity: 'info' | 'warning' | 'critical'; title: string; message: string;
  date: LocalDate | null; amount: Money | null; event_id: EntityId | null;
}
export interface ForecastSummary {
  closing_balance: Money; end_balance: Money; total_income: Money; total_expense: Money;
  minimum_balance: Money; minimum_balance_date: LocalDate; first_gap_date: LocalDate | null; maximum_shortage: Money;
  /** P(any balance < 0 in horizon), not the maximum daily probability. */
  any_gap_probability: Probability | null;
  risk_level: RiskLevel;
}
export interface DataQuality { observed_days: number; missing_days: number; duplicate_rows: number; uncategorized_share: Probability; warnings: string[] }
export interface ForecastSnapshot {
  id: EntityId; company_id: EntityId; created_at: UtcTimestamp; as_of_date: LocalDate;
  horizon_days: 30 | 60 | 90; currency: Currency; data_revision: number; model: ModelId; model_version: string;
  evaluation_id: EntityId | null; probability_method: 'residual_block_bootstrap' | 'unavailable';
  interval_coverage: Probability | null; simulation_count: number; random_seed: number | null;
  summary: ForecastSummary; days: ForecastDay[]; gaps: CashGap[]; warnings: ForecastWarning[]; data_quality: DataQuality;
}
export interface ForecastUpdateRequest { changed_from_date: LocalDate; expected_data_revision: number }
export interface ForecastUpdateResponse { forecast: ForecastSnapshot; mode: 'incremental' | 'full_retrain'; recomputed_from_date: LocalDate; reason: string }
export interface DelayIncomeScenario { kind: 'delay_income'; event_id: EntityId; delay_days: number }
export interface RevenueDropScenario { kind: 'revenue_drop'; percent: number; from_date: LocalDate; to_date: LocalDate }
export interface ExtraExpenseScenario { kind: 'extra_expense'; amount: Money; date: LocalDate; category_id: CategoryId }
export interface FixedCostIncreaseScenario { kind: 'fixed_cost_increase'; percent: number; category_ids: CategoryId[]; from_date: LocalDate; to_date: LocalDate }
export type ScenarioAdjustment = DelayIncomeScenario | RevenueDropScenario | ExtraExpenseScenario | FixedCostIncreaseScenario;
export interface ScenarioRequest { name: string; adjustments: ScenarioAdjustment[] }
export interface ScenarioResponse {
  id: EntityId; base_forecast_id: EntityId; name: string; adjustments: ScenarioAdjustment[]; forecast: ForecastSnapshot;
  delta: { end_balance: Money; maximum_shortage: Money; first_gap_shift_days: number | null };
}
export interface PlanActualDay {
  date: LocalDate; planned_income: Money; actual_income: Money | null; planned_expense: Money; actual_expense: Money | null;
  planned_balance: Money; actual_balance: Money | null; net_flow_variance: Money | null; overdue_event_ids: EntityId[];
}
export interface PlanActualQuery extends DateRangeQuery { forecast_id: EntityId; granularity?: 'day' | 'week' }
export interface PlanActualResponse { forecast_id: EntityId; data_revision: number; days: PlanActualDay[]; overdue_events: PlannedEvent[]; updated_forecast_id: EntityId | null }
export interface EvaluationRequest { training_end_date: LocalDate; test_days: 30 | 60 | 90; folds: number; models: ModelId[] }
export interface ModelMetrics {
  model: ModelId; mae_income: Money; mae_expense: Money; mae_balance: Money; wape_cashflow: number | null;
  interval_empirical_coverage: Probability | null; gap_precision: Probability | null; gap_recall: Probability | null;
  average_warning_lead_days: number | null; gap_brier_score: number | null; evaluated_days: number;
}
export interface EvaluationResponse {
  id: EntityId; company_id: EntityId; created_at: UtcTimestamp; data_revision: number;
  split_method: 'rolling_origin'; test_days: number; folds: { train_end: LocalDate; test_start: LocalDate; test_end: LocalDate }[];
  metrics: ModelMetrics[]; selected_model: ModelId; selection_reason: string; limitations: string[];
}
export interface AdviceRequest { business_type: string }
export interface AdviceResponse {
  forecast_id: EntityId; mode: 'llm' | 'rules'; analysis: string;
  recommendations: { title: string; rationale: string; related_event_ids: EntityId[]; priority: 'high' | 'normal' }[];
  generated_at: UtcTimestamp;
}
export interface Integration {
  id: EntityId; kind: IntegrationKind; name: string;
  status: 'connected' | 'disconnected' | 'error' | 'not_configured'; last_sync_at: UtcTimestamp | null; last_error: string | null;
  supported_entities: ('transactions' | 'invoices' | 'contracts' | 'taxes' | 'loans' | 'payroll' | 'payment_orders' | 'counterparty_status')[];
}
export interface IntegrationListResponse { items: Integration[] }
export interface IntegrationSyncResponse { integration_id: EntityId; imported_count: number; data_revision: number; synced_at: UtcTimestamp }

/** Request/response pairs; operation IDs match the OpenAPI catalog. GET request fields are query parameters. */
export interface ApiOperations {
  health: { request: never; response: HealthResponse };
  forecastV1: { request: ForecastRequest; response: ForecastResult };
  advisorV1: { request: AdvisorRequest; response: AdvisorResponse };
  capabilities: { request: never; response: CapabilitiesResponse };
  login: { request: LoginRequest; response: SessionResponse };
  session: { request: never; response: SessionResponse };
  logout: { request: never; response: LogoutResponse };
  listCompanies: { request: never; response: CompanyListResponse };
  createCompany: { request: CompanyCreateRequest; response: Company };
  getCompany: { request: never; response: Company };
  categories: { request: never; response: CategoryListResponse };
  importStatement: { request: StatementImportForm; response: ImportResponse };
  listTransactions: { request: TransactionQuery; response: TransactionListResponse };
  updateCategory: { request: CategoryUpdateRequest; response: Transaction };
  actuals: { request: ActualsQuery; response: ActualsResponse };
  recurring: { request: never; response: RecurringListResponse };
  listEvents: { request: EventQuery; response: EventListResponse };
  createEvent: { request: PlannedEventInput; response: PlannedEvent };
  updateEvent: { request: EventUpdateRequest; response: PlannedEvent };
  importExternalEvents: { request: ExternalEventsRequest; response: ExternalEventsResponse };
  createForecast: { request: CreateForecastRequest; response: ForecastSnapshot };
  getForecast: { request: never; response: ForecastSnapshot };
  updateForecast: { request: ForecastUpdateRequest; response: ForecastUpdateResponse };
  scenario: { request: ScenarioRequest; response: ScenarioResponse };
  planActual: { request: PlanActualQuery; response: PlanActualResponse };
  evaluate: { request: EvaluationRequest; response: EvaluationResponse };
  getEvaluation: { request: never; response: EvaluationResponse };
  advice: { request: AdviceRequest; response: AdviceResponse };
  integrations: { request: never; response: IntegrationListResponse };
  syncIntegration: { request: never; response: IntegrationSyncResponse };
}
/** All company-scoped v2 resources require an authenticated company-owned session. */
export const API_ROUTES = {
  health: ['get', '/health'],
  forecastV1: ['post', '/api/v1/forecast'],
  advisorV1: ['post', '/api/v1/ai-advisor'],
  capabilities: ['get', '/api/v2/capabilities'],
  login: ['post', '/api/v2/auth/login'],
  session: ['get', '/api/v2/auth/session'],
  logout: ['post', '/api/v2/auth/logout'],
  listCompanies: ['get', '/api/v2/companies'],
  createCompany: ['post', '/api/v2/companies'],
  getCompany: ['get', '/api/v2/companies/{company_id}'],
  categories: ['get', '/api/v2/categories'],
  importStatement: ['post', '/api/v2/companies/{company_id}/imports'],
  listTransactions: ['get', '/api/v2/companies/{company_id}/transactions'],
  updateCategory: ['patch', '/api/v2/companies/{company_id}/transactions/{transaction_id}/category'],
  actuals: ['get', '/api/v2/companies/{company_id}/actuals'],
  recurring: ['get', '/api/v2/companies/{company_id}/recurring'],
  listEvents: ['get', '/api/v2/companies/{company_id}/events'],
  createEvent: ['post', '/api/v2/companies/{company_id}/events'],
  updateEvent: ['put', '/api/v2/companies/{company_id}/events/{event_id}'],
  importExternalEvents: ['post', '/api/v2/companies/{company_id}/external-events'],
  createForecast: ['post', '/api/v2/companies/{company_id}/forecasts'],
  getForecast: ['get', '/api/v2/companies/{company_id}/forecasts/{forecast_id}'],
  updateForecast: ['post', '/api/v2/companies/{company_id}/forecasts/{forecast_id}/updates'],
  scenario: ['post', '/api/v2/companies/{company_id}/forecasts/{forecast_id}/scenarios'],
  planActual: ['get', '/api/v2/companies/{company_id}/plan-actual'],
  evaluate: ['post', '/api/v2/companies/{company_id}/evaluations'],
  getEvaluation: ['get', '/api/v2/companies/{company_id}/evaluations/{evaluation_id}'],
  advice: ['post', '/api/v2/companies/{company_id}/forecasts/{forecast_id}/advice'],
  integrations: ['get', '/api/v2/companies/{company_id}/integrations'],
  syncIntegration: ['post', '/api/v2/companies/{company_id}/integrations/{integration_id}/sync'],
} as const satisfies Record<keyof ApiOperations, readonly ['get' | 'post' | 'put' | 'patch', string]>;
