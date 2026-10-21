import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";
import type { CyElements } from "../api/types";

/**
 * Positions: investigated accounts sit on a large circle; each counterparty is
 * placed at the centre of the accounts it connects to (plus a small deterministic
 * jitter), so counterparties shared by the same accounts form visible clusters.
 */
function positions(elements: CyElements): Record<string, { x: number; y: number }> {
  const subjects = elements.nodes.filter((n) => n.data.is_subject).map((n) => n.data.id);
  const pos: Record<string, { x: number; y: number }> = {};
  const R = 400;
  subjects.forEach((id, i) => {
    const a = (2 * Math.PI * i) / Math.max(subjects.length, 1) - Math.PI / 2;
    pos[id] = { x: R * Math.cos(a), y: R * Math.sin(a) };
  });
  const nbrs: Record<string, string[]> = {};
  for (const e of elements.edges) {
    const { source, target } = e.data;
    if (pos[source] && !pos[target]) (nbrs[target] ??= []).push(source);
    if (pos[target] && !pos[source]) (nbrs[source] ??= []).push(target);
  }
  let k = 0;
  for (const n of elements.nodes) {
    if (pos[n.data.id]) continue;
    const linked = nbrs[n.data.id] ?? [];
    const cx = linked.length ? linked.reduce((s, id) => s + pos[id].x, 0) / linked.length : 0;
    const cy = linked.length ? linked.reduce((s, id) => s + pos[id].y, 0) / linked.length : 0;
    const a = k * 2.399963; // golden angle spiral keeps the cluster compact and deterministic
    const r = 9 * Math.sqrt(k++ % 400);
    pos[n.data.id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }
  return pos;
}

/**
 * Cytoscape view of a ring. Subject accounts are large dark nodes; counterparties
 * are sized by degree so hubs stand out. Clicking a subject calls onSelect(id).
 */
export function RingGraph({ elements, onSelect, height = 520 }: {
  elements: CyElements;
  onSelect?: (id: string, isSubject: boolean) => void;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const cy = cytoscape({
      container: ref.current,
      elements: [...elements.nodes, ...elements.edges] as cytoscape.ElementDefinition[],
      style: [
        { selector: "node", style: { width: "mapData(degree, 1, 6, 6, 18)", height: "mapData(degree, 1, 6, 6, 18)", "background-color": "#718096" } },
        { selector: "node[?is_subject]", style: { width: 40, height: 40, "background-color": "#1a365d", label: "data(label)", color: "#1a365d", "font-weight": "bold", "text-valign": "bottom", "text-margin-y": 4 } },
        { selector: "node[degree >= 3][!is_subject]", style: { "background-color": "#d69e2e" } },
        { selector: "edge", style: { width: 0.6, "line-color": "#cbd5e0", "curve-style": "haystack", opacity: 0.6 } },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#e53e3e" } },
      ],
      layout: { name: "preset", positions: positions(elements), fit: true, padding: 30 },
      wheelSensitivity: 0.2,
    });
    cy.on("tap", "node", (e) => onSelect?.(e.target.id(), !!e.target.data("is_subject")));
    return () => cy.destroy();
  }, [elements, onSelect]);
  return <div ref={ref} className="graph" style={{ height }} />;
}
