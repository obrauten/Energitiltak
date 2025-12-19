import streamlit as st
import pandas as pd
from datetime import time

# -------------------------------
# Side config
# -------------------------------
st.set_page_config(page_title="Energisparekalkulator", layout="wide")

# ===============================
# Konstanter og hjelpefunksjoner
# ===============================
RHO = 1.2             # kg/m³
CP_J = 1006.0         # J/(kg·K)
HDD = 4800            # graddager
Kh = HDD * 24         # K·h
HOURS_YEAR = 8760

def fmt_int(x: float) -> str:
    """Hele tall med tusenskille som mellomrom og uten desimaler."""
    return f"{int(round(float(x))):,}".replace(",", " ")

def nok_og_co2(kWh: float, pris_kr_per_kWh: float, utslipp_g_per_kWh: float):
    """Returnerer (kr/år, kg CO₂/år) gitt spart kWh og utslippsfaktor i g/kWh."""
    kr_aar = float(kWh) * float(pris_kr_per_kWh)
    kg_co2_aar = float(kWh) * (float(utslipp_g_per_kWh) / 1000.0)  # g → kg
    return kr_aar, kg_co2_aar

def payback_years(invest_kr: float, saving_kr_per_year: float):
    """Enkel tilbakebetalingstid. Returnerer None hvis saving <= 0."""
    if float(saving_kr_per_year) <= 0:
        return None
    return float(invest_kr) / float(saving_kr_per_year)

# ===============================
# Oversikt state + helpers
# ===============================
def init_overview_state():
    if "tiltak_liste" not in st.session_state:
        st.session_state["tiltak_liste"] = []

def add_to_overview(navn: str, kwh: float, kr: float, co2_kg: float, invest: float):
    st.session_state["tiltak_liste"].append({
        "Tiltak": navn,
        "Energisparing (kWh/år)": float(kwh),
        "Kostnadsbesparelse (kr/år)": float(kr),
        "CO₂-reduksjon (kg/år)": float(co2_kg),
        "Investering (kr)": float(invest),
        "Tilbakebetaling (år)": payback_years(float(invest), float(kr))
    })

# ===============================
# Resultat-lagring (løser "hopper vekk")
# ===============================
def set_result(key: str, navn: str, kwh: float, kr: float, co2_kg: float, extra: dict | None = None):
    st.session_state[key] = {
        "navn": navn,
        "kwh": float(kwh),
        "kr": float(kr),
        "co2": float(co2_kg),
        "extra": extra or {}
    }

def get_result(key: str):
    return st.session_state.get(key, None)

def clear_result(key: str):
    if key in st.session_state:
        del st.session_state[key]

def show_result_block(res_key: str):
    """Standard resultatvisning for tiltak."""
    res = get_result(res_key)
    if not res:
        return
    st.success(f"Energi spart: **{fmt_int(res['kwh'])} kWh/år**")
    st.info(f"Kostnadsbesparelse: **{fmt_int(res['kr'])} kr/år**  |  CO₂-reduksjon: **{fmt_int(res['co2'])} kg/år**")

def show_add_block_from_state(res_key: str, invest_key: str, add_key: str):
    """Vis investeringsfelt + payback + knapp for å legge til i oversikt (overlever reruns)."""
    res = get_result(res_key)
    if not res:
        return

    st.divider()
    st.subheader("Lønnsomhet")

    invest = st.number_input(
        "Investeringskostnad (kr)",
        min_value=0.0,
        value=float(st.session_state.get(invest_key, 0.0)),
        step=10_000.0,
        key=invest_key
    )

    pb = payback_years(invest, res["kr"])
    if pb is None:
        st.caption("Tilbakebetaling (enkel): –")
    else:
        st.caption(f"Tilbakebetaling (enkel): **{pb:.1f} år**")

    if st.button("Legg til i oversikt", key=add_key):
        add_to_overview(res["navn"], res["kwh"], res["kr"], res["co2"], invest)
        st.success("Lagt til i oversikt.")

# ===============================
# Driftstid-hjelper
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
# Solceller-hjelper
# ===============================
def areal_til_kwp(areal_m2: float, utnyttelse: float = 0.80, kwp_per_m2: float = 0.20) -> float:
    # kWp per m² tak = areal * utnyttelse * (kWp per m² moduler)
    return max(float(areal_m2) * float(utnyttelse) * float(kwp_per_m2), 0.0)

