"""Lectura de la bodega con poca memoria (16-10-2026).

Un mes de produccion son ~390.000 lineas y leerlo entero pesa 350 MB aunque
despues uno se quede con 183 filas. Aqui se lee primero SOLO la columna con la
que se decide y despues cada otra columna por separado, quedandose de una vez
con las filas pedidas: el pico baja de ~370 MB a ~210 MB por mes. Streamlit
Cloud tiene techo de ~1.000 MB y pasarse deja la app 'tardando mas de lo normal'.
"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def filas_de(archivo, columna: str, valores, columnas=None) -> pd.DataFrame:
    """Filas de `archivo` cuya `columna` esta en `valores`, con las `columnas` pedidas (todas si no se dice)."""
    pf = pq.ParquetFile(archivo)
    esquema = pf.schema_arrow
    if columna not in esquema.names:
        return pd.DataFrame()
    col = pf.read(columns=[columna]).column(0)
    idx = pc.indices_nonzero(pc.is_in(col, value_set=pa.array(list(valores), type=col.type)))
    del col
    if columnas:
        columnas = [c for c in columnas if c in esquema.names]
    return con_indices(pf, esquema, idx, columnas)


def con_indices(pf: pq.ParquetFile, esquema, idx, columnas=None) -> pd.DataFrame:
    """Las filas `idx` (posiciones) de las `columnas` pedidas, leidas de una en una."""
    nombres = list(columnas) if columnas else esquema.names
    arrs = [pf.read(columns=[n]).column(0).take(idx) for n in nombres]
    sub = pa.schema([esquema.field(n) for n in nombres], metadata=esquema.metadata)
    return pa.Table.from_arrays(arrs, schema=sub).to_pandas()
