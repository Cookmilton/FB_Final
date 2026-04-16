import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Cell, ResponsiveContainer, Tooltip } from "recharts";

// ══════════════════════════════════════════════════
// CONSTANTS
// ══════════════════════════════════════════════════

const RUN_FAM = new Set(["inside_zone","outside_zone","duo","power","draw"]);
const FG_RANGE = 35;

const FAM_CLR = {
  inside_zone:"#16a34a", outside_zone:"#22c55e", duo:"#15803d", power:"#166534", draw:"#4ade80",
  quick_game:"#3b82f6", dropback_pass:"#2563eb", screen:"#60a5fa",
  play_action:"#8b5cf6", fade_iso:"#a78bfa", two_point:"#f59e0b",
};
const FAM_LBL = {
  inside_zone:"Inside Zone", outside_zone:"Outside Zone", duo:"Duo", power:"Power", draw:"Draw",
  quick_game:"Quick Game", dropback_pass:"Dropback", screen:"Screen",
  play_action:"Play Action", fade_iso:"Fade/Iso",
};
const BASELINES = {
  short_yardage:  {inside_zone:0.58,duo:0.57,power:0.55,quick_game:0.50,play_action:0.46},
  medium_yardage: {inside_zone:0.41,outside_zone:0.40,quick_game:0.52,dropback_pass:0.50,screen:0.45,play_action:0.48},
  long_yardage:   {draw:0.26,screen:0.42,quick_game:0.39,dropback_pass:0.49,play_action:0.34},
  red_zone:       {inside_zone:0.43,power:0.44,quick_game:0.53,play_action:0.51,fade_iso:0.31},
  backed_up:      {inside_zone:0.44,outside_zone:0.42,quick_game:0.50,screen:0.46,dropback_pass:0.41},
};

// ══════════════════════════════════════════════════
// PLAY LIBRARY
// ══════════════════════════════════════════════════

