import streamlit as st
import pandas as pd
import numpy as np
import io

# Configuración avanzada de la interfaz
st.set_page_config(page_title="Core APS - Asignación Avanzada NV2", page_icon="🏭", layout="wide")

st.title("🏭 Motor de Asignación de Abasto y Cuotas (Modelo NV2)")
st.subheader("Optimización de Suministro en Cascada — Arquitectura Single-File XLSX")

# --- 1. CARGA DEL LIBRO DE EXCEL NATIVO ---
st.sidebar.header("📁 Carga de Insumos")
uploaded_file = st.sidebar.file_uploader("Subir Archivo de Asignación (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        # Leer las hojas disponibles para asegurar que es el archivo correcto
        excel_reader = pd.ExcelFile(uploaded_file, engine='openpyxl')
        hojas_disponibles = excel_reader.sheet_names
        
        if 'DETALLE' not in hojas_disponibles:
            st.error("❌ El archivo cargado no contiene la pestaña mandatoria llamada 'DETALLE'.")
        else:
            # Cargar la hoja de cálculo Core
            df = pd.read_excel(uploaded_file, sheet_name='DETALLE', engine='openpyxl')
            st.success("¡Archivo Excel y pestaña 'DETALLE' cargados con éxito!")
            
            columnas = df.columns.tolist()
            
            # Mapeo y validación de columnas industriales reales del modelo
            columnas_suministro = ['INV', 'PLAN_INS_DIA1', 'PLAN_INS']
            col_demanda = 'LBS_C' if 'LBS_C' in columnas else next((c for c in columnas if 'REQUERIDA' in c.upper() or 'CANTIDAD' in c.upper() or 'LBS' in c.upper()), None)
            
            missing_cols = [c for c in columnas_suministro if c not in columnas]
            
            if missing_cols:
                st.error(f"❌ Faltan las siguientes columnas de abasto en la hoja DETALLE: {missing_cols}")
            elif not col_demanda:
                st.error("❌ No se encontró la columna de demanda base (se buscaba 'LBS_C' o similar).")
            else:
                st.sidebar.info(f"Mapeo exitoso -> Demanda: `{col_demanda}`")
                
                # --- 2. BOTÓN DE ACTIVACIÓN DEL MOTOR ---
                if st.button("🚀 Ejecutar Simulación de Asignación en Cascada"):
                    with st.spinner("Ejecutando heurística de asignación industrial..."):
                        
                        # Inicializar nuevas variables de control operacional
                        df['CANTIDAD_ASIGNADA'] = 0.0
                        df['ESCENARIO_ASIGNADO'] = 'SIN ASIGNAR (HUÉRFANO)'
                        
                        # Sanitización de datos a tipo flotante para evitar errores de tipo string/vacíos
                        df['_demanda'] = df[col_demanda].fillna(0).astype(float)
                        df['_inv'] = df['INV'].fillna(0).astype(float)
                        df['_dia1'] = df['PLAN_INS_DIA1'].fillna(0).astype(float)
                        df['_semanal'] = df['PLAN_INS'].fillna(0).astype(float)
                        
                        # --- MOTOR DE CASCADA FILA POR FILA ---
                        for idx, row in df.iterrows():
                            demanda_neta = row['_demanda']
                            
                            if demanda_neta <= 0:
                                df.at[idx, 'ESCENARIO_ASIGNADO'] = 'SIN DEMANDA'
                                continue
                            
                            inv_fisi = row['_inv']
                            p_dia1 = row['_dia1']
                            p_sem = row['_semanal']
                            
                            # Escenario 1: Cubre al 100% solo con Inventario Físico
                            if inv_fisi >= demanda_neta:
                                df.at[idx, 'CANTIDAD_ASIGNADA'] = demanda_neta
                                df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 1: INVENTARIO'
                                
                            # Escenario 2: Requiere Inventario + Plan de 1 Día
                            elif (inv_fisi + p_dia1) >= demanda_neta:
                                df.at[idx, 'CANTIDAD_ASIGNADA'] = demanda_neta
                                df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 2: INV + PLAN 1 DÍA'
                                
                            # Escenario 3: Requiere Inventario + Plan de 1 Día + Plan Semanal (PLAN_INS)
                            elif (inv_fisi + p_dia1 + p_sem) >= demanda_neta:
                                df.at[idx, 'CANTIDAD_ASIGNADA'] = demanda_neta
                                df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 3: INV + PLAN SEMANAL'
                                
                            # Cobertura Parcial / Huérfanos por déficit de abasto absoluto
                            else:
                                total_disponible = inv_fisi + p_dia1 + p_sem
                                if total_disponible > 0:
                                    df.at[idx, 'CANTIDAD_ASIGNADA'] = total_disponible
                                    df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ASIGNACIÓN PARCIAL INSUFICIENTE'
                                else:
                                    df.at[idx, 'CANTIDAD_ASIGNADA'] = 0.0
                                    df.at[idx, 'ESCENARIO_ASIGNADO'] = 'SIN ASIGNAR (HUÉRFANO)'

                        # Limpieza de columnas temporales
                        df.drop(columns=['_demanda', '_inv', '_dia1', '_semanal'], inplace=True)
                        
                    # --- 3. DASHBOARD Y ANALÍTICA DE RESULTADOS ---
                    st.success("🎯 ¡Simulación concluida!")
                    
                    df_asignados = df[~df['ESCENARIO_ASIGNADO'].isin(['SIN ASIGNAR (HUÉRFANO)', 'SIN DEMANDA'])]
                    df_huerfanos = df[df['ESCENARIO_ASIGNADO'] == 'SIN ASIGNAR (HUÉRFANO)']
                    
                    total_filas = len(df)
                    total_asignados = len(df_asignados)
                    eficiencia = (total_asignados / total_filas) * 100 if total_filas > 0 else 0
                    
                    # Despliegue de KPIs
                    col1, col2, col3 = st.columns(3)
                    col1.metric(label="Eficiencia de Cobertura Obtenida", value=f"{eficiencia:.2f}%", delta=f"{eficiencia - 40.0:.2f}% vs Inicial")
                    col2.metric(label="Líneas con Suministro Asegurado", value=f"{total_asignados}")
                    col3.metric(label="Líneas en Condición Huérfana", value=f"{len(df_huerfanos)}")
                    
                    # --- 4. GENERACIÓN DEL EXCEL DE SALIDA ---
                    st.subheader("📥 Descarga de Resultados")
                    
                    # Salvar a buffer binario para descarga directa en Streamlit
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, sheet_name='DETALLE_PROCESADO', index=False)
                        df_huerfanos.to_excel(writer, sheet_name='REPORTE_HUERFANOS', index=False)
                    
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        label="⬇️ Descargar Reporte de Asignación Completo (.xlsx)",
                        data=excel_data,
                        file_name="REPORTE_OPTIMIZACION_NV2.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                    # Visualización de control en pantalla
                    st.subheader("🔍 Auditoría de Líneas Procesadas (Primeros 50 registros)")
                    columnas_control = ['DISPO', 'PLANTA_WIP', col_demanda, 'INV', 'PLAN_INS_DIA1', 'PLAN_INS', 'CANTIDAD_ASIGNADA', 'ESCENARIO_ASIGNADO']
                    st.dataframe(df[columnas_control].head(50))
                    
    except Exception as e:
        st.error(f"Falla en la lectura del motor Excel openpyxl: {e}")
else:
    st.info("💡 Esperando la carga del archivo maestro .xlsx en el panel lateral para iniciar el diagnóstico...")
