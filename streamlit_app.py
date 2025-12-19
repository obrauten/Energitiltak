import streamlit as st
import pandas as pd
from datetime import time

# ===============================
# Sideoppsett
# ===============================
st.set_page_config(page_title="Energisparekalkulator", layout="wide")

# ===============================
# Konstanter og hjelpefunksjoner
# ===============================
RHO = 1.2
CP_J = 1006.0
HDD = 4800
Kh = HDD * 24
HOURS_YEAR = 8760

def fmt_int(x: float) -> str:
    try:
        return f"{int(round(float(x))):,}".replace(",", " ")
    except Exception:
        return "–"

def fmt_1(x: float) -> str:
    try:
        return f"{float(x):.1f}".replace(".", ",")
    except Exception:
        return "–"

def nok_og_co2(kWh: float, pris_kr_per_kWh: float, utslipp_g_per_kWh: float):
    kr_aar = float(kWh) * float(pris_kr_per_kWh)
    kg_co2_aar = float(kWh) * (float(utslipp_g_per_kWh) / 1000.0)
    return kr_aar, kg_co2_aar

def payback_years(invest_kr: float, saving_kr_per_year: float):
    if saving_kr_per_year <= 0:
        return None
    return float(invest_kr) / float(saving_kr_per_year)

# -------------------------------
# Driftstid-hjelp
# -------------------------------
def daily_hours(t_start: time, t_end: time) -> float:
    start_h = t_start.hour + t_start.minute / 60
    end_h   = t_end.hour + t_end.minute / 60
    h = end_h - start_h
    if h < 0:
        h += 24
    return max(min(h, 24.0), 0.0)

def annual_hours_from_schedule(t_start: time, t_end: time, days_per_week: int, weeks_per_year: float = 52.0) -> float:
    h_day = daily_hours(t_start, t_end)
    return max(min(h_day * days_per_week * float(weeks_per_year), 8760.0), 0.0)

# -------------------------------
# Solceller-hjelp
# -------------------------------
def areal_til_kwp(areal_m2: float, utnyttelse: float = 0.80, kwp_per_m2: float = 0.20) -> float:
    return max(float(areal_m2) * float(utnyttelse) * float(kwp_per_m2), 0.0)

# ===============================
# Tiltaksberegninger (enkle)
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
# Oversikt / pakke
# ===============================
def init_overview_state():
    if "tiltak_liste" not in st.session_state:
        st.session_state["tiltak_liste"] = []

def add_or_replace_in_overview(tiltak_id: str, navn: str, kwh: float, invest: float):
    lst = st.session_state["tiltak_liste"]
    for row in lst:
        if row.get("ID") == tiltak_id:
            row.update({"Tiltak": navn, "kWh": float(kwh), "Invest": float(invest)})
            return
    lst.append({"ID": tiltak_id, "Tiltak": navn, "kWh": float(kwh), "Invest": float(invest)})