const LIB = {
  quick_game: [
    { name:"Stick", personnel:"11", formation:"Shotgun Trips Right", protection:"6-man half-slide",
      routes:{X:"Backside slant",H:"Stick route",Y:"Flat/arrow",Z:"Clear fade",RB:"Check-release weak"},
      vs_man:"H wins stick vs. press — attack flat combo immediately.",
      vs_zone:"H settles in the hole between LB and flat; Y stretches the flat.",
      kill_look:"Cover 0 / zero blitz with bracket outside — check to RB hot.",
      post_snap_alert:"Safety rotates high → Z fade is live on the back shoulder.",
      why:"High-pct. Attacks underneath leverage. Ball out fast." },
    { name:"Spacing", personnel:"11", formation:"Shotgun Doubles", protection:"5-man scat",
      routes:{X:"Hitch",H:"Hook",Y:"Hook",Z:"Hitch",RB:"Middle settle"},
      vs_man:"Hitches beat off-coverage. X/Z need clean outside releases.",
      vs_zone:"Hooks find voids. RB middle settle is the safety valve.",
      kill_look:"Press-man with corner blitz — hot to RB immediately.",
      post_snap_alert:"ILB drops to hook-curl zone → RB middle settle is wide open.",
      why:"Safe completion around the sticks vs. zone." },
    { name:"Slant-Flat", personnel:"11", formation:"Shotgun Trips Left", protection:"6-man slide",
      routes:{X:"Boundary slant",H:"Flat",Y:"Seam clear",Z:"Backside dig sit",RB:"Check-release strong"},
      vs_man:"X slant beats inside leverage. Flat is the quick answer vs. press.",
      vs_zone:"H flat pulls CB, opens X slant window. Z dig sits in void.",
      kill_look:"Cloud coverage on the trips side — work backside Z.",
      post_snap_alert:"MIKE scrapes hard to flat → Z backside dig is wide open.",
      why:"Simple triangle read. Clean front-side concept." },
  ],
  dropback_pass: [
    { name:"Dagger", personnel:"11", formation:"Shotgun Trips Right", protection:"6-man half-slide w/ RB scan",
      routes:{X:"Backside hitch",H:"Clear vertical seam",Y:"12-15yd dig",Z:"Outside go/clear",RB:"Check-release"},
      vs_man:"H clears the safety. Y dig is primary vs. man after the clear.",
      vs_zone:"H seam stresses deep third. Y digs into vacated MOF.",
      kill_look:"Cover 0 / all-out blitz — get to quick game or screen.",
      post_snap_alert:"Safety jumps H seam early → Y dig window opens immediately.",
      why:"Stresses safeties. Best medium/long yardage concept." },
    { name:"Drive", personnel:"11", formation:"Gun Doubles", protection:"6-man",
      routes:{X:"Dig",H:"Shallow cross",Y:"Sit over ball",Z:"Clear post",RB:"Swing/outlet"},
      vs_man:"H shallow cross hot vs. man. X dig beats trail technique.",
      vs_zone:"H clears underneath defenders. Y settles in the void.",
      kill_look:"MIKE walks up with no weak-side depth — check to draw or screen.",
      post_snap_alert:"Z clears two safeties → X dig is single coverage.",
      why:"Reliable chain-mover vs. man and zone." },
    { name:"Y-Cross", personnel:"11", formation:"Shotgun Trips Open", protection:"7-man",
      routes:{X:"Backside comeback",H:"Over/cross",Y:"Deep cross",Z:"Clear go",RB:"Insert, check-release"},
      vs_man:"Y deep cross wins vs. man. Z clears the safety.",
      vs_zone:"H and Y create layered stress across the field.",
      kill_look:"Tampa 2 — MIKE brackets Y deep. Work H underneath.",
      post_snap_alert:"Safety rotates to Z → X comeback backside is single coverage.",
      why:"Cross-field stress. Use when you need more than a quick throw." },
  ],
  screen: [
    { name:"RB Middle Screen", personnel:"11", formation:"Shotgun Doubles", protection:"Invite rush, OL delayed",
      routes:{X:"Clear outside",H:"Mandatory outside release",Y:"Clear seam",Z:"Clear vertical",RB:"Middle screen"},
      vs_man:"Man chases receivers deep — clear path for the screen.",
      vs_zone:"Works if LBs are rushing. Zone defenders dropping may read it.",
      kill_look:"LBs sitting in coverage with minimal rush — they will see this develop.",
      post_snap_alert:"LBs drop to zones at snap → consider checking at the line.",
      why:"Best answer to long-yardage pressure looks." },
    { name:"Trips Bubble", personnel:"11", formation:"Trips Right", protection:"Quick perimeter action",
      routes:{X:"Backside glance",H:"Bubble",Y:"Block alley/stalk",Z:"Block corner/stalk",RB:"Inside check"},
      vs_man:"Numbers advantage on the perimeter.",
      vs_zone:"Works if overhang is aggressive. Check MOFO safety alignment.",
      kill_look:"Extra defender walked out over trips — numbers are even. Check inside.",
      post_snap_alert:"3-on-3 on the perimeter → look inside first.",
      why:"Simple space play if numbers are favorable." },
  ],
  play_action: [
    { name:"Boot Flood", personnel:"12", formation:"Singleback Twins", protection:"Wide zone boot",
      routes:{X:"Post/clear backside",Y:"Deep out",H:"Flat in boot path",Z:"Intermediate over",RB:"Run fake, edge seal"},
      vs_man:"H flat in boot path is open immediately vs. man rotating to run.",
      vs_zone:"Y deep out and H flat create high-low on the perimeter.",
      kill_look:"Defense in pure pass look — fake won't freeze anyone.",
      post_snap_alert:"Corner sits flat → Y deep out is the shot.",
      why:"Changes launch point. Clean high-low on perimeter." },
    { name:"Y-Leak", personnel:"12", formation:"Singleback Ace", protection:"Max protect play-action",
      routes:{X:"Post clear",Y:"Delayed leak",H:"Deep crosser",Z:"Comeback",RB:"Run fake/protect"},
      vs_man:"Y leak beats any LB in man — automatic matchup win.",
      vs_zone:"Y leaks into seam as H clears the intermediate level.",
      kill_look:"Two-high with LBs in hook-curl — Y bracketed. Take H crosser.",
      post_snap_alert:"SS attacks Y fake → H deep crosser is 1-on-1.",
      why:"Red-zone shot-play vs. run-action overreaction.", td_pct:0.51 },
  ],
  inside_zone: [{ name:"Inside Zone Strong", personnel:"11", formation:"Shotgun Trips Right",
    run_scheme:"Inside zone to the strength", blocking:"Covered/uncovered zone rules. RB presses front-side A/B gap",
    vs_man:"Double at POA. MIKE movement sets the cut.", vs_zone:"RB presses until front-side crease declares.",
    kill_look:"8-man box with LBs stacked — check to quick pass.",
    post_snap_alert:"MIKE scrapes frontside → cut back to A gap.", why:"Stable box-count baseline run." }],
  outside_zone: [{ name:"Outside Zone Weak", personnel:"11", formation:"Shotgun Doubles",
    run_scheme:"Outside zone weak", blocking:"Full stretch zone rules. RB reads EMLOS to inside cut",
    vs_man:"Stretch forces backside pursuit — RB outruns angles.", vs_zone:"Cutback dependent on how defenders flow.",
    kill_look:"Weakside overhang walked up tight — he will wrong-arm.", post_snap_alert:"EMLOS squeezes hard → bend to cutback lane.",
    why:"Horizontal stress with cutback potential." }],
  duo: [{ name:"Duo", personnel:"12", formation:"Singleback Doubles Tight",
    run_scheme:"Duo downhill", blocking:"Double teams at POA. RB reads MIKE",
    vs_man:"Double teams move the line. MIKE movement sets cut.", vs_zone:"Press playside A until MIKE declares.",
    kill_look:"MIKE stacked inside — crease may not form.", post_snap_alert:"MIKE goes backside → press playside A gap.",
    why:"Short-yardage downhill. No true pullers needed." }],
  power: [{ name:"Power O", personnel:"21", formation:"I-Right",
    run_scheme:"Power right", blocking:"Backside guard pull. FB leads through play-side hole",
    vs_man:"Defined assignment blocks. Guard and FB lead.", vs_zone:"Forces teams to respect the gap scheme backside.",
    kill_look:"Backside LB crashing hard — meets the pulling guard.", post_snap_alert:"DE squeezes → FB logs him, RB bounces outside.",
    why:"Classic gap scheme. Defined entry in tight yardage." }],
  draw: [{ name:"Shotgun Draw", personnel:"11", formation:"Shotgun Trips",
    run_scheme:"Delayed draw", blocking:"Pass-set sell. OL climbs late to second level",
    vs_man:"Pass rush creates lanes as OL climbs.", vs_zone:"Zone may read the delay. Best vs. heavy rushers.",
    kill_look:"Spy LB or 3-man rush — he fills the gap.", post_snap_alert:"DEs rushing wide → A/B gap opens as OL climbs.",
    why:"Pressure counter on longer downs." }],
  fade_iso: [{ name:"Boundary Fade", personnel:"11", formation:"Shotgun Doubles", protection:"5-man quick",
    routes:{X:"Fade",H:"Speed out",Y:"Stick",Z:"Slant",RB:"Check-release"},
    vs_man:"Fade wins on back shoulder vs. off-coverage CB.", vs_zone:"Limited. CB drives downhill on the break.",
    kill_look:"CB pressing — 50/50 ball. Consider slant-flat instead.", post_snap_alert:"CB gives hard outside release → throw back-shoulder fade.",
    why:"Red-zone option when you trust the matchup outside.", td_pct:0.31 }],
  two_point: [
    { name:"Rub / Pick Slant", personnel:"11", formation:"Shotgun Bunch Right", protection:"5-man quick",
      routes:{X:"Clear fade",H:"Inside rub/pick",Y:"Slant off rub",Z:"Flat",RB:"Check-release middle"},
      vs_man:"Rub creates natural pick on slant — primary read.", vs_zone:"Slant finds void. Flat stretches defense.",
      kill_look:"Zone coverage — rub won't free anyone. Work flat/RB.", post_snap_alert:"CB follows H on rub → Y slant is open.",
      why:"Highest-pct 2-pt call vs. man in compressed EZ." },
    { name:"QB Power / Sneak", personnel:"22", formation:"I-Tight", run_scheme:"QB power or sneak",
      blocking:"Double team C-G gap. FB leads if QB keeps",
      vs_man:"Brute force in tight space.", vs_zone:"Same — half a yard is all you need.",
      kill_look:"9-man box — consider a pass instead.", post_snap_alert:"C gap closes → keep and bounce off FB shoulder.",
      why:"Most reliable short-yardage 2-pt option." },
    { name:"Shovel / RPO Bubble", personnel:"11", formation:"Shotgun Trips Left", protection:"RPO mesh",
      routes:{X:"Backside clearout",H:"Bubble",Y:"Shovel/mesh",Z:"Block/stalk",RB:"Inside zone mesh"},
      vs_man:"Bubble wins vs. man if outside is blocked.", vs_zone:"DE crashes → pull and throw bubble.",
      kill_look:"LB walked out over H pre-snap — go with shovel.", post_snap_alert:"DE crashes mesh → pull and throw bubble immediately.",
      why:"Puts defense in conflict. Run and perimeter." },
  ],
};

// ══════════════════════════════════════════════════
// LOGIC
// ══════════════════════════════════════════════════

