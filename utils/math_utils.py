import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

def calcular_curva_spline(df, coluna_taxa):
    """
    Faz a interpolação Cubic Spline nos dados de juros.
    Retorna arrays de X (dias úteis) e Y (taxas interpoladas).
    """
    # 1. Preparação: Garantir que temos dados únicos e ordenados por DU
    # Imprescindível para evitar erro de 'x must be strictly increasing' no SciPy
    df_sorted = df.sort_values("DIAS_UTEIS").drop_duplicates("DIAS_UTEIS")
    
    x_input = df_sorted["DIAS_UTEIS"].values
    y_input = df_sorted[coluna_taxa].values

    # 2. Criação do Objeto Spline
    # bc_type='natural' garante que a curvatura nas pontas seja zero (comum em finanças)
    cs = CubicSpline(x_input, y_input, bc_type='natural')

    # 3. Geração da Curva Suave
    # Criamos pontos de 1 em 1 dia útil do início ao fim da curva
    x_smooth = np.arange(x_input.min(), x_input.max() + 1, 1)
    y_smooth = cs(x_smooth)

    return x_smooth, y_smooth


# -----------------------------------------------------
def calcular_forward_nos_vertices(df):

    df_fwd = df.sort_values("DIAS_UTEIS").copy()
    
    # Cálculo dos fatores de capitalização nos vértices: (1 + i)^(DU/252)
    df_fwd['fator'] = (1 + df_fwd['taxa_corrente']/100) ** (df_fwd['DIAS_UTEIS']/252)
    
    forward_list = []
    labels = []
    
    for i in range(1, len(df_fwd)):
        t1 = df_fwd.iloc[i-1]['DIAS_UTEIS']
        t2 = df_fwd.iloc[i]['DIAS_UTEIS']
        f1 = df_fwd.iloc[i-1]['fator']
        f2 = df_fwd.iloc[i]['fator']
        
        # Fórmula da Forward entre dois pontos
        fwd = ((f2 / f1) ** (252 / (t2 - t1)) - 1) * 100
        forward_list.append(fwd)
        
        # Criamos um label para o eixo X (ex: "Jan25-Jan26")
        labels.append(f"{df_fwd.iloc[i-1]['simbolo']} → {df_fwd.iloc[i]['simbolo']}")
        
    return labels, forward_list



def get_forward_data(df):
    """
    Calcula a taxa forward entre cada par de vértices consecutivos (taxas spot).
    """
    df_fwd = df.sort_values("DIAS_UTEIS").copy()
    
    # Fator de capitalização: (1 + i)^(DU/252)
    df_fwd['fator'] = (1 + df_fwd['taxa_corrente']/100) ** (df_fwd['DIAS_UTEIS']/252)
    
    forwards = []
    labels = []
    spot_destino = []
    
    for i in range(1, len(df_fwd)):
        f1, t1 = df_fwd.iloc[i-1]['fator'], df_fwd.iloc[i-1]['DIAS_UTEIS']
        f2, t2 = df_fwd.iloc[i]['fator'], df_fwd.iloc[i]['DIAS_UTEIS']
        
        # Taxa Forward entre os dois vértices
        fwd = ((f2 / f1) ** (252 / (t2 - t1)) - 1) * 100
        forwards.append(round(fwd, 2))


        # Label: Símbolo + Data (Ex: DI1F25 (01/01/25))
        data_fmt = df_fwd.iloc[i]['vencto'].strftime('%d/%m/%y')
        simbolo = df_fwd.iloc[i]['simbolo']
        labels.append(f"{simbolo} - ({data_fmt})")
        
        # Guardamos a taxa spot do vértice de destino para alinhar o gráfico
        spot_destino.append(df_fwd.iloc[i]['taxa_corrente'])
        
        # Label do intervalo (ex: "F25 -> F26") 
        #labels.append(f"{df_fwd.iloc[i-1]['simbolo']} > {df_fwd.iloc[i]['simbolo']}")
        
    return labels, forwards, spot_destino