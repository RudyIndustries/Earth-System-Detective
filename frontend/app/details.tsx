'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, CircleCheck, CircleDashed, Download, ExternalLink } from 'lucide-react';
import { api, firstSuspect, imageUrl, modelUrl, number, reviewOutcomes, signed, states,
  type Audit, type BodyDetail, type Method, type WaterBody } from './data';
import { ClimateCharts, CrossChecks, WaterCharts } from './charts';
import { DataTable, Status } from './ui';

const tabs = ['Antes y después', 'Clima y causas', 'Agua natural vs. artificial', 'Pruebas y sospechosos', 'Alrededores', 'Auditoría'] as const;
const testLabels: Record<string, string> = {
  clima: 'Lo que el clima no explica', control: 'Gemela de control', coincidencia: 'Coincidencia en el tiempo',
};
const changes: Record<string, string> = {
  mining_ha: 'mining', mining_water_ha: 'mining', urban_ha: 'urban', population: 'urban', night_lights: 'urban',
  agri_ha: 'agri', dry_crop_ha: 'agri', pasture_ha: 'pasture', forest_loss_ha: 'forest_loss', burned_ha: 'forest_loss',
};
const placeKinds: Record<string, string[]> = {
  mining_ha: ['Mina o cantera'], urban_ha: ['Ciudad o pueblo', 'Industria'], population: ['Ciudad o pueblo'],
  night_lights: ['Industria', 'Ciudad o pueblo'], artificial_water_ha: ['Represa o canal'],
  mining_water_ha: ['Mina o cantera'], dry_crop_ha: ['Represa o canal'],
};

