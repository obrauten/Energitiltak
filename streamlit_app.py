import streamlit as st
import pandas as pd
from datetime import time

# ===============================
# Sideoppsett
# ===============================
st.set_page_config(page_title="Energisparekalkulator", layout="wide")
st.title("Energisparekalkulator")

# ===============================
# Konstanter og hjelpefunksjoner
# ===============================
RHO = 1.2             # kg/m³
CP_J = 1006.0         # J/(kg·K)
HDD = 4800            # graddager (grov standard)
Kh = HDD * 24         # K·h
HOURS_YEAR = 8760

def fmt_int(x: float) -> str:
    """Hele tall med tusenskille som mellomrom og uten desimaler."""
    return f"{int(round(x)):,}".replace(",", " ")

def nok_og_co2(kWh: float, pris_kr_per_kWh: float, utslipp_g_per_kWh: float):
    """Returnerer (kr/år, kg CO₂/år) gitt kWh og utslippsfaktor i g/kWh."""
    kr_aar = kWh * pris_kr_per_kWh
    kg_co2_aar = kWh * (utslipp_g_per_kWh / 1000.0)  # g → kg
    return kr_aar, kg_co2_aar

def payback_years(invest_kr: float, saving_kr_per_year: float):
    if saving_kr_per_year <= 0:
        return None
    return invest_kr / saving_kr_per_year

# ===============================
# Driftstid (hjelpekalkulator)
# ===============================
def daily_hours(t_start: time, t_end: time) -> float:
    """Timer per dag for et tidsrom. Håndterer også over midnatt."""
    start_h = t_start.hour + t_start.minute / 60
    end_h   = t_end.hour + t_end.minute / 60
    h = end_h - start_h
    if h < 0:
        h += 24
    return max(min(h, 24.0), 0.0)

def annual_hours_from_schedule(t_start: time, t_end: time, days_per_week: int, weeks_per_year: float = 52.0) -> float:
    h_day = daily_hours(t_start, t_end)
    return max(min(h_day * days_per_week * weeks_per_year, 8760.0), 0.0)

# ===============================
# Solceller – areal → kWp
# ===============================
def areal_til_kwp(areal_m2: float, utnyttelse: float = 0.80, kwp_per_m2: float = 0.20) -> float:
    # kwp_per_m2 ~ 0.18–0.22 (moderne panel + tetthet)
    return max(float(areal_m2) * float(utnyttelse) * float(kwp_per_m2), 0.0)

# ===============================
# Tiltaksberegninger (kWh/år)
# ===============================
def etterisolering(A_m2: float, U_old: float, U_new: float) -> float:
    dU = max(U_old - U_new, 0.0)
    return dU * A_m2 * Kh / 1000.0

def besparelse_varmegjenvinner(qv_m3_h: float, eta_old: float, eta_new: float, driftstimer: float) -> float:
    d_eta = max(eta_new - eta_old, 0.0)
    qv_m3_s = qv_m3_h / 3600.0
    H_W_per_K = RHO * CP_J * qv_m3_s
    duty = driftstimer / HOURS_YEAR
    E_kWh = (H_W_per_K / 1000.0) * d_eta * Kh * duty
    return max(E_kWh, 0.0)

def besparelse_sfp(qv_m3_h: float, SFP_old: float, SFP_new: float, driftstimer: float) -> float:
    dSFP = max(SFP_old - SFP_new, 0.0)
    qv_m3_s = qv_m3_h / 3600.0
    return max(dSFP * qv_m3_s * driftstimer, 0.0)

def besparelse_varmepumpe(Q_netto_kWh_year: float, eta_old: float, COP_new: float, dekningsgrad: float) -> float:
    """
    Q_netto_kWh_year: årlig nyttig varmebehov (kWh/år)
    eta_old: virkningsgrad gammel kjel/varmeløsning (0.5–1.0)
    COP_new: varmepumpens årsmiddel (SCOP)
    dekningsgrad: andel av varmebehovet som VP dekker (0–1)
    """
    eta_old = max(float(eta_old), 1e-6)
    COP_new = max(float(COP_new), 1e-6)
    dekningsgrad = max(min(float(dekningsgrad), 1.0), 0.0)

    Q_vp = float(Q_netto_kWh_year) * dekningsgrad
    return max(Q_vp * (1.0/eta_old - 1.0/COP_new), 0.0)

