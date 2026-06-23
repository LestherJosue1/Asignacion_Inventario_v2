import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime

try:
    import plotly.express as px
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

st.set_page_config(page_title="Planificación APS — NV2", page_icon="🏭", layout="wide")

st.title("🏭 Sistema Avanzado de Asignación Industrial (Modelo NV2)")
st.caption("Filtros por Escenario Independiente, Control de Umbrales y Respeto a Capacidad de Lotes")

# --- SIDEBAR CONTROL ---
st.sidebar.header("📁 Carga de Datos y Configuración")
uploaded_file = st.sidebar.file_uploader("Subir Archivo de Operaciones (.xlsx)", type=["xlsx"])

# Selector de Escenario Solicitado
escenario_seleccionado = st.sidebar.radio(
    "Selecciona el Escenario a Correr:",
    ["1. Solo Inventario Físico", "2. Inventario + Plan 1 Día", "3. Inventario + Plan Semanal (Completo)"]
)

umbral_minimo = st.sidebar.slider("Umbral mínimo de completitud de la DISPO (%)", 70, 100, 90) / 100.0

if uploaded_file:
    try:
        excel_file = pd.ExcelFile(uploaded_file, engine='openpyxl')
        hojas = excel_file.sheet_names
        
        # Validar pestañas reales del usuario
        if 'WIP' not in hojas or 'CONFIG' not in hojas:
            st.error("❌ Estructura incorrecta. El archivo debe contener al menos las pestañas 'WIP' y 'CONFIG'.")
        else:
            df_wip = pd.read_excel(uploaded_file, sheet_name='WIP', engine='openpyxl')
            df_config = pd.read_excel(uploaded_file, sheet_name='CONFIG', engine='openpyxl')
            df_cuota = pd.read_excel(uploaded_file, sheet_name='CUOTA', engine='openpyxl') if 'CUOTA' in hojas else None
            
            st.success("📊 Hojas 'WIP', 'CUOTA' y 'CONFIG' cargadas correctamente.")
            
            # --- PREPARACIÓN DE CAPACIDADES DESDE CONFIG ---
            # Crear un diccionario para controlar el tope de capacidad máxima por LOTSIZE
            capacidad_limite = {}
            if 'LOTSIZE' in df_config.columns and 'CAPACIDAD_SEMANAL_LBS' in df_config.columns:
                # Filtrar filas vacías de la configuración
                df_cfg_clean = df_config.dropna(subset=['LOTSIZE', 'CAPACIDAD_SEMANAL_LBS'])
                for _, cfg_row in df_cfg_clean.iterrows():
                    capacidad_limite[str(cfg_row['LOTSIZE']).strip()] = float(cfg_row['CAPACIDAD_SEMANAL_LBS'])

            # --- BOTÓN DE PROCESAMIENTO ---
            if st.button("🚀 Correr Modelo de Optimización Industrial"):
                with st.spinner("Procesando asignaciones y validando restricciones de lote..."):
                    
                    df_res = df_wip.copy()
                    df_res['LBS_ASIGNADO'] = 0.0
                    df_res['STATUS_DISPO'] = 'SIN ASIGNAR (HUÉRFANO)'
                    
                    # Diccionario para controlar el consumo en tiempo real de los lotes y no violar la CONFIG
                    consumo_lotes_actual = {k: 0.0 for k in capacidad_limite.keys()}
                    
                    # --- PROCESAMIENTO FILA POR FILA ---
                    for idx, row in df_res.iterrows():
                        demanda = float(row.get('LBS_C', 0))
                        if demanda <= 0:
                            df_res.at[idx, 'STATUS_DISPO'] = 'SIN DEMANDA'
                            continue
                            
                        # Determinar abasto disponible según el escenario seleccionado por el usuario
                        inv_fisico = float(row.get('INV', 0))
                        plan_1dia = float(row.get('PLAN_INS_DIA1', 0))
                        plan_semanal = float(row.get('PLAN_INS', 0))
                        
                        if "1. Solo Inventario" in escenario_seleccionado:
                            abasto_disponible = inv_fisico
                        elif "2. Inventario + Plan 1 Día" in escenario_seleccionado:
                            abasto_disponible = inv_fisico + plan_1dia
                        else:
                            abasto_disponible = inv_fisico + plan_1dia + plan_semanal
                        
                        # Validar restricción de lotes desde la hoja CONFIG
                        tipo_lote = str(row.get('LOTSIZE', '')).strip()
                        capacidad_permisible = True
                        if tipo_lote in consumo_lotes_actual:
                            # Si meter este pedido supera la capacidad máxima de libras por lote de la planta, se bloquea
                            if consumo_lotes_actual[tipo_lote] + demanda > capacidad_limite[tipo_lote]:
                                capacidad_permisible = False
                        
                        # APLICACIÓN DEL UMBRAL ESTRICTO: Solo si cubre el X% configurado y hay capacidad de lote
                        if abasto_disponible >= (demanda * umbral_minimo) and capacidad_permisible:
                            libras_a_asignar = min(demanda, abasto_disponible)
                            df_res.at[idx, 'LBS_ASIGNADO'] = libras_a_asignar
                            df_res.at[idx, 'STATUS_DISPO'] = f'APROBADO ({escenario_seleccionado.split(".")[1].strip()})'
                            
                            # Acumular el consumo del lote para respetar la capacidad de la planta
                            if tipo_lote in consumo_lotes_actual:
                                consumo_lotes_actual[tipo_lote] += libras_a_asignar
                        else:
                            if not capacidad_permisible:
                                df_res.at[idx, 'STATUS_DISPO'] = 'RECHAZADO: CAPACIDAD DE LOTE EXCEDIDA'
                            else:
                                df_res.at[idx, 'STATUS_DISPO'] = 'SIN ASIGNAR (NO ALCANZA UMBRAL)'

                    df_res['LBS_FALTANTE'] = df_res['LBS_C'] - df_res['LBS_ASIGNADO']
                    
                    # --- GENERACIÓN DE REPORTES EN PANTALLA ---
                    st.success("🎯 Simulación completada para el escenario seleccionado.")
                    
                    # KPIs Rápidos
                    total_lbs = df_res['LBS_C'].sum()
                    asignadas_lbs = df_res['LBS_ASIGNADO'].sum()
                    pct_cumplimiento = (asignadas_lbs / total_lbs) * 100 if total_lbs > 0 else 0
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Eficiencia Global del Escenario", f"{pct_cumplimiento:.2f}%")
                    col2.metric("Total Libras Asignadas", f"{asignadas_lbs:,.0f} Lbs")
                    col3.metric("Libras Huérfanas/Faltantes", f"{(total_lbs - asignadas_lbs):,.0f} Lbs")
                    
                    # --- GRÁFICOS DE CONTROL OPERACIONAL (PLOTLY) ---
                    if PLOTLY_OK:
                        st.markdown("### 📊 Reporte Analítico de Cumplimiento")
                        g1, g2 = st.columns(2)
                        
                        with g1:
                            # 1. Reporte por Prioridad de Entrega
                            df_entrega = df_res.groupby('ENTREGA')['LBS_ASIGNADO'].sum().reset_index()
                            fig_ent = px.bar(df_entrega, x='ENTREGA', y='LBS_ASIGNADO', 
                                             title="Libras Asignadas por Prioridad de Entrega",
                                             labels={'LBS_ASIGNADO': 'Libras', 'ENTREGA': 'Prioridad'})
                            st.plotly_chart(fig_ent, use_container_width=True)
                            
                        with g2:
                            # 2. Reporte de Consumo de Capacidad por Lotsize (CONFIG vs Real)
                            df_lotes = pd.DataFrame(list(consumo_lotes_actual.items()), columns=['LOTSIZE', 'Lbs_Asignadas'])
                            fig_lote = px.bar(df_lotes, x='LOTSIZE', y='Lbs_Asignadas', 
                                              title="Uso de Capacidad de Lotes (Lbs)",
                                              color_discrete_sequence=['#ff7f0e'])
                            st.plotly_chart(fig_lote, use_container_width=True)

                    # --- DETALLE DE LAS DISPOs ASIGNADAS ---
                    st.markdown("### 🔍 Detalle Operativo de DISPOs")
                    cols_mostrar = ['DISPO', 'ENTREGA', 'PLANTA_WIP', 'LOTSIZE', 'LBS_C', 'LBS_ASIGNADO', 'STATUS_DISPO']
                    st.dataframe(df_res[cols_mostrar].head(100), use_container_width=True)
                    
                    # --- GENERACIÓN DEL EXCEL MULTIHOJA DE SALIDA ---
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_res.to_excel(writer, sheet_name='WIP_PROCESADO', index=False)
                        if df_cuota is not None:
                            df_cuota.to_excel(writer, sheet_name='CUOTA', index=False)
                        df_config.to_excel(writer, sheet_name='CONFIG', index=False)
                        
                    st.download_button(
                        label="📥 Descargar Libro de Resultados Optimizado (.xlsx)",
                        data=output.getvalue(),
                        file_name=f"RESULTADO_PLAN_NV2_{datetime.now().strftime('%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    
    except Exception as e:
        st.error(f"Error crítico en el procesamiento del archivo Excel: {e}")
else:
    st.info("💡 Por favor, sube el archivo maestro Excel en el panel izquierdo para comenzar a simular los escenarios.")