# ===============================
# Tiltaksberegninger
# ===============================
def etterisolering(A_m2: float, U_old: float, U_new: float) -> float:
    dU = max(float(U_old) - float(U_new), 0.0)
    return dU * float(A_m2) * Kh / 1000.0

def besparelse_varmegjenvinner(qv_m3_h: float, eta_old: float, eta_new: float, driftstimer: float) -> float:
    d_eta = max(float(eta_new) - float(eta_old), 0.0)
    qv_m3_s = float(qv_m3_h) / 3600.0
    H_W_per_K = RHO * CP_J * qv_m3_s
    duty = float(driftstimer) / HOURS_YEAR
    E_kWh = (H_W_per_K / 1000.0) * d_eta * Kh * duty
    return max(E_kWh, 0.0)

def besparelse_sfp(qv_m3_h: float, SFP_old: float, SFP_new: float, driftstimer: float) -> float:
    dSFP = max(float(SFP_old) - float(SFP_new), 0.0)
    qv_m3_s = float(qv_m3_h) / 3600.0
    return max(dSFP * qv_m3_s * float(driftstimer), 0.0)

def besparelse_varmepumpe(Q_netto_kWh_year: float, eta_old: float, COP_new: float, dekningsgrad: float) -> float:
    eta_old = max(float(eta_old), 1e-6)
    COP_new = max(float(COP_new), 1e-6)
    dekningsgrad = max(min(float(dekningsgrad), 1.0), 0.0)
    Q_vp = float(Q_netto_kWh_year) * dekningsgrad
    return max(Q_vp * (1.0/eta_old - 1.0/COP_new), 0.0)

def besparelse_tempreduksjon(Q_space_kWh_year: float, delta_T_C: float) -> float:
    return max(float(Q_space_kWh_year) * 0.05 * max(float(delta_T_C), 0.0), 0.0)

def besparelse_nattsenking(Q_space_kWh_year: float, setback_C: float, timer_per_dogn: float) -> float:
    duty = max(min(float(timer_per_dogn), 24.0), 0.0) / 24.0
    return max(float(Q_space_kWh_year) * 0.05 * max(float(setback_C), 0.0) * duty, 0.0)

# ===============================
# Belysning – hjelpetabell
# ===============================
LUMINAIRE_MAP = [
    {"navn": "T8 2×58 W",              "gammel_W": 2*58,  "led_factor": 0.40},
    {"navn": "T8 4×18 W",              "gammel_W": 4*18,  "led_factor": 0.45},
    {"navn": "T5 2×49 W",              "gammel_W": 2*49,  "led_factor": 0.50},
    {"navn": "Downlight halogen 50 W", "gammel_W": 50,    "led_factor": 0.20},
    {"navn": "Metallhalogen 150 W",    "gammel_W": 150,   "led_factor": 0.40},
    {"navn": "HQL 125 W",              "gammel_W": 125,   "led_factor": 0.45},
    {"navn": "Egendefinert",           "gammel_W": None,  "led_factor": 0.40},
]

def besparelse_belysning(ant_armatur: int, W_gammel: float, W_led: float, timer_per_aar: float) -> float:
    dW = max(float(W_gammel) - float(W_led), 0.0)
    return (dW * int(ant_armatur) * float(timer_per_aar)) / 1000.0

# ===============================
# UI
# ===============================
st.title("Energisparekalkulator")
init_overview_state()

tabs = st.tabs([
    "Etterisolering", "Varmegjenvinner", "SFP (vifter)", "Varmepumpe",
    "Temperaturreduksjon", "Nattsenking", "Belysning (LED)", "Solceller", "Oversikt"
])