def besparelse_tempreduksjon(Q_space_kWh_year: float, delta_T_C: float) -> float:
    return max(Q_space_kWh_year * 0.05 * max(delta_T_C, 0.0), 0.0)

def besparelse_nattsenking(Q_space_kWh_year: float, setback_C: float, timer_per_dogn: float) -> float:
    duty = max(min(timer_per_dogn, 24.0), 0.0) / 24.0
    return max(Q_space_kWh_year * 0.05 * max(setback_C, 0.0) * duty, 0.0)

# ===============================
# Belysning – tabell
# ===============================
LUMINAIRE_MAP = [
    {"navn": "T8 2×58 W",             "gammel_W": 2*58,  "led_factor": 0.40},
    {"navn": "T8 4×18 W",             "gammel_W": 4*18,  "led_factor": 0.45},
    {"navn": "T5 2×49 W",             "gammel_W": 2*49,  "led_factor": 0.50},
    {"navn": "Downlight halogen 50 W","gammel_W": 50,    "led_factor": 0.20},
    {"navn": "Metallhalogen 150 W",   "gammel_W": 150,   "led_factor": 0.40},
    {"navn": "HQL 125 W",             "gammel_W": 125,   "led_factor": 0.45},
    {"navn": "Egendefinert",          "gammel_W": None,  "led_factor": 0.40},
]

def besparelse_belysning(ant_armatur: int, W_gammel: float, W_led: float, timer_per_aar: float) -> float:
    dW = max(W_gammel - W_led, 0.0)
    return (dW * ant_armatur * timer_per_aar) / 1000.0

# ===============================
# Oversikt-state
# ===============================
def init_overview_state():
    if "tiltak_liste" not in st.session_state:
        st.session_state["tiltak_liste"] = []

def add_to_overview(navn: str, kwh: float, invest: float):
    st.session_state["tiltak_liste"].append({
        "Tiltak": navn,
        "Energisparing (kWh/år)": float(kwh),
        "Investering (kr)": float(invest),
    })

def store_result(key: str, navn: str, kwh: float):
    st.session_state[key] = {"navn": navn, "kwh": float(kwh)}

def get_result(key: str):
    return st.session_state.get(key, None)

def show_result_and_profitability(result_key: str, pris: float, utslipp_g: float,
                                  invest_default: float, invest_key: str, add_key: str,
                                  invest_hint: str = ""):
    """
    Viser siste beregnede resultat (lagret i session_state) + lønnsomhet som ikke "hopper vekk".
    """
    res = get_result(result_key)
    if not res:
        st.info("Trykk **Beregn** for å få resultat og lønnsomhet.")
        return

    kWh = res["kwh"]
    kr, kg = nok_og_co2(kWh, pris, utslipp_g)

    st.success(f"Energi: **{fmt_int(kWh)} kWh/år**")
    st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂: **{fmt_int(kg)} kg/år**")

    st.divider()
    st.subheader("Lønnsomhet (enkel)")

    col1, col2 = st.columns([1, 1])
    with col1:
        use_default = st.checkbox("Bruk foreslått investeringskostnad", value=True, key=f"{invest_key}_use_default")
    with col2:
        st.caption(invest_hint)

    if use_default:
        invest = float(invest_default)
        st.caption(f"Foreslått investering: **{fmt_int(invest)} kr**")
    else:
        invest = st.number_input("Investeringskostnad (kr)", min_value=0.0, value=float(invest_default),
                                 step=10_000.0, key=invest_key)

    pb = payback_years(invest, kr)
    if pb is None:
        st.caption("Tilbakebetaling: –")
    else:
        st.caption(f"Tilbakebetaling (enkel): **{pb:.1f} år**")

    if st.button("Legg til i oversikt", key=add_key):
        add_to_overview(res["navn"], kWh, invest)
        st.success("Lagt til i oversikt.")

init_overview_state()