def show_result_and_add(tiltak_id: str, navn: str, pris: float, utslipp_g: float, invest_key: str, add_key: str):
    """
    Viser sist-beregnet resultat for tiltak (hvis finnes i session_state),
    og lar deg legge til/oppdatere oversikten uten å måtte trykke 'Beregn' på nytt.
    """
    key_calc = f"calc_{tiltak_id}"
    if key_calc not in st.session_state:
        return

    kwh = float(st.session_state[key_calc]["kWh"])
    default_inv = float(st.session_state[key_calc].get("default_invest", 0.0))

    kr_aar, co2_kg = nok_og_co2(kwh, pris, utslipp_g)

    st.success(f"Energi: **{fmt_int(kwh)} kWh/år**")
    st.info(f"Kostnad: **{fmt_int(kr_aar)} kr/år**  |  CO₂: **{fmt_int(co2_kg)} kg/år**")

    st.divider()
    st.subheader("Lønnsomhet")

    invest = st.number_input(
        "Investeringskostnad (kr)",
        min_value=0.0,
        value=default_inv,
        step=10_000.0,
        key=invest_key
    )

    pb = payback_years(invest, kr_aar)
    st.caption("Tilbakebetaling (enkel): " + ("–" if pb is None else f"**{pb:.1f} år**"))

    if st.button("Legg til / oppdater i oversikt", key=add_key):
        add_or_replace_in_overview(tiltak_id, navn, kwh, invest)
        st.success("Lagt til/oppdatert i oversikt ✅")

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
# Sidebar
# -------------------------------
with st.sidebar:
    st.header("Økonomi og CO₂")
    pris = st.number_input("Strøm-/energipris (kr/kWh)", min_value=0.0, max_value=20.0, value=1.25, step=0.05)
    utslipp_g = st.number_input("Utslippsfaktor (g CO₂/kWh)", min_value=0.0, max_value=2000.0, value=20.0, step=1.0)

    st.divider()
    st.header("Driftstid (hjelpekalkulator)")

    t_start = st.time_input("Fra", value=time(7, 0))
    t_end   = st.time_input("Til", value=time(17, 0))

    dagvalg = st.selectbox("Dager", ["Alle dager", "Man–fre", "Egendefinert"], index=1)

    if dagvalg == "Alle dager":
        days_per_week = 7
    elif dagvalg == "Man–fre":
        days_per_week = 5
    else:
        days_per_week = st.slider("Antall dager per uke", 1, 7, 5)

    weeks_per_year = st.slider("Uker i drift per år", 1, 52, 52)

    h_per_day = daily_hours(t_start, t_end)
    driftstimer_calc = annual_hours_from_schedule(t_start, t_end, days_per_week, weeks_per_year)

    utenfor = max(8760 - driftstimer_calc, 0.0)
    st.caption(f"**Driftstimer/år:** {int(round(driftstimer_calc))} h")
    st.caption(f"**Utenfor driftstid/år:** {int(round(utenfor))} h")
    st.caption(f"**I drift per dag:** {h_per_day:.1f} h  |  **Utenfor per dag:** {24 - h_per_day:.1f} h")

# ===============================
# Tab 0: Etterisolering
# ===============================
with tabs[0]:
    st.subheader("Etterisolering")

    A = st.number_input("Areal (m²)", min_value=0.0, max_value=1_000_000.0, value=1800.0, step=10.0, key="iso_area")
    col1, col2 = st.columns(2)
    with col1:
        U_old = st.number_input("U-verdi før (W/m²K)", min_value=0.05, max_value=6.0, value=0.30, step=0.05, format="%.2f", key="iso_u_old")
    with col2:
        U_new = st.number_input("U-verdi etter (W/m²K)", min_value=0.05, max_value=6.0, value=0.18, step=0.05, format="%.2f", key="iso_u_new")

    kr_per_m2 = st.number_input("Standard invest (kr/m²) – grovt", 0.0, 10000.0, 2800.0, 100.0, key="iso_kr_m2")

    if st.button("Beregn", key="btn_iso"):
        kWh = etterisolering(A, U_old, U_new)
        default_inv = float(kr_per_m2) * float(A)
        st.session_state["calc_iso"] = {"kWh": kWh, "default_invest": default_inv}

    show_result_and_add("iso", "Etterisolering", pris, utslipp_g, "inv_iso", "add_iso")

# ===============================
# Tab 1: Varmegjenvinner
# ===============================
with tabs[1]:
    st.subheader("Varmegjenvinner")

    qv = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="hrv_qv")
    eta_old = st.slider("Virkningsgrad før (%)", 50, 90, 80, key="hrv_eta_old") / 100
    eta_new = st.slider("Virkningsgrad etter (%)", 60, 95, 88, key="hrv_eta_new") / 100
    driftstimer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="hrv_hours")

    kr_per_m3h = st.number_input("Standard invest (kr per m³/h) – grovt", 0.0, 200.0, 35.0, 1.0, key="hrv_kr_m3h")

    if st.button("Beregn", key="btn_hrv"):
        kWh = besparelse_varmegjenvinner(qv, eta_old, eta_new, driftstimer)
        default_inv = float(kr_per_m3h) * float(qv)
        st.session_state["calc_hrv"] = {"kWh": kWh, "default_invest": default_inv}

    show_result_and_add("hrv", "Oppgradering varmegjenvinner", pris, utslipp_g, "inv_hrv", "add_hrv")

