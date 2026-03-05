import streamlit as st
import requests
import pandas as pd
import numpy as np
import holidays
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.math_utils import calcular_curva_spline, get_forward_data
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
    
    # Cálculo de DU
    df['DIAS_UTEIS'] = [np.busday_count(hoje, d.date(), holidays=lista_feriados) for d in df['vencto']]
    
    df = df[df['taxa_corrente'] > 0].sort_values('vencto').reset_index(drop=True)
    
    # Tratamento de erro para quando não tiver mais de 2 vertices 
    if len(df) < 2:
         return pd.DataFrame() # Retorna vazio
    
    return df


def classificar_inclinacao(valor):
    if valor > 0.20: return "🟢 Inclinada"
    elif valor < -0.20: return "🔴 Invertida"
    else: return "🟡 Plana"



# ---- Lógica da interpolação -----
@st.cache_data(ttl=30)
def processar_visualizacao(df):
    
    # Verificação de liquidez
    if df is None or len(df) < 2:
        return None, None 

    x_d0, y_d0 = calcular_curva_spline(df, "taxa_corrente")         # Curva interpolada para D0
    x_d1, y_d1 = calcular_curva_spline(df, "taxa_dia_anterior")     # Curva interpolada para D-1
    
    return (x_d0, y_d0), (x_d1, y_d1)



# --- FRAGMENTO ---
@st.fragment(run_every="30s")
def render_monitor():
    feriados = get_feriados_br()
    raw_df, ultima_att = fetch_curva_di()
    
    if raw_df.empty:
        st.warning("Aguardando dados da B3...")
        return

    df = processar_dados(raw_df, feriados)

    if df.empty:
        st.warning("⚠️ Aguardando abertura do pregão ou liquidez nos vértices da B3...")
        return # Para a execução do fragmento aqui
    
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
                    **Inclinação da Curva de Juros:**  
                    A curva apresenta inclinação **{classificar_inclinacao(incl_curto_longo).lower()}**
                    no trecho curto → longo, com diferença de **{incl_curto_longo:.2f} p.p.**.
                    O movimento intraday pode ser avaliado pela comparação entre as curvas
                    D0 e D-1.
                    
                    A inclinação da curva reflete como o mercado precifica risco, liquidez e expectativas de política monetária ao longo do tempo. 
                    Curvas mais inclinadas indicam prêmio maior para prazos longos, enquanto curvas mais planas ou invertidas sugerem incerteza ou expectativa de desaceleração econômica.
                    """)

        st.caption(f"🕒 Última atualização B3: {ultima_att}")


    # processa a matemática (cacheado em camada única)
    curva_d0, curva_d1 = processar_visualizacao(df)
    
    x_smooth_d0, y_smooth_d0 = curva_d0
    x_smooth_d1, y_smooth_d1 = curva_d1



    # --- GRÁFICO ---
    
    fig = go.Figure()
    # 1. LINHA INTERPOLADA D-1
    fig.add_trace(go.Scatter(
        x=x_smooth_d1, y=y_smooth_d1,
        mode="lines",
        line=dict(color="orange", dash="dash", width=1),
        name="Curva D-1 (Spline)"
    ))

    # 2. PONTOS REAIS D-1 (Vértices)
    fig.add_trace(go.Scatter(
        x=df["DIAS_UTEIS"], y=df["taxa_dia_anterior"],
        mode="markers",
        marker=dict(color="orange", size=6, symbol="circle"), #-open"),
        name="Vértices D-1"
    ))

    # 3. LINHA INTERPOLADA D0 
    fig.add_trace(go.Scatter(
        x=x_smooth_d0, y=y_smooth_d0,
        mode="lines",
        line=dict(color="#1f77b4", width=2),
        name="Curva Atual (Spline)"
    ))

    # 4. PONTOS REAIS D0 (Vértices)
    fig.add_trace(go.Scatter(
        x=df["DIAS_UTEIS"], y=df["taxa_corrente"],
        mode="markers",
        marker=dict(color="#1f77b4", size=8),
        name="Vértices D0 (Spot)"
    ))

    fig.update_layout(
        title= "Estrutura a Termo - DI Futuro (Com Interpolação Cubic Spline)",
        xaxis_title="Dias Úteis",
        yaxis_title="Taxa (%)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('A interpolação por cubic spline permite estimar taxas para prazos intermediários, suavizando a curva entre os vencimentos efetivamente negociados. Esse método preserva a continuidade da curva e facilita a análise do formato e da inclinação ao longo do tempo.')

    # --- TABELA RANKING DE LIQUIDEZ ---
    st.subheader("📊 Contratos mais negociados: acompanhamento da liquidez")
    st.caption("A concentração de liquidez em determinados vértices indica onde o mercado está mais ativo no momento. Esses pontos tendem a carregar mais informação sobre expectativas correntes e ajustes de posição dos agentes.")
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
    
    # Grafico Forward
    st.divider() # Uma linha para separar 

    st.subheader("🔭 Expectativas Forward (Taxas entre Vértices)")
    labels, fwds, spots = get_forward_data(df)

    fig_fwd = go.Figure()

    # 1. Barras Forward
    fig_fwd.add_trace(go.Bar(
        x=labels, 
        y=fwds, 
        text=fwds, 
        textposition='auto', 
        marker_color='rgba(44, 160, 44, 0.5)',
        name="Taxa Forward (no período)"
    ))

    # 2. Linha Spot no mesmo eixo
    fig_fwd.add_trace(go.Scatter(
        x=labels, 
        y=spots, 
        mode="lines+markers",
        line=dict(color="#1f77b4", width=3),
        marker=dict(size=10, symbol="diamond"),
        name="Taxa Spot (Vértice Final)"
    ))

    fig_fwd.update_layout(
        bargap=0.3, # aumentar o espaço entre as barras
        title="Análise de Expectativa: Taxas Forward vs. Spot por Vértice",
        yaxis_title="Taxa (% a.a.)",
        xaxis_tickangle=0, 
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500
    )

    fig_fwd.update_xaxes(
    tickangle=-90,          # labels na vertical
    tickfont=dict(size=10),
    automargin=True         # garante que as datas não cortem no fim da tela
    )

    # --- AJUSTES NO EIXO Y ---
    # Calcular o mínimo dinamicamente para não "cortar" a curva se as taxas caírem
    min_taxa = min(min(fwds), min(spots)) - 0.5 # margem de segurança de 0.5pp

    fig_fwd.update_yaxes(
        range=[max(0, min_taxa), max(spots + fwds) + 0.5], # começa no min_taxa, mas nunca abaixo de 0
        nticks=10
    )

    st.plotly_chart(fig_fwd, use_container_width=True)
    
# --- EXECUÇÃO PRINCIPAL ---
st.title("📈 Monitoramento da Curva de Juros (Contratos de DI Futuro)")
#st.write("Dashboard escalável para múltiplos usuários com cache compartilhado.")

render_monitor()


st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #9E9D9D;'>"
    "Desenvolvido por Gabriela Vemieiro"
    "</div>",
    unsafe_allow_html=True
)
# with st.sidebar:
#     st.header("Informações")
#     st.write("Dashboard escalável para múltiplos usuários com cache compartilhado.")


# --- Melhorias estética
# esconder o menu do github
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# adicionando um favicon 
st.set_page_config (
    page_title="Curva de Juros - DI Futuro",
    page_icon="📈",
    layout="wide")