# ===============================
# Sidebar
# ===============================
with st.sidebar:
    st.header("Økonomi og CO₂")
    pris = st.number_input("Strøm-/energipris (kr/kWh)", min_value=0.0, max_value=20.0, value=1.25, step=0.05, key="econ_price")
    utslipp_g = st.number_input("Utslippsfaktor (g CO₂/kWh)", min_value=0.0, max_value=2000.0, value=20.0, step=1.0, key="econ_emis")

    st.divider()
    st.header("Driftstid (hjelpekalkulator)")
    t_start = st.time_input("Fra", value=time(7, 0), key="drift_from")
    t_end   = st.time_input("Til", value=time(17, 0), key="drift_to")

    dagvalg = st.selectbox("Dager", ["Alle dager", "Man–fre", "Egendefinert"], index=1, key="drift_days_mode")
    if dagvalg == "Alle dager":
        days_per_week = 7
    elif dagvalg == "Man–fre":
        days_per_week = 5
    else:
        days_per_week = st.slider("Antall dager per uke", 1, 7, 5, key="drift_days_custom")

    weeks_per_year = st.slider("Uker i drift per år", 1, 52, 52, key="drift_weeks")

    h_per_day = daily_hours(t_start, t_end)
    driftstimer_calc = annual_hours_from_schedule(t_start, t_end, days_per_week, weeks_per_year)
    utenfor = max(8760 - driftstimer_calc, 0.0)

    st.caption(f"**Driftstimer/år:** {int(round(driftstimer_calc))} h")
    st.caption(f"**Utenfor driftstid/år:** {int(round(utenfor))} h")
    st.caption(f"**I drift per dag:** {h_per_day:.1f} h  |  **Utenfor per dag:** {24 - h_per_day:.1f} h")

# ===============================
# Tabs
# ===============================
tabs = st.tabs([
    "Etterisolering",
    "Varmegjenvinner",
    "SFP (vifter)",
    "Varmepumpe",
    "Temperaturreduksjon",
    "Nattsenking",
    "Belysning (LED)",
    "Solceller",
    "Oversikt"
])

# -------------------------------
# 0 Etterisolering
# -------------------------------
with tabs[0]:
    st.subheader("Etterisolering")
    A = st.number_input("Areal (m²)", min_value=0.0, max_value=1_000_000.0, value=1800.0, step=10.0, key="iso_area")
    c1, c2 = st.columns(2)
    with c1:
        U_old = st.number_input("U-verdi før (W/m²K)", min_value=0.05, max_value=6.0, value=0.30, step=0.05, format="%.2f", key="iso_u_old")
    with c2:
        U_new = st.number_input("U-verdi etter (W/m²K)", min_value=0.05, max_value=6.0, value=0.18, step=0.05, format="%.2f", key="iso_u_new")

    # Typisk invest: kr/m²
    unit_cost = st.number_input("Typisk invest (kr/m²) – forslag", min_value=0.0, value=4500.0, step=250.0, key="iso_unit_cost")
    invest_default = A * unit_cost
    invest_hint = "Typisk: tak 2 000–4 000 kr/m², vegg 4 000–6 000 kr/m²"

    if st.button("Beregn", key="btn_iso"):
        kWh = etterisolering(A, U_old, U_new)
        store_result("res_iso", "Etterisolering", kWh)

    show_result_and_profitability(
        result_key="res_iso",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_iso",
        add_key="add_iso",
        invest_hint=invest_hint
    )

# -------------------------------
# 1 Varmegjenvinner
# -------------------------------
with tabs[1]:
    st.subheader("Varmegjenvinner")
    qv = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="hrv_qv")
    eta_old = st.slider("Virkningsgrad før (%)", 50, 90, 80, key="hrv_eta_old") / 100
    eta_new = st.slider("Virkningsgrad etter (%)", 60, 95, 88, key="hrv_eta_new") / 100
    driftstimer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="hrv_hours")

    # Typisk invest: qv * kr/(m3/h)
    unit = st.number_input("Typisk invest (kr per m³/h) – forslag", min_value=0.0, value=25.0, step=1.0, key="hrv_unit")
    invest_default = qv * unit
    invest_hint = "Typisk: 20–40 kr per m³/h (avhenger av plass/kanaler)"

    if st.button("Beregn", key="btn_hrv"):
        kWh = besparelse_varmegjenvinner(qv, eta_old, eta_new, driftstimer)
        store_result("res_hrv", "Varmegjenvinner", kWh)

    show_result_and_profitability(
        result_key="res_hrv",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_hrv",
        add_key="add_hrv",
        invest_hint=invest_hint
    )

