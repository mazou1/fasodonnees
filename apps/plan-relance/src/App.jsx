import { useState, useEffect, useRef } from "react";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Legend, AreaChart, Area, ReferenceLine } from "recharts";

const C = { bg: "#0B0E14", card: "#13161F", dark: "#0B0E14", text: "#fff", muted: "rgba(255,255,255,0.65)", gold: "#D4A843", emerald: "#2D6A4F", terra: "#C1553B", red: "#E84040", blue: "#3B82F6", green: "#22C55E", orange: "#F59E0B", purple: "#8B5CF6", teal: "#14B8A6", pink: "#EC4899", border: "rgba(255,255,255,0.06)", shadow: "0 2px 8px rgba(0,0,0,0.3)" };

const useVisible = (t = 0.12) => {
  const r = useRef(null);
  const [v, setV] = useState(false);
  useEffect(() => {
    const el = r.current;
    if (!el) return;
    const o = new IntersectionObserver(([e]) => { if (e.isIntersecting) setV(true); }, { threshold: t });
    o.observe(el);
    return () => o.disconnect();
  }, [t]);
  return [r, v];
};

const Num = ({ value, suffix = "" }) => {
  const [cur, setCur] = useState(0);
  const [ref, vis] = useVisible();
  useEffect(() => {
    if (!vis) return;
    let s = 0; const step = value / 120;
    const t = setInterval(() => { s += step; if (s >= value) { setCur(value); clearInterval(t); } else setCur(s); }, 16);
    return () => clearInterval(t);
  }, [vis, value]);
  return <span ref={ref}>{value % 1 !== 0 ? cur.toFixed(1) : Math.round(cur)}{suffix}</span>;
};

/* ── Tooltips corrigés ── */
const tipStyle = { background: "rgba(11,14,20,0.96)", borderRadius: 10, padding: "12px 16px", border: "1px solid rgba(212,168,67,0.15)", fontSize: 14, fontFamily: "'DM Sans',sans-serif", boxShadow: "0 8px 24px rgba(0,0,0,0.5)", backdropFilter: "blur(8px)", color: "#fff" };

const Tip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={tipStyle}>
      {label && <div style={{ color: "rgba(255,255,255,0.65)", marginBottom: 4 }}>{label}</div>}
      {payload.map((p, i) => <div key={i} style={{ color: p.color || p.fill || "#fff", fontWeight: 600 }}>{p.name}: {typeof p.value === "number" ? p.value.toLocaleString("fr-FR") : p.value}</div>)}
    </div>
  );
};

const PieTip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div style={tipStyle}>
      <div style={{ color: d.payload?.fill || d.payload?.color || d.color || "#fff", fontWeight: 600 }}>{d.name}: {d.value}%</div>
    </div>
  );
};

/* Tooltip wrapper — élimine l'artefact noir par défaut de Recharts */
const tipWrap = { outline: "none", zIndex: 50 };

const relance = [
  { l: "R", t: "Réformes structurelles", d: "Réformes profondes de l'État et des finances", c: "#DC3545" },
  { l: "E", t: "Économie productive", d: "Production locale et transformation", c: "#F59E0B" },
  { l: "L", t: "Leadership de l'État", d: "État stratège et investisseur", c: "#22C55E" },
  { l: "A", t: "Accélération", d: "Investissements à fort impact", c: "#3B82F6" },
  { l: "N", t: "Nation unie", d: "Mobilisation des forces vives", c: "#8B5CF6" },
  { l: "C", t: "Croissance inclusive", d: "Emplois décents pour tous", c: "#EC4899" },
  { l: "E", t: "Équité territoriale", d: "Répartition juste entre régions", c: "#14B8A6" },
];

/* Tableau 5 — Cadrage macroéconomique, scénario volontariste vs référence */
const growth = [
  { y: "2021", v: 6.9, r: 6.9 }, { y: "2022", v: 1.6, r: 1.6 }, { y: "2023", v: 3.0, r: 3.0 },
  { y: "2024", v: 4.8, r: 4.8 }, { y: "2025", v: 6.5, r: 6.5 }, { y: "2026", v: 7.7, r: 6.0 },
  { y: "2027", v: 7.3, r: 6.1 }, { y: "2028", v: 6.7, r: 6.1 }, { y: "2029", v: 7.0, r: 6.2 },
  { y: "2030", v: 7.1, r: 6.1 },
];

/* Graphique 3 du document PND (INSD, EHCVM 2021) — 13 régions + National
   Objectif national 2030 : ramener l'incidence NATIONALE à 35%
   Objectif régions > national : ramener la moyenne de 53,5% à 47% */
const poverty = [
  { rg: "Liptako+Soum", v2021: 76.1 },
  { rg: "Yaadga", v2021: 67.5 },
  { rg: "Bankui+Sourou", v2021: 56.1 },
  { rg: "Goulmou+Tapoa+Sirba", v2021: 53.9 },
  { rg: "Kuilsé", v2021: 49.6 },
  { rg: "Oubri", v2021: 45.5 },
  { rg: "Nando", v2021: 44.6 },
  { rg: "Nazinon", v2021: 44.4 },
  { rg: "Djôrô", v2021: 43.5 },
  { rg: "National", v2021: 43.2 },
  { rg: "Guiriko", v2021: 37.4 },
  { rg: "Tannounyan", v2021: 36.9 },
  { rg: "Nakambé", v2021: 34.7 },
  { rg: "Kadiogo", v2021: 8.0 },
];

const energy = [
  { y: "2020", mw: 335 }, { y: "2022", mw: 500 }, { y: "2024", mw: 678 },
  { y: "2026", mw: 1050 }, { y: "2028", mw: 1350 }, { y: "2030", mw: 2586 },
];

/* Indicateurs du Tableau 1 normalisés (valeur de référence / cible 2030, arrondi)
   Source : Tableau 1, p.38 — valeurs exactes indiquées en légende */
const radar = [
  { a: "Sécurité", c: 74, t: 100, ref: "73,6%", cib: "100%", u: "reconquête" },
  { a: "EFTP", c: 42, t: 100, ref: "5%", cib: "12%", u: "formation pro." },
  { a: "Santé", c: 91, t: 100, ref: "61,9 ans", cib: "68 ans", u: "espérance vie" },
  { a: "Énergie", c: 26, t: 100, ref: "678 MW", cib: "2 586 MW", u: "puissance" },
  { a: "Industrie", c: 54, t: 100, ref: "9,6%", cib: "17,7%", u: "part PIB" },
  { a: "Aliment.", c: 57, t: 100, ref: "33,9%", cib: "60%", u: "auto-approv." },
  { a: "Corruption", c: 89, t: 100, ref: "41/100", cib: "46/100", u: "indice" },
  { a: "Pauvreté", c: 81, t: 100, ref: "43,2%", cib: "35%", u: "incidence" },
];

