import streamlit as st
import requests
import pandas as pd
import numpy as np
import holidays
import plotly.graph_objects as go
from utils.math_utils import calcular_curva_spline
#from scipy.interpolate import CubicSpline


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Curva de Juros - DI Futuro", layout="wide")

# --- 1. CACHE DE LONGO PRAZO (Feriados) ---
@st.cache_data
def get_feriados_br():
    # Feriados não mudam a cada 30 segundos, então o cachea pode ficar por tempo indeterminado.
    br_holidays = holidays.Brazil()
    return [f for f in br_holidays['2023-01-01':'2040-05-04']]

# --- 2. CACHE DE DADOS (API B3) ---
@st.cache_data(ttl=30, max_entries=1)
def fetch_curva_di():
    try:
        url = "https://cotacao.b3.com.br/mds/api/v1/DerivativeQuotation/DI1"
        resp = requests.get(url, timeout=10)
        arquivo = resp.json()
        
        ultima_atualizacao = arquivo['Msg']['dtTm']
        scty_list = arquivo['Scty']
        

        data = {
            'simbolo': [s['symb'] for s in scty_list],
            'vencto': [s['asset']['AsstSummry']['mtrtyCode'] for s in scty_list],
            'volume': [s['asset']['AsstSummry'].get('tradQty', 0) for s in scty_list],
            'taxa_corrente': [s['SctyQtn'].get('curPrc', 0) for s in scty_list],
            'taxa_dia_anterior': [s['SctyQtn'].get('prvsDayAdjstmntPric', 0) for s in scty_list]
        }
        
        df = pd.DataFrame(data)[:-1]
        df['vencto'] = pd.to_datetime(df['vencto'])
        return df, ultima_atualizacao
    
    except Exception as e:
        st.error(f"Erro ao conectar com a B3: {e}")
        return pd.DataFrame(), "Erro"

# --- 3. LÓGICA DE PROCESSAMENTO ---
def processar_dados(df, lista_feriados):
    hoje = pd.Timestamp.now().normalize().date()
    
    # Cálculo de DU (Vetorizado para ser mais rápido que .apply)
    df['DIAS_UTEIS'] = [np.busday_count(hoje, d.date(), holidays=lista_feriados) for d in df['vencto']]
    
    df = df[df['taxa_corrente'] > 0].sort_values('vencto').reset_index(drop=True)
    return df


def classificar_inclinacao(valor):
    if valor > 0.20: return "🟢 Inclinada"
    elif valor < -0.20: return "🔴 Invertida"
    else: return "🟡 Plana"



# ---- Lógica da interpolação -----
@st.cache_data(ttl=30)
def processar_visualizacao(df):
    # Curva interpolada para D0
    x_d0, y_d0 = calcular_curva_spline(df, "taxa_corrente")
    
    # Curva interpolada para D-1
    x_d1, y_d1 = calcular_curva_spline(df, "taxa_dia_anterior")
    
    return (x_d0, y_d0), (x_d1, y_d1)