# ===============================
# Tab 2: SFP
# ===============================
with tabs[2]:
    st.subheader("SFP (vifter)")

    qv_sfp = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="sfp_qv")
    SFP_old = st.slider("SFP før (kW/(m³/s))", 0.5, 4.0, 1.8, 0.1, key="sfp_old")
    SFP_new = st.slider("SFP etter (kW/(m³/s))", 0.3, 3.0, 1.2, 0.1, key="sfp_new")
    drift = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="sfp_hours")

    default_inv_in = st.number_input("Standard invest (kr per aggregat) – grovt", 0.0, 10_000_000.0, 400_000.0, 10_000.0, key="sfp_inv_default")

    if st.button("Beregn", key="btn_sfp"):
        kWh = besparelse_sfp(qv_sfp, SFP_old, SFP_new, drift)
        st.session_state["calc_sfp"] = {"kWh": kWh, "default_invest": float(default_inv_in)}

    show_result_and_add("sfp", "SFP-tiltak / vifteoppgradering", pris, utslipp_g, "inv_sfp", "add_sfp")

# ===============================
# Tab 3: Varmepumpe (B: kW via fullasttimer)
# ===============================
with tabs[3]:
    st.subheader("Varmepumpe")

    Q_netto = st.number_input("Årlig netto varmebehov (kWh/år)", min_value=1000, max_value=50_000_000, value=600_000, step=10_000, key="vp_Q")
    eta_old = st.slider("Virkningsgrad gammel kjel", 0.5, 1.0, 0.95, 0.01, key="vp_eta")
    COP = st.slider("Varmepumpe COP (årsmiddel/SCOP)", 1.5, 8.0, 3.2, 0.1, key="vp_cop")
    dekn = st.slider("Dekningsgrad varmepumpe (%)", 0, 100, 85, 1, key="vp_dekn") / 100.0

    st.divider()
    st.subheader("Investeringskost (grov)")

    kr_per_kw = st.number_input("Kostnad (kr/kW) luft/vann (inkl. montasje)", min_value=1000.0, max_value=50_000.0, value=16_000.0, step=500.0, key="vp_kr_per_kw")
    fullasttimer = st.slider("Antatt fullasttimer (timer/år)", 1000, 3500, 2000, 100, key="vp_fullast")

    if st.button("Beregn", key="btn_vp"):
        kWh = besparelse_varmepumpe(Q_netto, eta_old, COP, dekn)

        Q_vp = float(Q_netto) * float(dekn)
        vp_kw = Q_vp / max(float(fullasttimer), 1.0)
        default_inv = vp_kw * float(kr_per_kw)

        st.session_state["calc_vp"] = {"kWh": kWh, "default_invest": default_inv}

        st.caption(f"Estimert VP-effekt: **{fmt_1(vp_kw)} kW** (≈ {fmt_int(Q_vp)} kWh/år / {fullasttimer} h)")
        st.caption(f"Estimert investering: **{fmt_int(default_inv)} kr**")

    show_result_and_add("vp", "Varmepumpe (luft–vann)", pris, utslipp_g, "inv_vp", "add_vp")

# ===============================
# Tab 4: Temperaturreduksjon
# ===============================
with tabs[4]:
    st.subheader("Temperaturreduksjon")

    Q_space = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000, value=600_000, step=10_000, key="temp_Q")
    deltaT = st.slider("Reduksjon i settpunkt (°C)", 0.0, 5.0, 1.0, 0.5, key="temp_delta")
    default_inv_in = st.number_input("Standard invest (kr) – grovt", 0.0, 2_000_000.0, 50_000.0, 10_000.0, key="temp_inv_default")

    if st.button("Beregn", key="btn_temp"):
        kWh = besparelse_tempreduksjon(Q_space, deltaT)
        st.session_state["calc_temp"] = {"kWh": kWh, "default_invest": float(default_inv_in)}

    show_result_and_add("temp", "Temperaturreduksjon", pris, utslipp_g, "inv_temp", "add_temp")