# -------------------------------
# 2 SFP
# -------------------------------
with tabs[2]:
    st.subheader("SFP (vifter)")
    qv_sfp = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="sfp_qv")
    SFP_old = st.slider("SFP før (kW/(m³/s))", 0.5, 4.0, 1.8, 0.1, key="sfp_old")
    SFP_new = st.slider("SFP etter (kW/(m³/s))", 0.3, 3.0, 1.2, 0.1, key="sfp_new")
    drift = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="sfp_hours")

    invest_default = st.number_input("Typisk invest (kr) – forslag", min_value=0.0, value=400000.0, step=50_000.0, key="sfp_invest_default")
    invest_hint = "Typisk: 300k–800k per aggregat (EC/frekvens/styring)"

    if st.button("Beregn", key="btn_sfp"):
        kWh = besparelse_sfp(qv_sfp, SFP_old, SFP_new, drift)
        store_result("res_sfp", "SFP-tiltak", kWh)

    show_result_and_profitability(
        result_key="res_sfp",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_sfp",
        add_key="add_sfp",
        invest_hint=invest_hint
    )

# -------------------------------
# 3 Varmepumpe
# -------------------------------
with tabs[3]:
    st.subheader("Varmepumpe")

    Q_netto = st.number_input("Årlig netto varmebehov (kWh/år)", min_value=1000, max_value=50_000_000,
                              value=600_000, step=10_000, key="vp_Q")
    eta_old = st.slider("Virkningsgrad gammel kjel", 0.5, 1.0, 0.95, 0.01, key="vp_eta")
    COP = st.slider("Varmepumpe COP (årsmiddel/SCOP)", 1.5, 8.0, 3.2, 0.1, key="vp_cop")
    dekn = st.slider("Dekningsgrad varmepumpe (%)", 0, 100, 85, 1, key="vp_dekn") / 100.0

    # Typisk invest: (dekket varme) * kr/kWh
    kr_per_kwh = st.number_input("Typisk invest (kr per kWh levert VP-varme) – forslag",
                                 min_value=0.0, value=1.2, step=0.1, key="vp_kr_per_kwh")
    dekket_varme = Q_netto * dekn
    invest_default = dekket_varme * kr_per_kwh
    invest_hint = "Typisk: L/V 0,8–1,2 kr/kWh, V/V 1,2–1,8 kr/kWh (grov tidligfase)"

    if st.button("Beregn", key="btn_vp"):
        kWh = besparelse_varmepumpe(Q_netto, eta_old, COP, dekn)
        store_result("res_vp", "Varmepumpe", kWh)
        st.caption(f"Varmepumpa dekker ca. {fmt_int(dekket_varme)} kWh/år av varmebehovet.")

    show_result_and_profitability(
        result_key="res_vp",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_vp",
        add_key="add_vp",
        invest_hint=invest_hint
    )

# -------------------------------
# 4 Temperaturreduksjon
# -------------------------------
with tabs[4]:
    st.subheader("Temperaturreduksjon")
    Q_space = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000,
                              value=600_000, step=10_000, key="temp_Q")
    deltaT = st.slider("Reduksjon i settpunkt (°C)", 0.0, 5.0, 1.0, 0.5, key="temp_delta")

    invest_default = st.number_input("Typisk invest (kr) – forslag", min_value=0.0, value=25000.0, step=5000.0, key="temp_invest_default")
    invest_hint = "Typisk: 0–50k (SD/drift/enkle justeringer)"

    if st.button("Beregn", key="btn_temp"):
        kWh = besparelse_tempreduksjon(Q_space, deltaT)
        store_result("res_temp", "Temperaturreduksjon", kWh)

    show_result_and_profitability(
        result_key="res_temp",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_temp",
        add_key="add_temp",
        invest_hint=invest_hint
    )

# -------------------------------
# 5 Nattsenking
# -------------------------------
with tabs[5]:
    st.subheader("Nattsenking")
    Q_space_n = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000,
                                value=600_000, step=10_000, key="night_Q")
    setback = st.slider("Senking (°C) i senketid", 0.0, 6.0, 2.0, 0.5, key="night_setback")
    hours = st.slider("Timer per døgn med senking", 0, 24, 8, 1, key="night_hours")

    invest_default = st.number_input("Typisk invest (kr) – forslag", min_value=0.0, value=25000.0, step=5000.0, key="night_invest_default")
    invest_hint = "Typisk: 0–50k (SD/drift/enkle justeringer)"

    if st.button("Beregn", key="btn_night"):
        kWh = besparelse_nattsenking(Q_space_n, setback, hours)
        store_result("res_night", "Nattsenking", kWh)

    show_result_and_profitability(
        result_key="res_night",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_night",
        add_key="add_night",
        invest_hint=invest_hint
    )

