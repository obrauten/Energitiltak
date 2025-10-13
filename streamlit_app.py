import streamlit as st

# -------------------------------
# Konstanter og hjelpefunksjoner
# -------------------------------
RHO = 1.2             # kg/m³
CP_J = 1006.0         # J/(kg·K)  (brukes for W/K)
HDD = 4800            # graddager
Kh = HDD * 24         # K·h
HOURS_YEAR = 8760

def fmt_int(x: float) -> str:
    """Hele tall med tusenskille som mellomrom og uten desimaler."""
    return f"{int(round(x)):,}".replace(",", " ")

def stepper(label: str, key: str, initial: int, step: int, min_val: int, max_val: int):
    """Viser en enkel ±-kontroll i tre kolonner. Returnerer gjeldende verdi i session_state."""
    if key not in st.session_state:
        st.session_state[key] = int(initial)
    c1, c2, c3 = st.columns([4, 1, 1])
    c1.markdown(f"**{label}:** {fmt_int(st.session_state[key])}")
    if c2.button("−", key=key+"-"):
        st.session_state[key] = max(min_val, st.session_state[key] - step)
    if c3.button("+", key=key+"+"):
        st.session_state[key] = min(max_val, st.session_state[key] + step)
    return st.session_state[key]

# -------------------------------
# Fysikk / tiltak
# -------------------------------
def etterisolering(A_m2: float, U_old: float, U_new: float) -> float:
    """kWh/år spart ved forbedret U-verdi."""
    dU = max(U_old - U_new, 0.0)
    return dU * A_m2 * Kh / 1000.0

def besparelse_varmegjenvinner(qv_m3_h: float, eta_old: float, eta_new: float, driftstimer: float) -> float:
    """
    kWh/år spart ved bedre varmegjenvinner.
    Skalerer 24/7-HDD med faktisk driftstidsandel.
    """
    d_eta = max(eta_new - eta_old, 0.0)
    qv_m3_s = qv_m3_h / 3600.0
    H_W_per_K = RHO * CP_J * qv_m3_s                 # W/K
    duty = driftstimer / HOURS_YEAR
    E_kWh = (H_W_per_K / 1000.0) * d_eta * Kh * duty # kWh/år
    return max(E_kWh, 0.0)

def besparelse_sfp(qv_m3_h: float, SFP_old: float, SFP_new: float, driftstimer: float) -> float:
    """kWh/år spart el til vifter ved lavere SFP."""
    dSFP = max(SFP_old - SFP_new, 0.0)               # kW/(m³/s)
    qv_m3_s = qv_m3_h / 3600.0
    return dSFP * qv_m3_s * driftstimer              # kWh/år

def besparelse_varmepumpe(Q_netto_kWh_year: float, eta_old: float, COP_new: float) -> float:
    """kWh/år spart levert energi ved overgang til varmepumpe."""
    return max(Q_netto_kWh_year * (1.0/eta_old - 1.0/ max(COP_new, 0.0001)), 0.0)

def nok_og_co2(kWh: float, pris_kr_per_kWh: float, utslipp_g_per_kWh: float):
    """Returnerer (kr/år, kg CO₂/år) gitt spart kWh, pris og utslippsfaktor i g/kWh."""
    kr_aar = kWh * pris_kr_per_kWh
    kg_co2_aar = kWh * (utslipp_g_per_kWh / 1000.0)  # g → kg
    return kr_aar, kg_co2_aar

# -------------------------------
# UI
# -------------------------------
st.title("💡 Energitiltak – enkel kalkulator")
st.caption("Forenklet NS3031-logikk (HDD) – grove estimat per tiltak. Tall formateres med mellomrom som tusenskille.")

tabs = st.tabs(["Etterisolering", "Varmegjenvinner", "SFP (vifter)", "Varmepumpe"])