const pillars = [
  { n: 1, t: "Sécurité & Cohésion sociale", c: "#DC3545", i: "🛡️",
    prg: ["Défense et sécurité", "Cohésion sociale et paix"],
    obj: ["Reconquête 100% du territoire", "Ratio agent sécurité/pop. : 495", "Taux maillage sécuritaire : 75%", "70% conflits résolus"] },
  { n: 2, t: "Refondation de l'État", c: "#3B82F6", i: "⚖️",
    prg: ["Gouvernance politique", "Pilotage développement", "Gouvernance administrative", "Gouvernance économique", "Décentralisation", "Mobilisation communautaire"],
    obj: ["Constitution Ve République", "Pression fiscale 20,6%", "100 e-services", "Corruption : 46/100"] },
  { n: 3, t: "Capital humain", c: "#22C55E", i: "🎓",
    prg: ["Santé et nutrition", "Éducation et formation", "Recherche et innovation", "Travail et protection sociale", "Environnement et cadre de vie"],
    obj: ["Espérance de vie 68 ans", "EFTP 12%", "Malnutrition chronique < 10%", "Emploi formel 15%"] },
  { n: 4, t: "Infrastructures & Économie", c: "#F59E0B", i: "🏗️",
    prg: ["Agro-sylvo-pastoral", "Souveraineté énergétique", "Industrie et artisanat", "Commerce", "Transport", "Numérique", "Culture et sport"],
    obj: ["Énergie 2 586 MW", "Industrie 17,7% PIB", "Auto-approvisionnement 60%", "Import. énergie 49→20%"] },
];

/* Risques — Tableau 8, page 97 du document PND 2026-2030
   Criticité = Occurrence × Incidence (échelle 1-3 chacun)
   Source exacte : Section III.6, pages 95-98 */
const risks = [
  { i: "🤝", r: "Effritement de la cohésion sociale et faible mobilisation communautaire", occ: 2, inc: 2, crit: 4, label: "Moyenne",
    mesures: "Renforcer la cohésion sociale, la participation aux initiatives communautaires, valoriser les savoirs locaux, co-construire des solutions endogènes" },
  { i: "🌍", r: "Chocs extérieurs (volatilité prix, crises économiques, tensions géopolitiques)", occ: 2, inc: 3, crit: 6, label: "Élevée",
    mesures: "Renforcer la résilience économique, diversifier les revenus, améliorer la gouvernance budgétaire, accroître la mobilisation des ressources internes" },
  { i: "💸", r: "Faible mobilisation des ressources financières", occ: 2, inc: 2, crit: 4, label: "Moyenne",
    mesures: "Améliorer le système de mobilisation des ressources internes, l'efficacité de la dépense publique, développer les stratégies de financements innovants" },
  { i: "🔒", r: "Dégradation de la situation sécuritaire au niveau sous-régional", occ: 2, inc: 3, crit: 6, label: "Élevée",
    mesures: "Renforcer la coopération militaire sous-régionale, accentuer les capacités techniques et opérationnelles des forces combattantes" },
  { i: "🌪️", r: "Catastrophes naturelles (inondations, instabilité saisons, sécheresses)", occ: 2, inc: 2, crit: 4, label: "Moyenne",
    mesures: "Actualiser et mettre en œuvre les programmes d'adaptation au changement climatique et les plans de riposte aux catastrophes naturelles" },
];

