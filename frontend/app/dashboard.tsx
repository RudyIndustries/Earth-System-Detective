'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
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
const views = {
  panorama: { name: 'Panorama', label: 'Panorama', icon: LayoutDashboard },
  mapa: { name: 'Mapa 3D de Bolivia', label: 'Mapa 3D', icon: MapIcon },
  monitoreo: { name: 'Monitoreo', label: 'Monitoreo', icon: Table2 },
  ficha: { name: 'Ficha del cuerpo de agua', label: 'Fichas', icon: ScanSearch },
  vigilancia: { name: 'Vigilancia semanal', label: 'Incendios', icon: Flame },
} as const;
type View = keyof typeof views;

function locationFor(view: View, method: Method, body?: string | null) {
  const params = new URLSearchParams();
  if (view !== 'panorama') params.set('vista', view);
  if (method === 'conservative') params.set('metodo', 'conservador');
  if (body) params.set('laguna', body);
  return params.size ? `/?${params}` : '/';
}

export function Dashboard() {
  const router = useRouter();
  const params = useSearchParams();
  const candidate = params.get('vista');
  const view = candidate && Object.hasOwn(views, candidate) ? candidate as View : 'panorama';
  const requestedMethod: Method = params.get('metodo') === 'conservador' ? 'conservative' : 'balance';
  const selected = params.get('laguna');
  const [snapshots, setSnapshots] = useState<Partial<Record<Method, Snapshot>>>({});
  const [weekly, setWeekly] = useState<Weekly>();
  const [error, setError] = useState<{ method: Method; message: string }>();
  const [weeklyError, setWeeklyError] = useState('');
  const [showControls, setShowControls] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [weeklyAttempt, setWeeklyAttempt] = useState(0);
  const method = snapshots.balance?.conservativeAvailable === false ? 'balance' : requestedMethod;
  const snapshot = snapshots[method];
  const currentError = error?.method === method ? error.message : undefined;

  useEffect(() => {
    if (snapshots.balance) return;
    const request = new AbortController();
    api<Snapshot>('dashboard', { signal: request.signal })
      .then((balance) => setSnapshots((previous) => ({ ...previous, balance })))
      .catch((error: Error) => {
        if (!request.signal.aborted) setError({ method: requestedMethod, message: error.message });
      });
    return () => request.abort();
  }, [attempt, requestedMethod, snapshots.balance]);

  useEffect(() => {
    if (method !== 'conservative' || !snapshots.balance?.conservativeAvailable || snapshot) return;
    const request = new AbortController();
    api<Snapshot>(modelUrl('dashboard', 'conservative'), { signal: request.signal })
      .then((conservative) => setSnapshots((previous) => ({ ...previous, conservative })))
      .catch((error: Error) => {
        if (!request.signal.aborted) setError({ method: 'conservative', message: error.message });
      });
    return () => request.abort();
  }, [attempt, method, snapshot, snapshots.balance?.conservativeAvailable]);

  useEffect(() => {
    const request = new AbortController();
    api<Weekly>('weekly', { signal: request.signal }).then(setWeekly).catch((error: Error) => {
      if (!request.signal.aborted) setWeeklyError(error.message);
    });
    return () => request.abort();
  }, [weeklyAttempt]);

  const controls = new Set(snapshot?.results.map((body) => body.control_id).filter(Boolean));
  const visible = snapshot?.results.filter((body) => body.body_id === selected || showControls ||
    !controls.has(body.body_id) || humanEvidenceStates.includes(body.state)) ?? [];
  const current = visible.find((body) => body.body_id === selected);

  function openDetails(id: string) {
    router.push(locationFor('ficha', method, id));
  }

  function selectBody(id: string | null) {
    router.replace(locationFor(view, method, id), { scroll: false });
  }

  return <div className="shell">
    <a className="skip-link" href="#contenido">Ir al contenido</a>
    <header className="site-header">
      <div className="navbar">
        <Link className="brand" href={locationFor('panorama', method)}>
          <span className="brand-mark"><Droplets size={21} aria-hidden="true" /></span>
          <span>Detector de huella humana</span>
        </Link>
        <nav aria-label="Navegación principal">
          {(Object.keys(views) as View[]).map((key) => {
            const { label, icon: Icon } = views[key];
            const body = key === 'mapa' || key === 'ficha' ? selected : null;
            return <Link key={key} href={locationFor(key, method, body)} aria-current={key === view ? 'page' : undefined}>
              <Icon size={17} aria-hidden="true" /><span>{label}</span>
            </Link>;
          })}
        </nav>
      </div>
    </header>
    <main id="contenido" className="main-content">
      <header className="page-header"><div>
        <p className="eyebrow">Agua de Bolivia</p>
        <h1>{views[view].name}</h1>
        {view === 'panorama' && <p>Superficie de agua, veredictos y señales de presión sobre las cuencas.</p>}
        {view === 'mapa' && <p>Explora el relieve y selecciona una columna para enfocar la laguna y consultar su ficha.</p>}
      </div>
        {view !== 'vigilancia' && <div className="page-actions">
          {(view === 'panorama' || view === 'mapa' || view === 'ficha') && snapshot && <label className="control-check">
            <input type="checkbox" checked={showControls} onChange={(event) => {
              setShowControls(event.target.checked);
              if (!event.target.checked && current && controls.has(current.body_id) && !humanEvidenceStates.includes(current.state)) {
                selectBody(null);
              }
            }} /> Mostrar gemelas de control
          </label>}
          {snapshots.balance?.conservativeAvailable && <fieldset className="method-switch">
            <legend>Método de análisis</legend>
            <div>{(Object.keys(methodNames) as Method[]).map((option) => (
              <label key={option}><input type="radio" name="analysis-method" checked={method === option} onChange={() => {
                setError(undefined);
                router.push(locationFor(view, option, selected), { scroll: false });
              }} /><span>{methodNames[option]}</span></label>
            ))}</div>
          </fieldset>}
        </div>}
      </header>
      {currentError && view !== 'vigilancia' && <div className="notice danger" role="alert">
        <p>{currentError}</p>
        <button type="button" onClick={() => { setError(undefined); setAttempt((value) => value + 1); }}>Reintentar</button>
      </div>}
      {!snapshot && !currentError && view !== 'vigilancia' && <p className="loading" role="status">Cargando datos del detector…</p>}
      {snapshot?.sample && <p className="notice">Datos ficticios de prueba.</p>}
      {snapshot && method === 'conservative' && view !== 'vigilancia' && <p className="notice model-note">
        <span>Modelo conservador aplicado a los casos con análisis completo. <Link href={locationFor('mapa', 'balance')}>Ver el barrido nacional en el mapa.</Link></span>
      </p>}
      {snapshot && view === 'panorama' && <>
        <div className="overview-actions">
          <Link className="button-link primary" href={locationFor('mapa', method)}><MapIcon size={17} aria-hidden="true" /> Abrir mapa 3D <ArrowUpRight size={15} aria-hidden="true" /></Link>
          {method === 'balance' && snapshot.conservativeAvailable && <Link className="button-link" href={locationFor('mapa', 'conservative')}>
            Ver modelo conservador en el mapa
          </Link>}
        </div>
        <Overview snapshot={snapshot} method={method} bodies={visible} weekly={weekly} openDetails={openDetails} />
      </>}
      {snapshot && view === 'mapa' && <MapView key={method} method={method} snapshot={snapshot} bodies={visible} selected={current} select={selectBody} openDetails={openDetails} />}
      {snapshot && view === 'monitoreo' && <Monitor key={method} method={method} snapshot={snapshot} weekly={weekly} openDetails={openDetails} />}
      {snapshot && view === 'ficha' && (visible.length ? <Details key={method} method={method} bodies={visible} id={current?.body_id ?? visible[0].body_id}
        select={selectBody} back={() => router.push(locationFor('mapa', method, current?.body_id ?? visible[0].body_id))} />
        : <p className="notice">No hay cuerpos de agua disponibles.</p>)}
      {view === 'vigilancia' && (weeklyError ? <div className="notice danger" role="alert">
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
