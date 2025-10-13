import streamlit as st

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
    return f"{int(round(x)):,}".replace(",", " ")

def nok_og_co2(kWh: float, pris_kr_per_kWh: float, utslipp_g_per_kWh: float):
    """Returnerer (kr/år, kg CO₂/år) gitt spart kWh og utslippsfaktor i g/kWh."""
    kr_aar = kWh * pris_kr_per_kWh
    kg_co2_aar = kWh * (utslipp_g_per_kWh / 1000.0)  # g → kg
    return kr_aar, kg_co2_aar

# ===============================
# Tiltaksberegninger
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

def besparelse_varmepumpe(Q_netto_kWh_year: float, eta_old: float, COP_new: float) -> float:
    return max(Q_netto_kWh_year * (1.0/eta_old - 1.0/max(COP_new, 0.0001)), 0.0)

def besparelse_tempreduksjon(Q_space_kWh_year: float, delta_T_C: float) -> float:
    return max(Q_space_kWh_year * 0.05 * max(delta_T_C, 0.0), 0.0)

def besparelse_nattsenking(Q_space_kWh_year: float, setback_C: float, timer_per_dogn: float) -> float:
    duty = max(min(timer_per_dogn, 24.0), 0.0) / 24.0
    return max(Q_space_kWh_year * 0.05 * max(setback_C, 0.0) * duty, 0.0)

# ===============================
# Belysning – hjelpetabell
# (bruke REN sum av lamper uten ballastekstra; f.eks. T8 2×58 W = 116 W)
# ===============================
LUMINAIRE_MAP = [
    {"navn": "T8 2×58 W",           "gammel_W": 2*58},   # 116 W
    {"navn": "T8 4×18 W",           "gammel_W": 4*18},   # 72 W
    {"navn": "T5 2×49 W",           "gammel_W": 2*49},   # 98 W
    {"navn": "Downlight halogen 50 W", "gammel_W": 50},
    {"navn": "Metallhalogen 150 W", "gammel_W": 150},
    {"navn": "HQL 125 W",           "gammel_W": 125},
    {"navn": "Egendefinert",        "gammel_W": None},
]

def besparelse_belysning(ant_armatur: int, W_gammel: float, W_led: float, timer_per_aar: float) -> float:
    dW = max(W_gammel - W_led, 0.0)  # W pr armatur
    return (dW * ant_armatur * timer_per_aar) / 1000.0  # kWh/år

# ===============================
# UI
# ===============================
st.title("Energisparekalkulator")

tabs = st.tabs([
    "Etterisolering", "Varmegjenvinner", "SFP (vifter)", "Varmepumpe",
    "Temperaturreduksjon", "Nattsenking", "Belysning (LED)"
])

# Felles økonomi/CO₂ i sidemenyen
with st.sidebar:
    st.header("Økonomi og CO₂")
    pris = st.number_input("Strøm-/energipris (kr/kWh)", min_value=0.0, max_value=20.0, value=1.25, step=0.05, key="econ_price")
    utslipp_g = st.number_input("Utslippsfaktor (g CO₂/kWh)", min_value=0.0, max_value=2000.0, value=20.0, step=1.0, key="econ_emis")

# === Etterisolering ===
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
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Varmegjenvinner ===
with tabs[1]:
    st.subheader("Varmegjenvinner")
    qv = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="hrv_qv")
    eta_old = st.slider("Virkningsgrad før (%)", 50, 90, 80, key="hrv_eta_old") / 100
    eta_new = st.slider("Virkningsgrad etter (%)", 60, 95, 88, key="hrv_eta_new") / 100
    driftstimer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="hrv_hours")
    if st.button("Beregn", key="btn_hrv"):
        kWh = besparelse_varmegjenvinner(qv, eta_old, eta_new, driftstimer)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === SFP (vifter) ===
with tabs[2]:
    st.subheader("SFP (vifter)")
    qv_sfp = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="sfp_qv")
    SFP_old = st.slider("SFP før (kW/(m³/s))", 0.5, 4.0, 1.8, 0.1, key="sfp_old")
    SFP_new = st.slider("SFP etter (kW/(m³/s))", 0.3, 3.0, 1.2, 0.1, key="sfp_new")
    drift = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="sfp_hours")
    if st.button("Beregn", key="btn_sfp"):
        kWh = besparelse_sfp(qv_sfp, SFP_old, SFP_new, drift)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Varmepumpe ===