# -------------------------------
# 6 Belysning
# -------------------------------
with tabs[6]:
    st.subheader("Belysning (LED)")
    navn_liste = [d["navn"] for d in LUMINAIRE_MAP]
    valg = st.selectbox("Velg eksisterende armaturtype", navn_liste, index=0, key="lights_type")
    data = next(d for d in LUMINAIRE_MAP if d["navn"] == valg)
    gammel_W = data["gammel_W"]
    led_factor = data["led_factor"]

    # init ved førstegang
    if "lights_prev_type" not in st.session_state:
        st.session_state["lights_prev_type"] = valg
        if gammel_W is None:
            st.session_state["lights_W_old"] = 200
            st.session_state["lights_W_led"] = int(round(200 * led_factor))
        else:
            st.session_state["lights_W_old"] = int(gammel_W)
            st.session_state["lights_W_led"] = int(round(gammel_W * led_factor))

    # hvis type endres
    if valg != st.session_state["lights_prev_type"]:
        if gammel_W is None:
            st.session_state["lights_W_old"] = 200
            st.session_state["lights_W_led"] = int(round(200 * led_factor))
        else:
            st.session_state["lights_W_old"] = int(gammel_W)
            st.session_state["lights_W_led"] = int(round(gammel_W * led_factor))
        st.session_state["lights_prev_type"] = valg

    colA, colB, colC = st.columns(3)
    with colA:
        ant = st.number_input("Antall armaturer (stk)", min_value=0, max_value=1_000_000, value=200, step=10, key="lights_count")
    with colB:
        timer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="lights_hours")
    with colC:
        kr_per_arm = st.number_input("Typisk invest (kr/armatur) – forslag", min_value=0.0, value=1200.0, step=100.0, key="lights_kr_per_arm")

    c1, c2 = st.columns(2)
    with c1:
        W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                value=int(st.session_state.get("lights_W_old", 200)), step=1, key="lights_W_old")
    with c2:
        auto_led = int(round(float(W_old) * led_factor))
        W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                value=int(st.session_state.get("lights_W_led", auto_led)), step=1, key="lights_W_led")

    invest_default = ant * kr_per_arm
    invest_hint = "Typisk: 800–2 000 kr/armatur (inkl. montasje)"

    if st.button("Beregn", key="btn_lights"):
        kWh = besparelse_belysning(ant, W_old, W_led, timer)
        store_result("res_lights", "LED-belysning", kWh)

    show_result_and_profitability(
        result_key="res_lights",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_lights",
        add_key="add_lights",
        invest_hint=invest_hint
    )

# -------------------------------
# 7 Solceller
# -------------------------------
with tabs[7]:
    st.subheader("Solceller")

    c1, c2, c3 = st.columns(3)
    with c1:
        areal = st.number_input("Tilgjengelig takareal (m²)", min_value=10.0, max_value=200_000.0,
                                value=1000.0, step=50.0, key="pv_area")
    with c2:
        utnyttelse = st.slider("Utnyttelsesgrad tak (%)", 50, 100, 80, 5, key="pv_util") / 100.0
    with c3:
        kwp_per_m2 = st.number_input("kWp per m² modulert areal – forslag", min_value=0.10, max_value=0.30,
                                     value=0.20, step=0.01, key="pv_kwp_m2")

    st.caption("Tips: 0,18–0,22 kWp/m² er vanlig tommelfinger (moderne panel + tetthet).")

    spes_prod = st.selectbox("Forventet årsproduksjon (kWh/kWp)", [700, 750, 800, 850, 900, 950], index=1, key="pv_spec")

    st.markdown("""
**Veiledende nivåer for årsproduksjon (kWh/kWp):**
- **700–750**: øst/vest, lav vinkel, mer skygge eller nordligere lokasjon
- **800**: typisk Midt-Norge / “normalt tak”
- **850**: gode forhold, lite skygge
- **900–950**: svært gode forhold (sørvendt, god vinkel, lite skygge)
""")

    kWp = areal_til_kwp(areal, utnyttelse, kwp_per_m2)
    st.caption(f"Estimert installert effekt: **{kWp:.1f} kWp**")

    kr_per_kwp = st.number_input("Typisk invest (kr/kWp) – forslag", min_value=0.0, value=11500.0, step=500.0, key="pv_kr_per_kwp")
    invest_default = kWp * kr_per_kwp
    invest_hint = "Typisk: 10 000–14 000 kr/kWp (næring), ofte lavere ved store tak"

    if st.button("Beregn", key="btn_pv"):
        kWh = kWp * float(spes_prod)
        store_result("res_pv", "Solceller", kWh)

    show_result_and_profitability(
        result_key="res_pv",
        pris=float(pris), utslipp_g=float(utslipp_g),
        invest_default=float(invest_default),
        invest_key="inv_pv",
        add_key="add_pv",
        invest_hint=invest_hint
    )