# -------------------------------
# Sidebar: Økonomi + driftstid
# -------------------------------
with st.sidebar:
    st.header("Økonomi og CO₂")
    pris = st.number_input("Strøm-/energipris (kr/kWh)", min_value=0.0, max_value=20.0, value=1.25, step=0.05, key="econ_price")
    utslipp_g = st.number_input("Utslippsfaktor (g CO₂/kWh)", min_value=0.0, max_value=2000.0, value=20.0, step=1.0, key="econ_emis")

    st.divider()
    st.header("Driftstid (hjelpekalkulator)")

    t_start = st.time_input("Fra", value=time(7, 0), key="sch_from")
    t_end   = st.time_input("Til", value=time(17, 0), key="sch_to")

    dagvalg = st.selectbox("Dager", ["Alle dager", "Man–fre", "Egendefinert"], index=1, key="sch_days_mode")
    if dagvalg == "Alle dager":
        days_per_week = 7
    elif dagvalg == "Man–fre":
        days_per_week = 5
    else:
        days_per_week = st.slider("Antall dager per uke", 1, 7, 5, key="sch_days_custom")

    weeks_per_year = st.slider("Uker i drift per år", 1, 52, 52, key="sch_weeks")

    h_per_day = daily_hours(t_start, t_end)
    driftstimer_hint = annual_hours_from_schedule(t_start, t_end, days_per_week, weeks_per_year)

    utenfor = max(8760 - driftstimer_hint, 0.0)
    andel_drift = driftstimer_hint / 8760.0

    st.caption(f"**Driftstimer/år:** {int(round(driftstimer_hint))} h")
    st.caption(f"**Utenfor driftstid/år:** {int(round(utenfor))} h")
    st.caption(f"**Andel drift:** {andel_drift*100:.1f} %  |  **Utenfor:** {(1-andel_drift)*100:.1f} %")
    st.caption(f"**I drift per dag:** {h_per_day:.1f} h  |  **Utenfor per dag:** {24 - h_per_day:.1f} h")

# ===============================
# Tabs
# ===============================

# --- Etterisolering ---
with tabs[0]:
    st.subheader("Etterisolering")
    A = st.number_input("Areal (m²)", min_value=0.0, max_value=1_000_000.0, value=1800.0, step=10.0, key="iso_area")
    col1, col2 = st.columns(2)
    with col1:
        U_old = st.number_input("U-verdi før (W/m²K)", min_value=0.05, max_value=6.0, value=0.30, step=0.05, format="%.2f", key="iso_u_old")
    with col2:
        U_new = st.number_input("U-verdi etter (W/m²K)", min_value=0.05, max_value=6.0, value=0.18, step=0.05, format="%.2f", key="iso_u_new")

    if st.button("Beregn", key="btn_iso"):
        kWh = etterisolering(A, U_old, U_new)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_iso", "Etterisolering", kWh, kr, kg)

    show_result_block("res_iso")
    show_add_block_from_state("res_iso", invest_key="inv_iso", add_key="add_iso")

    if get_result("res_iso"):
        if st.button("Nullstill beregning", key="clear_iso"):
            clear_result("res_iso")
            st.rerun()

# --- Varmegjenvinner ---
with tabs[1]:
    st.subheader("Varmegjenvinner")
    qv = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="hrv_qv")
    eta_old = st.slider("Virkningsgrad før (%)", 50, 90, 80, key="hrv_eta_old") / 100
    eta_new = st.slider("Virkningsgrad etter (%)", 60, 95, 88, key="hrv_eta_new") / 100
    driftstimer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="hrv_hours")

    if st.button("Beregn", key="btn_hrv"):
        kWh = besparelse_varmegjenvinner(qv, eta_old, eta_new, driftstimer)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_hrv", "Varmegjenvinner", kWh, kr, kg)

    show_result_block("res_hrv")
    show_add_block_from_state("res_hrv", invest_key="inv_hrv", add_key="add_hrv")

    if get_result("res_hrv"):
        if st.button("Nullstill beregning", key="clear_hrv"):
            clear_result("res_hrv")
            st.rerun()

# --- SFP ---
with tabs[2]:
    st.subheader("SFP (vifter)")
    qv_sfp = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="sfp_qv")
    SFP_old = st.slider("SFP før (kW/(m³/s))", 0.5, 4.0, 1.8, 0.1, key="sfp_old")
    SFP_new = st.slider("SFP etter (kW/(m³/s))", 0.3, 3.0, 1.2, 0.1, key="sfp_new")
    drift = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="sfp_hours")

    if st.button("Beregn", key="btn_sfp"):
        kWh = besparelse_sfp(qv_sfp, SFP_old, SFP_new, drift)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_sfp", "SFP (vifter)", kWh, kr, kg)

    show_result_block("res_sfp")
    show_add_block_from_state("res_sfp", invest_key="inv_sfp", add_key="add_sfp")

    if get_result("res_sfp"):
        if st.button("Nullstill beregning", key="clear_sfp"):
            clear_result("res_sfp")
            st.rerun()

