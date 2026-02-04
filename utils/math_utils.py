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