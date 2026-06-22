import streamlit as st
import pandas as pd
import numpy as np

# Configuración de la página de Streamlit
st.set_page_config(page_title="Core APS - Optimización de Asignación", layout="wide")

st.title("🏭 Sistema de Asignación de Abasto y Cuotas (Model NV2)")
st.subheader("Arquitectura de Optimización Industrial en Cascada")

def clean_key(text):
    """Normaliza de forma estricta las llaves de cruce industrial."""
    if pd.isna(text):
        return ""
    text_str = str(text).strip().upper()
    if '|' in text_str:
        text_str = text_str.split('|')[0].strip()
    return text_str

# --- 1. CARGA DE ARCHIVOS EN LA INTERFAZ ---
st.sidebar.header("📁 Carga de Insumos (Formatos CSV)")
uploaded_detalle = st.sidebar.file_uploader("Subir DETALLE (Demanda)", type=["csv"])
uploaded_inv = st.sidebar.file_uploader("Subir INV_LIBRE (Inventario)", type=["csv"])

if uploaded_detalle and uploaded_inv:
    # Leer datos subidos por el usuario
    df_detalle = pd.read_csv(uploaded_detalle)
    df_inv = pd.read_csv(uploaded_inv)
    
    st.success("¡Archivos cargados correctamente de forma interna!")
    
    # --- 2. PROCESAMIENTO Y NORMALIZACIÓN ---
    for df in [df_detalle, df_inv]:
        for col in df.columns:
            if 'LINK' in col.upper():
                df[f'{col}_CLEAN'] = df[col].apply(clean_key)
            if 'FAMILIA' in col.upper():
                df[f'{col}_CLEAN'] = df[col].apply(clean_key)
                
    link_col_det = 'LINK2_CLEAN' if 'LINK2_CLEAN' in df_detalle.columns else 'LINK_CLEAN'
    link_col_inv = 'LINK2_CLEAN' if 'LINK2_CLEAN' in df_inv.columns else 'LINK_CLEAN'
    fam_col_det = 'FAMILIA_CLEAN' if 'FAMILIA_CLEAN' in df_detalle.columns else 'FAMILIA'
    fam_col_inv = 'FAMILIA_CLEAN' if 'FAMILIA_CLEAN' in df_inv.columns else 'FAMILIA'

    # --- 3. BOTÓN DE ACTIVACIÓN DEL MOTOR ---
    if st.button("🚀 Ejecutar Optimización de Asignación"):
        
        with st.spinner("Procesando asignación multimétodo..."):
            # Inicializar columnas de control
            df_detalle['CANTIDAD_ASIGNADA'] = 0.0
            df_detalle['ESCENARIO_ASIGNADO'] = 'SIN ASIGNAR'
            
            # --- CAPA 1: Inventario Físico Disponible (Match Exacto) ---
            inv_disponibilidad = df_inv.groupby(link_col_inv)['CANTIDAD_LIBRE'].sum().to_dict()
            
            for idx, row in df_detalle.iterrows():
                key = row[link_col_det]
                cant_req = row['CANTIDAD_REQUERIDA'] if 'CANTIDAD_REQUERIDA' in df_detalle.columns else row.get('CANTIDAD', 0)
                
                if key in inv_disponibilidad and inv_disponibilidad[key] > 0:
                    asignado = min(cant_req, inv_disponibilidad[key])
                    inv_disponibilidad[key] -= asignado
                    df_detalle.at[idx, 'CANTIDAD_ASIGNADA'] = asignado
                    df_detalle.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 1: INVENTARIO'
            
            # --- CAPA 2: Plan Semanal (Flexibilización por Familia) ---
            huerfanos_idx = df_detalle[df_detalle['ESCENARIO_ASIGNADO'] == 'SIN ASIGNAR'].index
            
            if fam_col_det in df_detalle.columns and fam_col_inv in df_inv.columns:
                inv_familia_disp = df_inv.groupby(fam_col_inv)['CANTIDAD_LIBRE'].sum().to_dict()
                
                for idx in huerfanos_idx:
                    row = df_detalle.loc[idx]
                    fam_key = row[fam_col_det]
                    cant_req = row['CANTIDAD_REQUERIDA'] if 'CANTIDAD_REQUERIDA' in df_detalle.columns else row.get('CANTIDAD', 0)
                    pendiente = cant_req - df_detalle.at[idx, 'CANTIDAD_ASIGNADA']
                    
                    if fam_key in inv_familia_disp and inv_familia_disp[fam_key] > 0:
                        asignado = min(pendiente, inv_familia_disp[fam_key])
                        inv_familia_disp[fam_key] -= asignado
                        df_detalle.at[idx, 'CANTIDAD_ASIGNADA'] += asignado
                        df_detalle.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 3: PLAN SEMANAL FLEX'

        # --- 4. SECCIÓN DE DASHBOARD Y MÉTRICAS CONTRA EL 60% ---
        df_reporte = df_detalle[df_detalle['ESCENARIO_ASIGNADO'] != 'SIN ASIGNAR']
        df_huerfanos = df_detalle[df_detalle['ESCENARIO_ASIGNADO'] == 'SIN ASIGNAR']
        
        total_filas = len(df_detalle)
        total_asignados = len(df_reporte)
        eficiencia = (total_asignados / total_filas) * 100 if total_filas > 0 else 0

        st.success("🎯 ¡Optimización completada con éxito!")
        
        col1, col2, col3 = st.columns(3)
        col1.metric(label="Eficiencia General de Asignación", value=f"{eficiencia:.2f}%", delta=f"{eficiencia - 40.0:.2f}% vs Anterior")
        col2.metric(label="Órdenes Asignadas", value=f"{total_asignados} SKUs")
        col3.metric(label="Huérfanos Restantes (Críticos)", value=f"{len(df_huerfanos)} SKUs")

        # --- 5. DESCARGA DE RESULTADOS DESDE LA INTERFAZ ---
        st.subheader("📥 Descarga de Reportes Generados")
        col_down1, col_down2 = st.columns(2)
        
        csv_diagnostico = df_reporte.to_csv(index=False).encode('utf-8')
        col_down1.download_button(
            label="⬇️ Descargar Reporte de Asignados (Diagnóstico)",
            data=csv_diagnostico,
            file_name="NUEVO_REPORTE_DIAGNOSTICO.csv",
            mime="text/csv"
        )
        
        csv_huerfanos = df_huerfanos.to_csv(index=False).encode('utf-8')
        col_down2.download_button(
            label="⬇️ Descargar Nuevos Huérfanos",
            data=csv_huerfanos,
            file_name="NUEVO_REPORTE_HUERFANOS.csv",
            mime="text/csv"
        )
        
        # Muestra previa en pantalla
        st.subheader("🔍 Vista Previa de Asignaciones")
        st.dataframe(df_detalle[[link_col_det, 'CANTIDAD_ASIGNADA', 'ESCENARIO_ASIGNADO']].head(20))

else:
    st.info("💡 Por favor, sube los archivos de DETALLE e INV_LIBRE en la barra lateral para iniciar el proceso.")
