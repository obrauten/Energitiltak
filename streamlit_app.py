import streamlit as st

# ===============================
# Konstanter og hjelpefunksjoner
# ===============================
RHO = 1.2             # kg/m³
CP_J = 1006.0         # J/(kg·K)  (brukes for W/K)
HDD = 4800            # graddager (kan hentes fra st.secrets senere)
Kh = HDD * 24         # K·h
HOURS_YEAR = 8760

def fmt_int(x: float) -> str:
    """Hele tall med tusenskille som mellomrom og uten desimaler."""
    return f"{int(round(x)):,}".replace(",", " ")

def stepper(label: str, key: str, initial: int, step: int, min_val: int, max_val: int):
    """±-kontroll i tre kolonner. Returnerer gjeldende verdi fra session_state."""
    if key not in st.session_state:
        st.session_state[key] = int(initial)
    c1, c2, c3 = st.columns([4, 1, 1])
    c1.markdown(f"**{label}:** {fmt_int(st.session_state[key])}")
    if c2.button("−", key=key+"-"):
        st.session_state[key] = max(min_val, st.session_state[key] - step)
    if c3.button("+", key=key+"+"):
        st.session_state[key] = min(max_val, st.session_state[key] + step)
    return st.session_state[key]

def nok_og_co2(kWh: float, pris_kr_per_kWh: float, utslipp_g_per_kWh: float):
    """Returnerer (kr/år, kg CO₂/år) gitt spart kWh og utslippsfaktor i g/kWh."""
    kr_aar = kWh * pris_kr_per_kWh
    kg_co2_aar = kWh * (utslipp_g_per_kWh / 1000.0)  # g → kg
    return kr_aar, kg_co2_aar

# ===============================
# Tiltaksberegninger
# ===============================
def etterisolering(A_m2: float, U_old: float, U_new: float) -> float:
    """kWh/år spart ved forbedret U-verdi (vegg/tak/vindu)."""
    dU = max(U_old - U_new, 0.0)
    return dU * A_m2 * Kh / 1000.0

def besparelse_varmegjenvinner(qv_m3_h: float, eta_old: float, eta_new: float, driftstimer: float) -> float:
    """kWh/år spart ved bedre varmegjenvinner (skaleres med faktisk driftstid)."""
    d_eta = max(eta_new - eta_old, 0.0)
    qv_m3_s = qv_m3_h / 3600.0
    H_W_per_K = RHO * CP_J * qv_m3_s
    duty = driftstimer / HOURS_YEAR
    E_kWh = (H_W_per_K / 1000.0) * d_eta * Kh * duty
    return max(E_kWh, 0.0)

def besparelse_sfp(qv_m3_h: float, SFP_old: float, SFP_new: float, driftstimer: float) -> float:
    """kWh/år spart el til vifter ved lavere SFP."""
    dSFP = max(SFP_old - SFP_new, 0.0)               # kW/(m³/s)
    qv_m3_s = qv_m3_h / 3600.0
    return max(dSFP * qv_m3_s * driftstimer, 0.0)

def besparelse_varmepumpe(Q_netto_kWh_year: float, eta_old: float, COP_new: float) -> float:
    """kWh/år spart levert energi ved overgang fra kjel/elkjel til varmepumpe."""
    return max(Q_netto_kWh_year * (1.0/eta_old - 1.0/max(COP_new, 0.0001)), 0.0)

# Enkle driftstiltak for næringsbygg
def besparelse_tempreduksjon(Q_space_kWh_year: float, delta_T_C: float) -> float:
    """Tommelfinger: ~5 % lavere varmebehov per °C reduksjon i settpunkt."""
    return max(Q_space_kWh_year * 0.05 * max(delta_T_C, 0.0), 0.0)

def besparelse_nattsenking(Q_space_kWh_year: float, setback_C: float, timer_per_dogn: float) -> float:
    """~5 %/°C skalert med andel av døgnet i senket modus."""
    duty = max(min(timer_per_dogn, 24.0), 0.0) / 24.0
    return max(Q_space_kWh_year * 0.05 * max(setback_C, 0.0) * duty, 0.0)

