import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';
import Database from 'better-sqlite3';
import { parse } from 'csv-parse/sync';

interface Result {
  body_id: string;
  control_id?: string;
  name: string;
  lat: number;
  lon: number;
  state: string;
  confidence: string;
  trend: { change_pct: number };
}

interface Place { lat: number; lon: number }
interface SuspectRow { body_id: string; year: string; suspect: string; value: string; area?: string }
interface Context { years: [number, number]; window_km: number; changes_ha: Record<string, number> }
interface Verification { lagunas?: Record<string, unknown> }

export const reviewOutcomes = ['En revision', 'Confirmado en campo', 'Falso positivo', 'Requiere mas datos'];

@Injectable()
export class ObservatoryService {
  private readonly root = resolve(__dirname, '../../');
  private readonly national = join(this.root, 'data', 'national');
  private readonly jsonCache = new Map<string, { mtime: number; size: number; value: unknown }>();

  private get data() {
    const configured = process.env.UMA_DATA;
    if (configured) return isAbsolute(configured) ? configured : resolve(this.root, configured);
    const real = join(this.root, 'data', 'real');
    return existsSync(join(real, 'results.json')) ? real : join(this.root, 'data', 'sample');
  }

  private json<T>(file: string, fallback: T): T {
    if (!existsSync(file)) return fallback;
    const { mtimeMs, size } = statSync(file);
    const previous = this.jsonCache.get(file);
    if (previous?.mtime === mtimeMs && previous.size === size) return previous.value as T;
    const contents = readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
    // Older Python exports emitted non-finite literals for unavailable measurements.
    const validJson = contents.replace(/"(?:\\.|[^"\\])*"|-?Infinity|NaN/g, (token) => token.startsWith('"') ? token : 'null');
    const value: T = JSON.parse(validJson);
    this.jsonCache.set(file, { mtime: mtimeMs, size, value });
    return value;
  }

  private modelDir(method?: string, dir = this.data) {
    if (method === 'conservative') return join(dir, 'validation');
    if (!method || method === 'balance') return dir;
    throw new BadRequestException('Método de análisis desconocido.');
  }

  private results(dir = this.data) {
    const file = join(dir, 'results.json');
    if (!existsSync(file)) throw new NotFoundException('No se encontró results.json.');
    return this.json<Result[]>(file, []);
  }

  private result(id: string, dir = this.data) {
    if (!/^[a-z0-9_]+$/i.test(id)) throw new NotFoundException('Cuerpo de agua no encontrado.');
    const result = this.results(dir).find((item) => item.body_id === id);
    if (!result) throw new NotFoundException('Cuerpo de agua no encontrado.');
    return result;
  }

  dashboard(method?: string) {
    const dir = this.data;
    return {
      results: this.results(this.modelDir(method, dir)),
      national: method === 'conservative' ? [] : this.json<Result[]>(join(this.national, 'results.json'), []),
      artificial: this.json(join(this.national, 'agua_artificial.json'), null),
      sample: dir === join(this.root, 'data', 'sample'),
      conservativeAvailable: existsSync(join(dir, 'validation', 'results.json')),
    };
  }

  places(id: string, dir = this.data) {
    this.result(id, dir);
    return this.json<Place[]>(join(dir, 'context', `${id}_lugares.json`), []);
  }

  detail(id: string, method?: string) {
    const dir = this.data;
    const result = this.result(id, this.modelDir(method, dir));
    const contextDir = join(dir, 'context');
    const context = ['antes', 'despues', 'cambios'].every((suffix) => existsSync(join(contextDir, `${id}_${suffix}.png`)))
      ? this.json<Context | null>(join(contextDir, `${id}_meta.json`), null)
      : null;
    const imagesDir = join(dir, 'img');
    const images = existsSync(imagesDir) ? new Set(readdirSync(imagesDir)) : new Set<string>();
    const imageYears = [...images].flatMap((filename) => {
      const match = filename.match(new RegExp(`^${id}_(\\d{4})\\.png$`));
      return match ? [{ year: Number(match[1]), mask: images.has(`${id}_${match[1]}_water.png`) }] : [];
    }).sort((a, b) => a.year - b.year);
    const csv = join(dir, 'suspects.csv');
    const waterTypes = new Set(['natural_water_ha', 'artificial_water_ha', 'mining_water_ha', 'desaguadero_water_ha']);
    const water = existsSync(csv) ? (parse(readFileSync(csv), {
      columns: true, skip_empty_lines: true, bom: true,
    }) as SuspectRow[]).flatMap((row) => (
      row.body_id === id && row.area && waterTypes.has(row.suspect) && row.value.trim() !== '' && Number.isFinite(Number(row.value))
        ? [{ area: row.area, year: Number(row.year), suspect: row.suspect, value: Number(row.value) }]
        : []
    )) : [];
    const verification = this.json<Verification | null>(join(dir, 'verificacion.json'), null)?.lagunas?.[id] ?? null;
    const river = id === 'poopo' || id === 'uru_uru' || id === 'titicaca_menor'
      ? this.json(join(dir, 'desaguadero.json'), null)
      : null;
    return { result, context, imageYears, places: this.places(id, dir), water, verification, river };
  }

  image(folder: string, filename: string) {
    if ((folder !== 'context' && folder !== 'img') || !/^[a-z0-9_]+\.png$/i.test(filename)) {
      throw new NotFoundException('Imagen no encontrada.');
    }
    const file = join(this.data, folder, filename);
    if (!existsSync(file)) throw new NotFoundException('Imagen no encontrada.');
    return readFileSync(file);
  }

  download(method?: string) {
    return Buffer.from(JSON.stringify(this.results(this.modelDir(method)), null, 2));
  }

  private withDb<T>(callback: (db: Database.Database) => T, fallback: T, write = false, dir = this.data) {
    const file = join(dir, 'uma.db');
    if (!existsSync(file)) return fallback;
    const db = new Database(file, { readonly: !write, fileMustExist: true });
    try {
      return callback(db);
    } finally {
      db.close();
    }
  }

  history(id: string, method?: string) {
    const dir = this.modelDir(method);
    this.result(id, dir);
    return this.withDb((db) => ({
      available: true,
      runs: db.prepare(`
        SELECT r.run_id AS corrida, r.created_at AS fecha, v.state AS estado, v.confidence AS confianza,
          v.n_pass AS pruebas, ROUND(v.change_pct) AS cambio_pct, v.control_id AS gemela,
          r.note AS nota, r.inputs_sha256 AS huella_datos, r.code_sha256 AS huella_codigo
        FROM verdicts v JOIN runs r USING(run_id) WHERE v.body_id = ? ORDER BY r.run_id DESC
      `).all(id),
      reviews: db.prepare(`
        SELECT created_at AS fecha, reviewer AS revisor, outcome AS resultado, comment AS comentario
        FROM reviews WHERE body_id = ? ORDER BY review_id DESC
      `).all(id),
      alerts: db.prepare(`
        SELECT state AS estado, opened_at AS abierta, closed_at AS cerrada, status AS situacion
        FROM alerts WHERE body_id = ? ORDER BY alert_id DESC
      `).all(id),
    }), { available: false, runs: [], reviews: [], alerts: [] }, false, dir);
  }

  review(id: string, body: Record<string, unknown> | undefined, method?: string) {
    const dir = this.modelDir(method);
    this.result(id, dir);
    const { reviewer, outcome, comment = '' } = body ?? {};
    if (typeof reviewer !== 'string' || !reviewer.trim() || reviewer.length > 200 ||
        typeof outcome !== 'string' || !reviewOutcomes.includes(outcome) ||
        typeof comment !== 'string' || comment.length > 5000) {
      throw new BadRequestException('Completa el nombre y el resultado de la revisión.');
    }
    const saved = this.withDb((db) => {
      db.prepare(`
        INSERT INTO reviews (body_id, run_id, created_at, reviewer, outcome, comment)
        VALUES (?, (SELECT MAX(run_id) FROM runs), ?, ?, ?, ?)
      `).run(id, new Date().toISOString(), reviewer.trim(), outcome, comment.trim());
      return true;
    }, false, true, dir);
    if (!saved) throw new NotFoundException('No hay una base de auditoría para estos datos.');
    return { saved };
  }

  weekly() {
    const report = this.json(join(this.data, 'alertas_semanales.json'), null);
    const history = this.withDb((db) => {
      const table = db.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'operational_alerts'").get();
      return table ? db.prepare(`
        SELECT week_end AS semana, body_id, area, fires AS focos, normal, alert AS alerta, notified AS aviso
        FROM operational_alerts ORDER BY week_end DESC
      `).all() : [];
    }, []);
    return { report, history };
  }
}
