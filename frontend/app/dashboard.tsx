'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowUpRight, Download, Flame, Layers, Map as MapIcon, ScanSearch, Search, Table2 } from 'lucide-react';
import { api, downloadCsv, firstSuspect, humanEvidenceStates, methodNames, modelUrl, number, signed, states,
  visibleStates, type Method, type Snapshot, type State, type WaterBody, type Weekly } from './data';
import { Status, DataTable } from './ui';
import { MissionNav } from './mission-nav';
import { MissionHome } from './mission-home';

const MapView = dynamic(() => import('./map-view'), {
  ssr: false,
  loading: () => <div className="map-frame loading" role="status">Cargando mapa…</div>,
});
const Details = dynamic(() => import('./details').then((module) => module.Details), {
  loading: () => <p className="loading" role="status">Cargando ficha…</p>,
});
const Overview = dynamic(() => import('./overview'), {
  loading: () => <p className="loading" role="status">Cargando el análisis de los lagos…</p>,
});
const Vegetation = dynamic(() => import('./vegetation'), {
  loading: () => <p className="loading" role="status">Cargando vegetación…</p>,
});
const lakeViews = {
  mapa: { name: 'Lagos de Bolivia', label: 'Mapa 3D', icon: MapIcon, description: 'Explora el relieve de Bolivia, selecciona una laguna y consulta cómo cambió su superficie.' },
  monitoreo: { name: 'Monitoreo de lagos', label: 'Monitoreo', icon: Table2, description: 'Busca los lagos que te interesan, compara sus diagnósticos y descarga los datos filtrados.' },
  ficha: { name: 'Fichas de lagos', label: 'Fichas', icon: ScanSearch, description: 'Compara imágenes, revisa la evolución del agua y consulta la evidencia de cada diagnóstico.' },
} as const;
const views = {
  panorama: { name: 'Análisis de los lagos', description: 'Superficie de agua, diagnósticos y señales de presión sobre las cuencas.' },
  ...lakeViews,
  vigilancia: { name: 'Incendios', description: 'Consulta los focos térmicos semanales detectados cerca de los lagos y en sus cuencas.' },
  vegetacion: { name: 'Vegetación', description: 'Explora la pérdida de bosque, las áreas quemadas y los cambios de uso del suelo alrededor de los lagos.' },
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
  const view = candidate === 'lagos' ? 'mapa' : candidate === 'incendios' ? 'vigilancia'
    : candidate && Object.hasOwn(views, candidate) ? candidate as View : 'panorama';
  const lakeSection = view === 'mapa' || view === 'monitoreo' || view === 'ficha';
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
  const vegetationId = snapshot?.results.find((body) => body.body_id === selected)?.body_id
    ?? snapshot?.results.find((body) => body.body_id === 'poopo')?.body_id ?? snapshot?.results[0]?.body_id;
  const links = {
    inicio: locationFor('panorama', method),
    lagos: locationFor('mapa', method, selected),
    incendios: locationFor('vigilancia', method),
    vegetacion: locationFor('vegetacion', method, selected),
  };

  function openDetails(id: string) {
    router.push(locationFor('ficha', method, id));
  }

  function selectBody(id: string | null) {
    router.replace(locationFor(view, method, id), { scroll: false });
  }

  return <div className="shell">
    <a className="skip-link" href="#contenido">Ir al contenido</a>
    <MissionNav links={links} active={lakeSection ? 'lagos' : view === 'vigilancia' ? 'incendios' : view === 'vegetacion' ? 'vegetacion' : 'inicio'} />
    <main id="contenido" className={view === 'panorama' ? 'main-content mission-home' : 'main-content mission-subpage'}>
      {view === 'panorama' && <MissionHome lakes={links.lagos} fires={links.incendios} vegetation={links.vegetacion} />}
      {lakeSection && <nav className="lake-nav" aria-label="Explorar lagos">
        {(Object.entries(lakeViews) as [keyof typeof lakeViews, typeof lakeViews[keyof typeof lakeViews]][]).map(([key, { label, icon: Icon }]) =>
          <Link key={key} href={locationFor(key, method, key === 'monitoreo' ? null : selected)} aria-current={key === view ? 'page' : undefined}>
            <Icon size={17} aria-hidden="true" />{label}
          </Link>)}
      </nav>}
      <header className="page-header"><div>
        {view === 'panorama' ? <h2>{views[view].name}</h2> : <h1>{views[view].name}</h1>}
        <p>{views[view].description}</p>
      </div>
        {(view === 'panorama' || lakeSection) && <div className="page-actions">
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
      {snapshot && method === 'conservative' && (view === 'panorama' || lakeSection) && <p className="notice model-note">
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
      {snapshot && view === 'vegetacion' && (vegetationId
        ? <Vegetation bodies={snapshot.results} id={vegetationId} method={method} select={selectBody} details={locationFor('ficha', method, vegetationId)} />
        : <p className="notice">No hay cuerpos de agua con datos de vegetación.</p>)}
      {view === 'vigilancia' && (weeklyError ? <div className="notice danger" role="alert">
        {weeklyError} <button type="button" onClick={() => { setWeeklyError(''); setWeeklyAttempt((value) => value + 1); }}>Reintentar</button>
      </div> : <Watch weekly={weekly} map={links.lagos} />)}
      <footer>Los diagnósticos se basan en coincidencia y consistencia estadística. Fuentes: Landsat, NASA POWER y FIRMS, NOAA, JRC, MapBiomas Bolivia, Hansen, HydroBASINS y OpenStreetMap.</footer>
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

function Watch({ weekly, map }: { weekly?: Weekly; map: string }) {
  const [area, setArea] = useState('cuenca');
  if (!weekly) return <p className="loading" role="status">Cargando vigilancia semanal…</p>;
  const report = weekly.report;
  const alerts = report?.rows.filter((entry) => entry.alerta).length ?? 0;
  const counts = report?.rows.flatMap((row) => row.areas[area] ? [{ name: row.name, ...row.areas[area] }] : []) ?? [];
  const scale = Math.max(1, ...counts.map(({ focos, normal }) => Math.max(focos, normal)));
  return <>
    {report ? <>
      <div className={`notice ${alerts ? 'danger' : 'success'}`}><Flame size={20} aria-hidden="true" /><div>
        <strong>{alerts ? `${alerts} cuerpos de agua con alerta de incendios` : 'Sin alertas en el último reporte'}</strong>
        <p>Reporte guardado de la semana al {report.week_end} · Revisado {report.checked_at.replace('T', ' ').slice(0, 16)} · {report.notified}</p>
      </div></div>
      <section className="panel mission-data-panel">
        <div className="mission-chart-heading">
          <div><h2>Focos térmicos por lago</h2><p>La referencia es el promedio de la misma semana en los cinco años anteriores.</p></div>
          <label><span id="fire-area-label">Área</span><select aria-labelledby="fire-area-label"
            value={area} onChange={(event) => setArea(event.target.value)}>
            <option value="cuenca">Toda la cuenca</option><option value="cerca">Cerca de la laguna</option>
          </select></label>
        </div>
        <div className="mission-fire-key"><span><i /> Semana del reporte</span><span><i /> Promedio histórico</span></div>
        {counts.length ? <ul className="mission-fire-chart">
          {counts.map(({ name, focos, normal }) => <li key={name}><strong>{name}</strong>
            <div aria-label={`${focos} focos esta semana y ${number(normal, 1)} de promedio`}>
              <div><i style={{ width: `${focos / scale * 100}%` }} /><b>{number(focos)}</b></div>
              <div><i style={{ width: `${normal / scale * 100}%` }} /><b>{number(normal, 1)}</b></div>
            </div>
          </li>)}
        </ul> : <p className="notice">El reporte no incluye focos para esta área.</p>}
        <Link className="button-link" href={map}>Abrir mapa y sus capas <ArrowUpRight size={16} aria-hidden="true" /></Link>
      </section>
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