# Belysning – hjelpetabell (typisk næringsbygg, gamle → LED)
LUMINAIRE_MAP = [
    {"navn": "T8 2×58 W (armatur m/konv. forkobling)", "gammel_W": 2*58 + 10, "LED_W": 2*30},
    {"navn": "T8 4×18 W (raster)",                     "gammel_W": 4*18 + 8,  "LED_W": 4*9},
    {"navn": "T5 2×49 W (kontor/raster)",              "gammel_W": 2*49 + 6,  "LED_W": 2*28},
    {"navn": "Downlight halogen 50 W",                 "gammel_W": 50,        "LED_W": 8},
    {"navn": "Metallhalogen 150 W (lager/sal)",        "gammel_W": 165,       "LED_W": 95},
    {"navn": "Utearmatur HQL 125 W",                   "gammel_W": 140,       "LED_W": 55},
    {"navn": "Egendefinert",                           "gammel_W": None,      "LED_W": None},
]

def besparelse_belysning(ant_armatur: int, W_gammel: float, W_led: float, timer_per_aar: float) -> float:
    dW = max(W_gammel - W_led, 0.0)  # W pr armatur
    return (dW * ant_armatur * timer_per_aar) / 1000.0  # kWh/år

# ===============================
# UI
# ===============================
st.title("💡 Energitiltak – enkel kalkulator")
st.caption("Forenklet NS3031-logikk (HDD) – grove estimat per tiltak. Tall formateres med mellomrom som tusenskille.")

tabs = st.tabs([
    "Etterisolering", "Varmegjenvinner", "SFP (vifter)", "Varmepumpe",
    "Temperaturreduksjon", "Nattsenking", "Belysning (LED)"
])

# Felles økonomi/CO₂ i sidemenyen
with st.sidebar:
    st.header("Økonomi og CO₂")
    pris = st.number_input("Strøm-/energipris (kr/kWh)", min_value=0.0, max_value=20.0, value=1.25, step=0.05, key="econ_price")
    utslipp_g = st.number_input("Utslippsfaktor (g CO₂/kWh)", min_value=0.0, max_value=2000.0, value=20.0, step=1.0, key="econ_emis")
    st.caption("Utslippsfaktor oppgis i **gram CO₂/kWh**. Resultat vises i **kg CO₂/år**.")

# === Etterisolering ===
with tabs[0]:
    st.subheader("Etterisolering (vegg/tak/vindu)")
    A = stepper("Areal (m²)", key="iso_area", initial=1800, step=10, min_val=0, max_val=1_000_000)
    col1, col2 = st.columns(2)
    with col1:
        U_old = st.number_input("U-verdi før (W/m²K)", min_value=0.05, max_value=6.0, value=0.30, step=0.05, format="%.2f", key="iso_u_old")
    with col2:
        U_new = st.number_input("U-verdi etter (W/m²K)", min_value=0.05, max_value=6.0, value=0.18, step=0.05, format="%.2f", key="iso_u_new")
    if st.button("Beregn besparelse", key="btn_iso"):
        kWh = etterisolering(A, U_old, U_new)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Varmegjenvinner ===