# --- Varmepumpe ---
with tabs[3]:
    st.subheader("Varmepumpe")

    Q_netto = st.number_input("Årlig netto varmebehov (kWh/år)", min_value=1000, max_value=50_000_000,
                              value=600_000, step=10_000, key="vp_Q")
    eta_old = st.slider("Virkningsgrad gammel kjel", 0.5, 1.0, 0.95, 0.01, key="vp_eta")
    COP = st.slider("Varmepumpe COP (årsmiddel/SCOP)", 1.5, 8.0, 3.2, 0.1, key="vp_cop")
    dekn = st.slider("Dekningsgrad varmepumpe (%)", 0, 100, 85, 1, key="vp_dekn") / 100.0

    if st.button("Beregn", key="btn_vp"):
        kWh = besparelse_varmepumpe(Q_netto, eta_old, COP, dekn)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_vp", "Varmepumpe", kWh, kr, kg, extra={"dekn": dekn, "Q_netto": Q_netto})

    res = get_result("res_vp")
    if res:
        show_result_block("res_vp")
        st.caption(f"Varmepumpa dekker ca. {fmt_int(res['extra']['Q_netto'] * res['extra']['dekn'])} kWh/år av varmebehovet.")
        show_add_block_from_state("res_vp", invest_key="inv_vp", add_key="add_vp")

        if st.button("Nullstill beregning", key="clear_vp"):
            clear_result("res_vp")
            st.rerun()

# --- Temperaturreduksjon ---
with tabs[4]:
    st.subheader("Temperaturreduksjon")
    Q_space = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000,
                              value=600_000, step=10_000, key="temp_Q")
    deltaT = st.slider("Reduksjon i settpunkt (°C)", 0.0, 5.0, 1.0, 0.5, key="temp_delta")

    if st.button("Beregn", key="btn_temp"):
        kWh = besparelse_tempreduksjon(Q_space, deltaT)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_temp", "Temperaturreduksjon", kWh, kr, kg)

    show_result_block("res_temp")
    show_add_block_from_state("res_temp", invest_key="inv_temp", add_key="add_temp")

    if get_result("res_temp"):
        if st.button("Nullstill beregning", key="clear_temp"):
            clear_result("res_temp")
            st.rerun()

# --- Nattsenking ---
with tabs[5]:
    st.subheader("Nattsenking")
    Q_space_n = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000,
                                value=600_000, step=10_000, key="night_Q")
    setback = st.slider("Senking (°C) i senketid", 0.0, 6.0, 2.0, 0.5, key="night_setback")
    hours = st.slider("Timer per døgn med senking", 0, 24, 8, 1, key="night_hours")

    if st.button("Beregn", key="btn_night"):
        kWh = besparelse_nattsenking(Q_space_n, setback, hours)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_night", "Nattsenking", kWh, kr, kg)

    show_result_block("res_night")
    show_add_block_from_state("res_night", invest_key="inv_night", add_key="add_night")

    if get_result("res_night"):
        if st.button("Nullstill beregning", key="clear_night"):
            clear_result("res_night")
            st.rerun()

# --- Belysning ---
with tabs[6]:
    st.subheader("Belysning (LED)")

    navn_liste = [d["navn"] for d in LUMINAIRE_MAP]
    valg = st.selectbox("Velg eksisterende armaturtype", navn_liste, index=0, key="lights_type")
    data = next(d for d in LUMINAIRE_MAP if d["navn"] == valg)
    gammel_W = data["gammel_W"]
    led_factor = data["led_factor"]

    if "lights_prev_type" not in st.session_state:
        st.session_state["lights_prev_type"] = valg

    if valg != st.session_state["lights_prev_type"]:
        if gammel_W is None:
            st.session_state["lights_W_old"] = 200
            st.session_state["lights_W_led"] = int(round(200 * led_factor))
        else:
            st.session_state["lights_W_old"] = int(gammel_W)
            st.session_state["lights_W_led"] = int(round(gammel_W * led_factor))
        st.session_state["lights_prev_type"] = valg

    colA, colB = st.columns(2)
    with colA:
        ant = st.number_input("Antall armaturer (stk)", min_value=0, max_value=1_000_000,
                              value=200, step=10, key="lights_count")
        timer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR,
                                value=3000, step=100, key="lights_hours")
    with colB:
        if gammel_W is None:
            W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                    value=st.session_state.get("lights_W_old", 200), step=1, key="lights_W_old")
            default_led = int(round(st.session_state["lights_W_old"] * led_factor))
            W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                    value=st.session_state.get("lights_W_led", default_led), step=1, key="lights_W_led")
        else:
            W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                    value=st.session_state.get("lights_W_old", int(gammel_W)), step=1, key="lights_W_old")
            auto_led = int(round(st.session_state["lights_W_old"] * led_factor))
            W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                    value=st.session_state.get("lights_W_led", auto_led), step=1, key="lights_W_led")

    if st.button("Beregn", key="btn_lights"):
        kWh = besparelse_belysning(ant, st.session_state["lights_W_old"], st.session_state["lights_W_led"], timer)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_led", "Belysning (LED)", kWh, kr, kg)

    show_result_block("res_led")
    show_add_block_from_state("res_led", invest_key="inv_led", add_key="add_led")

    if get_result("res_led"):
        if st.button("Nullstill beregning", key="clear_led"):
            clear_result("res_led")
            st.rerun()

