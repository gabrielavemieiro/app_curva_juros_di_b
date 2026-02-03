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
import time
from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="Curva de Juros - DI Futuro",
    layout="wide"
)

# Reexecuta o script a cada 5 segundos
st_autorefresh(interval=10000, key="refresh")

st.title("📈 Curva de Juros – DI Futuro (B3)")
st.caption("Atualização a cada 5 segundos")



#placeholder = st.empty()
info = st.empty()

while True:
    df, ultima_atualizacao = get_curva_di()

    fig = px.line(
        df,
        x="DIAS_UTEIS",
        y="taxa_corrente",
        markers=True,
        hover_data=["simbolo", "vencto", "volume"],
        labels={
            "DIAS_UTEIS": "Dias Úteis",
            "taxa_corrente": "Taxa (%)"
        },
        title="Estrutura a Termo da Taxa de Juros"
    )

    # 2. Adição da linha "taxa_dia_anterior" na cor laranja
    fig.add_scatter(
        x=df["DIAS_UTEIS"], 
        y=df["taxa_dia_anterior"], 
        mode="lines+markers", 
        name="Taxa Dia Anterior",
        line=dict(color="orange"),
        hovertemplate="Taxa Dia Anterior: %{y}%<extra></extra>")

    fig.update_layout(
        xaxis_title="Dias Úteis",
        yaxis_title="Taxa (%)",
        hovermode="x unified"
    )

    # Calculo da inclinação da curva
    df_liq = df[df["volume"] > 0]

    curto = df_liq.loc[df_liq["DIAS_UTEIS"].idxmin()]
    longo = df_liq.loc[df_liq["DIAS_UTEIS"].idxmax()]

    inclinação = longo["taxa_corrente"] - curto["taxa_corrente"]


    if inclinação > 0.20:
        status = "Curva inclinada (steep)"
        cor = "🟢"
    elif inclinação < -0.20:
        status = "Curva invertida"
        cor = "🔴"
    else:
        status = "Curva plana (flat)"
        cor = "🟡"


    st.metric(
    label="Inclinação da Curva (curto × longo)",
    value=f"{inclinação:.2f} p.p.",
    help=f"{curto['simbolo']} → {longo['simbolo']} | {status}")


    st.markdown(
    f"""
    **Leitura econômica:**  
    A curva apresenta **{status.lower()}**, com diferença de 
    **{inclinação:.2f} p.p.** entre os vencimentos curto e longo.  
    Isso sugere expectativa de {"alta" if inclinação > 0 else "queda"} 
    das taxas no horizonte mais longo.
    """)



    #placeholder.plotly_chart(fig, use_container_width=True)

    st.plotly_chart(fig, use_container_width=True, key="curva_di")

    info.markdown(
        f"🕒 **Última atualização B3:** `{ultima_atualizacao}`"
    )

    time.sleep(10)
