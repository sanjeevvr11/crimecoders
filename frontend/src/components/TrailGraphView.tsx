import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";
import type { TrailChain, TrailGraph } from "../api/types";
import { inrShort } from "./format";
import { GraphFrame } from "./GraphFrame";

export type TrailSelection =
  | { type: "node"; ref: string }
  | { type: "edge"; source: string; target: string }
  | null;

const GAP = 260; // px between hop columns
const SUB = 130; // px between sub-columns when a hop has many nodes
const ROW = 64; // px between nodes in a column
const PER_COL = 9; // nodes per sub-column before wrapping
const TIER_RING: Record<string, string> = { HIGH: "#ff304f", MEDIUM: "#ff9d35", LOW: "#4d83ff" };

/**
 * Hop columns: money sources on the left (negative levels), the investigated
 * account in the middle, destinations on the right. Inside a column the
 * largest flows sit nearest the middle row; a hop with many nodes wraps into
 * several sub-columns so the picture stays wide rather than tall. Linked
 * investigated accounts at level 0 are stacked above and below the start.
 */
function layout(g: TrailGraph) {
  const pos: Record<string, { x: number; y: number }> = {};
  const byLevel = new Map<number, typeof g.nodes>();
  for (const n of g.nodes) byLevel.set(n.level, [...(byLevel.get(n.level) ?? []), n]);
  const width = (l: number) => (Math.ceil((byLevel.get(l)?.length ?? 0) / PER_COL) - 1) * SUB;
  // x of each column's first sub-column (nearest the start), walking outwards from 0;
  // a side may skip a hop number, so walk the levels that exist, not 1, 2, 3
  const colX = new Map<number, number>([[0, 0]]);
  const levels = [...byLevel.keys()].sort((a, b) => a - b);
  for (const side of [1, -1]) {
    let edge = 0;
    for (const l of levels.filter((x) => Math.sign(x) === side).sort((a, b) => Math.abs(a) - Math.abs(b))) {
      colX.set(l, edge + side * GAP);
      edge = colX.get(l)! + side * width(l);
    }
  }
  for (const [level, ns] of byLevel) {
    if (level === 0) {
      ns.filter((n) => n.is_start).forEach((n) => (pos[n.ref] = { x: 0, y: 0 }));
      ns.filter((n) => !n.is_start).forEach((n, i) => (pos[n.ref] = { x: 0, y: (i % 2 ? 1 : -1) * 170 * Math.ceil((i + 1) / 2) }));
      continue;
    }
    const side = Math.sign(level);
    const sorted = [...ns].sort((a, b) => Math.max(b.amount_in, b.amount_out) - Math.max(a.amount_in, a.amount_out));
    const rows = Math.min(PER_COL, sorted.length);
    sorted.forEach((n, i) => {
      const sub = Math.floor(i / PER_COL), j = i % PER_COL;
      // 0, +1, -1, +2, -2 ... rows so the biggest flows stay central
      const k = j === 0 ? 0 : (j % 2 ? 1 : -1) * Math.ceil(j / 2);
      const stagger = sub % 2 ? ROW / 2 : 0;
      pos[n.ref] = { x: colX.get(level)! + side * sub * SUB, y: k * ROW + (rows > 1 ? stagger : 0) };
    });
  }
  const top = Math.min(...Object.values(pos).map((p) => p.y), 0) - 80;
  const heads = levels.map((l) => ({ level: l, x: colX.get(l)! + Math.sign(l) * width(l) / 2 }));
  return { pos, heads, top };
}

function columnTitle(level: number) {
  if (level === 0) return "UNDER INVESTIGATION";
  const h = Math.abs(level);
  return level < 0 ? `SOURCE · ${h} HOP${h > 1 ? "S" : ""} BACK` : `DESTINATION · ${h} HOP${h > 1 ? "S" : ""} ON`;
}

/**
 * Money trail graph: blue transfers with moving dashes in the direction
 * money flowed (thicker = more money), dotted teal links where a counterparty also deals with another investigated
 * account. `chain` highlights one chain end to end with amounts on each hop.
 */