const getBucket = c => {
  if (c.territory==="opponents" && c.yardline<=20) return "red_zone";
  if (c.territory==="own" && c.yardline<=10) return "backed_up";
  if (c.distance<=2) return "short_yardage";
  if (c.distance<=6) return "medium_yardage";
  return "long_yardage";
};

const deriveMode = c => {
  if (c.gameMode!=="normal") return c.gameMode;
  if ([2,4].includes(c.quarter) && c.secondsRemaining<=120) return "two_minute";
  if ((c.scoreDiff<=-14&&c.quarter===4)||(c.scoreDiff<=-8&&c.quarter===4&&c.secondsRemaining<=240)) return "must_score";
  if (c.scoreDiff>=10&&c.quarter===4&&c.secondsRemaining>120) return "drain_clock";
  return "normal";
};

const scoreAll = (c, bucket) => {
  const s = {...BASELINES[bucket]};
  const n = (f,a) => { if (f in s) s[f] = +(s[f]+a).toFixed(3); };
  if (c.down===1) { n("inside_zone",.02); n("play_action",.02); }
  if (c.down===2&&c.distance>=7) { n("dropback_pass",.03); n("quick_game",.02); }
  if (c.down===3) { n("dropback_pass",.04); if(c.distance<=4)n("quick_game",.03); if(c.distance>=8)n("screen",.02); }
  if (c.boxCount<=6) { n("inside_zone",.04); n("outside_zone",.03); n("duo",.02); n("dropback_pass",-.02); }
  else if (c.boxCount>=8) { n("inside_zone",-.04); n("duo",-.03); n("dropback_pass",.04); n("quick_game",.03); }
  if (["cover_0","cover_1"].includes(c.coverageShell)) { n("play_action",.05); n("screen",.04); n("quick_game",.03); n("dropback_pass",-.03); }
  else if (c.coverageShell==="cover_2") { n("outside_zone",.03); n("dropback_pass",.02); n("quick_game",-.02); }
  else if (c.coverageShell==="cover_3") { n("dropback_pass",.04); }
  else if (["cover_4","quarters"].includes(c.coverageShell)) { n("quick_game",.05); n("draw",.03); n("play_action",-.03); }
  if (c.safeties==="single_high") { n("play_action",.04); n("dropback_pass",.03); }
  else if (c.safeties==="two_high") { n("quick_game",.03); n("screen",.02); n("dropback_pass",-.02); }
  if (c.blitzLikely) { n("screen",.05); n("quick_game",.04); n("dropback_pass",-.03); n("play_action",-.02); }
  if (c.weather==="wind"&&c.windMph>=20) { n("play_action",-.05); n("dropback_pass",-.04); n("inside_zone",.04); n("quick_game",.03); }
  if (["rain","snow"].includes(c.weather)) { n("dropback_pass",-.06); n("play_action",-.04); n("screen",-.03); n("inside_zone",.05); n("duo",.04); }
  if (c.gameMode==="drain_clock") { n("inside_zone",.06); n("duo",.04); n("power",.03); n("dropback_pass",-.05); n("screen",-.04); }
  else if (c.gameMode==="must_score") { n("dropback_pass",.05); n("play_action",.04); n("inside_zone",-.03); }
  else if (c.gameMode==="two_minute") { n("quick_game",.06); n("dropback_pass",.04); n("inside_zone",-.05); n("play_action",-.04); }
  if (c.qbLimited) { n("dropback_pass",-.04); n("play_action",-.03); n("inside_zone",.04); n("quick_game",.03); }
  if ("play_action" in s && c.runPlaysThisDrive<3) n("play_action",-.04);
  return s;
};

const chooseFamily = (c, bucket) => {
  const s = scoreAll(c, bucket);
  if (c.down===4) {
    const pref = c.distance<=2 ? ["duo","power","inside_zone","quick_game"] : ["quick_game","dropback_pass","screen"];
    const f = Object.fromEntries(Object.entries(s).filter(([k])=>pref.includes(k)));
    if (Object.keys(f).length) return Object.entries(f).reduce((a,b)=>a[1]>b[1]?a:b)[0];
  }
  return Object.entries(s).reduce((a,b)=>a[1]>b[1]?a:b)[0];
};

const choosePlay = (family, c) => {
  const cands = LIB[family]||[];
  if (!cands.length) return null;
  const find = n => cands.find(p=>p.name===n);
  if (family==="quick_game") {
    if (c.distance<=3) { const p=find("Stick"); if(p)return p; }
    if (c.distance>=6) { const p=find("Slant-Flat"); if(p)return p; }
  }
  if (family==="dropback_pass") {
    if (c.distance>=8) { const p=find("Dagger"); if(p)return p; }
    else { const p=find("Drive"); if(p)return p; }
  }
  if (family==="play_action" && c.territory==="opponents" && c.yardline<=20) {
    const p=find("Y-Leak"); if(p)return p;
  }
  return cands[Math.floor(Math.random()*cands.length)];
};

const fdAdvice = c => {
  if (c.down!==4) return null;
  const inFG = c.territory==="opponents" && c.yardline<=FG_RANGE;
  const fgD  = c.territory==="opponents" ? c.yardline+17 : null;
  const ms   = ["must_score","two_minute"].includes(c.gameMode)||(c.scoreDiff<0&&c.quarter===4&&c.secondsRemaining<300);
  if (c.territory==="opponents"&&c.yardline<=2)            return {rec:"Go for it",  reason:"Goal line — take the TD.", fgD:null, color:"#22c55e"};
  if (inFG&&!ms&&c.distance>3)                             return {rec:"Field goal",  reason:`~${fgD}-yard attempt. Take the points.`, fgD, color:"#3b82f6"};
  if (c.distance<=1)                                       return {rec:"Go for it",  reason:"1 yard or less — conversion rate exceeds field position risk.", fgD, color:"#22c55e"};
  if (c.territory==="opponents"&&c.yardline<=40&&c.distance<=3) return {rec:"Go for it", reason:`${c.distance} yards in opp. territory — attempt it.`, fgD:inFG?fgD:null, color:"#22c55e"};
  if (ms)                                                  return {rec:"Go for it",  reason:"Game script demands the conversion.", fgD:inFG?fgD:null, color:"#22c55e"};
  return {rec:"Punt", reason:"Outside FG range — flip field position.", fgD:null, color:"#9ca3af"};
};

const recommend = c => {
  const mode   = deriveMode(c);
  const cx     = {...c, gameMode:mode};
  if (mode==="two_point") {
    const cands = LIB.two_point||[];
    return {ctx:cx, bucket:"two_point", family:"two_point", play:cands[Math.floor(Math.random()*cands.length)], scores:{}, fd:null};
  }
  const bucket = getBucket(cx);
  const scores = scoreAll(cx, bucket);
  const family = chooseFamily(cx, bucket);
  const play   = choosePlay(family, cx);
  return {ctx:cx, bucket, family, play, scores, fd:fdAdvice(cx)};
};