# ===============================
# Tab 5: Nattsenking
# ===============================
with tabs[5]:
    st.subheader("Nattsenking")

    Q_space_n = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000, value=600_000, step=10_000, key="night_Q")
    setback = st.slider("Senking (°C) i senketid", 0.0, 6.0, 2.0, 0.5, key="night_setback")
    hours = st.slider("Timer per døgn med senking", 0, 24, 8, 1, key="night_hours")
    default_inv_in = st.number_input("Standard invest (kr) – grovt", 0.0, 2_000_000.0, 75_000.0, 10_000.0, key="night_inv_default")

    if st.button("Beregn", key="btn_night"):
        kWh = besparelse_nattsenking(Q_space_n, setback, hours)
        st.session_state["calc_night"] = {"kWh": kWh, "default_invest": float(default_inv_in)}

    show_result_and_add("night", "Nattsenking", pris, utslipp_g, "inv_night", "add_night")

# ===============================
# Tab 6: LED
# ===============================
with tabs[6]:
    st.subheader("Belysning (LED)")

    navn_liste = [d["navn"] for d in LUMINAIRE_MAP]
    valg = st.selectbox("Velg eksisterende armaturtype", navn_liste, index=0, key="lights_type")
    data = next(d for d in LUMINAIRE_MAP if d["navn"] == valg)
    gammel_W = data["gammel_W"]
    led_factor = data["led_factor"]

    if "lights_prev_type" not in st.session_state:
        st.session_state["lights_prev_type"] = valg
        if gammel_W is None:
            st.session_state["lights_W_old"] = 200
            st.session_state["lights_W_led"] = int(round(200 * led_factor))
        else:
            st.session_state["lights_W_old"] = int(gammel_W)
            st.session_state["lights_W_led"] = int(round(gammel_W * led_factor))

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
        ant = st.number_input("Antall armaturer (stk)", min_value=0, max_value=1_000_000, value=200, step=10, key="lights_count")
    with colB:
        timer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="lights_hours")

    col1, col2 = st.columns(2)
    with col1:
        W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                value=int(st.session_state.get("lights_W_old", 200)), step=1, key="lights_W_old")
    with col2:
        auto_led = int(round(float(W_old) * float(led_factor)))
        W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                value=int(st.session_state.get("lights_W_led", auto_led)), step=1, key="lights_W_led")

    kr_per_arm = st.number_input("Standard invest (kr per armatur) – grovt", 0.0, 50_000.0, 3000.0, 100.0, key="led_kr_arm")

    if st.button("Beregn", key="btn_lights"):
        kWh = besparelse_belysning(ant, st.session_state["lights_W_old"], st.session_state["lights_W_led"], timer)
        default_inv = float(kr_per_arm) * float(ant)
        st.session_state["calc_led"] = {"kWh": kWh, "default_invest": default_inv}

    show_result_and_add("led", "LED-ombygging", pris, utslipp_g, "inv_led", "add_led")

