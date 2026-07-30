// Aides ECharts : couleurs lues depuis les rôles CSS (light/dark suivent le thème),
// specs de marques du guide dataviz (barres fines, bouts arrondis 4px côté données,
// grille discrète, texte en encres - jamais en couleur de série).
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export function roles() {
  const s = getComputedStyle(document.documentElement);
  const v = (nom) => s.getPropertyValue(nom).trim();
  return {
    serie1: v("--series-1"),
    serie2: v("--series-2") || "#b3841a", // doré du drapeau, validé face au vert
    texte: v("--text-primary"),
    texteSecondaire: v("--text-secondary"),
    grille: v("--border"),
    surface: v("--surface-1"),
  };
}

export function baseOptions(c) {
  return {
    textStyle: { color: c.texteSecondaire, fontFamily: "system-ui, sans-serif" },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: c.surface,
      borderColor: c.grille,
      textStyle: { color: c.texte },
    },
  };
}

export function monter(el, options) {
  const chart = echarts.init(el);
  chart.setOption(options);
  const obs = new ResizeObserver(() => chart.resize());
  obs.observe(el);
  return () => {
    obs.disconnect();
    chart.dispose();
  };
}