// ══════════════════════════════════════════════════
// THEME
// ══════════════════════════════════════════════════

const T = {
  bg:    "#0c0f14",
  card:  "#111820",
  bdr:   "#1e2836",
  gold:  "#f5c518",
  text:  "#e2e8f0",
  muted: "#6b7280",
  mono:  "'Courier New', Courier, monospace",
  head:  "Impact, 'Arial Black', sans-serif",
};

// ══════════════════════════════════════════════════
// SMALL UI COMPONENTS
// ══════════════════════════════════════════════════

const Btn = ({label, sel, onClick, accent="#f5c518", small}) => (
  <button onClick={onClick} style={{
    padding: small ? "4px 8px" : "7px 11px",
    borderRadius: 4, border:"1px solid",
    borderColor: sel ? accent : T.bdr,
    background: sel ? `${accent}18` : T.card,
    color: sel ? accent : T.muted,
    fontSize: small ? 10 : 12, fontFamily: T.mono,
    cursor: "pointer", minWidth: small ? 28 : 36, minHeight: small ? 28 : 34,
  }}>{label}</button>
);

const BtnGrp = ({label, options, value, onChange, small, accent}) => (
  <div style={{marginBottom:10}}>
    {label && <div style={{color:T.muted, fontSize:10, fontFamily:T.mono, letterSpacing:"0.08em", textTransform:"uppercase", marginBottom:5}}>{label}</div>}
    <div style={{display:"flex", flexWrap:"wrap", gap:3}}>
      {options.map(o => {
        const v = typeof o==="object" ? o.value : o;
        const l = typeof o==="object" ? o.label : String(o);
        return <Btn key={v} label={l} sel={value===v} onClick={()=>onChange(v)} small={small} accent={accent}/>;
      })}
    </div>
  </div>
);

const Sld = ({label, min, max, value, onChange, fmt}) => (
  <div style={{marginBottom:10}}>
    <div style={{display:"flex", justifyContent:"space-between", marginBottom:4}}>
      <span style={{color:T.muted, fontSize:10, fontFamily:T.mono, letterSpacing:"0.08em", textTransform:"uppercase"}}>{label}</span>
      <span style={{color:T.gold, fontFamily:T.mono, fontSize:12}}>{fmt ? fmt(value) : value}</span>
    </div>
    <input type="range" min={min} max={max} value={value} step={1}
      onChange={e=>onChange(+e.target.value)} style={{width:"100%", accentColor:T.gold}}/>
  </div>
);

const SecH = ({children}) => (
  <div style={{color:T.gold, fontFamily:T.head, fontSize:15, letterSpacing:"0.06em",
    marginTop:16, marginBottom:8, paddingBottom:4, borderBottom:`1px solid ${T.bdr}`}}>
    {children}
  </div>
);

const IRow = ({icon, label, text, color="#9ca3af"}) => (
  <div style={{display:"flex", gap:6, marginBottom:5, padding:"5px 8px",
    borderRadius:4, background:"rgba(255,255,255,0.02)"}}>
    <span style={{color, fontFamily:T.mono, fontSize:11, flexShrink:0}}>{icon}</span>
    <span style={{color, fontFamily:T.mono, fontSize:9, textTransform:"uppercase",
      minWidth:66, paddingTop:1, letterSpacing:"0.06em", flexShrink:0}}>{label}</span>
    <span style={{color:"#d1d5db", fontFamily:T.mono, fontSize:11, flex:1, lineHeight:1.4}}>{text}</span>
  </div>
);

// ══════════════════════════════════════════════════
// FOOTBALL FIELD SVG
// ══════════════════════════════════════════════════

const Field = ({c}) => {
  const YPX=5.2, EZ=44, W=624, H=86, FL=EZ, FR=W-EZ;
  const bx  = c.territory==="own" ? FL+c.yardline*YPX : FR-c.yardline*YPX;
  const fdx = Math.max(FL+2, Math.min(FR-2, c.territory==="own" ? bx+c.distance*YPX : bx-c.distance*YPX));
  const rzL = FR-20*YPX;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{width:"100%", display:"block", borderRadius:5, border:`1px solid ${T.bdr}`}}>
      <rect width={W} height={H} fill="#090e0b"/>
      {[...Array(10)].map((_,i)=>(
        <rect key={i} x={FL+i*10*YPX} y={0} width={10*YPX} height={H} fill={i%2===0?"#0c1a0f":"#0e1f12"}/>
      ))}
      <rect x={0}  y={0} width={EZ} height={H} fill="#0b1a0c"/>
      <rect x={FR} y={0} width={EZ} height={H} fill="#1a0b0b"/>
      <rect x={rzL} y={0} width={20*YPX} height={H} fill="rgba(220,38,38,0.06)"/>
      <line x1={rzL} y1={0} x2={rzL} y2={H} stroke="rgba(220,38,38,0.3)" strokeWidth={1} strokeDasharray="3 2"/>
      {[...Array(11)].map((_,i)=>(
        <line key={i} x1={FL+i*10*YPX} y1={0} x2={FL+i*10*YPX} y2={H} stroke="rgba(255,255,255,0.16)" strokeWidth={1}/>
      ))}
      {[...Array(21)].map((_,i)=>{
        const x=FL+i*5*YPX;
        return [
          <line key={`a${i}`} x1={x} y1={H*.28} x2={x} y2={H*.42} stroke="rgba(255,255,255,0.1)" strokeWidth={0.5}/>,
          <line key={`b${i}`} x1={x} y1={H*.58} x2={x} y2={H*.72} stroke="rgba(255,255,255,0.1)" strokeWidth={0.5}/>
        ];
      })}
      {[10,20,30,40,50].map(y=>(
        <text key={y} x={FL+y*YPX} y={H/2+3.5} fill="rgba(255,255,255,0.18)"
          fontSize={8} textAnchor="middle" fontFamily="monospace" fontWeight="700">{y}</text>
      ))}
      {[60,70,80,90].map(y=>(
        <text key={y} x={FL+y*YPX} y={H/2+3.5} fill="rgba(255,255,255,0.18)"
          fontSize={8} textAnchor="middle" fontFamily="monospace" fontWeight="700">{100-y}</text>
      ))}
      <text x={EZ/2}   y={H/2+3} fill="rgba(255,255,255,0.22)" fontSize={7} textAnchor="middle" fontFamily="monospace">OWN</text>
      <text x={W-EZ/2} y={H/2+3} fill="rgba(255,255,255,0.22)" fontSize={7} textAnchor="middle" fontFamily="monospace">OPP</text>
      <line x1={fdx} y1={0} x2={fdx} y2={H} stroke={T.gold} strokeWidth={1.5} strokeDasharray="4 3" opacity={0.6}/>
      <line x1={bx}  y1={4} x2={bx}  y2={H-4} stroke={T.gold} strokeWidth={2.5}/>
      <ellipse cx={bx} cy={H/2} rx={6} ry={3.8} fill="#c47e3a" stroke="#e09050" strokeWidth={0.5}
        transform={`rotate(-20 ${bx} ${H/2})`}/>
      <rect x={bx-14} y={4} width={28} height={12} rx={2} fill="rgba(0,0,0,0.8)"/>
      <text x={bx} y={13} fill={T.gold} fontSize={8} textAnchor="middle"
        fontFamily="monospace">{c.down}&amp;{c.distance}</text>
      {c.territory==="opponents" && c.yardline<=20 && (
        <>
          <rect x={rzL+3} y={3} width={28} height={10} rx={2} fill="rgba(220,38,38,0.35)"/>
          <text x={rzL+17} y={10.5} fill="#fca5a5" fontSize={6.5} textAnchor="middle" fontFamily="monospace">RED ZONE</text>
        </>
      )}
    </svg>
  );
};

