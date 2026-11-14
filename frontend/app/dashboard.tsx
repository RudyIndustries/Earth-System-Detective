'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { ArrowUpRight, Download, Droplets, Flame, Layers, LayoutDashboard, Map as MapIcon, ScanSearch, Search, Table2 } from 'lucide-react';
import { api, downloadCsv, firstSuspect, humanEvidenceStates, methodNames, modelUrl, number, signed, states,
  visibleStates, type Method, type Snapshot, type State, type WaterBody, type Weekly } from './data';
import { Status, DataTable } from './ui';

const MapView = dynamic(() => import('./map-view'), {
  ssr: false,
  loading: () => <div className="map-frame loading" role="status">Cargando mapa…</div>,
});
const Details = dynamic(() => import('./details').then((module) => module.Details), {
  loading: () => <p className="loading" role="status">Cargando ficha…</p>,
});
const Overview = dynamic(() => import('./overview'), {
  loading: () => <p className="loading" role="status">Cargando panorama…</p>,
});
const views = [
  { name: 'Panorama', icon: LayoutDashboard },
  { name: 'Mapa de alertas', icon: MapIcon },
  { name: 'Monitoreo', icon: Table2 },
  { name: 'Ficha del cuerpo de agua', icon: ScanSearch },
  { name: 'Vigilancia semanal', icon: Flame },
] as const;