with tabs[3]:
    st.subheader("Varmepumpe")
    Q_netto = st.number_input("Årlig netto varmebehov (kWh/år)", min_value=1000, max_value=50_000_000, value=600_000, step=10_000, key="vp_Q")
    eta_old = st.slider("Virkningsgrad gammel kjel", 0.5, 1.0, 0.95, 0.01, key="vp_eta")
    COP = st.slider("Varmepumpe COP", 1.5, 8.0, 3.2, 0.1, key="vp_cop")
    if st.button("Beregn", key="btn_vp"):
        kWh = besparelse_varmepumpe(Q_netto, eta_old, COP)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Temperaturreduksjon ===
with tabs[4]:
    st.subheader("Temperaturreduksjon")
    Q_space = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000, value=600_000, step=10_000, key="temp_Q")
    deltaT = st.slider("Reduksjon i settpunkt (°C)", 0.0, 5.0, 1.0, 0.5, key="temp_delta")
    if st.button("Beregn", key="btn_temp"):
        kWh = besparelse_tempreduksjon(Q_space, deltaT)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Nattsenking ===
with tabs[5]:
    st.subheader("Nattsenking")
    Q_space_n = st.number_input("Årlig netto romoppvarming (kWh/år)", min_value=1000, max_value=50_000_000, value=600_000, step=10_000, key="night_Q")
    setback = st.slider("Senking (°C) i senketid", 0.0, 6.0, 2.0, 0.5, key="night_setback")
    hours = st.slider("Timer per døgn med senking", 0, 24, 8, 1, key="night_hours")
    if st.button("Beregn", key="btn_night"):
        kWh = besparelse_nattsenking(Q_space_n, setback, hours)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Belysning (LED) ===
with tabs[6]:
    st.subheader("Belysning (LED)")

    # 1) Velg armaturtype
    navn_liste = [d["navn"] for d in LUMINAIRE_MAP]
    valg = st.selectbox("Velg eksisterende armaturtype", navn_liste, index=0, key="lights_type")
    data = next(d for d in LUMINAIRE_MAP if d["navn"] == valg)

    # 2) Når valg endres, oppdater automatisk W_old og W_led (LED = 60 % av gammel)
    if "lights_prev_type" not in st.session_state:
        st.session_state["lights_prev_type"] = valg

    if valg != st.session_state["lights_prev_type"]:
        if data["gammel_W"] is None:
            st.session_state["lights_W_old"] = 200
            st.session_state["lights_W_led"] = int(round(200 * 0.60))
        else:
            st.session_state["lights_W_old"] = int(data["gammel_W"])
            st.session_state["lights_W_led"] = int(round(st.session_state["lights_W_old"] * 0.60))
        st.session_state["lights_prev_type"] = valg

    # 3) Antall og timer
    colA, colB, _ = st.columns(3)
    with colA:
        ant = st.number_input("Antall armaturer (stk)", min_value=0, max_value=1_000_000, value=200, step=10, key="lights_count")
    with colB:
        timer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="lights_hours")

    # 4) Effektfelt – auto-populeres, men kan overstyres
    if data["gammel_W"] is None:
        # Egendefinert: la bruker skrive begge
        default_old = st.session_state.get("lights_W_old", 200)
        default_led = st.session_state.get("lights_W_led", int(round(default_old * 0.60)))
        col1, col2 = st.columns(2)
        with col1:
            W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                    value=default_old, step=1, key="lights_W_old")
        with col2:
            W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                    value=default_led, step=1, key="lights_W_led")
    else:
        # Forhåndssett fra valg; vis felt som kan overstyres
        preset_old = st.session_state.get("lights_W_old", int(data["gammel_W"]))
        preset_led = st.session_state.get("lights_W_led", int(round(preset_old * 0.60)))
        col1, col2 = st.columns(2)
        with col1:
            W_old = st.number_input("Effekt pr gammel armatur (W)", min_value=1, max_value=2000,
                                    value=preset_old, step=1, key="lights_W_old")
        with col2:
            # Oppdater LED-forslag hvis W_old endres manuelt i denne visningen
            if st.session_state.get("lights_W_old", preset_old) != preset_old:
                preset_led = int(round(st.session_state["lights_W_old"] * 0.60))
                st.session_state["lights_W_led"] = preset_led
            W_led = st.number_input("Effekt pr LED-armatur (W)", min_value=1, max_value=2000,
                                    value=st.session_state.get("lights_W_led", preset_led), step=1, key="lights_W_led")

    # 5) Beregn
    if st.button("Beregn", key="btn_lights"):
        W_old_val = st.session_state["lights_W_old"]
        W_led_val = st.session_state["lights_W_led"]
        kWh = besparelse_belysning(ant, W_old_val, W_led_val, timer)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")
