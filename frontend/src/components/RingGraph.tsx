import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";
import type { CyElements } from "../api/types";
import { GraphFrame } from "./GraphFrame";

/** Colour per ring; accounts in no ring are slate. */
export const RING_COLORS = ["#4d83ff", "#8857ff", "#35d9e8", "#ff9d35", "#ff3d81", "#ffd166", "#7aa3ff", "#b39bff"];
export const NO_RING_COLOR = "#4a5b78";
export const ringColor = (ringId: string | null | undefined) =>
  ringId ? RING_COLORS[(Number(ringId.replace(/\D/g, "")) - 1) % RING_COLORS.length] : NO_RING_COLOR;

/**
 * Positions: investigated accounts that share counterparties sit on a circle,
 * grouped by ring; accounts that share nothing sit in a row underneath. Each
 * counterparty is placed at the centre of the accounts it connects to, in a
 * compact spiral per group, so counterparties shared by the same accounts form
 * one visible cluster.
 */
function positions(elements: CyElements): { pos: Record<string, { x: number; y: number }>; R: number } {
  const linked = new Set(elements.edges.flatMap((e) => [e.data.source, e.data.target]));
  const subjects = elements.nodes.filter((n) => n.data.is_subject).map((n) => n.data);
  const byRing = (a: (typeof subjects)[0], b: (typeof subjects)[0]) =>
    (a.ring_id ?? "~").localeCompare(b.ring_id ?? "~", undefined, { numeric: true }) || a.id.localeCompare(b.id, undefined, { numeric: true });
  const onCircle = subjects.filter((s) => linked.has(s.id)).sort(byRing);
  const alone = subjects.filter((s) => !linked.has(s.id)).sort(byRing);
  const pos: Record<string, { x: number; y: number }> = {};
  const R = Math.max(400, 110 * onCircle.length);
  onCircle.forEach((s, i) => {
    const a = (2 * Math.PI * i) / Math.max(onCircle.length, 1) - Math.PI / 2;
    pos[s.id] = { x: R * Math.cos(a), y: R * Math.sin(a) };
  });
  const perRow = 9, gap = (2 * R) / (perRow - 1);
  alone.forEach((s, i) => {
    pos[s.id] = { x: -R + (i % perRow) * gap, y: R + 220 + Math.floor(i / perRow) * 120 };
  });
  const nbrs: Record<string, string[]> = {};
  for (const e of elements.edges) {
    const { source, target } = e.data;
    if (pos[source] && !pos[target]) (nbrs[target] ??= []).push(source);
    if (pos[target] && !pos[source]) (nbrs[source] ??= []).push(target);
  }
  const counters: Record<string, number> = {};
  for (const n of elements.nodes) {
    if (pos[n.data.id]) continue;
    const ids = (nbrs[n.data.id] ?? []).sort();
    const key = ids.join("|");
    const cx = ids.length ? ids.reduce((s, id) => s + pos[id].x, 0) / ids.length : 0;
    const cy = ids.length ? ids.reduce((s, id) => s + pos[id].y, 0) / ids.length : 0;
    const k = (counters[key] = (counters[key] ?? 0) + 1);
    const a = k * 2.399963; // golden angle spiral keeps the cluster compact and deterministic
    const r = 7 * Math.sqrt(k);
    pos[n.data.id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }
  return { pos, R };
}

export interface GraphSelection {
  /** the clicked node, or the counterparty end of a clicked link */
  ref: string;
  isSubject: boolean;
  /** set when a link was clicked: the investigated account at its other end */
  account?: string;
}

/**
 * Cytoscape view of the network (one ring or all of it). Investigated accounts
 * are large nodes coloured by ring; counterparties are small, gold when linked
 * to 3+ accounts. Clicking a node or a link calls onSelect; the clicked node
 * and its links are highlighted.
 */
export function RingGraph({ elements, onSelect, height = 520 }: {
  elements: CyElements;
  onSelect?: (sel: GraphSelection) => void;
  height?: number | string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core>();
  useEffect(() => {
    if (!ref.current) return;
    const subjects = new Set(elements.nodes.filter((n) => n.data.is_subject).map((n) => n.data.id));
    const { pos, R } = positions(elements);
    const big = R / 400; // account dots and labels grow with the graph so they stay readable when it is fitted
    const cy = cytoscape({
      container: ref.current,
      elements: [...elements.nodes, ...elements.edges] as cytoscape.ElementDefinition[],
      style: [
        { selector: "node", style: { width: "mapData(degree, 1, 6, 6, 18)", height: "mapData(degree, 1, 6, 6, 18)", "background-color": "#5d6f8c" } },
        { selector: "node[?is_subject]", style: {
          width: 40 * big, height: 40 * big, "background-color": (n: cytoscape.NodeSingular) => ringColor(n.data("ring_id")),
          label: "data(label)", color: "#edf3ff", "font-weight": "bold", "font-size": 16 * big, "text-valign": "bottom", "text-margin-y": 4,
        } },
        { selector: "node[degree >= 3][!is_subject]", style: { "background-color": "#ffd166" } },
        { selector: "edge", style: { width: 0.6, "line-color": "#2a3d5c", "curve-style": "haystack", opacity: 0.7 } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: "edge.hl", style: { width: 2, "line-color": "#ff3d81", opacity: 1 } },
        { selector: "node.hl", style: { "border-width": 3, "border-color": "#ff3d81" } },
      ],
      layout: { name: "preset", positions: pos, fit: true, padding: 30 },
      userZoomingEnabled: false, // GraphFrame zooms with buttons, Ctrl/⌘ + wheel or a pinch
      minZoom: 0.05,
      maxZoom: 4,
    });
    cyRef.current = cy;
    const highlight = (els: cytoscape.Collection) => {
      cy.elements().removeClass("hl").addClass("faded");
      els.removeClass("faded").addClass("hl");
    };
    cy.on("tap", "node", (e) => {
      const n = e.target as cytoscape.NodeSingular;
      highlight(n.closedNeighborhood());
      onSelect?.({ ref: n.id(), isSubject: !!n.data("is_subject") });
    });
    cy.on("tap", "edge", (e) => {
      const edge = e.target as cytoscape.EdgeSingular;
      const { source, target } = edge.data();
      highlight(edge.union(edge.connectedNodes()));
      const account = subjects.has(source) ? source : target;
      const other = account === source ? target : source;
      onSelect?.({ ref: other, isSubject: subjects.has(other), account });
    });
    cy.on("tap", (e) => {
      if (e.target === cy) cy.elements().removeClass("hl faded");
    });
    return () => {
      cyRef.current = undefined;
      cy.destroy();
    };
  }, [elements, onSelect]);
  return <GraphFrame boxRef={ref} cyRef={cyRef} height={height} />;
}