export function Dashboard() {
  const [view, setView] = useState(0);
  const [method, setMethod] = useState<Method>('balance');
  const [loaded, setLoaded] = useState<{ method: Method; snapshot: Snapshot }>();
  const [weekly, setWeekly] = useState<Weekly>();
  const [error, setError] = useState('');
  const [weeklyError, setWeeklyError] = useState('');
  const [showControls, setShowControls] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [weeklyAttempt, setWeeklyAttempt] = useState(0);

  useEffect(() => {
    const request = new AbortController();
    api<Snapshot>(modelUrl('dashboard', method), { signal: request.signal })
      .then((snapshot) => setLoaded({ method, snapshot })).catch((error: Error) => {
      if (!request.signal.aborted) setError(error.message);
    });
    return () => request.abort();
  }, [attempt, method]);

  useEffect(() => {
    const request = new AbortController();
    api<Weekly>('weekly', { signal: request.signal }).then(setWeekly).catch((error: Error) => {
      if (!request.signal.aborted) setWeeklyError(error.message);
    });
    return () => request.abort();
  }, [weeklyAttempt]);

  const snapshot = loaded?.method === method ? loaded.snapshot : undefined;
  const controls = new Set(snapshot?.results.map((body) => body.control_id).filter(Boolean));
  const visible = snapshot?.results.filter((body) => showControls || !controls.has(body.body_id) || humanEvidenceStates.includes(body.state)) ?? [];
  const current = visible.find((body) => body.body_id === selected);

  function openDetails(id: string) {
    if (!visible.some((body) => body.body_id === id)) setShowControls(true);
    setSelected(id);
    setView(3);
  }

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Droplets size={22} aria-hidden="true" /></span><span>Detector de <br />huella humana</span></div>
      <nav aria-label="Vistas">
        {views.map(({ name, icon: Icon }, index) => <button key={name} type="button" aria-current={index === view ? 'page' : undefined}
          className={index === view ? 'nav-active' : ''} onClick={() => setView(index)}><Icon size={18} aria-hidden="true" />{name}</button>)}
      </nav>
      <label className="control-check"><input type="checkbox" checked={showControls} onChange={(event) => setShowControls(event.target.checked)} />
        Mostrar gemelas de control</label>
    </aside>
    <main className="main-content">
      <header className="page-header"><div>
        <p className="eyebrow">Agua de Bolivia</p>
        <h1>{views[view].name}</h1>
        {view === 0 && <p>Superficie de agua, veredictos y señales de presión sobre las cuencas de Bolivia.</p>}
        {view === 1 && <p>Variación de la superficie de agua y señales de presión sobre las cuencas.</p>}
      </div>
        {loaded?.snapshot.conservativeAvailable && view !== 4 && <label>Método de análisis
          <select aria-label="Método de análisis" value={method} onChange={(event) => { setError(''); setMethod(event.target.value as Method); }}>
            {Object.entries(methodNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
          </select></label>}
      </header>
      {error && <div className="notice danger" role="alert">
        <p>{error} Comprueba que NestJS esté iniciado.</p>
        <button type="button" onClick={() => { setError(''); setAttempt((value) => value + 1); }}>Reintentar</button>
      </div>}
      {!snapshot && !error && <p className="loading" role="status">Cargando datos del detector…</p>}
      {snapshot?.sample && <p className="notice">Datos ficticios de prueba.</p>}
      {snapshot && method === 'conservative' && view < 4 && <p className="notice">El modelo conservador muestra el análisis completo. Las 300 lagunas del barrido nacional se consultan en Balance hídrico.</p>}
      {snapshot && view === 0 && <Overview snapshot={snapshot} method={method} bodies={visible} weekly={weekly} openDetails={openDetails} />}
      {snapshot && view === 1 && <MapView key={method} method={method} snapshot={snapshot} bodies={visible} selected={current} select={setSelected} openDetails={openDetails} />}
      {snapshot && view === 2 && <Monitor key={method} method={method} snapshot={snapshot} weekly={weekly} openDetails={openDetails} />}
      {snapshot && view === 3 && (visible.length ? <Details key={method} method={method} bodies={visible} id={current?.body_id ?? visible[0].body_id}
        select={setSelected} back={() => setView(1)} /> : <p className="notice">No hay cuerpos de agua disponibles.</p>)}
      {snapshot && view === 4 && (weeklyError ? <div className="notice danger" role="alert">
        {weeklyError} <button type="button" onClick={() => { setWeeklyError(''); setWeeklyAttempt((value) => value + 1); }}>Reintentar</button>
      </div> : <Watch weekly={weekly} />)}
      {snapshot && <footer>Los diagnósticos se basan en coincidencia y consistencia estadística. Fuentes: Landsat, NASA POWER y FIRMS, NOAA, JRC, MapBiomas Bolivia, Hansen, HydroBASINS y OpenStreetMap.</footer>}
    </main>
  </div>;
}

function Monitor({ snapshot, weekly, method, openDetails }: { snapshot: Snapshot; weekly?: Weekly; method: Method; openDetails: (id: string) => void }) {
  const [search, setSearch] = useState('');
  const [state, setState] = useState<State | ''>('');
  const [mode, setMode] = useState('');
  const [minimum, setMinimum] = useState('');
  const controls = new Set(snapshot.results.map((body) => body.control_id).filter(Boolean));
  const stateList = visibleStates(method, [...snapshot.results, ...snapshot.national]);
  const fires = new Map(weekly?.report?.rows.map((body) => [body.body_id, body]));
  const rows = [
    ...snapshot.results.map((body) => ({ body, mode: controls.has(body.body_id) && !humanEvidenceStates.includes(body.state) ? 'Gemela de control' : 'Completo' })),
    ...snapshot.national.map((body) => ({ body, mode: 'Barrido nacional' })),
  ].filter((row) => (!state || row.body.state === state) && (!mode || row.mode === mode) &&
    row.body.name.toLocaleLowerCase('es').includes(search.trim().toLocaleLowerCase('es')) &&
    (!Number(minimum) || row.body.trend.change_pct <= -Math.abs(Number(minimum))))
    .sort((a, b) => stateList.indexOf(a.body.state) - stateList.indexOf(b.body.state) || a.body.trend.change_pct - b.body.trend.change_pct)
    .map(({ body, mode }) => {
      const fire = fires.get(body.body_id);
      const share = body.climate_share == null || body.trend.change_pct > -10 ? null
        : Math.round(100 * Math.max(-1, Math.min(2, body.climate_share)));
      return {
        body, mode, share, suspect: firstSuspect(body),
        fire: fire ? `${fire.alerta ? 'Alerta · ' : ''}${Object.entries(fire.areas).map(([area, a]) => `${area}: ${a.focos}`).join(' · ')}` : '',
      };
    });

  return <>
    <div className="toolbar panel">
      <label><span><Search size={15} aria-hidden="true" /> Buscar por nombre</span><input type="search" placeholder="Nombre del lago o laguna"
        value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Estado<select value={state} onChange={(event) => setState(event.target.value as State | '')}><option value="">Todos</option>
        {stateList.map((state) => <option key={state} value={state}>{states[state].label}</option>)}</select></label>
      <label>Análisis<select value={mode} onChange={(event) => setMode(event.target.value)}><option value="">Todos</option>
        <option>Completo</option><option>Gemela de control</option>{snapshot.national.length > 0 && <option>Barrido nacional</option>}</select></label>
      <label>Pérdida mínima (%)<input type="number" min="0" value={minimum} onChange={(event) => setMinimum(event.target.value)} placeholder="0" /></label>
    </div>
    <div className="section-bar"><p>{rows.length} {rows.length === 1 ? 'cuerpo de agua' : 'cuerpos de agua'}</p>
      <button type="button" disabled={!rows.length} onClick={() => downloadCsv(rows.map(({ body, mode, share, fire, suspect }) => ({
        'Cuerpo de agua': body.name, Estado: states[body.state].label, 'Análisis': mode, Confianza: body.confidence,
        Pruebas: `${body.n_pass}/3`, 'Cambio %': body.trend.change_pct, 'Clima explica %': share,
        'Sospechoso principal': suspect?.label ?? '', Evidencia: suspect?.evidence ?? '',
        'Motivos': body.why?.join(' ') ?? '',
        'Incendios 7 días': fire, Calidad: body.data_quality?.level ?? '',
        'Superficie (ha)': body.ha ?? body.baseline_mean_ha ?? null, Latitud: body.lat, Longitud: body.lon,
      })))}><Download size={16} aria-hidden="true" /> Descargar CSV</button>
    </div>
    {!!rows.length && <div className="table-wrap"><table>
      <thead><tr>{['Cuerpo de agua', 'Estado', 'Análisis', 'Cambio', 'Confianza', 'Clima explica', 'Sospechoso principal',
        'Calidad', 'Incendios 7 días', 'Superficie (ha)'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
      <tbody>{rows.map(({ body, mode, share, fire, suspect }) => <tr key={body.body_id}>
        <td>{mode === 'Barrido nacional' ? body.name : <button className="table-link" type="button" onClick={() => openDetails(body.body_id)}>
          {body.name}<ArrowUpRight size={14} aria-hidden="true" /></button>}</td><td><Status state={body.state} /></td>
        <td>{mode}</td><td>{signed(body.trend.change_pct)}%</td><td>{body.confidence} · {body.n_pass}/3</td>
        <td>{share == null ? '—' : `${share}%`}</td><td>{suspect?.label ?? '—'}{suspect?.evidence && <small>{suspect.evidence}</small>}</td>
        <td>{body.data_quality?.level ?? (body.quality ? (body.quality.eligible ? 'Elegible' : 'Poca calidad') : '—')}</td>
        <td>{fire || '—'}</td><td>{number(body.ha ?? body.baseline_mean_ha ?? 0)}</td>
      </tr>)}</tbody>
    </table></div>}
  </>;
}

function Watch({ weekly }: { weekly?: Weekly }) {
  if (!weekly) return <p className="loading" role="status">Cargando vigilancia semanal…</p>;
  const report = weekly.report;
  const alerts = report?.rows.filter((entry) => entry.alerta).length ?? 0;
  return <>
    {report ? <>
      <div className={`notice ${alerts ? 'danger' : 'success'}`}><Flame size={20} aria-hidden="true" /><div>
        <strong>{alerts ? `${alerts} cuerpos de agua con alerta de incendios` : 'Sin alertas en el último reporte'}</strong>
        <p>Semana al {report.week_end} · Revisado {report.checked_at.replace('T', ' ').slice(0, 16)} · {report.notified}</p>
      </div></div>
      <DataTable rows={report.rows.flatMap((body) => Object.entries(body.areas).map(([area, item]) => ({
        'Cuerpo de agua': body.name, Estado: states[body.state].label, Área: area === 'cerca' ? 'Cerca de la laguna' : 'Toda la cuenca',
        'Focos esta semana': item.focos, 'Normal para esta semana': item.normal, Alerta: item.alerta ? 'Sí' : 'No',
      })))} />
      <p className="muted">NASA FIRMS. Alerta con al menos 5 focos y el doble del promedio para la misma semana de los cinco años anteriores.</p>
    </> : <p className="notice">Aún no se ha generado un reporte de incendios.</p>}
    <h2 className="section-title"><Layers size={19} aria-hidden="true" /> Historial</h2>
    <DataTable rows={weekly.history} />
  </>;
}