export function TrailGraphView({ graph, chain, selection, onSelect, height = "calc(100vh - 120px)" }: {
  graph: TrailGraph;
  chain?: TrailChain | null;
  selection?: TrailSelection;
  onSelect?: (sel: TrailSelection) => void;
  height?: number | string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core>();
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;

  useEffect(() => {
    if (!box.current) return;
    const { pos, heads: cols, top } = layout(graph);
    const maxAmt = Math.max(1, ...graph.edges.map((e) => e.amount));
    const heads = cols.map(({ level: l, x }) => ({
      data: { id: `__col${l}`, display: columnTitle(l) },
      position: { x, y: top },
      classes: "colhead",
      selectable: false,
      grabbable: false,
    }));
    const cy = cytoscape({
      container: box.current,
      elements: [
        ...heads,
        ...graph.nodes.map((n) => ({
          data: { ...n, id: n.ref, display: n.is_subject ? `${n.label}\n${n.risk_score?.toFixed(0) ?? ""}` : n.label },
          position: pos[n.ref],
          classes: [n.is_subject ? "subject" : `cp kind-${n.kind}`, n.is_start ? "start" : "", n.circular ? "circular" : ""].join(" "),
        })),
        ...graph.edges.map((e) => ({
          data: { ...e, id: `${e.source}->${e.target}`, w: 1.5 + 7 * Math.sqrt(e.amount / maxAmt), amt: inrShort(e.amount) },
          classes: e.link,
        })),
      ] as cytoscape.ElementDefinition[],
      style: [
        { selector: "node", style: {
          label: "data(display)", color: "#a9b8d0", "font-size": 13, "text-valign": "bottom", "text-margin-y": 6,
          "text-wrap": "wrap", "text-max-width": "140px", "background-color": "#091323", "border-width": 2, "border-color": "#6f8db8",
          width: 26, height: 26,
        } },
        { selector: "node.kind-upi", style: { shape: "round-rectangle", "border-color": "#35d9e8" } },
        { selector: "node.kind-ifsc", style: { shape: "diamond", width: 30, height: 30, "border-color": "#8857ff" } },
        { selector: "node.kind-account", style: { shape: "rectangle", "border-color": "#4d83ff" } },
        { selector: "node.kind-name", style: { shape: "ellipse", "border-color": "#8a9bb6" } },
        { selector: "node.subject", style: {
          width: 54, height: 54, "background-color": "#0d192b", "border-width": 4, "font-size": 13, "font-weight": "bold",
          color: "#edf3ff", "text-valign": "center", "text-margin-y": 0,
          "border-color": (n: cytoscape.NodeSingular) => TIER_RING[n.data("tier")] ?? "#a0aec0",
        } },
        { selector: "node.circular", style: { "border-style": "double", "border-width": 7 } },
        { selector: "node.start", style: {
          width: 84, height: 84, "font-size": 16, "underlay-color": "#ff304f", "underlay-opacity": 0.3, "underlay-padding": 14,
          "underlay-shape": "ellipse",
        } as cytoscape.Css.Node },
        { selector: "node.colhead", style: {
          shape: "rectangle", width: 1, height: 1, "background-opacity": 0, "border-width": 0, color: "#a9b8d0",
          "font-size": 15, "font-weight": "bold", "text-valign": "center", "text-margin-y": 0, events: "no",
        } },
        { selector: "edge", style: {
          width: "data(w)", "line-color": "#4d83ff", "target-arrow-color": "#7aa3ff", "target-arrow-shape": "triangle",
          "arrow-scale": 0.9, "curve-style": "bezier", opacity: 0.75, "line-style": "dashed", "line-dash-pattern": [10, 6],
        } },
        { selector: "edge.shared", style: {
          "line-color": "#35d9e8", "target-arrow-color": "#35d9e8", "line-dash-pattern": [3, 6], width: 1.5, opacity: 0.8,
        } },
        { selector: ".faded", style: { opacity: 0.1 } },
        { selector: "node.hl", style: { "border-color": "#ff3d81", "border-width": 4 } },
        { selector: "edge.hl", style: {
          "line-color": "#ff3d81", "target-arrow-color": "#ff3d81", opacity: 1, label: "data(amt)", color: "#edf3ff",
          "font-size": 12, "font-weight": "bold", "text-background-color": "#030711", "text-background-opacity": 0.9,
          "text-background-padding": "3px", "z-index": 10,
        } },
      ],
      layout: { name: "preset", fit: true, padding: 40 },
      userZoomingEnabled: false, // GraphFrame zooms with buttons, Ctrl/⌘ + wheel or a pinch
      minZoom: 0.2,
      maxZoom: 3,
    });
    cy.on("tap", "node", (e) => {
      const n = e.target as cytoscape.NodeSingular;
      if (n.hasClass("colhead")) return;
      selectRef.current?.({ type: "node", ref: n.id() });
    });
    cy.on("tap", "edge", (e) => {
      const d = (e.target as cytoscape.EdgeSingular).data();
      selectRef.current?.({ type: "edge", source: d.source, target: d.target });
    });
    cy.on("tap", (e) => e.target === cy && selectRef.current?.(null));
    // moving dashes show the direction money flowed
    let offset = 0;
    let frame = 0;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const tick = () => {
      if (still) return;
      offset = (offset - 0.6) % 1000;
      cy.edges().style("line-dash-offset", offset);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    cyRef.current = cy;
    return () => {
      cancelAnimationFrame(frame);
      cyRef.current = undefined;
      cy.destroy();
    };
  }, [graph]);

  // highlight the chosen chain, node or edge
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass("hl faded");
    let els: cytoscape.Collection | null = null;
    if (chain) {
      els = cy.collection();
      chain.nodes.forEach((ref, i) => {
        els = els!.union(cy.getElementById(ref));
        if (i > 0) {
          const [a, b] = chain.direction === "backward" ? [ref, chain.nodes[i - 1]] : [chain.nodes[i - 1], ref];
          const fwd = cy.getElementById(`${a}->${b}`);
          els = els!.union(fwd.nonempty() ? fwd : cy.getElementById(`${b}->${a}`));
        }
      });
    } else if (selection?.type === "node") {
      els = cy.getElementById(selection.ref).closedNeighborhood();
    } else if (selection?.type === "edge") {
      const e = cy.getElementById(`${selection.source}->${selection.target}`);
      els = e.union(e.connectedNodes());
    }
    if (els && els.nonempty()) {
      cy.elements().not(".colhead").addClass("faded");
      els.removeClass("faded").addClass("hl");
    }
  }, [chain, selection, graph]);

  return <GraphFrame boxRef={box} cyRef={cyRef} height={height} className="trail-canvas" />;
}
