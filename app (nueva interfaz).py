import streamlit as st
import pandas as pd
import numpy as np

# Configuración de la interfaz
st.set_page_config(page_title="Core APS - Asignación Integrada", layout="wide")

st.title("🏭 Sistema de Asignación de Abasto y Cuotas (Model NV2)")
st.subheader("Optimización en Cascada (Matriz de Suministro Integrada)")

# --- 1. CARGA DEL ARCHIVO ÚNICO ---
st.sidebar.header("📁 Carga de Datos")
uploaded_file = st.sidebar.file_uploader("Subir archivo DETALLE o REPORTE (CSV)", type=["csv"])

if uploaded_file:
    # Leer el archivo único
    df = pd.read_csv(uploaded_file)
    st.success("¡Archivo cargado correctamente!")
    
    # Mostrar columnas detectadas para seguridad del usuario
    columnas = df.columns.tolist()
    
    # --- 2. VERIFICACIÓN DE COLUMNAS CRÍTICAS ---
    columnas_requeridas = ['INV', 'PLAN_INS_DIA1', 'PLAN_INSIDE']
    # Intentar detectar la columna de demanda (puede llamarse CANTIDAD, CANTIDAD_REQUERIDA o TOTAL)
    col_demanda = next((c for c in columnas if 'REQUERIDA' in c.upper() or 'CANTIDAD' in c.upper() or 'TOTAL' in c.upper()), None)
    
    # Validar que existan las columnas en el archivo subido
    missing_cols = [c for c in columnas_requeridas if c not in columnas]
    
    if missing_cols:
        st.error(f"❌ Al archivo le faltan las siguientes columnas esenciales de suministro: {missing_cols}")
    elif not col_demanda:
        st.error("❌ No se detectó la columna de demanda (ej. 'CANTIDAD_REQUERIDA' o 'CANTIDAD').")
    else:
        st.info(f"Columna de demanda detectada: `{col_demanda}`")
        
        # --- 3. BOTÓN DE ACTIVACIÓN DEL MOTOR ---
        if st.button("🚀 Ejecutar Optimización de Asignación"):
            with st.spinner("Procesando heurística de asignación industrial..."):
                
                # Inicializar variables de salida
                df['CANTIDAD_ASIGNADA'] = 0.0
                df['ESCENARIO_ASIGNADO'] = 'SIN ASIGNAR'
                
                # Copias de las columnas de abasto para simular el consumo dinámico fila por fila
                df['_inv_disp'] = df['INV'].fillna(0).astype(float)
                df['_dia1_disp'] = df['PLAN_INS_DIA1'].fillna(0).astype(float)
                df['_semanal_disp'] = df['PLAN_INSIDE'].fillna(0).astype(float)
                df['_demanda_neta'] = df[col_demanda].fillna(0).astype(float)
                
                # --- MOTOR DE ASIGNACIÓN EN CASCADA (Fila por Fila) ---
                for idx, row in df.iterrows():
                    demanda = row['_demanda_neta']
                    asignado = 0.0
                    
                    if demanda <= 0:
                        df.at[idx, 'ESCENARIO_ASIGNADO'] = 'SIN DEMANDA'
                        continue
                    
                    # Criterio 1: Asignar contra INVENTARIO (Físico inmediato)
                    if row['_inv_disp'] >= demanda:
                        asignado = demanda
                        df.at[idx, 'CANTIDAD_ASIGNADA'] = asignado
                        df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 1: INVENTARIO'
                        continue  # Satisfecho al 100%
                        
                    # Criterio 2: Asignar contra INVENTARIO + PLAN_INS_DIA1
                    elif (row['_inv_disp'] + row['_dia1_disp']) >= demanda:
                        asignado = demanda
                        df.at[idx, 'CANTIDAD_ASIGNADA'] = asignado
                        df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 2: INV + PLAN 1 DÍA'
                        continue
                        
                    # Criterio 3: Asignar contra INVENTARIO + PLAN_INS_DIA1 + PLAN_INSIDE
                    elif (row['_inv_disp'] + row['_dia1_disp'] + row['_semanal_disp']) >= demanda:
                        asignado = demanda
                        df.at[idx, 'CANTIDAD_ASIGNADA'] = asignado
                        df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ESCENARIO 3: INV + PLAN SEMANAL'
                        continue
                    
                    # Si no cubre con ninguno de los tres escenarios, se va parcial o se queda huérfano
                    else:
                        disponibilidad_total = row['_inv_disp'] + row['_dia1_disp'] + row['_semanal_disp']
                        if disponibilidad_total > 0:
                            df.at[idx, 'CANTIDAD_ASIGNADA'] = disponibilidad_total
                            df.at[idx, 'ESCENARIO_ASIGNADO'] = 'ASIGNACIÓN PARCIAL INSUFICIENTE'
                        else:
                            df.at[idx, 'CANTIDAD_ASIGNADA'] = 0.0
                            df.at[idx, 'ESCENARIO_ASIGNADO'] = 'SIN ASIGNAR (HUÉRFANO)'

                # Limpieza de columnas temporales de cálculo
                df.drop(columns=['_inv_disp', '_dia1_disp', '_semanal_disp', '_demanda_neta'], inplace=True)
                
            # --- 4. DASHBOARD DE RESULTADOS ---
            st.success("🎯 ¡Proceso de simulación completado!")
            
            # Filtrado de resultados
            df_asignados = df[~df['ESCENARIO_ASIGNADO'].isin(['SIN ASIGNAR (HUÉRFANO)', 'SIN DEMANDA'])]
            df_huerfanos = df[df['ESCENARIO_ASIGNADO'] == 'SIN ASIGNAR (HUÉRFANO)']
            
            total_pedidos = len(df)
            total_asignados = len(df_asignados)
            eficiencia = (total_asignados / total_pedidos) * 100 if total_pedidos > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            col1.metric(label="Eficiencia de Cobertura", value=f"{eficiencia:.2f}%")
            col2.metric(label="Registros Abastecidos", value=f"{total_asignados}")
            col3.metric(label="Registros Huérfanos", value=f"{len(df_huerfanos)}")
            
            # --- 5. DESCARGA DE REPORTE INTEGRADO ---
            st.subheader("📥 Descarga de Resultados")
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ Descargar Reporte de Asignación Completo",
                data=csv_data,
                file_name="REPORTE_ASIGNACION_PROCESADO.csv",
                mime="text/csv"
            )
            
            # Vista previa
            st.subheader("🔍 Vista Previa del Reporte Procesado")
            columnas_vista = [col_demanda, 'INV', 'PLAN_INS_DIA1', 'PLAN_INSIDE', 'CANTIDAD_ASIGNADA', 'ESCENARIO_ASIGNADO']
            st.dataframe(df[columnas_vista].head(50))
else:
    st.info("💡 Por favor, sube tu archivo CSV en la barra lateral que contenga las columnas de demanda e inventario/planes juntas.")
