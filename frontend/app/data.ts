export const states = {
  'Huella humana': { label: 'Huella humana', rgb: [255, 61, 102], action: 'Prevenir. Controlar la actividad sospechosa, proteger la cuenca y restaurar.' },
  'Alerta temprana': { label: 'Alerta temprana', rgb: [211, 98, 244], action: 'Actuar temprano para proteger la cuenca.' },
  'Sin explicar': { label: 'Sin explicar', rgb: [255, 214, 71], action: 'Revisar la pérdida de agua. La evidencia disponible aún es insuficiente para atribuirla.' },
  'Causa climatica': { label: 'Causa climática', rgb: [255, 151, 52], action: 'Adaptarse con cosecha de agua, reservorios y planes de sequía.' },
  Intacto: { label: 'Intacto', rgb: [66, 226, 157], action: 'Mantener el seguimiento.' },
} as const;

export type State = keyof typeof states;
export type Area = 'subcuenca_local' | 'cuenca_aporte';
export const areaNames: Record<Area, string> = { subcuenca_local: 'Cerca de la laguna', cuenca_aporte: 'Toda la cuenca de aporte' };
export const reviewOutcomes = {
  'En revision': 'En revisión',
  'Confirmado en campo': 'Confirmado en campo',
  'Falso positivo': 'Falso positivo',
  'Requiere mas datos': 'Requiere más datos',
};

export interface Suspect {
  suspect: string;
  label: string;
  evidence: string;
  onset: number | null;
  precedes: boolean;
  r2: number;
  together_with?: string[];
}

export interface WaterBody {
  body_id: string;
  name: string;
  lat: number;
  lon: number;
  control_id?: string;
  department?: string;
  state: State;
  confidence: string;
  years: number[];
  observed: (number | null)[];
  expected: (number | null)[];
  oni: number[];
  baseline_end: number;
  baseline_mean_ha: number;
  climate_r2: number;
  climate_share?: number | null;
  data_quality?: { level: string; r_jrc?: number | null; interpolated_years?: number[] };
  n_pass: number;
  trend: { change_pct: number; sen_ha_per_year: number; p: number; p_holm: number };
  tests: Record<string, { pass: boolean; detail: string }>;
  decomposition_ha: Record<string, number>;
  backtest: unknown;
  suspects: Suspect[];
  ha?: number;
}

export interface Place {
  name: string;
  detail: string;
  kind: string;
  dist_km: number;
  lat: number;
  lon: number;
  osm: string;
}

export interface BodyDetail {
  result: WaterBody;
  places: Place[];
  imageYears: { year: number; mask: boolean }[];
  context: { years: [number, number]; window_km: number; changes_ha: Record<string, number>;
    legend: Record<string, { label: string; color: string }> } | null;
  water: { area: Area; year: number; suspect: string; value: number }[];
}

export interface Snapshot {
  results: WaterBody[];
  national: WaterBody[];
  artificial: { year: number; points: { tipo: string; ha: number; lat: number; lon: number }[] } | null;
  sample: boolean;
  liveMap: boolean;
}

export type Row = Record<string, string | number | null>;
export interface Audit {
  available: boolean;
  runs: Row[];
  reviews: Row[];
  alerts: Row[];
}

export interface Weekly {
  history: Row[];
  report: {
    week_end: string;
    checked_at: string;
    notified: string;
    rows: {
      body_id: string;
      name: string;
      state: State;
      alerta: boolean;
      areas: Record<string, { focos: number; normal: number; alerta: boolean }>;
    }[];
  } | null;
}

export const number = (value: number, digits = 0) => new Intl.NumberFormat('es-BO', {
  maximumFractionDigits: digits,
}).format(value);
export const signed = (value: number, digits = 0) => `${value > 0 ? '+' : ''}${number(value, digits)}`;
export const imageUrl = (folder: 'img' | 'context', filename: string) => `/api/images/${folder}/${filename}.png`;

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/${path}`, { cache: 'no-store', ...options });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.message ?? `La API respondió con el código ${response.status}.`);
  }
  return response.json();
}

export function downloadCsv(rows: Row[]) {
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const cell = (value: string | number | null) => '"' + String(value ?? '').replaceAll('"', '""') + '"';
  const csv = [columns.map(cell).join(','), ...rows.map((row) => columns.map((key) => cell(row[key])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'uma_monitoreo.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
