'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, CircleHelp, Compass, X } from 'lucide-react';

const guides = {
  panorama: [
    { title: 'Elige qué explorar', text: 'Lagos reúne el mapa, la tabla y las fichas. Incendios muestra focos térmicos. Vegetación explica qué cambió en el suelo alrededor del agua.', target: 'explorar' },
    { title: 'Lee los diagnósticos en conjunto', text: 'El gráfico muestra cuántos cuerpos de agua hay en cada categoría. Puedes elegir entre el análisis completo y el barrido nacional.', target: 'diagnosticos-inicio' },
    { title: 'Abre un caso', text: 'Cada caso reúne el cambio en la superficie de agua y su diagnóstico. Entra a la ficha para ver imágenes y pruebas.', target: 'casos-lagos' },
  ],
  mapa: [
    { title: 'Encuentra un lago por nombre', text: 'Escribe Poopó, Titicaca u otro nombre. Elige un resultado y el mapa se acercará al lugar.', target: 'buscar-lago' },
    { title: 'Lee el mapa', text: 'Las gotas señalan lagos con ficha completa. Pasa el mouse para leer el cambio de agua y el diagnóstico. En celular, toca la gota o el punto.', target: 'mapa-lagos' },
    { title: 'Entiende los colores', text: 'Cada color representa un diagnóstico. Pasa el mouse por la tarjeta o tócala para ver qué significa esa categoría.', target: 'diagnosticos-map' },
  ],
  monitoreo: [
    { title: 'Busca o filtra la tabla', text: 'Escribe el nombre y usa los filtros para ver solo un diagnóstico o un tipo de análisis.', target: 'filtros-monitoreo' },
    { title: 'Lleva los datos contigo', text: 'Descargar CSV guarda las filas que ves después de aplicar los filtros. Los nombres con flecha abren una ficha completa.', target: 'datos-monitoreo' },
  ],
  ficha: [
    { title: 'Empieza por el resumen', text: 'Mira cuánto cambió la superficie del lago. El texto debajo del diagnóstico cuenta lo que las pruebas permiten concluir.', target: 'resumen-ficha' },
    { title: 'Observa los cambios desde satélite', text: 'En «Antes y después», arrastra el control de la imagen. Puedes cambiar las fechas o mirar el lago y sus alrededores.', target: 'secciones-ficha' },
    { title: 'Consulta las pruebas', text: 'Abre «Pruebas y posibles causas» para ver qué se evaluó. En «Auditoría» está el historial técnico de revisiones y resultados.', target: 'secciones-ficha' },
  ],
  vigilancia: [
    { title: 'Explora el archivo desde el mapa', text: 'Elige año y mes. Las barras más altas representan más detecciones en la vista «Focos por mes». Pasa el mouse o toca una barra para leer su valor.', target: 'mapa-incendios' },
    { title: 'Compara con lo habitual', text: 'En el selector del mapa puedes comparar un mes o la temporada de agosto a octubre con los años de referencia.', target: 'fire-map-layer' },
    { title: 'Revisa la semana guardada', text: 'El reporte compara los focos alrededor de cada lago con su promedio histórico. Mira la fecha y la etiqueta de simulacro cuando aparezca.', target: 'reporte-incendios' },
  ],
  vegetacion: [
    { title: 'Elige un lago y un indicador', text: 'Cada serie cuenta una parte del paisaje. Selecciona pérdida de bosque, superficie quemada, pasturas o cultivos y el área que quieres ver.', target: 'vegetation-series' },
    { title: 'Compara las imágenes', text: 'Las fotos muestran el paisaje en dos fechas. El mapa de cambios indica dónde aparecieron cambios de cobertura y cuántas hectáreas abarca cada tipo.', target: 'land-cover-images' },
  ],
} as const;

export type GuideView = keyof typeof guides;

export function Guide({ view }: { view: GuideView }) {
  const [index, setIndex] = useState(0);
  const [targetId, setTargetId] = useState<string>();
  const [targetMissing, setTargetMissing] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const steps = guides[view];
  const step = steps[index];
  const last = index === steps.length - 1;

  useEffect(() => {
    if (!targetId) return;
    const focusTarget = () => {
      const target = document.getElementById(targetId);
      if (!target || !dialog.current?.open) return false;
      dialog.current.close();
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: 'center' });
      return true;
    };
    if (focusTarget()) return;

    const observer = new MutationObserver(() => {
      if (focusTarget()) observer.disconnect();
    });
    const timeout = window.setTimeout(() => {
      setTargetId(undefined);
      setTargetMissing(true);
    }, 6000);
    observer.observe(document.getElementById('contenido') ?? document.body, { childList: true, subtree: true });
    return () => { observer.disconnect(); window.clearTimeout(timeout); };
  }, [targetId]);

  function changeStep(next: number) {
    setTargetId(undefined);
    setTargetMissing(false);
    setIndex(next);
  }

  return <>
    <button type="button" className="mission-guide-button" aria-haspopup="dialog" onClick={() => {
      changeStep(0);
      dialog.current?.showModal();
    }}><CircleHelp size={21} aria-hidden="true" /> Guía</button>
    <dialog className="mission-guide" ref={dialog} aria-labelledby="mission-guide-title" onClose={() => setTargetId(undefined)} onClick={(event) => {
      if (event.target === event.currentTarget) dialog.current?.close();
    }}>
      <div className="guide-content">
        <div className="guide-heading"><p><Compass size={19} aria-hidden="true" /> Guía de esta sección</p>
          <button type="button" aria-label="Cerrar la guía" onClick={() => dialog.current?.close()}><X size={20} aria-hidden="true" /></button></div>
        <div aria-live="polite" aria-atomic="true">
          <p className="guide-progress">Paso {index + 1} de {steps.length}</p>
          <h2 id="mission-guide-title">{step.title}</h2>
          <p>{step.text}</p>
        </div>
        <button type="button" className="guide-jump" disabled={!!targetId} onClick={() => {
          setTargetMissing(false);
          setTargetId(step.target);
        }}><ArrowDown size={16} aria-hidden="true" /> {targetId ? 'Buscando el control…' : 'Mostrar en la página'}</button>
        {targetMissing && <p className="muted" role="status">El control aún no está disponible. Cierra la guía para ver el estado de la sección.</p>}
        <div className="guide-actions">
          <button type="button" disabled={index === 0} onClick={() => changeStep(index - 1)}><ArrowLeft size={16} aria-hidden="true" /> Anterior</button>
          <button type="button" className="primary" onClick={() => last ? dialog.current?.close() : changeStep(index + 1)}>
            {last ? 'Terminar' : 'Siguiente'} {!last && <ArrowRight size={16} aria-hidden="true" />}
          </button>
        </div>
      </div>
    </dialog>
  </>;
}
