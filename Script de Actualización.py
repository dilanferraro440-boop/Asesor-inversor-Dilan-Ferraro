import yfinance as yf
import pandas as pd
import json
import datetime
import numpy as np
import sys

# Lista de 8 acciones populares de la Bolsa de Valores de Colombia (vía Yahoo Finance)
ACCIONES = [
    {"ticker": "ECOPETROL.CL", "nombre": "Ecopetrol", "nemotecnico": "ECOPETROL", "sector": "Petróleo y gas"},
    {"ticker": "PFBCOLOM.CL", "nombre": "Bancolombia Pref.", "nemotecnico": "PFBCOLOM", "sector": "Financiero"},
    {"ticker": "BCOLOMBIA.CL", "nombre": "Bancolombia Ordinaria", "nemotecnico": "BCOLOMBIA", "sector": "Financiero"},
    {"ticker": "ISA.CL", "nombre": "ISA", "nemotecnico": "ISA", "sector": "Energía"},
    {"ticker": "GEB.CL", "nombre": "Grupo Energía Bogotá", "nemotecnico": "GEB", "sector": "Energía"},
    {"ticker": "GRUPOSURA.CL", "nombre": "Grupo Sura", "nemotecnico": "GRUPOSURA", "sector": "Inversiones"},
    {"ticker": "NUTRESA.CL", "nombre": "Grupo Nutresa", "nemotecnico": "NUTRESA", "sector": "Alimentos"},
    {"ticker": "CELSIA.CL", "nombre": "Celsia", "nemotecnico": "CELSIA", "sector": "Energía"}
]

# Estructura base del JSON
datos_json = {
    "actualizado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "fuente": "Yahoo Finance (yfinance); rentabilidades con precio ajustado por dividendos",
    "trm": {"valor": None, "fecha": None},
    "acciones": [],
    "errores": []
}

# 1. Intentar descargar TRM (USD/COP)
try:
    trm_ticker = yf.Ticker("USDCOP=X")
    trm_hist = trm_ticker.history(period="5d")
    if not trm_hist.empty:
        datos_json["trm"]["valor"] = round(float(trm_hist['Close'].iloc[-1]), 2)
        datos_json["trm"]["fecha"] = trm_hist.index[-1].strftime("%Y-%m-%d")
except Exception as e:
    print(f"Advertencia: No se pudo obtener la TRM. ({e})")

# 2. Procesar cada acción
for accion in ACCIONES:
    ticker_str = accion["ticker"]
    try:
        tk = yf.Ticker(ticker_str)
        # Descargar 3 años de historia. auto_adjust=False para tener Close y Adj Close separados
        hist = tk.history(period="3y", auto_adjust=False)
        
        if hist.empty or len(hist) < 2:
            raise ValueError("Datos insuficientes o vacíos.")
        
        # Filtrar NaN
        hist = hist.dropna(subset=['Close', 'Adj Close'])
        
        # Precio actual y fecha
        precio_actual = float(hist['Close'].iloc[-1])
        fecha_actual = hist.index[-1].strftime("%Y-%m-%d")
        
        # Variación del día (%)
        precio_anterior = float(hist['Close'].iloc[-2])
        variacion_dia_pct = ((precio_actual / precio_anterior) - 1) * 100
        
        # Fecha de hace 1 año
        fecha_hace_1_ano = hist.index[-1] - pd.DateOffset(years=1)
        # Buscar el índice más cercano a hace 1 año
        idx_1a = hist.index.get_indexer([fecha_hace_1_ano], method='nearest')[0]
        
        # Rentabilidad 1 año (%) usando Adj Close
        adj_actual = float(hist['Adj Close'].iloc[-1])
        adj_1a = float(hist['Adj Close'].iloc[idx_1a])
        rent_1a_pct = ((adj_actual / adj_1a) - 1) * 100
        
        # Rentabilidad anualizada 3 años (%)
        adj_inicial = float(hist['Adj Close'].iloc[0])
        dias_transcurridos = (hist.index[-1] - hist.index[0]).days
        anios = dias_transcurridos / 365.25 if dias_transcurridos > 0 else 1
        rent_anual_3a_pct = ((adj_actual / adj_inicial) ** (1 / anios) - 1) * 100
        
        # Volatilidad anual del último año (%)
        hist_1a = hist.iloc[idx_1a:]
        # Rendimientos logarítmicos diarios
        log_ret = np.log(hist_1a['Adj Close'] / hist_1a['Adj Close'].shift(1)).dropna()
        volatilidad_anual_pct = log_ret.std() * np.sqrt(252) * 100
        
        # Caída máxima en 1 año (Max Drawdown)
        roll_max = hist_1a['Adj Close'].cummax()
        drawdown = (hist_1a['Adj Close'] / roll_max) - 1
        caida_maxima_1a_pct = drawdown.min() * 100
        
        # Rendimiento por dividendo (%) últimos 365 días
        div_1a = hist_1a['Dividends'].sum()
        dividendo_rend_pct = (div_1a / precio_actual) * 100 if precio_actual > 0 else 0
        
        # Histórico de cierres mensuales
        hist_mensual = hist['Close'].resample('ME').last().dropna()
        historico = [{"mes": k.strftime("%Y-%m"), "cierre": round(float(v), 2)} for k, v in hist_mensual.items()]
        
        # Agregar a la lista exitosa
        datos_json["acciones"].append({
            "ticker": ticker_str,
            "nombre": accion["nombre"],
            "nemotecnico": accion["nemotecnico"],
            "sector": accion["sector"],
            "moneda": "COP",
            "precio": round(precio_actual, 2),
            "fecha": fecha_actual,
            "variacion_dia_pct": round(variacion_dia_pct, 2),
            "rent_1a_pct": round(rent_1a_pct, 2),
            "rent_anual_3a_pct": round(rent_anual_3a_pct, 2),
            "volatilidad_anual_pct": round(volatilidad_anual_pct, 2),
            "caida_maxima_1a_pct": round(caida_maxima_1a_pct, 2),
            "dividendo_rend_pct": round(dividendo_rend_pct, 2),
            "historico": historico
        })
        
    except Exception as e:
        datos_json["errores"].append({"ticker": ticker_str, "motivo": str(e)})

# 3. Resumen y Guardado
print(f"Actualización completada: {len(datos_json['acciones'])} acciones exitosas, {len(datos_json['errores'])} errores.")

if len(datos_json['acciones']) == 0:
    print("AVISO: Todas las acciones fallaron. No se sobrescribirá datos.json para conservar los datos anteriores.")
    sys.exit(0) # Termina con éxito para no romper el workflow de GitHub

with open('datos.json', 'w', encoding='utf-8') as f:
    json.dump(datos_json, f, ensure_ascii=False, indent=2)

print("Archivo datos.json creado/actualizado con éxito.")
sys.exit(0)