// ══════════════════════════════════════════════════
// SCORE BAR CHART
// ══════════════════════════════════════════════════

const ScoreChart = ({scores}) => {
  if (!scores || !Object.keys(scores).length) return null;
  const data = Object.entries(scores)
    .sort(([,a],[,b])=>b-a)
    .map(([fam,score])=>({name:FAM_LBL[fam]||fam, score:+(score*100).toFixed(1), color:FAM_CLR[fam]||"#6b7280"}));
  return (
    <div style={{marginTop:18}}>
      <div style={{color:T.gold, fontFamily:T.head, fontSize:14, letterSpacing:"0.06em", marginBottom:8}}>
        Family scores
        <span style={{color:T.muted, fontFamily:T.mono, fontSize:9, marginLeft:8, letterSpacing:0}}>adjusted for situation</span>
      </div>
      <div style={{display:"flex", gap:8, marginBottom:8, flexWrap:"wrap"}}>
        {[{label:"Run", color:"#16a34a"},{label:"Pass", color:"#3b82f6"},{label:"PA", color:"#8b5cf6"}].map(({label,color})=>(
          <span key={label} style={{display:"flex", alignItems:"center", gap:4, fontSize:10, color:T.muted, fontFamily:T.mono}}>
            <span style={{width:10, height:10, borderRadius:2, background:color, display:"inline-block"}}/>
            {label}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={data.length*28+16}>
        <BarChart data={data} layout="vertical" margin={{left:4, right:36, top:2, bottom:2}}>
          <XAxis type="number" domain={[20,72]} hide/>
          <YAxis type="category" dataKey="name" width={82}
            tick={{fill:"#9ca3af", fontSize:10, fontFamily:"'Courier New'"}}/>
          <Tooltip
            formatter={v=>[`${v}%`, "Score"]}
            contentStyle={{background:"#1a2030", border:`1px solid ${T.bdr}`, borderRadius:4, fontFamily:"'Courier New'", fontSize:11}}/>
          <Bar dataKey="score" radius={[0,3,3,0]} barSize={15}
            label={{position:"right", formatter:v=>`${v}%`, fill:"#6b7280", fontSize:9, fontFamily:"'Courier New'"}}>
            {data.map((d,i)=><Cell key={i} fill={d.color}/>)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

// ══════════════════════════════════════════════════
// DRIVE LOG
// ══════════════════════════════════════════════════

const DriveLog = ({log, onReset}) => {
  const counts = {};
  log.forEach(r=>{ counts[r.family]=(counts[r.family]||0)+1; });
  const runs = log.filter(r=>RUN_FAM.has(r.family)).length;
  return (
    <div>
      <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10}}>
        <div style={{color:T.gold, fontFamily:T.head, fontSize:15, letterSpacing:"0.06em"}}>
          Drive log
          {log.length>0 && <span style={{color:T.muted, fontFamily:T.mono, fontSize:9, marginLeft:8, letterSpacing:0}}>
            {log.length} plays · {runs}R / {log.length-runs}P
          </span>}
        </div>
        {log.length>0 && (
          <button onClick={onReset} style={{background:"transparent", border:`1px solid ${T.bdr}`,
            borderRadius:4, color:T.muted, fontSize:9, fontFamily:T.mono, cursor:"pointer", padding:"3px 8px"}}>
            New drive
          </button>
        )}
      </div>
      {!log.length
        ? <div style={{color:"#374151", fontFamily:T.mono, fontSize:11}}>No plays logged this drive.</div>
        : <>
            <div style={{display:"flex", flexWrap:"wrap", gap:3, marginBottom:10}}>
              {log.map((r,i)=>(
                <span key={i} style={{padding:"2px 7px", borderRadius:3,
                  background:`${FAM_CLR[r.family]||"#6b7280"}1a`,
                  border:`1px solid ${FAM_CLR[r.family]||"#6b7280"}44`,
                  color:FAM_CLR[r.family]||"#9ca3af", fontSize:9, fontFamily:T.mono}}>
                  {FAM_LBL[r.family]||r.family} {r.yards>=0?"+":""}{r.yards}
                </span>
              ))}
            </div>
            {Object.entries(counts).filter(([,v])=>v>=3).map(([fam,cnt])=>(
              <div key={fam} style={{display:"flex", gap:6, padding:"6px 9px", borderRadius:4,
                background:"rgba(245,197,24,0.07)", border:"1px solid rgba(245,197,24,0.18)", marginBottom:4}}>
                <span style={{color:T.gold, fontFamily:T.mono, fontSize:9, textTransform:"uppercase", paddingTop:1}}>Tendency</span>
                <span style={{color:"#f5c518", fontFamily:T.mono, fontSize:11}}>
                  {FAM_LBL[fam]||fam} called {cnt}x this drive — defense is keying on it.
                </span>
              </div>
            ))}
          </>
      }
    </div>
  );
};

// ══════════════════════════════════════════════════
// PLAY CARD
// ══════════════════════════════════════════════════

const PlayCard = ({result, driveLog}) => {
  const {family, play, ctx} = result;
  const fc = FAM_CLR[family]||"#6b7280";
  const isMan = ["cover_0","cover_1"].includes(ctx.coverageShell);
  const covNote = ctx.coverageShell!=="unknown" ? (isMan ? play.vs_man : play.vs_zone) : null;
  const paWarn = family==="play_action" && ctx.runPlaysThisDrive<3
    ? `Run not established (${ctx.runPlaysThisDrive} run plays this drive) — fake may not freeze LBs.` : null;
  const wxWarn = ["wind","rain","snow"].includes(ctx.weather) && ["dropback_pass","play_action"].includes(family)
    ? (ctx.weather==="wind" ? `Wind ${ctx.windMph}mph — shorten the route tree.`
      : ctx.weather==="rain" ? "Wet conditions — prioritize short throws."
      : "Snow — consider running instead.") : null;
  const ovCnt = driveLog.filter(p=>p.family===family).length;

  return (
    <div style={{borderRadius:6, border:`1px solid ${fc}33`, background:`${fc}08`, overflow:"hidden"}}>
      <div style={{padding:"10px 13px", borderBottom:`1px solid ${fc}22`, background:`${fc}12`,
        display:"flex", justifyContent:"space-between", alignItems:"flex-start"}}>
        <div>
          <div style={{color:"#f0f4f8", fontFamily:T.head, fontSize:21, letterSpacing:"0.03em", lineHeight:1.1}}>{play.name}</div>
          <div style={{color:fc, fontFamily:T.mono, fontSize:9, letterSpacing:"0.1em", textTransform:"uppercase", marginTop:3}}>
            {FAM_LBL[family]||family}
          </div>
        </div>
        <div style={{textAlign:"right", flexShrink:0}}>
          {play.personnel && <div style={{color:T.muted, fontFamily:T.mono, fontSize:10}}>#{play.personnel}</div>}
          {play.td_pct && <div style={{color:T.gold, fontFamily:T.mono, fontSize:12, fontWeight:"bold"}}>TD {Math.round(play.td_pct*100)}%</div>}
        </div>
      </div>

      <div style={{padding:"11px 13px"}}>
        <div style={{display:"flex", gap:14, marginBottom:10, flexWrap:"wrap"}}>
          {play.formation && <div>
            <div style={{color:"#374151", fontSize:9, fontFamily:T.mono, textTransform:"uppercase", marginBottom:1}}>Formation</div>
            <div style={{color:"#d1d5db", fontFamily:T.mono, fontSize:11}}>{play.formation}</div>
          </div>}
          {(play.protection||play.blocking) && <div>
            <div style={{color:"#374151", fontSize:9, fontFamily:T.mono, textTransform:"uppercase", marginBottom:1}}>{play.protection?"Protection":"Blocking"}</div>
            <div style={{color:"#d1d5db", fontFamily:T.mono, fontSize:11}}>{play.protection||play.blocking}</div>
          </div>}
          {play.run_scheme && <div>
            <div style={{color:"#374151", fontSize:9, fontFamily:T.mono, textTransform:"uppercase", marginBottom:1}}>Scheme</div>
            <div style={{color:"#d1d5db", fontFamily:T.mono, fontSize:11}}>{play.run_scheme}</div>
          </div>}
        </div>

        {play.routes && (
          <div style={{marginBottom:10}}>
            <div style={{color:"#374151", fontSize:9, fontFamily:T.mono, textTransform:"uppercase", marginBottom:5}}>Routes</div>
            <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:"2px 12px"}}>
              {Object.entries(play.routes).map(([pos,route])=>(
                <div key={pos} style={{display:"flex", gap:7}}>
                  <span style={{color:fc, fontFamily:T.mono, fontSize:11, fontWeight:"bold", minWidth:20}}>{pos}</span>
                  <span style={{color:"#e2e8f0", fontFamily:T.mono, fontSize:11}}>{route}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{padding:"6px 9px", borderRadius:4, borderLeft:`2px solid ${fc}`,
          background:"rgba(255,255,255,0.025)", marginBottom:8}}>
          <span style={{color:T.muted, fontFamily:T.mono, fontSize:9, textTransform:"uppercase"}}>Why: </span>
          <span style={{color:"#d1d5db", fontFamily:T.mono, fontSize:11}}>{play.why}</span>
        </div>

        {covNote
          ? <IRow icon=">" label={`vs. ${ctx.coverageShell.replace(/_/g," ").toUpperCase()}`} text={covNote} color="#3b82f6"/>
          : <>{play.vs_man&&<IRow icon=">" label="vs. Man" text={play.vs_man} color="#3b82f6"/>}
               {play.vs_zone&&<IRow icon=">" label="vs. Zone" text={play.vs_zone} color="#60a5fa"/>}</>
        }
        {play.kill_look        && <IRow icon="X" label="Kill look"  text={play.kill_look}        color="#ef4444"/>}
        {play.post_snap_alert  && <IRow icon="*" label="Post-snap"  text={play.post_snap_alert}   color="#8b5cf6"/>}
        {paWarn                && <IRow icon="!" label="PA warn"    text={paWarn}                  color="#f59e0b"/>}
        {wxWarn                && <IRow icon="~" label="Weather"    text={wxWarn}                  color="#60a5fa"/>}
        {ctx.mismatch          && <IRow icon="*" label="Mismatch"   text={ctx.mismatch}            color="#f59e0b"/>}
        {ovCnt>=3              && <IRow icon="!" label="Tendency"   text={`${FAM_LBL[family]} called ${ovCnt}x this drive.`} color={T.gold}/>}
        {ctx.gameMode==="two_minute" && <IRow icon=">" label="Tempo" text={`Hurry-up — ${ctx.ownTimeouts} TOs left. Spike or go OOB.`} color="#f59e0b"/>}
        {ctx.gameMode==="drain_clock"&& <IRow icon=">" label="Tempo" text="Milk it — long cadence, stay in bounds." color="#22c55e"/>}
        {ctx.blitzLikely       && <IRow icon=">" label="Snap count" text="Hard count — see if they jump before the snap." color="#f59e0b"/>}
      </div>
    </div>
  );
};

// ══════════════════════════════════════════════════
// 4TH DOWN CARD
// ══════════════════════════════════════════════════

const FDCard = ({adv}) => {
  if (!adv) return null;
  return (
    <div style={{padding:"9px 12px", borderRadius:6, background:`${adv.color}10`,
      border:`1px solid ${adv.color}33`, marginBottom:10}}>
      <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:3}}>
        <span style={{color:adv.color, fontFamily:T.head, fontSize:16, letterSpacing:"0.05em"}}>
          4th down: {adv.rec}
        </span>
        {adv.fgD && <span style={{color:T.muted, fontFamily:T.mono, fontSize:10}}>~{adv.fgD} yds</span>}
      </div>
      <div style={{color:T.muted, fontFamily:T.mono, fontSize:11}}>{adv.reason}</div>
    </div>
  );
};

// ══════════════════════════════════════════════════
// OPTION SETS
// ══════════════════════════════════════════════════

const CVG  = [{value:"unknown",label:"?"},{value:"cover_0",label:"Cvr 0"},{value:"cover_1",label:"Cvr 1"},{value:"cover_2",label:"Cvr 2"},{value:"cover_3",label:"Cvr 3"},{value:"cover_4",label:"Cvr 4"},{value:"quarters",label:"Qtr"}];
const SAF  = [{value:"unknown",label:"?"},{value:"single_high",label:"Single"},{value:"two_high",label:"2-high"}];
const PERS = [{value:"unknown",label:"?"},{value:"nickel",label:"Nickel"},{value:"base",label:"Base"},{value:"dime",label:"Dime"},{value:"goal_line",label:"GL"}];
const WX   = [{value:"clear",label:"Clear"},{value:"wind",label:"Wind"},{value:"rain",label:"Rain"},{value:"snow",label:"Snow"}];
const MDS  = [{value:"normal",label:"Normal"},{value:"must_score",label:"Must score"},{value:"drain_clock",label:"Drain clock"},{value:"two_minute",label:"2-min drill"},{value:"two_point",label:"2-pt conv."}];
const BANNERS = {
  two_minute:  {t:"Two-minute drill",  c:"#ef4444"},
  must_score:  {t:"Must score",         c:"#ef4444"},
  drain_clock: {t:"Drain the clock",   c:"#22c55e"},
  two_point:   {t:"Two-point conversion", c:"#f59e0b"},
};

// ══════════════════════════════════════════════════
// MAIN APP
// ══════════════════════════════════════════════════

export default function App() {
  const [ctx, setCtx] = useState({
    down:1, distance:10, yardline:25, territory:"own",
    defPersonnel:"unknown", boxCount:7, coverageShell:"unknown",
    blitzLikely:false, safeties:"unknown",
    scoreDiff:0, quarter:2, secondsRemaining:1800,
    ownTimeouts:3, oppTimeouts:3,
    weather:"clear", windMph:0, qbLimited:false,
    mismatch:"", gameMode:"normal",
    runPlaysThisDrive:0, playsThisDrive:0,
  });
  const [result,   setResult]   = useState(null);
  const [driveLog, setDriveLog] = useState([]);
  const [yards,    setYards]    = useState("");
  const [tab,      setTab]      = useState("call");

  const set = (k,v) => setCtx(c=>({...c,[k]:v}));
  const fmtT = s => `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;

  const gen = () => {
    const runs = driveLog.filter(p=>RUN_FAM.has(p.family)).length;
    const r = recommend({...ctx, runPlaysThisDrive:runs, playsThisDrive:driveLog.length});
    setResult(r);
    setTab("play");
    setYards("");
  };

  const logResult = () => {
    if (!result) return;
    const y = parseInt(yards);
    if (isNaN(y)) return;
    const outcome = y>=ctx.distance ? "first_down" : y<-3 ? "sack" : "short";
    setDriveLog(l=>[...l, {family:result.family, yards:y, outcome}]);
    setYards("");
  };

  const effMode = result ? result.ctx.gameMode : deriveMode(ctx);
  const banner  = BANNERS[effMode];

  return (
    <div style={{height:"100vh", display:"flex", flexDirection:"column", background:T.bg, color:T.text}}>
      <style>{`*{box-sizing:border-box}::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:#252d3a}input[type=range]{accent-color:#f5c518;width:100%;cursor:pointer}input[type=text]{background:#111820;border:1px solid #1e2836;border-radius:4px;color:#e2e8f0;padding:5px 9px;font-size:11px;width:100%;outline:none;font-family:'Courier New',monospace}`}</style>

      {/* ── Header ── */}
      <div style={{display:"flex", alignItems:"center", gap:10, padding:"8px 16px",
        background:"#0d1118", borderBottom:`1px solid ${T.bdr}`, flexShrink:0, flexWrap:"wrap"}}>
        <span style={{fontFamily:T.head, fontSize:20, color:T.gold, letterSpacing:"0.06em"}}>Play Caller</span>
        <span style={{color:"#374151", fontFamily:T.mono, fontSize:9}}>Sideline OC</span>
        <div style={{flex:1}}/>
        {banner && (
          <div style={{padding:"2px 10px", borderRadius:3, background:`${banner.c}18`, color:banner.c,
            fontFamily:T.head, fontSize:13, letterSpacing:"0.08em"}}>{banner.t}</div>
        )}
        <span style={{color:T.muted, fontFamily:T.mono, fontSize:11}}>Q{ctx.quarter} {fmtT(ctx.secondsRemaining)}</span>
        <span style={{color:ctx.scoreDiff>0?"#22c55e":ctx.scoreDiff<0?"#ef4444":T.muted,
          fontFamily:T.mono, fontSize:12, fontWeight:"bold"}}>
          {ctx.scoreDiff>0?"+":""}{ctx.scoreDiff}
        </span>
      </div>

      {/* ── Tabs ── */}
      <div style={{display:"flex", background:"#0d1118", borderBottom:`1px solid ${T.bdr}`, flexShrink:0}}>
        {[{k:"call",l:"Call play"},{k:"play",l:"Play call"},{k:"drive",l:"Drive log"}].map(({k,l})=>(
          <button key={k} onClick={()=>setTab(k)} style={{
            flex:1, padding:"8px 0", background:"transparent", border:"none",
            borderBottom:`2px solid ${tab===k?T.gold:"transparent"}`,
            color:tab===k?T.gold:T.muted, fontFamily:T.mono, fontSize:11, cursor:"pointer", letterSpacing:"0.06em",
          }}>{l}</button>
        ))}
      </div>

      {/* ── Content ── */}
      <div style={{flex:1, overflow:"auto", padding:"14px 16px"}}>

        {/* ─ CALL PLAY tab ─ */}
        {tab==="call" && (
          <div>
            <SecH>Down &amp; distance</SecH>
            <BtnGrp label="Down" options={[1,2,3,4]} value={ctx.down} onChange={v=>set("down",v)}/>
            <BtnGrp label="Distance" options={[1,2,3,4,5,6,7,8,9,10,12,15,20]} value={ctx.distance} onChange={v=>set("distance",v)} small/>

            <SecH>Field position</SecH>
            <BtnGrp label="Territory" options={[{value:"own",label:"Own"},{value:"opponents",label:"Opp."}]} value={ctx.territory} onChange={v=>set("territory",v)}/>
            <Sld label="Yardline" min={1} max={50} value={ctx.yardline} onChange={v=>set("yardline",v)}
              fmt={v=>`${ctx.territory==="opponents"?"Opp.":"Own"} ${v}`}/>
            <div style={{marginBottom:12}}><Field c={ctx}/></div>

            <SecH>Defensive read</SecH>
            <BtnGrp label="Personnel" options={PERS} value={ctx.defPersonnel} onChange={v=>set("defPersonnel",v)} small/>
            <Sld label="Box count" min={4} max={9} value={ctx.boxCount} onChange={v=>set("boxCount",v)} fmt={v=>`${v} in box`}/>
            <BtnGrp label="Coverage" options={CVG} value={ctx.coverageShell} onChange={v=>set("coverageShell",v)} small/>
            <BtnGrp label="Safeties" options={SAF} value={ctx.safeties} onChange={v=>set("safeties",v)} small/>
            <div style={{marginBottom:10}}>
              <Btn label={`Blitz: ${ctx.blitzLikely?"Yes":"No"}`} sel={ctx.blitzLikely}
                onClick={()=>set("blitzLikely",!ctx.blitzLikely)} accent="#ef4444"/>
            </div>

            <SecH>Game script</SecH>
            <BtnGrp label="Quarter" options={[1,2,3,4]} value={ctx.quarter} onChange={v=>set("quarter",v)}/>
            <Sld label="Score differential" min={-28} max={28} value={ctx.scoreDiff} onChange={v=>set("scoreDiff",v)}
              fmt={v=>v===0?"Tied":v>0?`+${v} ahead`:`${Math.abs(v)} behind`}/>
            <Sld label="Time remaining" min={0} max={3600} value={ctx.secondsRemaining}
              onChange={v=>set("secondsRemaining",v)} fmt={fmtT}/>
            <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:10}}>
              <div>
                <div style={{color:T.muted, fontSize:10, fontFamily:T.mono, textTransform:"uppercase", marginBottom:4, letterSpacing:"0.08em"}}>Own TOs</div>
                <BtnGrp options={[0,1,2,3]} value={ctx.ownTimeouts} onChange={v=>set("ownTimeouts",v)} small/>
              </div>
              <div>
                <div style={{color:T.muted, fontSize:10, fontFamily:T.mono, textTransform:"uppercase", marginBottom:4, letterSpacing:"0.08em"}}>Opp TOs</div>
                <BtnGrp options={[0,1,2,3]} value={ctx.oppTimeouts} onChange={v=>set("oppTimeouts",v)} small/>
              </div>
            </div>

            <SecH>Extras</SecH>
            <BtnGrp label="Weather" options={WX} value={ctx.weather} onChange={v=>set("weather",v)} small/>
            {ctx.weather==="wind" && (
              <Sld label="Wind speed" min={5} max={40} value={ctx.windMph} onChange={v=>set("windMph",v)} fmt={v=>`${v} mph`}/>
            )}
            <div style={{display:"flex", gap:8, marginBottom:10, flexWrap:"wrap"}}>
              <Btn label={`QB limited: ${ctx.qbLimited?"Yes":"No"}`} sel={ctx.qbLimited}
                onClick={()=>set("qbLimited",!ctx.qbLimited)} accent="#f59e0b"/>
            </div>
            <BtnGrp label="Override mode" options={MDS} value={ctx.gameMode} onChange={v=>set("gameMode",v)} small/>
            <div style={{marginBottom:14}}>
              <div style={{color:T.muted, fontSize:10, fontFamily:T.mono, textTransform:"uppercase", marginBottom:4, letterSpacing:"0.08em"}}>Mismatch note</div>
              <input type="text" value={ctx.mismatch} onChange={e=>set("mismatch",e.target.value)}
                placeholder="e.g. slot CB is undersized..."/>
            </div>

            <button onClick={gen} style={{
              width:"100%", padding:"12px 0", borderRadius:6, border:"none",
              background:T.gold, color:"#0c0f14", fontFamily:T.head,
              fontSize:18, letterSpacing:"0.08em", cursor:"pointer", marginTop:4,
            }}>Generate play call</button>
          </div>
        )}

        {/* ─ PLAY CALL tab ─ */}
        {tab==="play" && (
          !result
            ? <div style={{color:"#374151", fontFamily:T.mono, fontSize:12, textAlign:"center", paddingTop:40}}>
                Go to "Call play" to generate a recommendation.
              </div>
            : <div>
                {result.ctx.gameMode in BANNERS && (
                  <div style={{padding:"7px 12px", borderRadius:5, marginBottom:12,
                    background:`${BANNERS[result.ctx.gameMode].c}12`,
                    border:`1px solid ${BANNERS[result.ctx.gameMode].c}33`}}>
                    <span style={{color:BANNERS[result.ctx.gameMode].c, fontFamily:T.head,
                      fontSize:15, letterSpacing:"0.06em"}}>{BANNERS[result.ctx.gameMode].t.toUpperCase()}</span>
                  </div>
                )}

                {/* Field visual */}
                <div style={{marginBottom:12}}>
                  <div style={{color:T.gold, fontFamily:T.head, fontSize:14, letterSpacing:"0.06em", marginBottom:6}}>Field position</div>
                  <Field c={result.ctx}/>
                  <div style={{display:"flex", justifyContent:"space-between", marginTop:4}}>
                    <span style={{color:T.muted, fontFamily:T.mono, fontSize:9}}>
                      Bucket: {result.bucket.replace(/_/g," ")}
                    </span>
                    <span style={{color:T.muted, fontFamily:T.mono, fontSize:9}}>
                      {result.ctx.coverageShell!=="unknown"
                        ? result.ctx.coverageShell.replace(/_/g," ")
                        : "Coverage unknown"}
                      {result.ctx.blitzLikely?" · Blitz expected":""}
                    </span>
                  </div>
                </div>

                {/* 4th down */}
                <FDCard adv={result.fd}/>

                {/* Play card */}
                {result.play && <PlayCard result={result} driveLog={driveLog}/>}

                {/* Score chart */}
                <ScoreChart scores={result.scores}/>

                {/* Log result */}
                <div style={{marginTop:16, padding:"10px 12px", borderRadius:6,
                  background:T.card, border:`1px solid ${T.bdr}`}}>
                  <div style={{color:T.gold, fontFamily:T.head, fontSize:14, letterSpacing:"0.06em", marginBottom:8}}>Log result</div>
                  <div style={{display:"flex", gap:6}}>
                    <input type="text" value={yards} onChange={e=>setYards(e.target.value)}
                      placeholder="Yards gained (e.g. 7 or -3)" style={{flex:1}}
                      onKeyDown={e=>{if(e.key==="Enter")logResult();}}/>
                    <button onClick={logResult} style={{
                      padding:"5px 14px", borderRadius:4, border:"1px solid #22c55e",
                      background:"rgba(34,197,94,0.1)", color:"#22c55e",
                      fontFamily:T.mono, fontSize:11, cursor:"pointer", whiteSpace:"nowrap",
                    }}>Log</button>
                  </div>
                </div>
              </div>
        )}

        {/* ─ DRIVE LOG tab ─ */}
        {tab==="drive" && (
          <DriveLog log={driveLog} onReset={()=>{setDriveLog([]);setResult(null);}}/>
        )}

      </div>
    </div>
  );
}