# --- Felles økonomi/CO2-inndata (brukes på alle faner) ---
with st.sidebar:
    st.header("Økonomi og CO₂")
    pris = st.number_input("Strøm-/energipris (kr/kWh)", min_value=0.0, max_value=20.0, value=1.25, step=0.05)
    utslipp_g = st.number_input("Utslippsfaktor (g CO₂/kWh)", min_value=0.0, max_value=2000.0, value=20.0, step=1.0)
    st.caption("Utslippsfaktor oppgis i **gram CO₂/kWh**. Kalkulatoren regner om til **kg** i resultat.")

# === Etterisolering ===
with tabs[0]:
    st.subheader("Etterisolering (vegg/tak/vindu)")
    # Areal som ±10
    A_init = 1800
    A = stepper("Areal (m²)", key="iso_area", initial=A_init, step=10, min_val=0, max_val=1_000_000)

    col1, col2 = st.columns(2)
    with col1:
        U_old = st.number_input("U-verdi før (W/m²K)", min_value=0.05, max_value=6.0, value=0.30, step=0.05, format="%.2f")
    with col2:
        U_new = st.number_input("U-verdi etter (W/m²K)", min_value=0.05, max_value=6.0, value=0.18, step=0.05, format="%.2f")

    if st.button("Beregn besparelse", key="btn_iso"):
        kWh = etterisolering(A, U_old, U_new)
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år**")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === Varmegjenvinner (uten “HRV”) ===
with tabs[1]:
    st.subheader("Varmegjenvinner")
    qv = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000)
    eta_old = st.slider("Virkningsgrad før (%)", 50, 90, 80) / 100
    eta_new = st.slider("Virkningsgrad etter (%)", 60, 95, 88) / 100
    driftstimer = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100)

    # Beregn teknisk først
    kWh_calc = besparelse_varmegjenvinner(qv, eta_old, eta_new, driftstimer)
    # Deretter gi mulighet for manuell finjustering med ±1000 (initial = beregnet, rundet til nærmeste 1000)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="hrv_kwh", initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)

    if st.button("Beregn besparelse", key="btn_hrv"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (teknisk: {fmt_int(kWh_calc)} kWh/år)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

# === SFP (vifter) ===
with tabs[2]:
    st.subheader("SFP (vifter)")
    qv_sfp = st.number_input("Luftmengde (m³/h)", min_value=1000, max_value=1_000_000, value=60_000, step=1_000, key="qv_sfp")
    SFP_old = st.slider("SFP før (kW/(m³/s))", 0.5, 4.0, 1.8, 0.1)
    SFP_new = st.slider("SFP etter (kW/(m³/s))", 0.3, 3.0, 1.2, 0.1)
    drift = st.number_input("Driftstimer/år", min_value=100, max_value=HOURS_YEAR, value=3000, step=100, key="t_sfp")

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
    Q_netto = st.number_input("Årlig netto varmebehov (kWh/år)", min_value=1000, max_value=50_000_000, value=600_000, step=10_000)
    eta_old = st.slider("Virkningsgrad gammel kjel", 0.5, 1.0, 0.95, 0.01)
    COP = st.slider("Varmepumpe COP", 1.5, 8.0, 3.2, 0.1)

    kWh_calc = besparelse_varmepumpe(Q_netto, eta_old, COP)
    init_kWh = int(round(kWh_calc / 1000.0)) * 1000
    kWh = stepper("Energi spart (kWh/år)", key="vp_kwh", initial=init_kWh, step=1000, min_val=0, max_val=100_000_000)

    if st.button("Beregn besparelse", key="btn_vp"):
        kr, kg = nok_og_co2(kWh, pris, utslipp_g)
        st.success(f"Energi spart: **{fmt_int(kWh)} kWh/år** (teknisk: {fmt_int(kWh_calc)} kWh/år)")
        st.info(f"Kostnadsbesparelse: **{fmt_int(kr)} kr/år**  |  CO₂-reduksjon: **{fmt_int(kg)} kg/år**")

st.divider()
st.caption("Tips: Øk/reduser ‘Energi spart’ i trinn på 1000 kWh/år med ± for å justere mot lokale erfaringstall. Areal i etterisolering justeres i trinn på 10 m².")
