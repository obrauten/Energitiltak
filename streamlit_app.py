import streamlit as st

# --- STANDARDVERDIER ---
RHO = 1.2           # kg/m³
CP = 0.00033        # kWh/(kg·K)
HDD = 4800          # graddager
Kh = HDD * 24       # K·h

# --- FUNKSJONER ---
def etterisolering(A, U_old, U_new):
    dU = max(U_old - U_new, 0)
    return dU * A * Kh / 1000

def bedre_HRV(qv_m3_s, eta_old, eta_new):
    d_eta = max(eta_new - eta_old, 0)
    return RHO * CP * qv_m3_s * d_eta * Kh

def lavere_SFP(qv_m3_s, SFP_old, SFP_new, timer):
    dSFP = max(SFP_old - SFP_new, 0)
    return dSFP * qv_m3_s * timer

def varmepumpe(Q_netto, eta_old, COP):
    return Q_netto * (1/eta_old - 1/COP)

# --- UI ---
st.title("💡 Enkel energisparekalkulator")
st.write("Forenklet NS3031-logikk – grove estimat i kWh/år for enkelttiltak.")

tabs = st.tabs(["Etterisolering", "Varmegjenvinner", "SFP (vifter)", "Varmepumpe", "Økonomi/CO₂"])

with tabs[0]:
    st.subheader("Etterisolering (vegg/tak/vindu)")
    A = st.number_input("Areal (m²)", 10, 100000, 1800)
    col1, col2 = st.columns(2)
    with col1:
        U_old = st.number_input("U-verdi før (W/m²K)", 0.1, 6.0, 0.30, step=0.05)
    with col2:
        U_new = st.number_input("U-verdi etter (W/m²K)", 0.05, 6.0, 0.18, step=0.05)
    if st.button("Beregn", key="isoler"):
        st.success(f"≈ {etterisolering(A, U_old, U_new):,.0f} kWh/år spart")

with tabs[1]:
    st.subheader("Bedre varmegjenvinner (HRV)")
    qv = st.number_input("Luftmengde (m³/h)", 1000, 500000, 60000)
    eta_old = st.slider("Virkningsgrad før (%)", 50, 90, 80)/100
    eta_new = st.slider("Virkningsgrad etter (%)", 60, 95, 88)/100
    if st.button("Beregn", key="hrv"):
        st.success(f"≈ {bedre_HRV(qv/3600, eta_old, eta_new):,.0f} kWh/år spart")

with tabs[2]:
    st.subheader("Lavere SFP (vifter)")
    qv = st.number_input("Luftmengde (m³/h)", 1000, 500000, 60000, key="qv_sfp")
    SFP_old = st.slider("SFP før (kW/(m³/s))", 0.5, 4.0, 1.8, 0.1)
    SFP_new = st.slider("SFP etter (kW/(m³/s))", 0.3, 3.0, 1.2, 0.1)
    timer = st.number_input("Driftstimer/år", 100, 8760, 3000)
    if st.button("Beregn", key="sfp"):
        st.success(f"≈ {lavere_SFP(qv/3600, SFP_old, SFP_new, timer):,.0f} kWh/år spart (el)")

with tabs[3]:
    st.subheader("Varmepumpe (romoppv. / tappevann)")
    Q_netto = st.number_input("Årlig netto varmebehov (kWh/år)", 1000, 50000000, 600000)
    eta_old = st.slider("Virkningsgrad gammel kjel", 0.5, 1.0, 0.95, 0.01)
    COP = st.slider("Varmepumpe COP", 1.5, 8.0, 3.2, 0.1)
    if st.button("Beregn", key="vp"):
        st.success(f"≈ {varmepumpe(Q_netto, eta_old, COP):,.0f} kWh/år spart levert energi")

with tabs[4]:
    st.subheader("Økonomi/CO₂ (valgfritt)")
    pris = st.number_input("Strøm-/energi­pris (kr/kWh)", 0.0, 10.0, 1.25, 0.05)
    co2 = st.number_input("Utslippsfaktor (kg CO₂/kWh)", 0.0, 1.0, 0.02, 0.01)
    kWh = st.number_input("Satt inn spart energi fra andre faner (kWh/år)", 0, 100000000, 100000)
    if st.button("Regn om", key="okonomi"):
        st.info(f"Sparte kostnader ≈ {kWh*pris:,.0f} kr/år  |  CO₂-reduksjon ≈ {kWh*co2:,.0f} kg/år")

st.caption("Merk: Grove estimat. For prosjektering bruk detaljert månedsbalanse/Simien.")