with tabs[1]:
    st.subheader("Varmegjenvinner")
    qv = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000,
                         value=60_000, step=1_000, key="hrv_qv")
    eta_old = st.slider("Virkningsgrad før (%)", 50, 90, 80, key="hrv_eta_old") / 100
    eta_new = st.slider("Virkningsgrad etter (%)", 60, 95, 88, key="hrv_eta_new") / 100
    driftstimer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR,
                                  value=3000, step=100, key="hrv_hours")
    kWh_calc = besparelse_varmegjenvinner(qv, eta_old, eta_new, driftstimer)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="hrv_kwh", initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)
    if st.button("Beregn besparelse", key="btn_hrv"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (teknisk: {fmt_int(kWh_calc)} kWh/år)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === SFP (vifter) ===
with tabs[2]:
    st.subheader("SFP (vifter)")
    qv_sfp = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000,
                              value=60_000, step=1_000, key="sfp_qv")
    SFP_old = st.slider("SFP før (kW/(m³/s))", 0.5, 4.0, 1.8, 0.1, key="sfp_old")
    SFP_new = st.slider("SFP etter (kW/(m³/s))", 0.3, 3.0, 1.2, 0.1, key="sfp_new")
    drift = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR,
                            value=3000, step=100, key="sfp_hours")
    kWh_calc = besparelse_sfp(qv_sfp, SFP_old, SFP_new, drift)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="sfp_kwh", initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)
    if st.button("Beregn besparelse", key="btn_sfp"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (teknisk: {fmt_int(kWh_calc)} kWh/år)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Varmepumpe ===
with tabs[3]:
    st.subheader("Varmepumpe")
    Q_netto = st.number_input("Årlig netto varmebehov (kWh/år)", min_value=1000, max_value=50_000_000,
                              value=600_000, step=10_000, key="vp_Q")
    eta_old = st.slider("Virkningsgrad gammel kjel", 0.5, 1.0, 0.95, 0.01, key="vp_eta")
    COP = st.slider("Varmepumpe COP", 1.5, 8.0, 3.2, 0.1, key="vp_cop")
    kWh_calc = besparelse_varmepumpe(Q_netto, eta_old, COP)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="vp_kwh", initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)
    if st.button("Beregn besparelse", key="btn_vp"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (teknisk: {fmt_int(kWh_calc)} kWh/år)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Temperaturreduksjon ===
with tabs[4]:
    st.subheader("Temperaturreduksjon (næringsbygg)")
    Q_space = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000,
                               value=600_000, step=10_000, key="temp_Q")
    deltaT = st.slider("Reduksjon i settpunkt (°C)", 0.0, 5.0, 1.0, 0.5, key="temp_delta")
    kWh_calc = besparelse_tempreduksjon(Q_space, deltaT)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="temp_kwh", initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)
    if st.button("Beregn besparelse", key="btn_temp"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (regel: ~5 %/°C)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Nattsenking ===
with tabs[5]:
    st.subheader("Nattsenking (næringsbygg)")
    Q_space_n = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000,
                                 value=600_000, step=10_000, key="night_Q")
    setback = st.slider("Senking (°C) i senketid", 0.0, 6.0, 2.0, 0.5, key="night_setback")
    hours = st.slider("Timer per døgn med senking", 0, 24, 8, 1, key="night_hours")
    kWh_calc = besparelse_nattsenking(Q_space_n, setback, hours)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="night_kwh", initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)
    if st.button("Beregn besparelse", key="btn_night"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (regel: ~5 %/°C · {hours}/24)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Belysning (LED) ===
with tabs[6]:
    st.subheader("Belysning (LED) – næringsbygg")
    navn_liste = [d["navn"] for d in LUMINAIRE_MAP]
    valg = st.selectbox("Velg eksisterende armaturtype", navn_liste, index=0, key="lights_type")
    data = next(d for d in LUMINAIRE_MAP if d["navn"] == valg)

    colA, colB, _ = st.columns(3)
    with colA:
        ant = st.number_input("Antall armaturer (stk)", min_value=0, max_value=1_000_000,
                               value=200, step=10, key="lights_count")
    with colB:
        timer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR,
                                value=3000, step=100, key="lights_hours")

    if data["gammel_W"] is None:
        col1, col2 = st.columns(2)
        with col1:
            W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                    value=200, step=5, key="lights_W_old")
        with col2:
            W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                    value=100, step=5, key="lights_W_led")
    else:
        W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                value=int(data["gammel_W"]), step=1, key="lights_W_old")
        W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                value=int(data["LED_W"]), step=1, key="lights_W_led")

    kWh_calc = besparelse_belysning(ant, W_old, W_led, timer)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="lights_kwh",
                  initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)
    if st.button("Beregn besparelse", key="btn_lights"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (teknisk: {fmt_int(kWh_calc)} kWh/år)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

st.divider()
st.caption("Tips: Juster ‘Energi spart (kWh/år)’ med ± i 1000-steg for å kalibrere mot lokale erfaringstall. Areal i etterisolering justeres i trinn på 10 m².")
