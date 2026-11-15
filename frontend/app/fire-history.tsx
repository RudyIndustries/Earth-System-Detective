'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import DeckGL from '@deck.gl/react';
import type { MapViewState, Position } from '@deck.gl/core';
import { ColumnLayer, PolygonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { Box, CalendarDays, CircleHelp, Map as MapIcon, Minus, Plus, RotateCcw } from 'lucide-react';
import { api, number, signed } from './data';

type Coordinates = [longitude: number, latitude: number];
type Archive = {
  source: { commit: string; file: string };
  res: number; y0: number; months: string[]; lat: number[]; lon: number[]; counts: number[];
  base: [number, number]; season: number[];
  forecasts: { h: number; month: string; val: number[] }[];
  model_anom: { year: number; val: number[] };
  boundary: Coordinates[][];
};
type LayerMode = 'observed' | 'season' | 'monthlyAnomaly' | 'seasonAnomaly' | 'forecast' | 'model';

const layerOptions: Record<LayerMode, { label: string; help: string }> = {
  observed: { label: 'Focos por mes', help: 'Mira cuántas detecciones hubo en el mes elegido.' },
  season: { label: 'Focos de agosto a octubre', help: 'Mira el total de detecciones de esta temporada para el año elegido.' },
  monthlyAnomaly: { label: 'Mes comparado con lo habitual', help: 'Compara las detecciones con lo habitual para ese mismo mes. Naranja indica más y azul indica menos.' },
  seasonAnomaly: { label: 'Temporada comparada con lo habitual', help: 'Compara agosto a octubre del año elegido con esa misma temporada en los años de referencia.' },
  forecast: { label: 'Estimaciones archivadas para 2026', help: 'Valores que estimó el modelo en el archivo de mapa3. El mapa de focos por mes muestra las detecciones observadas.' },
  model: { label: 'Temporada frente al modelo', help: 'Compara las detecciones de la temporada con lo que había estimado el modelo.' },
};

const homeCamera = { longitude: -64.7, latitude: -16.55, zoom: 4.85, pitch: 43, bearing: -14, minZoom: 3, maxZoom: 11 };
const cities = [
  { name: 'La Paz', position: [-68.15, -16.50] as Coordinates }, { name: 'Santa Cruz', position: [-63.18, -17.78] as Coordinates },
  { name: 'Cochabamba', position: [-66.16, -17.39] as Coordinates }, { name: 'Sucre', position: [-65.26, -19.04] as Coordinates },
  { name: 'Trinidad', position: [-64.90, -14.83] as Coordinates }, { name: 'Cobija', position: [-68.77, -11.03] as Coordinates },
  { name: 'Tarija', position: [-64.73, -21.53] as Coordinates }, { name: 'Oruro', position: [-67.12, -17.97] as Coordinates },
  { name: 'Potosí', position: [-65.75, -19.58] as Coordinates },
];

const dateLabel = (period: string) => {
  const [year, month] = period.split('-').map(Number);
  return new Intl.DateTimeFormat('es-BO', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(Date.UTC(year, month - 1, 1));
};

function sliceFor(data: Archive, months: number[]) {
  const size = data.lat.length;
  return data.lat.map((_, cell) => months.reduce((total, month) => total + data.counts[month * size + cell], 0));
}

function cellsFor(archive: Archive, mode: LayerMode, period: string, year: number, horizon: number) {
  const seasonal = mode === 'season' || mode === 'seasonAnomaly';
  const months = seasonal ? archive.season : [Number(period.split('-')[1])];
  const selected = seasonal ? year : Number(period.split('-')[0]);
  const indices = (y: number) => months.map((m) => (y - archive.y0) * 12 + m - 1).filter((index) => index >= 0 && index < archive.months.length);
  const forecast = archive.forecasts.find((entry) => entry.h === horizon);
  const observed = mode === 'forecast' ? (forecast?.val ?? [])
    : mode === 'model' ? archive.model_anom.val : sliceFor(archive, indices(selected));
  const anomaly = mode === 'monthlyAnomaly' || mode === 'seasonAnomaly';
  const baselines = anomaly
    ? Array.from({ length: archive.base[1] - archive.base[0] + 1 }, (_, i) => sliceFor(archive, indices(archive.base[0] + i))) : [];
  return observed.map((value, index) => {
    let average: number | undefined;
    let score = value;
    if (anomaly) {
      average = baselines.reduce((sum, slice) => sum + slice[index], 0) / baselines.length;
      const variance = baselines.reduce((sum, slice) => sum + (slice[index] - average!) ** 2, 0) / Math.max(1, baselines.length - 1);
      const hasSignal = seasonal ? average >= 1 || value >= 3 : average >= .3 || value >= 2;
      score = hasSignal ? (value - average) / Math.max(1, Math.sqrt(average), Math.sqrt(variance)) : 0;
    }
    return { index, position: [archive.lon[index], archive.lat[index]] as Coordinates, score, value, average };
  });
}

function FireArchive({ archive }: { archive: Archive }) {
  const [mode, setMode] = useState<LayerMode>('observed');
  // The archive's 2024 fire season is also the reference year used in the original map's model comparison.
  const [year, setYear] = useState(archive.months.includes(`${archive.model_anom.year}-09`) ? archive.model_anom.year : Number(archive.months.at(-1)?.slice(0, 4)));
  const [month, setMonth] = useState('09');
  const [horizon, setHorizon] = useState(archive.forecasts[0]?.h ?? 1);
  const [view, setView] = useState<MapViewState>(homeCamera);
  const camera = useRef<MapViewState>(homeCamera);
  const flat = view.pitch === 0;
  const [unavailable, setUnavailable] = useState(false);
  const [picked, setPicked] = useState<number>();
  const years = [...new Set(archive.months.map((period) => Number(period.slice(0, 4))))].reverse();
  const months = archive.months.filter((period) => period.startsWith(String(year)));
  const period = months.find((entry) => entry.endsWith(month)) ?? months.at(-1) ?? archive.months.at(-1)!;
  const cells = useMemo(() => cellsFor(archive, mode, period, year, horizon), [archive, mode, period, year, horizon]);
  const comparison = mode === 'model' || mode.endsWith('Anomaly');
  const active = cells.find((cell) => cell.index === picked);
  const maximum = Math.max(1, ...cells.map((cell) => Math.abs(cell.score)));
  const mapped = cells.filter((cell) => cell.score !== 0);
  const forecast = archive.forecasts.find((entry) => entry.h === horizon);
  const seasonal = mode === 'season' || mode === 'seasonAnomaly';
  const periodLabel = seasonal ? `Agosto a octubre de ${year}` : mode === 'model' ? `Agosto a octubre de ${archive.model_anom.year}`
    : dateLabel(mode === 'forecast' && forecast ? forecast.month : period);
  const shownValue = (cell: typeof cells[number]) => cell.average != null
    ? `${number(cell.value)} focos observados · ${number(cell.average, 1)} habituales`
    : mode === 'model' ? `${signed(cell.value, 1)} focos frente a lo esperado`
      : `${number(cell.value, mode === 'forecast' ? 1 : 0)} focos ${mode === 'forecast' ? 'estimados' : 'observados'}`;
  function moveCamera(next: MapViewState) {
    camera.current = next;
    setView({ ...next });
  }

  const layers = [
    new PolygonLayer<Position[]>({ id: 'bolivia-fire-boundary', data: archive.boundary.map((ring) =>
      ring.map(([lon, lat]) => [lon, lat, flat ? 0 : -16000] as Position)), getPolygon: (ring) => ring,
      extruded: !flat, getElevation: 13500, getFillColor: [45, 75, 117], getLineColor: [130, 163, 212], lineWidthMinPixels: 1.4 }),
    new PolygonLayer<Coordinates[]>({ id: 'bolivia-fire-border', data: archive.boundary, getPolygon: (ring) => ring,
      filled: false, getLineColor: [130, 163, 212], lineWidthMinPixels: 1.2 }),
    new ColumnLayer<typeof cells[number]>({ id: 'fire-grid', data: mapped, getPosition: (cell) => cell.position,
      radius: 8800, diskResolution: 4, angle: 45, extruded: !flat, pickable: true, autoHighlight: true,
      getElevation: (cell) => Math.sqrt(Math.abs(cell.score) / maximum) * 84000,
      getFillColor: (cell) => cell.score < 0 ? [88, 164, 255] :
        [255, Math.round(192 - 115 * Math.sqrt(cell.score / maximum)), 76],
      onClick: ({ object }) => { if (object) setPicked(object.index); } }),
    new ScatterplotLayer<typeof cells[number]>({ id: 'selected-fire-zone', data: active ? [active] : [],
      getPosition: (cell) => [cell.position[0], cell.position[1], flat ? 0 : Math.sqrt(Math.abs(cell.score) / maximum) * 84000],
      radiusUnits: 'pixels', getRadius: 15, getLineColor: [240, 255, 154], filled: false, stroked: true, lineWidthMinPixels: 2.5,
      parameters: { depthCompare: 'always', depthWriteEnabled: false } }),
    new TextLayer({ id: 'fire-place-names', data: cities, getPosition: (city) => city.position, getText: (city) => city.name,
      getSize: 12, getColor: [239, 247, 255], background: true, getBackgroundColor: [8, 18, 38, 223],
      backgroundPadding: [4, 2], billboard: true, characterSet: 'auto',
      parameters: { depthCompare: 'always', depthWriteEnabled: false } }),
  ];

  return <section id="mapa-incendios" className="panel mission-data-panel fire-archive" aria-labelledby="fire-map-title" tabIndex={-1}>
    <div className="mission-chart-heading">
      <div><p className="mission-eyebrow">Archivo satelital</p><h2 id="fire-map-title">¿Dónde se detectó más calor?</h2>
        <p>Elige un mes o una temporada y toca una barra para ver los focos de esa zona.</p></div>
      <div className="camera-switch" role="group" aria-label="Vista del mapa de incendios">
        <button type="button" aria-pressed={!flat} onClick={() => moveCamera({ ...camera.current, pitch: homeCamera.pitch, bearing: homeCamera.bearing })}><Box size={16} aria-hidden="true" /> 3D</button>
        <button type="button" aria-pressed={flat} onClick={() => moveCamera({ ...camera.current, pitch: 0, bearing: 0 })}><MapIcon size={16} aria-hidden="true" /> 2D</button>
      </div>
    </div>
    <div className="fire-controls">
      <label htmlFor="fire-map-layer"><span id="fire-map-layer-label">Qué quieres ver</span>
        <select id="fire-map-layer" aria-labelledby="fire-map-layer-label" value={mode} onChange={(event) => {
        setMode(event.target.value as LayerMode);
        setPicked(undefined);
      }}>{Object.entries(layerOptions).map(([key, option]) => <option key={key} value={key}>{option.label}</option>)}</select></label>
      {mode === 'forecast' ? <label htmlFor="fire-map-horizon"><span id="fire-map-horizon-label">Mes estimado</span>
        <select id="fire-map-horizon" aria-labelledby="fire-map-horizon-label" value={horizon}
        onChange={(event) => { setHorizon(Number(event.target.value)); setPicked(undefined); }}>
        {archive.forecasts.map((entry) => <option value={entry.h} key={entry.h}>{dateLabel(entry.month)}</option>)}
      </select></label> : mode !== 'model' && <>
        <label htmlFor="fire-map-year"><span id="fire-map-year-label"><CalendarDays size={15} aria-hidden="true" /> Año</span>
          <select id="fire-map-year" aria-labelledby="fire-map-year-label" value={year} onChange={(event) => { setYear(Number(event.target.value)); setPicked(undefined); }}>
            {years.map((option) => <option key={option}>{option}</option>)}
          </select></label>
        {!seasonal && <label htmlFor="fire-map-month"><span id="fire-map-month-label">Mes</span>
          <select id="fire-map-month" aria-labelledby="fire-map-month-label" value={period} onChange={(event) => {
          setMonth(event.target.value.slice(5));
          setPicked(undefined);
        }}>{months.map((entry) => <option key={entry} value={entry}>{dateLabel(entry).split(' de ')[0]}</option>)}</select></label>}
      </>}
    </div>
    <p className="fire-map-hint"><CircleHelp size={17} aria-hidden="true" /> {layerOptions[mode].help}
      {mode.endsWith('Anomaly') && ` Referencia ${archive.base.join('–')}.`}</p>
    <div className="fire-map-stage">
      {unavailable ? <p className="map-notice" role="status">El mapa interactivo necesita WebGL. Los datos del periodo están debajo.</p>
        : <DeckGL initialViewState={view} controller={{ scrollZoom: false, dragRotate: !flat, touchRotate: !flat }} layers={layers}
          onViewStateChange={({ viewState }) => { camera.current = viewState as MapViewState; }}
          onError={(error) => { if (/context|webgl|device/i.test(error.message)) setUnavailable(true); }}
          getTooltip={({ object }) => object?.position ? { text: `${periodLabel}\n${shownValue(object)}\n${number(Math.abs(object.position[1]), 2)}° S · ${number(Math.abs(object.position[0]), 2)}° O`,
            className: 'mission-map-tooltip' } : null} />}
      {!unavailable && <div className="fire-map-zoom" role="group" aria-label="Zoom del mapa de incendios">
        <button type="button" aria-label="Acercar" onClick={() => moveCamera({ ...camera.current, zoom: Math.min(homeCamera.maxZoom, camera.current.zoom + .7) })}><Plus size={19} aria-hidden="true" /></button>
        <button type="button" aria-label="Alejar" onClick={() => moveCamera({ ...camera.current, zoom: Math.max(homeCamera.minZoom, camera.current.zoom - .7) })}><Minus size={19} aria-hidden="true" /></button>
        <button type="button" aria-label="Restablecer vista de incendios" onClick={() => moveCamera(flat ? { ...homeCamera, pitch: 0, bearing: 0 } : homeCamera)}><RotateCcw size={17} aria-hidden="true" /></button>
      </div>}
      <p className="fire-map-credit">NASA FIRMS · MODIS Terra</p>
    </div>
    <div className="fire-map-readout" aria-live="polite">
      <div><strong>{periodLabel}</strong><span>{comparison
        ? `${number(mapped.filter((cell) => cell.score > 0).length)} zonas por encima de la referencia en el mapa`
        : `${number(cells.reduce((sum, cell) => sum + cell.value, 0), mode === 'forecast' ? 1 : 0)} focos ${mode === 'forecast' ? 'estimados' : 'detectados'} en las zonas del archivo`}</span></div>
      {active ? <div><strong>{number(Math.abs(active.position[1]), 2)}° S · {number(Math.abs(active.position[0]), 2)}° O</strong>
        <span>{shownValue(active)}</span><button type="button" onClick={() => setPicked(undefined)}>Quitar selección</button></div>
        : <div><strong className="fire-map-key"><i />{comparison ? 'Por encima' : 'Más focos'}{comparison && <><i /> Por debajo</>}</strong>
          <span>Cada barra representa una zona de aproximadamente {number(111 * archive.res)} km de lado. Su altura representa detecciones o diferencia respecto a la referencia, según la capa elegida.</span></div>}
    </div>
    <details className="mission-table-expand">
      <summary>Cómo se armó este mapa</summary>
      <p>Datos de {dateLabel(archive.months[0])} a {dateLabel(archive.months.at(-1)!)}, con detecciones de vegetación y confianza de 50 o más.
        Se incluyeron las {number(archive.lat.length)} zonas seleccionadas por el estudio original.
        Una detección indica calor visto por el satélite. Un incendio puede generar varias detecciones.</p>
      <a href={`https://github.com/gustavoantequerat-del/Earth-System-Detective/blob/${archive.source.commit}/${archive.source.file}`}>Ver mapa de origen en mapa3</a>
    </details>
  </section>;
}

export default function FireHistory() {
  const [archive, setArchive] = useState<Archive>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const request = new AbortController();
    api<Archive>('fires/map', { signal: request.signal }).then(setArchive).catch((error: Error) => {
      if (!request.signal.aborted) setError(error.message);
    });
    return () => request.abort();
  }, [attempt]);
  if (archive) return <FireArchive archive={archive} />;
  return <section id="mapa-incendios" className="panel mission-data-panel" tabIndex={-1}>
    <h2>Mapa histórico de focos</h2>
    {error ? <div className="notice danger" role="alert"><p>{error}</p>
      <button type="button" onClick={() => { setError(''); setAttempt((value) => value + 1); }}>Reintentar</button></div>
      : <p role="status" className="loading">Cargando el archivo MODIS…</p>}
  </section>;
}
