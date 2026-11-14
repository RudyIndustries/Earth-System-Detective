'use client';

import { ArrowUpRight, Droplets, Flame, Footprints, Gauge, ScanSearch, TrendingDown } from 'lucide-react';
import { firstSuspect, humanEvidenceStates, number, signed, states, visibleStates,
  type Method, type Snapshot, type State, type WaterBody, type Weekly } from './data';
import { Status } from './ui';

const color = (state: State) => `rgb(${states[state].rgb.join(',')})`;
const lossColors: Record<string, string> = {
  'Lluvia menos evaporacion': '#ffa26b', 'El Nino': '#ffd166', 'Huella humana': '#ff7a7a',
  Incalculable: '#a5b4fc', 'Cambio esperado por modelo': '#86a9ff', 'Diferencia de tendencias no atribuida': '#a5b4fc',
};
const lossLabels: Record<string, string> = { 'Lluvia menos evaporacion': 'Lluvia menos evaporación', 'El Nino': 'El Niño' };

function counts(bodies: WaterBody[], order: State[]) {
  return order.map((state) => ({ state, count: bodies.filter((body) => body.state === state).length })).filter((row) => row.count);
}

function distribution(rows: ReturnType<typeof counts>, total: number) {
  let start = 0;
  return rows.map(({ state, count }) => {
    const end = start + count / total * 100;
    const segment = `${color(state)} ${start}% ${end}%`;
    start = end;
    return segment;
  }).join(', ');
}

function VerdictDonut({ label, bodies, order }: { label: string; bodies: WaterBody[]; order: State[] }) {
  const rows = counts(bodies, order);
  const segments = distribution(rows, bodies.length);
  return <figure className="verdict-set">
    <div className="verdict-donut" style={{ background: segments ? `conic-gradient(${segments})` : undefined }} aria-hidden="true"><b>{bodies.length}</b></div>
    <figcaption><strong>{label}</strong><ul>{rows.map(({ state, count }) => <li key={state}><i style={{ background: color(state) }} />
      {states[state].label} <b>{count}</b></li>)}</ul></figcaption>
  </figure>;
}

function Bars({ items }: { items: { label: string; value: number; color: string }[] }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return <ul className="overview-bars">{items.map((item) => <li key={item.label}>
    <div><span>{item.label}</span><strong>{number(item.value)} ha</strong></div>
    <div className="bar-track"><i style={{ width: `${item.value / max * 100}%`, background: item.color }} /></div>
  </li>)}</ul>;
}

function Sparkline({ values, tint }: { values: (number | null)[]; tint: string }) {
  const finite = values.filter((value): value is number => Number.isFinite(value));
  if (finite.length < 2) return null;
  const min = Math.min(...finite);
  const spread = Math.max(Math.max(...finite) - min, 1);
  let open = false;
  const path = values.map((value, index) => {
    if (value == null) { open = false; return ''; }
    const command = open ? 'L' : 'M';
    open = true;
    return `${command}${index * 180 / (values.length - 1)},${38 - (value - min) / spread * 34}`;
  }).join(' ');
  return <svg aria-hidden="true" className="sparkline" viewBox="0 0 180 42" preserveAspectRatio="none">
    <path d={path} stroke={tint} fill="none" strokeWidth="2" vectorEffect="non-scaling-stroke" />
  </svg>;
}