export function Details({ bodies, id, method, select, back }: {
  bodies: WaterBody[]; id: string; method: Method; select: (id: string) => void; back: () => void;
}) {
  const [tab, setTab] = useState<(typeof tabs)[number]>(tabs[0]);
  const [loaded, setLoaded] = useState<{ id: string; detail?: BodyDetail; error?: string }>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const request = new AbortController();
    api<BodyDetail>(modelUrl(`bodies/${id}`, method), { signal: request.signal }).then((detail) => setLoaded({ id, detail }))
      .catch((error: Error) => { if (!request.signal.aborted) setLoaded({ id, error: error.message }); });
    return () => request.abort();
  }, [id, method, attempt]);
  const current = loaded?.id === id ? loaded : undefined;
  const detail = current?.detail;
  const body = detail?.result;
  const quality = body?.data_quality;

  return <>
    <div className="body-picker panel">
      <button type="button" onClick={back}><ArrowLeft size={16} aria-hidden="true" /> Volver al mapa</button>
      <label>Cuerpo de agua<select value={id} onChange={(event) => select(event.target.value)}>
        {bodies.map((body) => <option key={body.body_id} value={body.body_id}>{body.name}</option>)}</select></label>
    </div>
    {current?.error && <div className="notice danger" role="alert">
      {current.error} <button type="button" onClick={() => { setLoaded(undefined); setAttempt((value) => value + 1); }}>Reintentar</button>
    </div>}
    {!current && <p role="status" className="loading">Cargando ficha…</p>}
    {body && detail && <>
      <div className="detail-heading"><div><h2>{body.name}</h2><p>{body.department}</p></div><Status state={body.state} /></div>
      <div className="metrics">
        <div className="panel"><span>Cambio desde el periodo base</span><strong>{signed(body.trend.change_pct)}%</strong></div>
        <div className="panel" title={`Mann-Kendall p = ${number(body.trend.p, 3)} · Ajustado p = ${number(body.trend.p_holm, 3)}`}>
          <span>Tendencia de Sen</span><strong>{signed(body.trend.sen_ha_per_year, 1)} ha/año</strong></div>
        <div className="panel"><span>{body.method_version ? 'Nivel de evidencia' : 'Confianza'}</span><strong>{body.confidence}</strong><small>{body.n_pass} de 3 pruebas favorables</small></div>
        <div className="panel"><span>{body.method_version ? 'Presión priorizada' : 'Sospechoso principal'}</span><strong>{firstSuspect(body)?.label ?? '—'}</strong></div>
      </div>
      <div className="notice"><div>{states[body.state].action}
        {body.climate_share != null && <p>El cambio atribuible al clima equivale al {number(100 * Math.min(body.climate_share, 9.99))} % de la pérdida entre el periodo base y los últimos cinco años.</p>}
      </div></div>
      {quality?.r_jrc != null && <p className={quality.level === 'baja' ? 'notice warning' : 'muted'}>
        Calidad de datos {quality.level}. Correlación entre Landsat y JRC {number(quality.r_jrc, 2)}.
        {quality.interpolated_years?.length ? ` Años interpolados: ${quality.interpolated_years.join(', ')}.` : ''}
      </p>}
      {!!body.why?.length && <div className="notice reasons"><div>
        <strong>{body.state === 'Incalculable' ? 'Por qué es incalculable' : 'Motivos del diagnóstico'}</strong>
        <ul>{body.why.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      </div></div>}
      {body.quality && <p className={body.quality.eligible && body.model_validation?.reliable ? 'muted' : 'notice warning'}>
        Modelo seleccionado: {body.selected_model}. {body.quality.base_observed_n} años de agua observada en el periodo base,
        {body.quality.imputed_water_n} años imputados excluidos. {body.quality.reasons.join(' ')}
      </p>}
      <section className="panel detail-panel" aria-label="Datos del cuerpo de agua">
        <nav aria-label="Secciones de la ficha" className="tabs">
          {tabs.map((name) => <button type="button" key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}
        </nav>
        <div className="tab-content">
          {tab === 'Antes y después' && <Compare key={id} detail={detail} />}
          {tab === 'Clima y causas' && <><ClimateCharts body={body} /><CrossChecks detail={detail} /></>}
          {tab === 'Agua natural vs. artificial' && <WaterCharts key={id} detail={detail} />}
          {tab === 'Pruebas y sospechosos' && <Evidence body={body} />}
          {tab === 'Alrededores' && <Surroundings detail={detail} />}
          {tab === 'Auditoría' && <AuditView key={id} body={body} method={method} />}
        </div>
      </section>
    </>}
  </>;
}

function Compare({ detail }: { detail: BodyDetail }) {
  const { result, imageYears, context } = detail;
  const [mode, setMode] = useState(context ? 'context' : 'lake');
  const [before, setBefore] = useState(imageYears[0]?.year);
  const [after, setAfter] = useState(imageYears.at(-1)?.year);
  const [slider, setSlider] = useState(50);
  const [showChanges, setShowChanges] = useState(true);
  const [showWater, setShowWater] = useState(false);
  const isContext = mode === 'context' && context !== null;
  const id = result.body_id;
  const yearA = isContext ? context.years[0] : before;
  const yearB = isContext ? context.years[1] : after;
  const beforeUrl = isContext ? imageUrl('context', `${id}_antes`) : imageUrl('img', `${id}_${before}`);
  const afterUrl = isContext ? imageUrl('context', `${id}_despues`) : imageUrl('img', `${id}_${after}`);
  const maskA = imageYears.find((image) => image.year === before)?.mask;
  const maskB = imageYears.find((image) => image.year === after)?.mask;
  const waterA = result.observed[result.years.indexOf(yearA ?? 0)];
  const waterB = result.observed[result.years.indexOf(yearB ?? 0)];

  return <>
    {context && <div className="segmented">
      <button type="button" aria-pressed={!isContext} onClick={() => setMode('lake')}>La laguna</button>
      <button type="button" aria-pressed={isContext} onClick={() => setMode('context')}>Los alrededores</button>
    </div>}
    {!isContext && imageYears.length < 2 ? <p className="muted">Sin imágenes comparables para este cuerpo de agua.</p> : <>
      {!isContext && <div className="compare-options">
        <div><label htmlFor="image-before">Antes</label><select id="image-before" value={before} onChange={(event) => setBefore(Number(event.target.value))}>
          {imageYears.map(({ year }) => <option key={year}>{year}</option>)}</select></div>
        <div><label htmlFor="image-after">Después</label><select id="image-after" value={after} onChange={(event) => setAfter(Number(event.target.value))}>
          {imageYears.map(({ year }) => <option key={year}>{year}</option>)}</select></div>
      </div>}
      <div className="compare-frame">
        {/* Existing science images keep their original pixels and alignment for the overlays. */}
        {/* eslint-disable @next/next/no-img-element */}
        <img src={beforeUrl} alt={`Imagen satelital en ${yearA}`} />
        {!isContext && showWater && maskA && <img className="mask" alt="" src={imageUrl('img', `${id}_${before}_water`)} />}
        <div className="compare-after" style={{ clipPath: `inset(0 0 0 ${slider}%)` }}>
          <img src={afterUrl} alt={`Imagen satelital en ${yearB}`} />
          {!isContext && showWater && maskB && <img className="mask" alt="" src={imageUrl('img', `${id}_${after}_water`)} />}
          {isContext && showChanges && <img className="mask changes" alt="Cambios de uso de suelo" src={imageUrl('context', `${id}_cambios`)} />}
        </div>
        <span className="compare-label before">Antes · {yearA}</span><span className="compare-label after">Después · {yearB}</span>
        <span className="compare-divider" style={{ left: `${slider}%` }} aria-hidden="true"><b>↔</b></span>
        <input aria-label="Deslizador antes y después" type="range" min="0" max="100" value={slider} onChange={(event) => setSlider(Number(event.target.value))} />
      </div>
      {isContext ? <>
        <label className="control-check"><input type="checkbox" checked={showChanges} onChange={(event) => setShowChanges(event.target.checked)} /> Mostrar cambios alrededor</label>
        {showChanges && <div className="legend">{Object.entries(context.legend).map(([key, item]) => <span key={key}><i style={{ background: item.color }} />
          {item.label} · {number(context.changes_ha[key] ?? 0)} ha</span>)}</div>}
        <p className="muted">Ventana de {number(context.window_km)} km. MapBiomas Bolivia y pérdida de bosque de Hansen.</p>
      </> : <>
        {(maskA || maskB) && <label className="control-check"><input type="checkbox" checked={showWater} onChange={(event) => setShowWater(event.target.checked)} /> Mostrar el agua detectada por JRC</label>}
        {waterA != null && waterB != null && <p className="muted">Agua detectada: {number(waterA)} ha en {yearA} y {number(waterB)} ha en {yearB}. Imágenes Landsat de época seca.</p>}
      </>}
    </>}
  </>;
}

function Evidence({ body }: { body: WaterBody }) {
  return <>
    <ul className="evidence">{Object.entries(body.tests).map(([key, test]) => <li key={key}>
      {test.pass ? <CircleCheck className="passed" aria-label="Superada" /> : <CircleDashed className="muted" aria-label="Sin superar" />}
      <div><strong>{testLabels[key] ?? key}{(test.pass == null || test.evaluated === false) && ' · No evaluable'}</strong><p>{test.detail}</p></div>
    </li>)}</ul>
    <DataTable rows={body.suspects.map((suspect) => ({
      Sospechoso: suspect.label, Evidencia: suspect.evidence, 'Empieza a crecer': suspect.onset,
      'Antecede a la caída': suspect.precedes ? 'Sí' : 'No', 'R² con el residuo': suspect.r2 == null ? '—' : number(suspect.r2, 2),
      Tipo: suspect.indirect == null ? (suspect.data_provenance ?? '—') : suspect.indirect ? 'Indirecto' : 'Directo',
      'Inseparable de': suspect.together_with?.join(', ') || '—',
    }))} empty="Sin sospechosos registrados." />
    {body.control_validation && <div className="proof-group"><h3>Elegibilidad de la gemela</h3>
      <p>{body.control_validation.eligible ? 'Control elegible' : 'Control no elegible'}</p>
      {!!body.control_validation.reasons.length && <ul>{body.control_validation.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
    </div>}
    {!!body.independent_evidence?.length && <div className="proof-group"><h3>Intervenciones documentadas</h3>
      <DataTable rows={body.independent_evidence.map((entry) => ({ Actividad: entry.suspect, Año: entry.year, Fuente: entry.source }))} />
    </div>}
  </>;
}

function Surroundings({ detail }: { detail: BodyDetail }) {
  const { context, places, result } = detail;
  const top = result.suspects.filter((suspect) => suspect.evidence !== 'debil' && !suspect.indirect).slice(0, 2);
  return <>
    {(top.length ? top : result.suspects.slice(0, 1)).map((suspect) => {
      const key = suspect.suspect.split('@')[0];
      const change = changes[key];
      const nearest = places.filter((place) => place.name && placeKinds[key]?.includes(place.kind))
        .sort((a, b) => a.dist_km - b.dist_km).slice(0, 3);
      return <div className="notice" key={suspect.suspect}><div><strong>{suspect.label}</strong>
        <p>Evidencia {suspect.evidence}{suspect.onset ? ` · Crece desde ${suspect.onset}` : ''}</p>
        {!!context?.changes_ha[change] && <p>{context.legend[change]?.label} · {number(context.changes_ha[change])} ha entre {context.years.join(' y ')}.</p>}
        {!!nearest.length && <p>{nearest.map((place) => `${place.name} (${number(place.dist_km, 1)} km)`).join(' · ')}</p>}
      </div></div>;
    })}
    {places.length ? <div className="table-wrap"><table>
      <thead><tr>{['Tipo', 'Nombre', 'Detalle', 'Distancia', 'OpenStreetMap'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{places.map((place) => <tr key={place.osm}><td>{place.kind}</td><td>{place.name || '—'}</td><td>{place.detail}</td>
        <td>{number(place.dist_km, 1)} km</td><td><a href={place.osm} target="_blank" rel="noreferrer" aria-label={`Ver ${place.name || place.kind} en OpenStreetMap`}><ExternalLink size={17} /></a></td></tr>)}</tbody>
    </table></div> : <p className="muted">Sin lugares registrados en OpenStreetMap para esta zona.</p>}
  </>;
}

function AuditView({ body, method }: { body: WaterBody; method: Method }) {
  const [audit, setAudit] = useState<Audit>();
  const [status, setStatus] = useState<{ message: string; error?: boolean }>();
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const path = `bodies/${body.body_id}`;
  useEffect(() => {
    const request = new AbortController();
    api<Audit>(modelUrl(`${path}/audit`, method), { signal: request.signal }).then(setAudit).catch((error: Error) => {
      if (!request.signal.aborted) setStatus({ message: error.message, error: true });
    });
    return () => request.abort();
  }, [path, method, refresh]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    try {
      await api(modelUrl(`${path}/reviews`, method), { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.fromEntries(new FormData(form))) });
      setStatus({ message: 'Revisión guardada en la auditoría.' });
      setRefresh((value) => value + 1);
      form.reset();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }

  const [latest, previous] = audit?.runs ?? [];
  return <>
    {audit?.available ? <>
      <h3>Historial de corridas</h3>
      {latest && previous && latest.estado !== previous.estado && <p className="notice">El veredicto cambió de {previous.estado} a {latest.estado}. {latest.nota}</p>}
      <DataTable rows={audit.runs} />
      {!!audit.alerts.length && <><h3>Alertas</h3><DataTable rows={audit.alerts} /></>}
      <h3>Agregar revisión humana</h3>
      <form onSubmit={save} className="review-form">
        <label>Quién revisa<input name="reviewer" required maxLength={200} /></label>
        <label>Resultado<select name="outcome">{Object.entries(reviewOutcomes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="review-comment">Comentario<textarea rows={3} name="comment" maxLength={5000} /></label>
        <button type="submit" className="primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar revisión'}</button>
      </form>
      {!!audit.reviews.length && <><h3>Revisiones</h3><DataTable rows={audit.reviews} /></>}
    </> : <p className="muted">{audit ? 'Sin base de auditoría para estos datos.' : 'Cargando auditoría…'}</p>}
    {status && <p className={`notice ${status.error ? 'danger' : 'success'}`} role={status.error ? 'alert' : 'status'}>{status.message}</p>}
    <details className="technical"><summary>Modo técnico</summary><p>R² del modelo ({body.baseline_end}) · {body.climate_r2 == null ? '—' : number(body.climate_r2, 2)}</p>
      {body.climate_fit && <><h4>Ajuste del modelo climático</h4><pre>{JSON.stringify(body.climate_fit, null, 2)}</pre></>}
      {body.model_comparison && <><h4>Comparación de modelos</h4><DataTable rows={body.model_comparison.map((model) => ({
        Modelo: model.method, Seleccionado: model.selected ? 'Sí' : 'No',
        'Validaciones internas': model.cv_n, 'MAE interno (ha)': model.cv_mae_ha, 'MAE posterior (ha)': model.mae_ha,
      }))} /></>}
      <h4>Validación retrospectiva</h4><pre>{JSON.stringify(body.backtest, null, 2)}</pre>
      <h4>Pruebas</h4><pre>{JSON.stringify(body.tests, null, 2)}</pre>
    </details>
    <a className="button-link" href={modelUrl('/api/results.json', method)}><Download size={16} aria-hidden="true" /> Descargar resultados JSON</a>
  </>;
}
