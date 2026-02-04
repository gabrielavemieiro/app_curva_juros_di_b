import requests
import json
import pandas as pd
import numpy as np
import holidays
from datetime import datetime



def get_curva_di():
    feriados = holidays.Brazil()
    lista_feriados = [f for f in feriados['2023-01-01':'2040-05-04']]

    url = "https://cotacao.b3.com.br/mds/api/v1/DerivativeQuotation/DI1"
    resp = requests.get(url)
    arquivo = json.loads(resp.text)

    ultima_atualizacao = arquivo['Msg']['dtTm']

    n_contratos = range(len(arquivo['Scty']))

    taxa_dia_anterior = []
    taxa_corrente = []
    lista_ticker = []
    lista_vencimento = []
    lista_volume = []

    for n in n_contratos:
        scty = arquivo['Scty'][n]

        lista_ticker.append(scty['symb'])

        lista_vencimento.append(
            scty['asset']['AsstSummry']['mtrtyCode']
        )

        lista_volume.append(
            scty['asset']['AsstSummry'].get('tradQty', 0)
        )

        taxa_dia_anterior.append(
            scty['SctyQtn'].get('prvsDayAdjstmntPric', 0)
        )

        taxa_corrente.append(
            scty['SctyQtn'].get('curPrc', 0)
        )

    df = pd.DataFrame({
        'simbolo': lista_ticker,
        'vencto': lista_vencimento,
        'volume': lista_volume,
        'taxa_corrente': taxa_corrente,
        'taxa_dia_anterior': taxa_dia_anterior
    })[:-1]

    df['vencto'] = pd.to_datetime(df['vencto'])

    hoje = pd.Timestamp.now().normalize().date()

    df['DIAS_UTEIS'] = df['vencto'].apply(
        lambda x: np.busday_count(
            hoje,
            x.date(),
            holidays=lista_feriados
        )
    )

    df = (
        df[df['taxa_corrente'] > 0]
        .sort_values('vencto')
        .reset_index(drop=True)
    )

    return df, ultima_atualizacao


import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import time
from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="Curva de Juros - DI Futuro",
    layout="wide"
)

# Reexecuta o script a cada 30 segundos
st_autorefresh(interval=30000, key="refresh")

st.title("📈 Curva de Juros – DI Futuro (B3)")
st.caption("Atualização a cada 30 segundos")

# Função de classificação da inclinação
def classificar_inclinacao(valor):
    if valor > 0.20:
        return "🟢 Inclinada"
    elif valor < -0.20:
        return "🔴 Invertida: Isso sugere expectativa de queda das taxas no horizonte mais longo."
    else:
        return "🟡 Plana"


#placeholder = st.empty()
info = st.empty()

while True:
    df, ultima_atualizacao = get_curva_di()

    fig = go.Figure()

    # Curva D-1 (laranja, tracejada)
    fig.add_trace(
        go.Scatter(
            x=df["DIAS_UTEIS"],
            y=df["taxa_dia_anterior"],
            mode="lines+markers",
            line=dict(color="orange", dash="dash"),
            name="Taxa D-1"
        )
    )

    # Curva D0 (azul)
    fig.add_trace(
        go.Scatter(
            x=df["DIAS_UTEIS"],
            y=df["taxa_corrente"],
            mode="lines+markers",
            line=dict(color="#1f77b4"),
            name="Taxa Atual (D0)"
        )
    )

    fig.update_layout(
        title="Estrutura a Termo da Taxa de Juros – DI Futuro",
        xaxis_title="Dias Úteis",
        yaxis_title="Taxa (%)",
        hovermode="x unified"
    )


    # Calculo da inclinação da curva
    df_liq = df[df["volume"] > 0]

    curto = df_liq.loc[df_liq["DIAS_UTEIS"].idxmin()]
    longo = df_liq.loc[df_liq["DIAS_UTEIS"].idxmax()]
    medio = df_liq.iloc[(df_liq["DIAS_UTEIS"] - 252).abs().idxmin()]

    incl_curto_medio = medio["taxa_corrente"] - curto["taxa_corrente"]
    incl_medio_longo = longo["taxa_corrente"] - medio["taxa_corrente"]
    incl_curto_longo = longo["taxa_corrente"] - curto["taxa_corrente"]



    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Inclinação Curto → Médio",
            f"{incl_curto_medio:.2f} p.p.",
            help=classificar_inclinacao(incl_curto_medio)
        )

    with col2:
        st.metric(
            "Inclinação Médio → Longo",
            f"{incl_medio_longo:.2f} p.p.",
            help=classificar_inclinacao(incl_medio_longo)
        )

    with col3:
        st.metric(
            "Inclinação Curto → Longo",
            f"{incl_curto_longo:.2f} p.p.",
            help=classificar_inclinacao(incl_curto_longo)
        )

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

    # Ranking da quantidade de negociação
    df_tabela = (
        df[
            [
                "simbolo",
                "vencto",
                "taxa_corrente",
                "taxa_dia_anterior",
                "volume"
            ]
        ]
        .sort_values("volume", ascending=False)
        .reset_index(drop=True)
    )

    df_tabela = df_tabela.head(10)

    df_tabela["vencto"] = df_tabela["vencto"].dt.strftime("%d/%m/%Y")
    df_tabela["taxa_corrente"] = df_tabela["taxa_corrente"].map("{:.2f}".format)
    df_tabela["taxa_dia_anterior"] = df_tabela["taxa_dia_anterior"].map("{:.2f}".format)
    df_tabela["volume"] = df_tabela["volume"].map("{:,}".format)


    st.subheader("📊 Contratos mais negociados: acompanhamento da liquidez")

    st.dataframe(
        df_tabela,
        use_container_width=True,
        hide_index=True
    )


    #placeholder.plotly_chart(fig, use_container_width=True)

    st.plotly_chart(fig, use_container_width=True, key="curva_di")

    info.markdown(
        f"🕒 **Última atualização B3:** `{ultima_atualizacao}`"
    )

    time.sleep(30)