# --- Solceller ---
with tabs[7]:
    st.subheader("Solceller")

    areal = st.number_input("Tilgjengelig takareal (m²)", min_value=10.0, max_value=200_000.0,
                            value=1000.0, step=50.0, key="pv_area")

    utnyttelse = st.slider("Utnyttelsesgrad tak (%)", 50, 100, 80, 5, key="pv_util") / 100.0

    spes_prod = st.selectbox("Forventet årsproduksjon (kWh/kWp)", [700, 750, 800, 850, 900, 950],
                             index=1, key="pv_spec")

    st.markdown("""
**Veiledende nivåer for årsproduksjon (kWh/kWp):**

| kWh/kWp | Typisk situasjon |
|--------:|-----------------|
| 700 | Nord-Norge / ugunstige forhold |
| 750 | Øst/vest-tak, lav vinkel (~10°), evt. noe skygge |
| 800 | Typiske forhold i Midt-Norge |
| 850 | Gode forhold, lite skygge |
| 900 | Sør-Norge eller svært gode solforhold |
| 950 | Optimale forhold (sørvendt, god vinkel 25–35°) |
""")

    # kWp per m² moduler (juster her hvis du vil)
    kwp_per_m2_moduler = 0.20

    kWp = areal_til_kwp(areal, utnyttelse, kwp_per_m2=kwp_per_m2_moduler)
    st.caption(f"Estimert installert effekt: **{kWp:.1f} kWp**")

    if st.button("Beregn", key="btn_pv"):
        kWh = kWp * float(spes_prod)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        set_result("res_pv", "Solceller", kWh, kr, kg, extra={"kWp": kWp, "spes": spes_prod, "areal": areal, "utnytt": utnyttelse})

    res = get_result("res_pv")
    if res:
        show_result_block("res_pv")
        st.caption(
            f"Tommelfinger: {res['extra']['kWp']/res['extra']['areal']:.2f} kWp/m² tilgjengelig tak "
            f"(utnyttelse {res['extra']['utnytt']*100:.0f} %, {kwp_per_m2_moduler:.2f} kWp/m² moduler)"
        )
        show_add_block_from_state("res_pv", invest_key="inv_pv", add_key="add_pv")

        if st.button("Nullstill beregning", key="clear_pv"):
            clear_result("res_pv")
            st.rerun()

# --- Oversikt ---
with tabs[8]:
    st.subheader("Oversikt tiltak")

    if len(st.session_state["tiltak_liste"]) == 0:
        st.info("Ingen tiltak lagt til enda. Gå til et tiltak, beregn, og trykk 'Legg til i oversikt'.")
    else:
        df = pd.DataFrame(st.session_state["tiltak_liste"])

        st.dataframe(df, use_container_width=True)

        sum_kwh = df["Energisparing (kWh/år)"].sum()
        sum_kr = df["Kostnadsbesparelse (kr/år)"].sum()
        sum_co2 = df["CO₂-reduksjon (kg/år)"].sum()
        sum_inv = df["Investering (kr)"].sum()

        st.divider()
        st.subheader("Sum")
        st.write(f"**Sum energisparing:** {fmt_int(sum_kwh)} kWh/år")
        st.write(f"**Sum kostnadsbesparelse:** {fmt_int(sum_kr)} kr/år")
        st.write(f"**Sum CO₂-reduksjon:** {fmt_int(sum_co2)} kg/år")
        st.write(f"**Sum investering:** {fmt_int(sum_inv)} kr")

        if sum_kr > 0:
            st.write(f"**Samlet tilbakebetaling (enkel):** {sum_inv / sum_kr:.1f} år")
        else:
            st.write("**Samlet tilbakebetaling (enkel):** –")

        st.caption("Merk: Summert besparelse er en forenkling. Tiltak kan påvirke hverandre (dobbelttelling).")

    if st.button("Tøm oversikt", key="clear_overview"):
        st.session_state["tiltak_liste"] = []
        st.success("Oversikten er tømt.")
        st.rerun()