export default function App() {
  const [ap, setAp] = useState(0);
  const [scrollY, setSY] = useState(0);
  const [mt, setMt] = useState(false);
  const [ww, setWw] = useState(typeof window !== "undefined" ? window.innerWidth : 1200);
  const mob = ww < 768;
  const pdata = mob ? poverty.map(d => ({...d, rg: d.rg.length > 14 ? d.rg.slice(0,12) + "…" : d.rg })) : poverty;


  useEffect(() => { setMt(true); const h = () => setSY(window.scrollY); const r = () => setWw(window.innerWidth); window.addEventListener("scroll", h, { passive: true }); window.addEventListener("resize", r); return () => { window.removeEventListener("scroll", h); window.removeEventListener("resize", r); }; }, []);

  const KPI = ({ label, from, to, unit, icon, color }) => {
    const [hv, setHv] = useState(false);
    return (
      <div onMouseEnter={() => setHv(true)} onMouseLeave={() => setHv(false)} style={{ background: C.card, borderRadius: 14, padding: "22px 18px", border: `1px solid ${hv ? color : "rgba(255,255,255,0.03)"}`, transition: "all 0.35s", transform: hv ? "translateY(-3px)" : "none", boxShadow: hv ? "0 16px 32px rgba(0,0,0,0.4)" : "none", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: `linear-gradient(90deg,${color},transparent)`, opacity: hv ? 1 : 0.3, transition: "opacity 0.3s" }} />
        <div style={{ fontSize: 24, marginBottom: 6 }}>{icon}</div>
        <div style={{ fontSize: 12, color: "rgba(255,255,255,0.60)", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 6 }}>{label}</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 14, color: "rgba(255,255,255,0.50)", textDecoration: "line-through" }}>{from}</span>
          <span style={{ color: "rgba(255,255,255,0.1)" }}>→</span>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 22, fontWeight: 700, color }}><Num value={parseFloat(to)} suffix={unit} /></span>
        </div>
      </div>
    );
  };

  const Sec = ({ children, sub }) => (
    <div style={{ marginBottom: 44, textAlign: "center" }}>
      <h2 style={{ fontFamily: "'Cormorant Garamond',Georgia,serif", fontSize: "clamp(24px,4.5vw,42px)", fontWeight: 700, color: "#fff", letterSpacing: "-0.5px", lineHeight: 1.15, margin: 0 }}>{children}</h2>
      {sub && <p style={{ fontSize: 15, color: "rgba(255,255,255,0.65)", marginTop: 10, maxWidth: 600, marginLeft: "auto", marginRight: "auto", lineHeight: 1.6 }}>{sub}</p>}
    </div>
  );

  /* ── Custom bar shape pour poverty chart ── */
  const PovertyBar = (props) => {
    const { x, y, width, height, fill, payload } = props;
    const isNational = payload?.rg === "National";
    return (
      <g>
        <rect x={x} y={y} width={width} height={height} fill={fill} rx={3} ry={3} />
        {isNational && <rect x={x} y={y} width={width} height={height} fill="none" stroke={C.gold} strokeWidth={2} rx={3} ry={3} strokeDasharray="4 2" />}
      </g>
    );
  };

  /* ── Tooltip personnalisé pour pauvreté ── */
  const PovertyTip = ({ active, payload }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    if (!d) return null;
    const isNat = d.rg === "National";
    const aboveNat = d.v2021 > 43.2;
    const belowTarget = d.v2021 < 35;
    return (
      <div style={tipStyle}>
        <div style={{ fontWeight: 700, marginBottom: 6, color: "#fff", fontSize: 13 }}>{d.rg}</div>
        <div style={{ marginBottom: 6 }}>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", textTransform: "uppercase" }}>Taux de pauvreté 2021</div>
          <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 18, fontWeight: 700, color: d.v2021 > 50 ? C.red : d.v2021 > 43.2 ? C.orange : d.v2021 > 35 ? "#F59E0B" : C.green }}>{d.v2021}%</div>
        </div>
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 6, fontSize: 12, color: "rgba(255,255,255,0.65)", lineHeight: 1.5 }}>
          {isNat ? (
            <span>Objectif national 2030 : <strong style={{ color: C.green }}>35%</strong> (−8,2 pts)</span>
          ) : belowTarget ? (
            <span style={{ color: C.green }}>✓ Déjà sous l'objectif national de 35%</span>
          ) : aboveNat ? (
            <span>Au-dessus de la moyenne nationale — écart : <strong style={{ color: C.red }}>+{(d.v2021 - 43.2).toFixed(1)} pts</strong></span>
          ) : (
            <span>Entre l'objectif national (35%) et la moyenne (43,2%)</span>
          )}
        </div>
      </div>
    );
  };

  const RadarTip = ({ active, payload }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    if (!d) return null;
    return (
      <div style={tipStyle}>
        <div style={{ fontWeight: 700, marginBottom: 6, color: "#fff", fontSize: 13 }}>{d.a}</div>
        <div style={{ display: "flex", gap: 18, marginBottom: 6 }}>
          <div>
            <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase" }}>Actuel</div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 16, fontWeight: 700, color: C.orange }}>{d.ref}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase" }}>Cible 2030</div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 16, fontWeight: 700, color: C.green }}>{d.cib}</div>
          </div>
        </div>
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 5, fontSize: 12, color: C.muted }}>
          Progression : <strong style={{ color: d.c >= 80 ? C.green : d.c >= 50 ? C.orange : C.red }}>{d.c}%</strong> de la cible
        </div>
      </div>
    );
  };

  const GrowthTip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const vol = payload.find(p => p.dataKey === "v");
    const ref = payload.find(p => p.dataKey === "r");
    const isPast = parseInt(label) <= 2025;
    return (
      <div style={tipStyle}>
        <div style={{ fontWeight: 700, marginBottom: 6, color: "#fff", fontSize: 14 }}>{label}</div>
        {isPast ? (
          <div>
            <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase" }}>Croissance réalisée</div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 18, fontWeight: 700, color: C.green }}>{vol?.value}%</div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 4, fontStyle: "italic" }}>Données historiques (les 2 scénarios divergent à partir de 2026)</div>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 20 }}>
            <div>
              <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase" }}>Scénario volontariste</div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 16, fontWeight: 700, color: C.green }}>{vol?.value}%</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: C.muted, textTransform: "uppercase" }}>Scénario de référence</div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 16, fontWeight: 700, color: "rgba(255,255,255,0.60)" }}>{ref?.value}%</div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ background: C.bg, color: "#fff", fontFamily: "'DM Sans',sans-serif", overflowX: "hidden" }}>
      {/* retour vers Faso Données Publiques — target _top : navigue la page
          parente quand le dossier est encapsulé (/dossiers/plan-relance) */}
      <a href={window.self === window.top ? "/" : "/dossiers"} target="_top" style={{ position: "fixed", top: 14, left: 16, zIndex: 100, fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.55)", textDecoration: "none", background: "rgba(11,14,20,0.6)", padding: "6px 12px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.08)", backdropFilter: "blur(6px)" }}>
        ← Faso <span style={{ color: C.gold }}>Données Publiques</span>
      </a>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&family=JetBrains+Mono:wght@400;700&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        html{scroll-behavior:smooth}
        ::-webkit-scrollbar{width:5px}
        ::-webkit-scrollbar-track{background:#0B0E14}
        ::-webkit-scrollbar-thumb{background:rgba(212,168,67,0.2);border-radius:3px}
        @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
        @keyframes slideUp{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}
        @keyframes gShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        .hl{display:inline-flex;align-items:center;justify-content:center;width:48px;height:58px;font-size:28px;font-weight:700;border-radius:9px;margin:0 2px;transition:all 0.3s;cursor:default;font-family:'Cormorant Garamond',serif}
        .hl:hover{transform:scale(1.12) rotate(-2deg)}
        .pt{padding:11px 16px;border-radius:10px;cursor:pointer;transition:all 0.3s;font-size:13px;font-weight:600;border:1px solid transparent;white-space:nowrap}
        .mc{background:#13161F;border-radius:14px;padding:22px;border:1px solid rgba(255,255,255,0.05);transition:all 0.3s}
        .mc:hover{border-color:rgba(212,168,67,0.2);transform:translateY(-2px);box-shadow:0 8px 20px rgba(0,0,0,0.3)}
        .sx{padding:70px 18px;max-width:1060px;margin:0 auto}
        .recharts-tooltip-wrapper{outline:none!important;pointer-events:none!important}
        .recharts-default-tooltip{display:none!important}
        @media(max-width:768px){
          .hl{width:34px;height:42px;font-size:20px}
          .sx{padding:44px 12px}
          .g2{grid-template-columns:1fr!important}
          .g3{grid-template-columns:1fr!important}
          .g4{grid-template-columns:1fr 1fr!important}
          .ptw{flex-wrap:wrap!important}
          .gm{grid-template-columns:1fr!important}
        }
      `}</style>

      {/* ═══ HERO ═══ */}
      <section style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", position: "relative", overflow: "hidden", padding: "36px 18px",  }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 25% 15%,#2D6A4F10 0%,transparent 55%),radial-gradient(ellipse at 75% 85%,#B8860B0C 0%,transparent 50%),radial-gradient(ellipse at 50% 50%,#C1553B06 0%,transparent 65%)", transform: `translateY(${Math.min(scrollY * 0.2, 120)}px)` }} />
        <div style={{ position: "absolute", inset: 0, opacity: 0.02, backgroundImage: "repeating-linear-gradient(0deg,transparent,transparent 59px,rgba(255,255,255,0.65) 60px),repeating-linear-gradient(90deg,transparent,transparent 59px,rgba(255,255,255,0.65) 60px)" }} />

        <div style={{ position: "relative", zIndex: 1, textAlign: "center", animation: mt ? "slideUp 0.9s ease-out" : "none" }}>
          <div style={{ fontSize: 13, letterSpacing: 4, textTransform: "uppercase", color: C.gold, marginBottom: 22, fontWeight: 600 }}>
            Burkina Faso — Plan National de Développement 2026-2030
          </div>
          <div style={{ display: "flex", justifyContent: "center", flexWrap: "wrap", marginBottom: 14, gap: 2 }}>
            {relance.map((x, i) => <div key={i} className="hl" style={{ background: `${x.c}15`, color: x.c, border: `2px solid ${x.c}30` }} title={x.t}>{x.l}</div>)}
          </div>
          <h1 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: "clamp(32px,6.5vw,64px)", fontWeight: 700, lineHeight: 1.05, letterSpacing: "-1.5px", maxWidth: 700, margin: "0 auto 18px", background: "linear-gradient(135deg,#fff 0%,#D4A843 50%,#C1553B 100%)", backgroundSize: "200% 200%", animation: "gShift 6s ease infinite", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Plan de Relance
          </h1>
          <p style={{ fontSize: 16, color: "rgba(255,255,255,0.65)", maxWidth: 500, margin: "0 auto 32px", lineHeight: 1.7, fontWeight: 300 }}>
            Une stratégie endogène pour un Burkina Faso souverain et prospère, au service du bien-être de tous.
          </p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap", marginBottom: 40 }}>
            {[{ l: "Budget total", v: "36 191 Mds" }, { l: "Horizon", v: "2026—2030" }, { l: "Croissance", v: "7,2%/an" }, { l: "Piliers", v: "4 stratégiques" }].map((x, i) => (
              <div key={i} style={{ background: "rgba(255,255,255,0.015)", border: "1px solid rgba(255,255,255,0.04)", borderRadius: 10, padding: "12px 18px", minWidth: 110 }}>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.50)", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 3 }}>{x.l}</div>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 14, fontWeight: 700, color: C.gold }}>{x.v}</div>
              </div>
            ))}
          </div>
          <div style={{ animation: "float 3s ease-in-out infinite", fontSize: 20, color: "rgba(255,255,255,0.06)" }}>↓</div>
        </div>
      </section>

      {/* ═══ RELANCE MEANING ═══ */}
      <section style={{ padding: "60px 18px", background: "linear-gradient(180deg,rgba(212,168,67,0.025) 0%,transparent 100%)" }}>
        <div style={{ maxWidth: 960, margin: "0 auto" }}>
          <Sec sub="Chaque lettre porte une orientation stratégique majeure">Que signifie <span style={{ color: C.gold }}>R.E.L.A.N.C.E.</span> ?</Sec>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>
            {relance.map((x, i) => (
              <div key={i} style={{ background: C.card, borderRadius: 12, padding: "18px 16px", border: `1px solid ${x.c}15`, display: "flex", gap: 12, alignItems: "flex-start" }}>
                <div style={{ width: 38, height: 38, borderRadius: 8, background: `${x.c}12`, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Cormorant Garamond',serif", fontSize: 18, fontWeight: 700, color: x.c, flexShrink: 0 }}>{x.l}</div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 2 }}>{x.t}</div>
                  <div style={{ fontSize: 13, color: "rgba(255,255,255,0.60)", lineHeight: 1.5 }}>{x.d}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ CONSTAT ═══ */}
      <section className="sx">
        <Sec sub="État des lieux : les indicateurs clés qui justifient la relance (Tableau 1, p.38).">📊 Le Constat</Sec>
        <div className="g4" style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 32 }}>
          <KPI label="Reconquête territoire" from="73,6%" to="100" unit="%" icon="🛡️" color={C.red} />
          <KPI label="Pauvreté" from="43,2%" to="35" unit="%" icon="📉" color={C.orange} />
          <KPI label="Industrie / PIB" from="9,6%" to="17.7" unit="%" icon="🏭" color={C.blue} />
          <KPI label="Puissance élec." from="678 MW" to="2586" unit=" MW" icon="⚡" color={C.green} />
          <KPI label="Espérance de vie" from="61,9 ans" to="68" unit=" ans" icon="❤️" color={C.purple} />
          <KPI label="Formation pro. (EFTP)" from="5%" to="12" unit="%" icon="🎓" color={C.teal} />
          <KPI label="Import. aliment." from="11,5%" to="8" unit="%" icon="🌾" color={C.terra} />
          <KPI label="Contribution comm." from="33%" to="41" unit="%" icon="👥" color="#06B6D4" />
        </div>

        {/* ─── Pauvreté par région : Constat 2021 vs Objectif national 2030 ─── */}
        <div style={{ background: C.card, borderRadius: 16, padding: "24px 18px", border: "1px solid rgba(255,255,255,0.03)", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 6 }}>
            <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 18 }}>Incidence de la pauvreté par région <span style={{ color: "rgba(255,255,255,0.55)", fontSize: 14 }}>(2021)</span></h3>
            <div style={{ display: "flex", gap: mob ? 6 : 12, flexWrap: "wrap" }}>
              <div style={{ background: "rgba(232,64,64,0.08)", borderRadius: 8, padding: "6px 12px", border: "1px solid rgba(232,64,64,0.15)" }}>
                <span style={{ fontSize: 12, color: "rgba(255,255,255,0.60)" }}>Moy. nationale : </span>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 13, fontWeight: 700, color: C.orange }}>43,2%</span>
              </div>
              <div style={{ background: "rgba(34,197,94,0.08)", borderRadius: 8, padding: "6px 12px", border: "1px solid rgba(34,197,94,0.15)" }}>
                <span style={{ fontSize: 12, color: "rgba(255,255,255,0.60)" }}>Objectif 2030 : </span>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 13, fontWeight: 700, color: C.green }}>35%</span>
              </div>
            </div>
          </div>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.55)", marginBottom: 14 }}>Source : INSD, EHCVM 2021 (Graphique 3, p.21) — Les lignes verticales montrent la moyenne nationale et l'objectif à atteindre</p>
          <div style={{ overflowX: mob ? "auto" : "visible", WebkitOverflowScrolling: "touch" }}>
          <ResponsiveContainer width="100%" height={mob ? 520 : 480} minWidth={mob ? 500 : undefined}>
            <BarChart data={pdata} layout="vertical" margin={{ left: mob ? 10 : 130, right: mob ? 20 : 40, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis type="number" domain={[0, 80]} tick={{ fill: "rgba(255,255,255,0.55)", fontSize: 12 }} tickFormatter={(v) => `${v}%`} />
              <YAxis dataKey="rg" type="category" tick={{ fill: "rgba(255,255,255,0.70)", fontSize: mob ? 10 : 12 }} width={mob ? 105 : 125} />
              <Tooltip content={<PovertyTip />} wrapperStyle={tipWrap} cursor={{ fill: "rgba(255,255,255,0.01)" }} />
              <ReferenceLine x={35} stroke={C.green} strokeWidth={2} strokeDasharray="8 4" label={{ value: mob ? "Obj. 35%" : "Objectif national 2030 : 35%", position: "top", fill: C.green, fontSize: 12, fontWeight: 700 }} />
              <ReferenceLine x={43.2} stroke={C.orange} strokeDasharray="4 4" strokeWidth={1.5} label={{ value: mob ? "Moy. 43,2%" : "Moyenne nationale 2021 : 43,2%", position: "insideBottomRight", fill: C.orange, fontSize: 11, dy: 8 }} />
              <Bar dataKey="v2021" name="Taux pauvreté 2021 (%)" shape={<PovertyBar />}>
                {pdata.map((e, i) => (
                  <Cell key={i} fill={e.rg === "National" ? C.gold : e.v2021 > 50 ? C.red : e.v2021 > 43.2 ? C.orange : e.v2021 > 35 ? "#F59E0B88" : C.green} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          </div>
          <div style={{ display: "flex", justifyContent: "center", gap: mob ? 8 : 18, marginTop: 8, flexWrap: "wrap" }}>
            {[
              { c: C.red, l: "> 50% — Situation critique" },
              { c: C.orange, l: "> 43,2% — Au-dessus de la moyenne" },
              { c: "#F59E0B88", l: "35-43% — Zone intermédiaire" },
              { c: C.green, l: "< 35% — Sous l'objectif national" },
              { c: C.gold, l: "Moyenne nationale" },
            ].map((x, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: x.c }} />
                <span style={{ color: "rgba(255,255,255,0.65)" }}>{x.l}</span>
              </div>
            ))}
          </div>
          {/* Résumé chiffré constat vs objectif */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 10, marginTop: 16 }}>
            {[
              { l: "Incidence nationale", f: "43,2%", t: "35%", c: C.orange, tc: C.green },
              { l: "Moy. régions > national", f: "53,5%", t: "47%", c: C.red, tc: C.green },
              { l: "Régions > 50%", f: "4 régions", t: "Réduire", c: C.red, tc: C.blue },
              { l: "IDH", f: "0,459", t: "0,50", c: C.purple, tc: C.green },
            ].map((x, i) => (
              <div key={i} style={{ background: "rgba(255,255,255,0.01)", borderRadius: 8, padding: "10px 12px", border: "1px solid rgba(255,255,255,0.025)", textAlign: "center" }}>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{x.l}</div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 4, justifyContent: "center" }}>
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 14, fontWeight: 700, color: x.c }}>{x.f}</span>
                  <span style={{ color: "rgba(255,255,255,0.1)", fontSize: 14 }}>→</span>
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 14, fontWeight: 700, color: x.tc }}>{x.t}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="g2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div style={{ background: C.card, borderRadius: 16, padding: "24px 18px", border: "1px solid rgba(255,255,255,0.03)" }}>
            <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 18, marginBottom: 4 }}>Progression des indicateurs d'impact</h3>
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.50)", marginBottom: 12 }}>% d'atteinte de la cible 2030 — Survolez pour les valeurs exactes</p>
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radar}>
                <PolarGrid stroke="rgba(255,255,255,0.04)" />
                <PolarAngleAxis dataKey="a" tick={{ fill: "rgba(255,255,255,0.70)", fontSize: 12 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
                <Radar name="Actuel (% de la cible)" dataKey="c" stroke={C.orange} fill={C.orange} fillOpacity={0.12} strokeWidth={2} />
                <Radar name="Cible 2030 (100%)" dataKey="t" stroke={C.green} fill={C.green} fillOpacity={0.04} strokeWidth={1.5} strokeDasharray="5 4" />
                <Tooltip content={<RadarTip />} wrapperStyle={tipWrap} />
                <Legend wrapperStyle={{ fontSize: 13 }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div style={{ background: C.card, borderRadius: 16, padding: "24px 18px", border: "1px solid rgba(255,255,255,0.03)" }}>
            <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 18, marginBottom: 16 }}>Pauvreté — Chiffres clés</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              {[
                { l: "Incidence nationale", from: "43,2%", to: "35%", c: C.orange },
                { l: "Moy. régions déficitaires", from: "53,5%", to: "47%", c: C.red },
                { l: "Pression fiscale", from: "17,1%", to: "20,6%", c: C.blue },
                { l: "Territoire reconquis", from: "73,6%", to: "100%", c: C.terra },
                { l: "IDH", from: "0,459", to: "0,50", c: C.purple },
                { l: "Croissance PIB moy.", from: "4,6%/an", to: "7,2%/an", c: C.green },
              ].map((x, i) => (
                <div key={i} style={{ background: "rgba(255,255,255,0.01)", borderRadius: 8, padding: "10px 12px", border: "1px solid rgba(255,255,255,0.025)" }}>
                  <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{x.l}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 13, color: "rgba(255,255,255,0.55)", textDecoration: x.up ? "none" : "line-through" }}>{x.from}</span>
                    <span style={{ color: "rgba(255,255,255,0.06)" }}>→</span>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 15, fontWeight: 700, color: x.c }}>{x.to}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══ TRAJECTOIRE ═══ */}
      <section style={{ padding: "60px 18px", background: "linear-gradient(180deg,rgba(34,197,94,0.025) 0%,transparent 100%)" }}>
        <div style={{ maxWidth: 1060, margin: "0 auto" }}>
          <Sec sub="Scénario volontariste : 7,2% par an, porté par industrie, agriculture et mines.">📈 Trajectoire économique</Sec>
          <div className="g2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
            <div style={{ background: C.card, borderRadius: 16, padding: "24px 18px", border: "1px solid rgba(255,255,255,0.03)" }}>
              <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 17, marginBottom: 4 }}>Croissance PIB réel (%)</h3>
              <p style={{ fontSize: 12, color: C.muted, marginBottom: 14 }}>2021-2025 : données historiques · 2026-2030 : projections du cadrage macro-budgétaire</p>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={growth}>
                  <defs><linearGradient id="gV" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.green} stopOpacity={0.18} /><stop offset="95%" stopColor={C.green} stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="y" tick={{ fill: "rgba(255,255,255,0.60)", fontSize: 12 }} />
                  <YAxis domain={[0, 9]} tickFormatter={(v) => `${v}%`} tick={{ fill: "rgba(255,255,255,0.60)", fontSize: 12 }} />
                  <Tooltip content={<GrowthTip />} wrapperStyle={tipWrap} />
                  <ReferenceLine x="2025" stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" label={{ value: "Projections ▸", position: "top", fill: C.muted, fontSize: 11 }} />
                  <Area type="monotone" dataKey="r" name="Référence (6,1%)" stroke="rgba(255,255,255,0.50)" fill="rgba(255,255,255,0.03)" strokeWidth={2} strokeDasharray="6 4" />
                  <Area type="monotone" dataKey="v" name="Volontariste (7,2%)" stroke={C.green} fill="url(#gV)" strokeWidth={2.5} />
                </AreaChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", gap: 16, justifyContent: "center", marginTop: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13 }}><div style={{ width: 20, height: 3, borderRadius: 2, background: C.green }} /><span style={{ color: "#fff", fontWeight: 600 }}>Volontariste (7,2%)</span></div>
                <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13 }}><div style={{ width: 20, height: 3, borderRadius: 2, background: "#9CA3AF" }} /><span style={{ color: C.muted }}>Référence (6,1%)</span></div>
              </div>
            </div>
            <div style={{ background: C.card, borderRadius: 16, padding: "24px 18px", border: "1px solid rgba(255,255,255,0.03)" }}>
              <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 17, marginBottom: 16 }}>Puissance électrique installée (MW)</h3>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={energy}>
                  <defs><linearGradient id="gE" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.orange} stopOpacity={0.22} /><stop offset="95%" stopColor={C.orange} stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="y" tick={{ fill: "rgba(255,255,255,0.60)", fontSize: 12 }} />
                  <YAxis tick={{ fill: "rgba(255,255,255,0.60)", fontSize: 12 }} />
                  <Tooltip content={<Tip />} wrapperStyle={tipWrap} />
                  <Area type="monotone" dataKey="mw" name="MW" stroke={C.orange} fill="url(#gE)" strokeWidth={2.5} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 10 }}>
            <div style={{ gridColumn: "1 / -1", background: C.card, borderRadius: 12, padding: "14px 18px", border: `1px solid ${C.border}`, marginBottom: 6 }}>
              <p style={{ fontSize: 13, color: C.muted, lineHeight: 1.7, margin: 0 }}>
                <strong style={{ color: "#fff" }}>💡 Lecture :</strong> Le <strong style={{ color: C.green }}>scénario volontariste</strong> (retenu par le PND) table sur des réformes structurelles et une industrialisation accélérée pour 7,2% de croissance annuelle. Le <strong style={{ color: "rgba(255,255,255,0.60)" }}>scénario de référence</strong> (6,1%) correspond à la trajectoire sans effort supplémentaire. Avant 2026, les deux courbes se confondent (données historiques).
              </p>
            </div>
            {[{ l: "Primaire", v: "+7,2%/an", c: C.green }, { l: "Secondaire", v: "+9,3%/an", c: C.orange }, { l: "Tertiaire", v: "+5,0%/an", c: C.blue }, { l: "Import. énergie", v: "49→20%", c: C.red }, { l: "Investissement", v: "24% PIB", c: C.purple }, { l: "Inflation", v: "< 3%", c: C.teal }].map((s, i) => (
              <div key={i} style={{ background: C.card, borderRadius: 10, padding: "14px 12px", border: `1px solid ${s.c}15`, textAlign: "center" }}>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 3 }}>{s.l}</div>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 18, fontWeight: 700, color: s.c }}>{s.v}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ 4 PILIERS ═══ */}
      <section style={{ padding: "70px 18px", background: "linear-gradient(180deg,rgba(26,26,46,0.4) 0%,transparent 100%)" }}>
        <div style={{ maxWidth: 1060, margin: "0 auto" }}>
          <Sec sub="4 piliers stratégiques, 20 programmes d'action.">🏛️ Les 4 Piliers</Sec>
          <div className="ptw" style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 24, flexWrap: "wrap" }}>
            {pillars.map((p, i) => (
              <div key={i} className="pt" onClick={() => setAp(i)} style={{ background: ap === i ? `${p.c}15` : "rgba(255,255,255,0.015)", color: ap === i ? p.c : "rgba(255,255,255,0.55)", borderColor: ap === i ? `${p.c}35` : "rgba(255,255,255,0.03)" }}>
                {p.i} Pilier {p.n}
              </div>
            ))}
          </div>
          {(() => {
            const p = pillars[ap];
            return (
              <div style={{ background: C.card, borderRadius: 16, padding: "28px 24px", border: `1px solid ${p.c}22`, transition: "all 0.4s" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
                  <div style={{ width: 46, height: 46, borderRadius: 11, background: `${p.c}10`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24 }}>{p.i}</div>
                  <div>
                    <div style={{ fontSize: 12, color: p.c, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>Pilier {p.n}</div>
                    <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 20 }}>{p.t}</h3>
                  </div>
                </div>
                <div className="g2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
                  <div>
                    <div style={{ fontSize: 12, color: "rgba(255,255,255,0.50)", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 8 }}>Programmes ({p.prg.length})</div>
                    {p.prg.map((x, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                        <div style={{ width: 4, height: 4, borderRadius: "50%", background: p.c, flexShrink: 0 }} />
                        <span style={{ fontSize: 14, color: "rgba(255,255,255,0.70)" }}>{x}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: "rgba(255,255,255,0.50)", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 8 }}>Objectifs phares</div>
                    {p.obj.map((x, i) => (
                      <div key={i} style={{ background: `${p.c}06`, borderRadius: 8, padding: "10px 12px", marginBottom: 6, border: `1px solid ${p.c}10`, fontSize: 14, color: "rgba(255,255,255,0.7)" }}>
                        <span style={{ color: p.c, marginRight: 6 }}>✓</span>{x}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      </section>

      {/* ═══ MÉTHODE — 7 principes directeurs + 5 innovations ═══ */}
      <section className="sx">
        <Sec sub="7 principes directeurs et des innovations structurantes dans la conduite du développement (Sections II.2-II.3).">🔧 La Méthode</Sec>

        <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 17, marginBottom: 16, color: C.gold }}>Principes directeurs (Section II.3, p.33-37)</h3>
        <div className="gm" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12, marginBottom: 28 }}>
          {[
            { i: "🏛️", t: "Souveraineté & leadership national", d: "L'État demeure garant ultime des choix stratégiques, veillant à l'indépendance et à la dignité nationale tout en s'ouvrant à la coopération dans le respect mutuel.", c: C.blue },
            { i: "🌱", t: "Développement endogène", d: "Utilisation des ressources disponibles localement pour la transformation économique et sociale. Le territoire et la communauté au centre de leur propre développement.", c: C.green },
            { i: "⚖️", t: "Équité et inclusion", d: "Implication de toutes les parties prenantes, égalité des opportunités et réduction des disparités géographiques. Attention particulière aux PDI et personnes vulnérables.", c: C.gold },
            { i: "🤝", t: "Subsidiarité & partenariat", d: "Décisions prises au niveau le plus proche des concernés. Collaboration active entre État, collectivités territoriales, secteur privé et société civile.", c: C.purple },
            { i: "📊", t: "Gestion axée sur les résultats", d: "Objectifs et indicateurs préalablement définis, reddition des comptes portant sur la performance, responsabilisation de chaque acteur dans l'atteinte des résultats.", c: C.terra },
            { i: "🔭", t: "Proactivité & intelligence économique", d: "Anticiper les risques via la veille stratégique, l'analyse prédictive, les plateformes collaboratives public-privé-académique et les systèmes d'alerte précoce.", c: C.teal },
            { i: "♻️", t: "Durabilité", d: "Utilisation rationnelle des ressources naturelles, modes de production et consommation responsables, sans compromettre les besoins des générations futures.", c: C.pink },
          ].map((m, i) => (
            <div key={i} className="mc">
              <div style={{ fontSize: 28, marginBottom: 8 }}>{m.i}</div>
              <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 5, color: m.c }}>{m.t}</h4>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,0.65)", lineHeight: 1.6 }}>{m.d}</p>
            </div>
          ))}
        </div>

        <h3 style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: 17, marginBottom: 16, color: C.gold }}>Innovations structurantes (Sections II.2 & III.1-III.2)</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12, marginBottom: 20 }}>
          {[
            { i: "🏗️", t: "État stratège & investisseur", d: "L'État redevient planificateur, investisseur et régulateur. Il oriente les priorités nationales avec leadership et souveraineté, dans le cadre de la Vision Burkina 2060.", c: C.blue },
            { i: "📋", t: "Approche-programme intégrée", d: "Cohérence horizontale et verticale des interventions. Les Initiatives présidentielles (IPP3A, Faso Mêbo, IPDC, IPEQ, IPS) agissent comme accélérateurs de résultats.", c: C.green },
            { i: "💰", t: "Financement innovant & endogène", d: "Actionnariat populaire (5% du besoin, soit 548 Mds FCFA), contributions communautaires, revenus du portefeuille étatique, Sukuk souverains, obligations vertes, diaspora bonds et PPP.", c: C.gold },
            { i: "👥", t: "Maîtrise d'œuvre distribuée", d: "Investissements distribués entre communautés à la base, collectivités territoriales et ministères. Suivi ouvert aux coordonnateurs de programmes et entreprises publiques.", c: C.purple },
            { i: "🗺️", t: "Développement territorial (PARD)", d: "Chaque Cadre régional de dialogue (CRD) élabore un Plan d'action régional (PARD) cohérent avec le PND et les Plans locaux de développement (PCD, PRD).", c: C.teal },
          ].map((m, i) => (
            <div key={i} style={{ background: C.card, borderRadius: 14, padding: "20px", border: `1px solid ${m.c}15`, display: "flex", gap: 14, alignItems: "flex-start" }}>
              <div style={{ fontSize: 28, flexShrink: 0 }}>{m.i}</div>
              <div>
                <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 4, color: m.c }}>{m.t}</h4>
                <p style={{ fontSize: 13, color: "rgba(255,255,255,0.65)", lineHeight: 1.6 }}>{m.d}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Dispositif de suivi */}
        <div style={{ background: C.card, borderRadius: 14, padding: "20px", border: "1px solid rgba(255,255,255,0.03)" }}>
          <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 10, color: C.gold }}>Dispositif de suivi & évaluation (Section III.3)</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 10 }}>
            {[
              { t: "COS", d: "Comité d'orientation stratégique — présidé par le Premier Ministre", c: C.red },
              { t: "CNS", d: "Comité national de suivi — validation technique des bilans", c: C.blue },
              { t: "CSD", d: "Cadres sectoriels de dialogue — suivi par secteur de planification", c: C.green },
              { t: "CRD", d: "Cadres régionaux de dialogue — supervision régionale des investissements", c: C.orange },
              { t: "SEN-PND", d: "Secrétariat exécutif national — coordination et impulsion des réformes", c: C.purple },
            ].map((o, i) => (
              <div key={i} style={{ background: "rgba(255,255,255,0.01)", borderRadius: 8, padding: "10px 12px", border: `1px solid ${o.c}10` }}>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 14, fontWeight: 700, color: o.c, marginBottom: 3 }}>{o.t}</div>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.60)", lineHeight: 1.5 }}>{o.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ FINANCEMENT — Tableau 7, p.92 ═══ */}
      <section style={{ padding: "60px 18px", background: "linear-gradient(180deg,rgba(232,185,49,0.025) 0%,transparent 100%)" }}>
        <div style={{ maxWidth: 1060, margin: "0 auto" }}>
          <Sec sub="36 191 milliards FCFA — 7 238 milliards par an en moyenne (Tableau 7, p.92).">💰 Le Financement</Sec>
          <div className="g2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
            {[
              { t: "Répartition des dépenses", d: [{ name: "Dép. courantes", value: 41.4, color: C.blue }, { name: "Investissement", value: 34.5, color: C.gold }, { name: "Amort. dette", value: 24.1, color: "rgba(255,255,255,0.50)" }] },
              { t: "Sources de financement", d: [{ name: "Ressources propres", value: 63.9, color: C.green }, { name: "Ressources ext.", value: 5.8, color: C.blue }, { name: "Besoin additionnel", value: 30.3, color: C.red }] },
            ].map((ch, ci) => (
              <div key={ci} style={{ background: C.card, borderRadius: 16, padding: "24px", border: "1px solid rgba(255,255,255,0.03)" }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: "rgba(255,255,255,0.70)" }}>{ch.t}</h4>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={ch.d} cx="50%" cy="50%" innerRadius={45} outerRadius={72} paddingAngle={3} dataKey="value">
                      {ch.d.map((e, i) => <Cell key={i} fill={e.color} />)}
                    </Pie>
                    <Tooltip content={<PieTip />} wrapperStyle={tipWrap} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display: "flex", justifyContent: "center", gap: 12, marginTop: 4, flexWrap: "wrap" }}>
                  {ch.d.map((d, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13 }}>
                      <div style={{ width: 7, height: 7, borderRadius: 2, background: d.color }} />
                      <span style={{ color: "rgba(255,255,255,0.65)" }}>{d.name}: <strong style={{ color: d.color }}>{d.value}%</strong></span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(155px,1fr))", gap: 10 }}>
            {[
              { l: "Investissement public", v: "12 495 Mds", s: "2 499 Mds/an", c: C.gold },
              { l: "Ressources propres", v: "23 136 Mds", s: "63,9% du coût", c: C.green },
              { l: "Ressources extérieures", v: "2 100 Mds", s: "5,8% du coût", c: C.blue },
              { l: "Besoin additionnel", v: "10 955 Mds", s: "30,3% du coût", c: C.red },
            ].map((m, i) => (
              <div key={i} style={{ background: C.card, borderRadius: 10, padding: "16px", border: `1px solid ${m.c}15`, textAlign: "center" }}>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.50)", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 5 }}>{m.l}</div>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 22, fontWeight: 700, color: m.c }}>{m.v}</div>
                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.15)", marginTop: 2 }}>{m.s}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ RISQUES — Tableau 8 & 9, pages 97-98 du document ═══ */}
      <section className="sx">
        <Sec sub="5 risques identifiés dans le document avec mesures d'atténuation (Tableau 8-9, p.97-98).">⚠️ Analyse des risques</Sec>
        <p style={{ fontSize: 13, color: "rgba(255,255,255,0.50)", textAlign: "center", marginTop: -30, marginBottom: 20 }}>
          Criticité = Occurrence × Incidence (échelle 1 à 3 chacun) — Faible (1-2) · Moyenne (3-4) · Élevée (6-9)
        </p>
        <div style={{ display: "grid", gap: 12 }}>
          {risks.sort((a, b) => b.crit - a.crit).map((x, i) => (
            <div key={i} style={{ background: C.card, borderRadius: 12, padding: "20px", border: `1px solid ${x.crit >= 6 ? "rgba(232,64,64,0.12)" : "rgba(255,255,255,0.03)"}` }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <span style={{ fontSize: 24, flexShrink: 0 }}>{x.i}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
                    <h4 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>{x.r}</h4>
                    <span style={{
                      fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 20,
                      background: x.crit >= 6 ? "rgba(232,64,64,0.12)" : "rgba(245,158,11,0.12)",
                      color: x.crit >= 6 ? C.red : C.orange,
                      border: `1px solid ${x.crit >= 6 ? "rgba(232,64,64,0.2)" : "rgba(245,158,11,0.2)"}`
                    }}>
                      Criticité {x.crit}/9 — {x.label}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 16, marginBottom: 8, fontSize: 13 }}>
                    <span style={{ color: "rgba(255,255,255,0.55)" }}>Occurrence: <strong style={{ color: "rgba(255,255,255,0.70)" }}>{x.occ}/3</strong></span>
                    <span style={{ color: "rgba(255,255,255,0.55)" }}>Incidence: <strong style={{ color: "rgba(255,255,255,0.70)" }}>{x.inc}/3</strong></span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <div style={{ flex: 1, height: 4, borderRadius: 3, background: "rgba(255,255,255,0.025)", overflow: "hidden" }}>
                      <div style={{ width: `${(x.crit / 9) * 100}%`, height: "100%", borderRadius: 3, background: x.crit >= 6 ? C.red : C.orange, transition: "width 1.5s ease" }} />
                    </div>
                  </div>
                  <div style={{ fontSize: 13, color: "rgba(255,255,255,0.60)", lineHeight: 1.5 }}>
                    <span style={{ color: C.green, fontWeight: 600, marginRight: 4 }}>Atténuation :</span>{x.mesures}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ═══ FOOTER ═══ */}
      <section style={{ padding: "70px 18px 40px", textAlign: "center", position: "relative" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 100%,#B8860B0C 0%,transparent 55%)" }} />
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ fontFamily: "'Cormorant Garamond',serif", fontSize: "clamp(18px,3.2vw,32px)", fontWeight: 600, maxWidth: 600, margin: "0 auto 16px", lineHeight: 1.3, fontStyle: "italic" }}>
            « Le Burkina Faso, une Nation souveraine et prospère, bâtissant un développement endogène et durable au service du bien-être de tous »
          </div>
          <div style={{ fontSize: 13, color: C.gold, fontWeight: 600 }}>— Vision du PND 2026-2030</div>
          <div style={{ height: 1, background: `linear-gradient(90deg,transparent,${C.gold}25,transparent)`, maxWidth: 300, margin: "36px auto 16px" }} />
          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.55)" }}>Source : Ministère de l'Économie et des Finances — Burkina Faso — 2026</div>
        </div>
      </section>
    </div>
  );
}
