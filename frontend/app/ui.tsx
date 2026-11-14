import type { CSSProperties } from 'react';
import { Activity, CloudSunRain, Footprints, ShieldCheck, Siren } from 'lucide-react';
import { states, type Row, type State } from './data';

const icons = { 'Huella humana': Footprints, 'Alerta temprana': Siren, 'Sin explicar': Activity,
  'Causa climatica': CloudSunRain, Intacto: ShieldCheck };

export function Status({ state }: { state: State }) {
  const config = states[state];
  const Icon = icons[state];
  return <span className="status" style={{ '--status': `rgb(${config.rgb.join(',')})` } as CSSProperties}>
    <Icon size={15} aria-hidden="true" /> {config.label}
  </span>;
}

export function DataTable({ rows, empty = 'Sin registros.' }: { rows: Row[]; empty?: string }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  const columns = Object.keys(rows[0]);
  return <div className="table-wrap"><table>
    <thead><tr>{columns.map((column) => <th key={column} scope="col">{column.replaceAll('_', ' ')}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}</tr>)}</tbody>
  </table></div>;
}