# ===============================
# Tab 7: Solceller
# ===============================
with tabs[7]:
    st.subheader("Solceller")

    colA, colB, colC = st.columns(3)
    with colA:
        areal = st.number_input("Tilgjengelig takareal (m²)", min_value=10.0, max_value=200_000.0, value=1000.0, step=50.0, key="pv_areal")
    with colB:
        utnyttelse = st.slider("Utnyttelsesgrad tak (%)", 50, 100, 80, 5, key="pv_utnytt") / 100.0
    with colC:
        kwp_per_m2 = st.number_input("kWp per m² modulflate", min_value=0.10, max_value=0.30, value=0.20, step=0.01, key="pv_kwp_m2")

    spes_prod = st.selectbox("Forventet årsproduksjon (kWh/kWp)", [700, 750, 800, 850, 900, 950], index=1, key="pv_spes")

    st.markdown("""
**Veiledende nivåer for årsproduksjon (kWh/kWp):**

| kWh/kWp | Typisk situasjon |
|--------:|-----------------|
| 700 | Nord-Norge / ugunstige forhold |
| 750 | Øst/vest-tak, lav vinkel (~10°), evt. noe skygge |
| 800 | Typiske forhold i Midt-Norge |
| 850 | Gode forhold, lite skygge |
| 900 | Sør-Norge eller svært gode solforhold |
| 950 | Optimale forhold (sørvendt, 25–35°, lite skygge) |
""")

    kWp = areal_til_kwp(areal, utnyttelse, kwp_per_m2)
    st.caption(f"Estimert installert effekt: **{kWp:.1f} kWp**")

    kr_per_kwp = st.number_input("Standard invest (kr/kWp) – grovt", 0.0, 50_000.0, 10_500.0, 250.0, key="pv_kr_kwp")

    if st.button("Beregn", key="btn_pv"):
        kWh = float(kWp) * float(spes_prod)
        default_inv = float(kr_per_kwp) * float(kWp)
        st.session_state["calc_pv"] = {"kWh": kWh, "default_invest": default_inv}

    show_result_and_add("pv", "Solceller", pris, utslipp_g, "inv_pv", "add_pv")

# ===============================
# === Oversikt ===
with tabs[8]:
    st.subheader("Oversikt tiltak (pakken)")

    if len(st.session_state["tiltak_liste"]) == 0:
        st.info("Ingen tiltak lagt til enda. Gå til et tiltak, beregn, og trykk 'Legg til / oppdater i oversikt'.")
    else:
        rows = []
        for r in st.session_state["tiltak_liste"]:
            kWh = float(r["kWh"])
            inv = float(r["Invest"])
            kr_aar, co2_kg = nok_og_co2(kWh, pris, utslipp_g)
            pb = payback_years(inv, kr_aar)
            rows.append({
                "Tiltak": r["Tiltak"],
                "Energisparing (kWh/år)": kWh,
                "Kostnadsbesparelse (kr/år)": kr_aar,
                "CO₂-reduksjon (kg/år)": co2_kg,
                "Investering (kr)": inv,
                "Tilbakebetaling (år)": (None if pb is None else pb)
            })

        df = pd.DataFrame(rows)

        # --- Formatering: heltall + tusenskille (mellomrom) ---
        def int_space(x):
            return f"{int(round(x)):,}".replace(",", " ")

        def years_1(x):
            if pd.isna(x):
                return "–"
            return f"{x:.1f}".replace(".", ",")

        styler = df.style.format({
            "Energisparing (kWh/år)": int_space,
            "Kostnadsbesparelse (kr/år)": int_space,
            "CO₂-reduksjon (kg/år)": int_space,
            "Investering (kr)": int_space,
            "Tilbakebetaling (år)": years_1
        })

        st.dataframe(styler, use_container_width=True)

        # Summer (samme som før)
        sum_kwh = df["Energisparing (kWh/år)"].sum()
        sum_kr = df["Kostnadsbesparelse (kr/år)"].sum()
        sum_co2 = df["CO₂-reduksjon (kg/år)"].sum()
        sum_inv = df["Investering (kr)"].sum()

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sum energisparing", f"{int(round(sum_kwh)):,}".replace(",", " ") + " kWh/år")
        c2.metric("Sum besparelse", f"{int(round(sum_kr)):,}".replace(",", " ") + " kr/år")
        c3.metric("Sum CO₂-reduksjon", f"{int(round(sum_co2)):,}".replace(",", " ") + " kg/år")
        c4.metric("Sum investering", f"{int(round(sum_inv)):,}".replace(",", " ") + " kr")

        st.caption(
            "**Samlet tilbakebetaling (enkel):** "
            + ("–" if sum_kr <= 0 else f"**{(sum_inv / sum_kr):.1f} år**".replace(".", ","))
        )

    if st.button("Tøm oversikt", key="clear_overview"):
        st.session_state["tiltak_liste"] = []
        st.success("Oversikten er tømt.")