# -------------------------------
# 8 Oversikt + stresstest
# -------------------------------
with tabs[8]:
    st.subheader("Oversikt tiltak")

    if len(st.session_state["tiltak_liste"]) == 0:
        st.info("Ingen tiltak lagt til enda. Gå til et tiltak, trykk **Beregn**, og velg **Legg til i oversikt**.")
    else:
        df0 = pd.DataFrame(st.session_state["tiltak_liste"])

        st.caption(f"Sidebar nå: **{float(pris):.2f} kr/kWh** og **{float(utslipp_g):.0f} g CO₂/kWh**")

        st.divider()
        st.subheader("Stresstest (pakke-lønnsomhet)")

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            testpris = st.number_input("Testpris (kr/kWh)", min_value=0.0, max_value=20.0, value=float(pris),
                                       step=0.05, key="testpris")
        with c2:
            testutslipp = st.number_input("Test utslipp (g CO₂/kWh)", min_value=0.0, max_value=2000.0,
                                          value=float(utslipp_g), step=1.0, key="testutslipp")
        with c3:
            st.caption("Endre testpris for å se hvor robust tiltakspakken er ved lav/høy energipris.")

        df = df0.copy()
        df["Kostnadsbesparelse (kr/år)"] = df["Energisparing (kWh/år)"] * float(testpris)
        df["CO₂-reduksjon (kg/år)"] = df["Energisparing (kWh/år)"] * (float(testutslipp) / 1000.0)
        df["Tilbakebetaling (år)"] = df.apply(lambda r: payback_years(r["Investering (kr)"], r["Kostnadsbesparelse (kr/år)"]), axis=1)

        st.dataframe(df, use_container_width=True)

        sum_kwh = df["Energisparing (kWh/år)"].sum()
        sum_kr  = df["Kostnadsbesparelse (kr/år)"].sum()
        sum_co2 = df["CO₂-reduksjon (kg/år)"].sum()
        sum_inv = df["Investering (kr)"].sum()

        st.divider()
        st.subheader("Sum (basert på testpris)")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Sum energisparing", f"{fmt_int(sum_kwh)} kWh/år")
        m2.metric("Sum besparelse", f"{fmt_int(sum_kr)} kr/år")
        m3.metric("Sum CO₂", f"{fmt_int(sum_co2)} kg/år")
        m4.metric("Sum investering", f"{fmt_int(sum_inv)} kr")

        if sum_kr > 0:
            st.write(f"**Samlet tilbakebetaling (enkel):** {sum_inv / sum_kr:.1f} år")
        else:
            st.write("**Samlet tilbakebetaling (enkel):** –")

        st.caption("Merk: Summert besparelse er en forenkling. Tiltak kan påvirke hverandre (dobbelttelling).")

        st.divider()
        st.subheader("Hurtig-sensitivitet")

        pris_liste = st.multiselect(
            "Vis samlet payback for flere energipriser (kr/kWh)",
            options=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0],
            default=[0.75, 1.25, 2.0],
            key="sens_prices"
        )

        if pris_liste:
            rows = []
            for p in sorted(pris_liste):
                sum_kr_p = float(sum_kwh) * float(p)
                pb_p = (float(sum_inv) / sum_kr_p) if sum_kr_p > 0 else None
                rows.append({
                    "Energipris (kr/kWh)": p,
                    "Sum besparelse (kr/år)": sum_kr_p,
                    "Samlet payback (år)": pb_p
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

    if st.button("Tøm oversikt", key="clear_overview"):
        st.session_state["tiltak_liste"] = []
        st.success("Oversikten er tømt.")
        st.rerun()