export default function Overview({ bodies, snapshot, weekly, method, openDetails }: {
  bodies: WaterBody[]; snapshot: Snapshot; weekly?: Weekly; method: Method; openDetails: (id: string) => void;
}) {
  const combined = [...bodies, ...snapshot.national];
  const order = visibleStates(method, combined);
  const sorted = [...bodies].sort((a, b) => order.indexOf(a.state) - order.indexOf(b.state) || a.trend.change_pct - b.trend.change_pct);
  const lost = bodies.reduce((total, body) => total + Math.max(0, body.baseline_mean_ha * -body.trend.change_pct / 100), 0);
  const fires = weekly?.report?.rows.filter((entry) => entry.alerta).length;
  const kpis = [
    { label: 'Análisis completos', value: number(bodies.length), icon: Droplets },
    { label: 'Con evidencia de intervención', value: number(bodies.filter((body) => humanEvidenceStates.includes(body.state)).length), icon: Footprints },
    { label: method === 'balance' ? 'Incalculables' : 'Pérdidas no explicadas', value: number(bodies.filter((body) =>
      method === 'balance' ? body.state === 'Incalculable' || body.state === 'Sin explicar' : body.state === 'Perdida no explicada').length), icon: Gauge },
    { label: 'Agua perdida en los últimos cinco años', value: `${number(lost)} ha`, icon: TrendingDown },
    { label: 'Alertas de incendio', value: fires == null ? '—' : number(fires), icon: Flame },
    ...(method === 'balance' ? [{ label: 'Lagunas en el barrido nacional', value: number(snapshot.national.length), icon: ScanSearch }] : []),
  ];
  const losses = new Map<string, number>();
  for (const body of bodies) {
    for (const [cause, value] of Object.entries(body.decomposition_ha)) {
      if (value < 0) losses.set(cause, (losses.get(cause) ?? 0) - value);
    }
  }
  const regions = [
    { name: 'Altiplano y valles', bodies: combined.filter((body) => body.lon < -65.6 && body.lat < -14.5) },
    { name: 'Llanos, Chaco y Amazonía', bodies: combined.filter((body) => !(body.lon < -65.6 && body.lat < -14.5)) },
  ];
  const artificial = new Map<string, { count: number; ha: number }>();
  for (const item of snapshot.artificial?.points ?? []) {
    const total = artificial.get(item.tipo) ?? { count: 0, ha: 0 };
    total.count++;
    total.ha += item.ha;
    artificial.set(item.tipo, total);
  }
  return <>
    <div className="overview-kpis">{kpis.map(({ label, value, icon: Icon }) => <article key={label} className="panel overview-kpi">
      <Icon size={19} aria-hidden="true" /><strong>{value}</strong><span>{label}</span>
    </article>)}</div>
    <div className="overview-grid">
      <section className="panel overview-panel">
        <h2>Veredictos</h2>
        <div className="verdicts"><VerdictDonut label="Análisis completo" bodies={bodies} order={order} />
          {!!snapshot.national.length && <VerdictDonut label="Barrido nacional" bodies={snapshot.national} order={order} />}</div>
      </section>
      <section className="panel overview-panel">
        <h2>{method === 'balance' ? 'De dónde viene el agua perdida' : 'Cambio modelado y diferencia no atribuida'}</h2>
        {losses.size ? <Bars items={[...losses].sort((a, b) => b[1] - a[1]).map(([label, value]) => ({
          label: lossLabels[label] ?? label, value, color: lossColors[label] ?? '#a5abc9',
        }))} /> : <p className="muted">Sin pérdidas registradas en los casos visibles.</p>}
        <p className="muted">Suma de los componentes negativos de los casos con análisis completo.</p>
      </section>
    </div>
    <h2 className="overview-title">Cuerpos de agua con análisis completo</h2>
    <div className="overview-bodies">{sorted.map((body) => {
      const suspect = firstSuspect(body);
      return <article key={body.body_id} className="panel overview-body">
        <h3>{body.name}</h3><Status state={body.state} />
        <div className="overview-body-metrics"><strong style={{ color: color(body.state) }}>{signed(body.trend.change_pct)}%</strong>
          <span>{body.n_pass}/3 pruebas · {body.confidence}</span></div>
        <Sparkline values={body.observed} tint={color(body.state)} />
        {suspect && <p className="muted">{suspect.label} · {suspect.evidence}</p>}
        <button type="button" onClick={() => openDetails(body.body_id)} aria-label={`Ver ficha de ${body.name}`}>
          Ver ficha <ArrowUpRight size={15} aria-hidden="true" /></button>
      </article>;
    })}</div>
    <div className="overview-grid">
      <section className="panel overview-panel">
        <h2>Por región</h2>
        <ul className="overview-bars">{regions.map(({ name, bodies }) => <li key={name}>
          <div><span>{name}</span><strong>{bodies.length}</strong></div>
          <div className="bar-track" style={{ background: distribution(counts(bodies, order), bodies.length)
            ? `linear-gradient(to right, ${distribution(counts(bodies, order), bodies.length)})` : undefined }} />
        </li>)}</ul>
        <p className="muted">{method === 'balance' ? 'Incluye el barrido nacional.' : 'Incluye los cuerpos de agua con análisis completo.'}</p>
      </section>
      <section className="panel overview-panel">
        <h2>Agua artificial en Bolivia</h2>
        {snapshot.artificial && artificial.size ? <>
          <Bars items={[...artificial].sort((a, b) => b[1].ha - a[1].ha).map(([kind, total], index) => ({
            label: `${kind} (${number(total.count)})`, value: total.ha, color: ['#22e5ff', '#7dd3fc', '#a5b4fc'][index % 3],
          }))} />
          <p className="muted">{number(snapshot.artificial.points.length)} manchas de MapBiomas Agua · {snapshot.artificial.year}</p>
        </> : <p className="muted">Sin datos de agua artificial en esta copia.</p>}
      </section>
    </div>
  </>;
}