# --- 4. FRAGMENTO ---
@st.fragment(run_every="30s")
def render_monitor():
    feriados = get_feriados_br()
    raw_df, ultima_att = fetch_curva_di()
    
    if raw_df.empty:
        st.warning("Aguardando dados da B3...")
        return

    df = processar_dados(raw_df, feriados)
    
    # --- MÉTRICAS DE INCLINAÇÃO ---
    df_liq = df[df["volume"] > 0]
    if not df_liq.empty:
        curto = df_liq.loc[df_liq["DIAS_UTEIS"].idxmin()]
        longo = df_liq.loc[df_liq["DIAS_UTEIS"].idxmax()]
        medio = df_liq.iloc[(df_liq["DIAS_UTEIS"] - 252).abs().idxmin()]

        incl_curto_medio = medio["taxa_corrente"] - curto["taxa_corrente"]
        incl_medio_longo = longo["taxa_corrente"] - medio["taxa_corrente"]
        incl_curto_longo = longo["taxa_corrente"] - curto["taxa_corrente"]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Inclinação Curto → Longo", f"{incl_curto_longo:.2f} p.p.", help=classificar_inclinacao(incl_curto_longo))
        c2.metric("Inclinação Curto → Médio", f"{incl_curto_medio:.2f} p.p.", help=classificar_inclinacao(incl_curto_medio))
        c3.metric("Inclinação Médio → Longo", f"{incl_medio_longo:.2f} p.p.", help=classificar_inclinacao(incl_medio_longo))

        st.markdown(
                    f"""
                    **Leitura econômica:**  
                    A curva apresenta inclinação **{classificar_inclinacao(incl_curto_longo).lower()}**
                    no trecho curto → longo, com diferença de **{incl_curto_longo:.2f} p.p.**.
                    O movimento intraday pode ser avaliado pela comparação entre as curvas
                    D0 e D-1.""")

        st.caption(f"🕒 Última atualização B3: {ultima_att}")


    # Processa o cálculo da interpolação (cacheado em camada única)
    # Retorna as tuplas: ((x0, y0), (x1, y1))
    curva_d0, curva_d1 = processar_visualizacao(df)
    
    x_smooth_d0, y_smooth_d0 = curva_d0
    x_smooth_d1, y_smooth_d1 = curva_d1



    # --- GRÁFICO ---
    fig = go.Figure()
    
    # 1. LINHA INTERPOLADA D-1 (Tracejada)
    fig.add_trace(go.Scatter(
        x=x_smooth_d1, y=y_smooth_d1,
        mode="lines",
        line=dict(color="orange", dash="dash", width=1),
        name="Curva D-1 (Spline)"
        #,hoverinfo='skip' # pra não ficar mt poluído
    ))

    # 2. PONTOS REAIS D-1 (Vértices)
    fig.add_trace(go.Scatter(
        x=df["DIAS_UTEIS"], y=df["taxa_dia_anterior"],
        mode="markers",
        marker=dict(color="orange", size=6, symbol="circle"),
        name="Vértices D-1"
    ))

    # 3. LINHA INTERPOLADA D0 
    fig.add_trace(go.Scatter(
        x=x_smooth_d0, y=y_smooth_d0,
        mode="lines",
        line=dict(color="#1f77b4", width=2),
        name="Curva Atual (Spline)"
        #,hoverinfo='skip'
    ))

    # 4. PONTOS REAIS D0 (Vértices)
    fig.add_trace(go.Scatter(
        x=df["DIAS_UTEIS"], y=df["taxa_corrente"],
        mode="markers",
        marker=dict(color="#1f77b4", size=8),
        name="Vértices D0 (Spot)"
    ))

    fig.update_layout(
        title="Estrutura a Termo - DI Futuro (Com Interpolação Cubic Spline)",
        xaxis_title="Dias Úteis",
        yaxis_title="Taxa (%)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)


    # --- TABELA RANKING DE LIQUIDEZ ---
    st.subheader("📊 Contratos mais negociados: acompanhamento da liquidez")
    df_tabela = df.sort_values("volume", ascending=False).head(10).copy()
    df_tabela["variação"] = (df["taxa_corrente"] - df["taxa_dia_anterior"]).abs()
    df_tabela["vencto"] = df_tabela["vencto"].dt.strftime("%d/%m/%Y")
    st.dataframe(df_tabela[["simbolo", "vencto", "taxa_corrente", "volume", 'variação']], use_container_width=True, hide_index=True)


    st.markdown(
            f"""
            **Leitura econômica:**  
            A curva apresenta inclinação **{classificar_inclinacao(incl_curto_longo).lower()}**
            no trecho curto → longo, com diferença de **{incl_curto_longo:.2f} p.p.**.
            O movimento intraday pode ser avaliado pela comparação entre as curvas
            D0 e D-1.

            | Trecho | O que reflete |
            | :--- | :--- |
            | **Curto (até ~6m)** | Política monetária atual / Copom |
            | **Médio (1–2 anos)** | Expectativas de ciclo |
            | **Longo (3+ anos)** | Inflação estrutural / risco fiscal |
            """
        )
    
# --- EXECUÇÃO PRINCIPAL ---
st.title("📈 Monitor de Juros Brasil")
st.write("Para adicionar mais detalhes do dash...")
render_monitor()

with st.sidebar:
    st.header("Informações")
    st.write("Espaço para adicionar mais informações... esse dashboard escalável para múltiplos usuários com cache compartilhado.")
    