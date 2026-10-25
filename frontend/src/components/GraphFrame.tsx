import type cytoscape from "cytoscape";
import { useEffect, useRef, useState, type MutableRefObject, type RefObject } from "react";

/**
 * Frame around a Cytoscape canvas with easy view controls: zoom in / out,
 * fit to screen and full screen buttons. The mouse wheel scrolls the page as
 * usual; Ctrl/⌘ + wheel (or a trackpad pinch) zooms at the pointer, so a big
 * graph never traps the page scroll. Dragging the background moves the view.
 * The graph refits when the frame changes size.
 */
export function GraphFrame({ boxRef, cyRef, height, className = "", hint = true }: {
  boxRef: RefObject<HTMLDivElement>;
  cyRef: MutableRefObject<cytoscape.Core | undefined>;
  height: number | string;
  className?: string;
  hint?: boolean;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  const [nudge, setNudge] = useState(false);

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    let timer = 0;
    const onWheel = (e: WheelEvent) => {
      const cy = cyRef.current;
      if (!cy) return;
      if (!(e.ctrlKey || e.metaKey)) {
        setNudge(true);
        clearTimeout(timer);
        timer = window.setTimeout(() => setNudge(false), 1200);
        return;
      }
      e.preventDefault();
      const r = box.getBoundingClientRect();
      const level = cy.zoom() * Math.exp(-e.deltaY * 0.004);
      cy.zoom({ level: Math.min(cy.maxZoom(), Math.max(cy.minZoom(), level)), renderedPosition: { x: e.clientX - r.left, y: e.clientY - r.top } });
    };
    box.addEventListener("wheel", onWheel, { passive: false });
    // Safari sends trackpad pinches as gesture events rather than Ctrl + wheel
    let startZoom = 1;
    const onGestureStart = (e: Event) => { e.preventDefault(); startZoom = cyRef.current?.zoom() ?? 1; };
    const onGestureChange = (e: Event) => {
      const cy = cyRef.current;
      const g = e as Event & { scale: number; clientX: number; clientY: number };
      if (!cy) return;
      e.preventDefault();
      const r = box.getBoundingClientRect();
      const level = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), startZoom * g.scale));
      cy.zoom({ level, renderedPosition: { x: g.clientX - r.left, y: g.clientY - r.top } });
    };
    box.addEventListener("gesturestart", onGestureStart);
    box.addEventListener("gesturechange", onGestureChange);
    const ro = new ResizeObserver(() => {
      const cy = cyRef.current;
      if (!cy) return;
      cy.resize();
      cy.fit(undefined, 40);
    });
    ro.observe(box);
    const onFs = () => setFull(document.fullscreenElement === frame.current);
    document.addEventListener("fullscreenchange", onFs);
    return () => {
      clearTimeout(timer);
      box.removeEventListener("wheel", onWheel);
      box.removeEventListener("gesturestart", onGestureStart);
      box.removeEventListener("gesturechange", onGestureChange);
      ro.disconnect();
      document.removeEventListener("fullscreenchange", onFs);
    };
  }, [boxRef, cyRef]);

  const zoomBy = (f: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    const level = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), cy.zoom() * f));
    const { x1, x2, y1, y2 } = cy.extent();
    cy.animate({ zoom: { level, position: { x: (x1 + x2) / 2, y: (y1 + y2) / 2 } } }, { duration: 180 });
  };
  const fit = () => cyRef.current?.animate({ fit: { eles: cyRef.current.elements(), padding: 40 } }, { duration: 250 });
  const toggleFull = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else frame.current?.requestFullscreen?.();
  };

  return (
    <div ref={frame} className={`graph-frame ${className}`}>
      <div ref={boxRef} className="graph-canvas" style={{ height: full ? "100vh" : height }} />
      <div className="graph-tools">
        <button type="button" title="Zoom in" aria-label="Zoom in" onClick={() => zoomBy(1.35)}>+</button>
        <button type="button" title="Zoom out" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.35)}>−</button>
        <button type="button" title="Fit the whole graph on screen" onClick={fit}>Fit</button>
        <button type="button" title={full ? "Exit full screen" : "Full screen"} onClick={toggleFull}>{full ? "Exit full screen" : "Full screen"}</button>
      </div>
      {hint && <div className={`graph-hint${nudge ? " show" : ""}`}>
        Use the + and − buttons, or hold Ctrl / ⌘ and scroll to zoom. Drag the background to move around.
      </div>}
    </div>
  );
}
