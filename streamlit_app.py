import streamlit as st
import pandas as pd
import io
import os
from mistralai import Mistral
import tempfile

# Make sure docx_processor and parse_xml are in the same directory or accessible in PYTHONPATH
from docx_processor import WordProcessor
from parse_xml import check_consent_from_docx, check_proxima_visita_checkbox

# --- PDF Processing Functions (Adapted from your script) ---

# Get API key (Use st.secrets for deployment)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
# You might want to use st.secrets["MISTRAL_API_KEY"] when deploying
# if not MISTRAL_API_KEY:
#     st.error("MISTRAL_API_KEY environment variable not set.")
#     # Or use st.stop() if the app can't function without it

# Initialize Mistral client (consider initializing only when needed)
# client = Mistral(api_key=MISTRAL_API_KEY) # Initialize later if key might be missing
model = "mistral-large-latest"
ocr_model = "mistral-ocr-latest"

# Define the functions directly here or import from a separate pdf_processor.py file
# (Functions upload_pdf, get_signed_url, get_ocr_result, get_pdf_markdown, get_final_result go here)
# Note: Modified get_final_result to return the text instead of writing to file.

def upload_pdf(client, file_name, file_content):
    """
    Upload a PDF file content to Mistral for OCR processing

    Args:
        client: The initialized Mistral client.
        file_name (str): The original name of the file.
        file_content (bytes): The byte content of the file.

    Returns:
        UploadFileOut: Response from Mistral file upload
    """
    try:
        # Use BytesIO to treat bytes as a file-like object
        # file_like_object = io.BytesIO(file_content) # No longer needed
        uploaded_pdf = client.files.upload(
            file={
                "file_name": file_name,
                # Pass the raw bytes directly
                "content": file_content,
            },
            purpose="ocr"
        )
        return uploaded_pdf
    except Exception as e:
        # Add more detail to the error message if possible
        st.error(f"Error al subir archivo a Mistral: {e}")
        # Consider logging the full exception details for debugging
        # import traceback
        # st.error(traceback.format_exc())
        return None

def get_signed_url(client, file_id):
    """ Get a signed URL for a file from Mistral """
    try:
        signed_url = client.files.get_signed_url(file_id=file_id)
        return signed_url
    except Exception as e:
        st.error(f"Error al obtener URL firmada de Mistral: {e}")
        return None

def get_ocr_result(client, document_url):
    """ Get OCR results from Mistral """
    try:
        ocr_response = client.ocr.process(
            model=ocr_model, # Use defined variable
            document={
                "type": "document_url",
                "document_url": document_url,
            }
        )
        return ocr_response
    except Exception as e:
        st.error(f"Error al procesar OCR con Mistral: {e}")
        return None

def get_pdf_markdown(client, file_name, file_content):
    """Processes PDF bytes to get markdown content via Mistral OCR."""
    uploaded_pdf = upload_pdf(client, file_name, file_content)
    if not uploaded_pdf: return None

    signed_url = get_signed_url(client, uploaded_pdf.id)
    if not signed_url: return None

    ocr_result = get_ocr_result(client, signed_url.url)
    if not ocr_result: return None

    try:
        # Access the model dump and join markdown pages
        ocr_data = ocr_result.model_dump()
        joined_markdown ="\n\n".join([page['markdown'] for page in ocr_data.get("pages", [])])
        return joined_markdown
    except Exception as e:
        st.error(f"Error al extraer markdown del resultado OCR: {e}")
        return None


def get_final_summary(client, summary_markdown):
    """Gets the final structured summary from Mistral based on markdown."""
    messages = [
         {"role": "system", "content": (
            "Eres un asistente encargado de extraer información de un texto en formato markdown."
            "Tu tarea es seguir las instrucciones que te doy a continuación para extraer los datos de manera precisa y sin inventar información.\n"
            "\n"
            "Consideraciones importantes:\n"
            "1. Si el resumen no tiene información para un apartado, usa 'No hay información'.\n"
            "2. Si algún valor entre corchetes se encuentra en el markdown, reemplázalo con la información correcta, si no existe, escribe N/A y modifica el texto para que tenga sentido.\n"
            "3. El formato de respuesta debe seguir exactamente el esquema que te proporciono. No alteres ni modifiques el formato, solo rellena los campos con la información extraída del markdown.\n"
            "4. Si hay datos de varias instancias o personas, incluye solo una si es común a todas ellas, en caso contrario, incluir todas ellas en una lista. Para ello, añade el apartado varias veces.\n"
            "5. Prioriza escribir el nombre del hospital o centro médico en lugar del nombre de la persona o entidad emisora en cada punto.\n"
            "6. En la resonancia magnética y rayos X, no asumir que es este tipo de exploración si no se escribe específicamente.\n"
            "\n"
            "Formato de respuesta:\n\n"
            "1. Parte al juzgado de guardia\n"
            "Resumen: Parte al juzgado de guardia emitido por {Nombre de la persona o entidad emisora} con fecha {Fecha de la parte}.\n"
            "2. Informe de alta de Urgencia\n"
            "Resumen: Informe de alta de Urgencias de {Nombre del hospital o institución} con fecha {Fecha del informe de alta}.\n"
            "Descripción: {Descripción extensa del informe de alta de Urgencia en lenguaje natural. Reemplazadas ibuprofeno, paracetamol y Ketazolam por 'medicación habitual'}\n"
            "3. Informe biomecánico\n"
            "Resumen: Informe biomecánico emitido por {Nombre de la institución o persona que emite el informe} con fecha {Fecha del informe}.\n"
            "Descripción: Por ingenieros se informa {Descripción extensa del informe biomecánico incluyendo velocidad de impacto, delta V y aceleración media y conclusiones.}\n"
            "4. Informe Médico de Seguimiento\n"
            "Resumen: Informe Médico de Seguimiento emitido por {Nombre de la persona o entidad} de fecha o fechas {Fecha(s) del informe de seguimiento}.\n"
            "Descripción: {Descripción resumida (2 o 3 frases largas) del seguimiento médico. Si hay varios días, incluye la fecha y descripción por cada uno.}\n"
            "5. Parte Médico de baja-alta\n"
            "Resumen: Parte Médico de baja-alta emitido por {Nombre del médico} de fechas {Fecha de baja} a {Fecha de alta}.\n"
            "Descripción: De baja por su médico del día {Fecha de baja} al {Fecha de alta}.\n"
            "6. Parte Médico de baja \n"
            "Resumen: Parte Médico de baja emitido por {Nombre del médico} de fecha {Fecha de baja}.\n"
            "Descripción: De baja por su médico desde el día {Fecha de baja}.\n"
            "7. Estudio de resonancia magnética (RMN)\n"
            "Resumen: Estudio de RMN de {zona del cuerpo} realizado por {Incluir nombre del médico o hospital y fecha del estudio si existen, sino poner N/A}.\n"
            "Descripción: {Descripción extensa del estudio de resonancia magnética}\n"
            "8. Estudio de rayos X (RX)\n"
            "Resumen: Estudio de RX de {zona del cuerpo} realizado por {Incluir nombre del médico o hospital y fecha del estudio si existen, sino poner N/A}.\n"
            "Descripción: {Descripción extensa del estudio de rayos X}\n"
            "9. Certificado de asistencia a rehabilitación\n"
            "Resumen: Certificado de asistencia a rehabilitación de {Fecha de inicio} a {Fecha de finalización si existe, sino poner N/A}.\n"
            "Descripción: Acredita {Número de sesiones. Dejar en blanco si el numero no existe} sesiones de rehabilitación realizadas desde el {Fecha de inicio} hasta el {Fecha de finalización si existe, sino poner N/A}.\n"
            "10. Informe médico-pericial\n"
            "Resumen: Informe médico-pericial emitido por {Nombre de la persona o entidad emisora} de fecha {Fecha del informe}.\n"
            "Descripción: Por médico perito / forense {Nombre del perito o forense} se indica que ha curado de una {lesión y descripción de la lesión} en {número de días} días de los cuales {número de días de perjuicio moderado} fueron de perjuicio personal moderado y {número de días de perjuicio básico} días de perjuicio personal básico, valorando a su vez las secuelas: {lista de secuelas en bullet points con la valoración de cada una con puntos}.\n"
            "11. Resolución de INNSS\n"
            "Resumen: Resolución de INNSS de fecha {Fecha de la resolución}.\n"
            "12. Hoja de anamnesis\n"
            "Resumen: Hoja de anamnesis de {tipo de hoja de anamnesis} de fecha {Fecha de la anamnesis}.\n"
            "\n\n"
        )},
        {"role": "user", "content": f"Contenido del markdown: {summary_markdown}"}
    ]

    try:
        # Get response from Mistral
        chat_response = client.chat.complete(
            model=model, # Use defined variable
            messages=messages,
            temperature=0.0
        )
        answer = chat_response.choices[0].message.content
        return answer
    except Exception as e:
        st.error(f"Error al obtener resumen de Mistral: {e}")
        return None

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("Procesador de Documentos")

# --- Create Tabs ---
tab1, tab2 = st.tabs(["Procesador de Informes DOCX", "Resumidor de PDF"])

# --- DOCX Processor Tab ---
with tab1:
    st.header("Procesar Archivo DOCX")
    uploaded_docx_file = st.file_uploader("Selecciona un archivo .docx", type="docx", key="docx_uploader")

    if uploaded_docx_file is not None:
        # To read the file content into memory
        file_bytes_docx = uploaded_docx_file.getvalue()
        original_filename_docx = uploaded_docx_file.name

        # Use BytesIO to treat the bytes as a file for processing
        docx_file_like_object_processor = io.BytesIO(file_bytes_docx)
        docx_file_like_object_xml = io.BytesIO(file_bytes_docx) # Create a second one for XML functions

        st.write(f"Procesando DOCX: {original_filename_docx}")

        try:
            # --- Process the DOCX file ---
            doc = WordProcessor(docx_file_like_object_processor)

            # --- Get additional data from XML ---
            perdida_c_vida = check_consent_from_docx(docx_file_like_object_xml)
            docx_file_like_object_xml.seek(0) # Reset stream position
            proxima_visita_list = check_proxima_visita_checkbox(docx_file_like_object_xml)

            # --- Get Doc Number from filename ---
            doc_number = "N/A"
            if original_filename_docx:
                doc_number = os.path.basename(original_filename_docx).split(" ")[0]

            # --- Combine DataFrames ---
            visits = [doc.first_medical_visit] + doc.next_medical_visits
            combined_visits_list = []

            num_visits = len(visits)
            if len(proxima_visita_list) < num_visits:
                proxima_visita_list.extend(['NO'] * (num_visits - len(proxima_visita_list)))
            elif len(proxima_visita_list) > num_visits:
                st.warning(f"Se encontraron {len(proxima_visita_list)} resultados de casilla 'Próxima visita' pero {num_visits} visitas analizadas. Usando resultados para las primeras {num_visits} visitas.")
                proxima_visita_list = proxima_visita_list[:num_visits]

            base_df = doc.df.reset_index(drop=True)
            if base_df.empty:
                 st.error("No se pudo extraer información base (Compañia, fechas, etc.). Verifica la estructura de la tabla 1.")

            for i, visit_df in enumerate(visits):
                if visit_df is None or visit_df.empty:
                    st.warning(f"Los datos de la visita {i+1} faltan o están vacíos. Omitiendo.")
                    continue

                current_base_df = base_df.iloc[[0]] if not base_df.empty else pd.DataFrame()
                combined = pd.concat([current_base_df, visit_df.reset_index(drop=True)], axis=1)

                combined['Pérdida c vida'] = perdida_c_vida
                combined['Proxima visita'] = proxima_visita_list[i] if i < len(proxima_visita_list) else 'NO'
                combined['Numero de documento'] = doc_number
                combined_visits_list.append(combined)

            if combined_visits_list:
                all_doc_visits_combined = [df.loc[:, ~df.columns.duplicated()] for df in combined_visits_list]

                all_columns = pd.Index([])
                for df in all_doc_visits_combined:
                    all_columns = all_columns.union(df.columns)

                final_list = [df.reindex(columns=all_columns) for df in all_doc_visits_combined]
                final_df = pd.concat(final_list, ignore_index=True)

                # --- Define desired columns and rename mapping ---
                desired_columns = [
                    "Compañía", "Fecha siniestro", "Hora", "Lugar de la visita", "Fecha visita",
                    "Nombre y apellidos", "Condición", "Domicilio", "NIF", "Población",
                    "Teléfono (FyM)", "C.P.", "Edad", "Fecha nacimiento", "Provincia", "Sexo",
                    "Lateralidad", "Profesión", "Nivel s.e.", "Puesto de trabajo / ocupación",
                    "Deportes", "Situación laboral en el momento del accidente", "Actividades de ocio",
                    "Mail", "Protección", "¿Agravación por no uso protección?", "Estado civil",
                    "Nº de Hijos", "Menores", "Miembros unidad familiar", "<18 años", ">18 años",
                    "Miembros discapacitados", "Ama de casa", "Total", "Parcial",
                    "Antecedentes médicos del lesionado", "Descripción del accidente", "Tipo",
                    "Fecha ingreso", "Fecha alta", "Nº Historial Clínico", "Códigos", "Diagnóstico",
                    "Tratamiento y evolución - processed", "HISTORIA ACTUAL", "EXPLORACION FISICA",
                    "Pruebas complementarias", "Relación de causalidad", "Cronológico", "Topográfico",
                    "Intensidad", "Continuidad evolutiva", "Exclusión", "Lesiones muy graves", "Lesiones graves",
                    "Lesiones moderados", "Lesiones basicos",
                    "Fecha alta",
                    "Motivos variacion fecha final",
                    "Prevista", "Definitiva",
                    "Intervenciones quirúrgicas", "Patrimonial. Daño emergente (se indemniza su importe)",
                    "Codigo Secuela", "Descripción secuela", "analogía secuela", "rango secuela",
                    "prev/defin secuela", "puntuación secuela",
                    "Valoración Total Secuelas", "Motivos variación", "DM psicofisico", "DM estético",
                    "Pérdida c vida", "DMxperd c vida", "Pérdida feto", "P excepcional",
                    "Asis sanit futur", "Protesis/ortesis", "RHB dom/amb", "Ayuda técnica",
                    "Coste movilidad", "Tercera persona", "Descripción de las necesidades",
                    "Adecuación de vehículo", "Adecuación de vivienda",
                    "Nombre abogado", "Telefono abogado",
                    "Actitud frente a la compañía", "Posibilidad transacción", "Precisa investigador",
                    "Consentimiento informado", "Aclaraciones", "Medio de transporte", "Hasta",
                    "Otros", "Seguimiento", "Final", "Final Definitivo", "Fecha", "Próxima visita"
                ]

                # Mapping from ORIGINAL names in docx_processor DataFrames to FINAL names in desired_columns
                column_rename_map = {
                    # Table 1 & common fields (likely no renames needed, match desired_columns)
                    "Teléfono": "Teléfono (FyM)", # Assuming Teléfono from table 1 is this one
                    "Códigos Diagnóstico": "Códigos",
                    "Lesiones muy graves": "Muy graves",
                    "Lesiones graves": "Graves",
                    "Lesiones moderados": "Moderados",
                    "Lesiones basicos": "Básicos",
                    "Motivos variación de fecha inicial": "Motivos variacion fecha final",
                    "Motivos variacion fecha final": "Motivos variación de fecha inicial",
                    "Codigo Secuela": "Código",
                    "analogía secuela": "Analogía",
                    "rango secuela": "Rango",
                    "prev/defin secuela": "Prev./Defin.",
                    "puntuación secuela": "Puntuación",
                    "Descripción secuela": "Descripción secuela",
                    "Descripción de las necesidades": "Descripción de las necesidades",
                    "Descripción del accidente": "Descripción del accidente",
                    
                    

                    # Table 4 fields (likely no renames needed)

                    # Table 6 fields (First Medical Visit) - Use names defined in populate_first_medical_visit_dataframe
                    # "Muy graves": "Lesiones muy graves", # Already handled by docx_processor mapping
                    # "Graves": "Lesiones graves",
                    # "Moderados": "Lesiones moderados",
                    # "Básicos": "Lesiones basicos",
                    # "Fecha alta": "Fecha alta", # Keep this name, it's distinct from table 4's Fecha alta
                    # "Motivos variación de fecha inicial": "Motivos variacion fecha final",

                    # Table 7 fields (Secuelas) - Use names defined in populate_first_medical_visit_dataframe
                    # "Código": "Codigo Secuela",
                    # "Descripción secuela": "Descripción secuela",
                    # "Analogía": "analogía secuela",
                    # "Rango": "rango secuela",
                    # "Prev./Defin.": "prev/defin secuela",
                    # "Puntuación": "puntuación secuela",

                    # Table 8 fields (Economic Damage - 'Patrimonial...') - Check docx_processor for exact names if needed

                    # Table 9 fields (Lawyer) - Use names defined in populate_first_medical_visit_dataframe
                    # "Nombre abogado": "Nombre abogado",
                    # "Teléfono": "Telefono abogado", # Need to distinguish lawyer phone

                    # Table 10 fields (Visit details)
                    "Tratamiento y evolución. Exploraciones complementarias": "Tratamiento y evolución - processed",
                    # "HISTORIA ACTUAL", "EXPLORACION FISICA", "Pruebas complementarias" - likely match desired_columns

                    # Table 11 fields (Causality) - likely match desired_columns

                    # Table 12 fields (Company Attitude) - likely match desired_columns

                    # Fields added manually/from XML
                    # 'Pérdida c vida' - matches
                    # 'Proxima visita' - matches
                    # 'Numero de documento' - matches
                }

                # --- Rename columns based on the map ---
                # Make sure renames happen *before* adding missing columns
                final_df.rename(columns=column_rename_map, inplace=True, errors='ignore') # Ignore errors if a column to rename isn't found

                # --- Ensure all desired columns exist, add missing ones with "" ---
                for col in desired_columns:
                    if col not in final_df.columns:
                        final_df[col] = "" # Add missing column filled with empty strings

                # --- Reindex to keep only desired columns in the specified order ---
                # This ensures the final_df has the correct structure BEFORE transposing
                final_df = final_df[desired_columns]

                # --- Transpose the final DataFrame ---
                # Apply .T to swap rows and columns
                try:
                    final_df_transposed = final_df.T
                    # If there were multiple visits (rows) in final_df,
                    # the columns in final_df_transposed will be 0, 1, 2...
                    # You could rename them if desired:
                    # final_df_transposed.columns = [f"Visit_{i+1}" for i in range(len(final_df_transposed.columns))]

                    st.write("### Datos DOCX Procesados")
                    # Display the transposed DataFrame
                    st.dataframe(final_df_transposed)

                    # --- Prepare Excel download ---
                    output_excel = io.BytesIO()
                    with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                        # Write the TRANSPOSED DataFrame to Excel
                        # index=True includes the original column names (now the index)
                        final_df_transposed.to_excel(writer, index=True, sheet_name='Datos Procesados Transpuestos')
                    excel_data = output_excel.getvalue()

                    output_filename_excel = f"procesado_transpuesto_{os.path.splitext(original_filename_docx)[0]}.xlsx"

                    st.download_button(
                        label="📥 Descargar Resultados DOCX (Excel)", # Label indicates transposed data
                        data=excel_data,
                        file_name=output_filename_excel, # Filename indicates transposed data
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                except Exception as transpose_error:
                    st.error(f"Ocurrió un error durante la transposición: {transpose_error}")
                    st.write("Mostrando datos originales (no transpuestos) en su lugar.")
                    st.dataframe(final_df) # Fallback to showing original if transpose fails

            else:
                 st.warning("No se pudieron procesar datos de visitas para este documento DOCX.")

        except Exception as e:
            st.error(f"Ocurrió un error durante el procesamiento DOCX: {e}")
            # import traceback
            # st.exception(e) # Uncomment for detailed traceback

        finally:
            # Close the BytesIO objects
            docx_file_like_object_processor.close()
            docx_file_like_object_xml.close()

# --- PDF Summarizer Tab ---
with tab2:
    st.header("Resumir Archivo PDF usando Mistral AI")

    # Check for API Key before showing uploader
    if not MISTRAL_API_KEY:
        st.warning("⚠️ MISTRAL_API_KEY no está configurado. Por favor, configúralo como variable de entorno o secreto de Streamlit.")
        st.stop() # Stop execution in this tab if key is missing

    # Initialize client only if key exists
    try:
        client = Mistral(api_key=MISTRAL_API_KEY)
    except Exception as e:
        st.error(f"Error al inicializar el cliente Mistral: {e}")
        st.stop()


    uploaded_pdf_file = st.file_uploader("Selecciona un archivo .pdf", type="pdf", key="pdf_uploader")

    if uploaded_pdf_file is not None:
        pdf_bytes = uploaded_pdf_file.getvalue()
        pdf_filename = uploaded_pdf_file.name
        st.write(f"Procesando PDF: {pdf_filename}")

        with st.spinner("Extrayendo texto del PDF usando Mistral OCR..."):
            markdown_content = get_pdf_markdown(client, pdf_filename, pdf_bytes)

        if markdown_content:
            st.success("✅ Texto extraído correctamente.")
            # st.text_area("Extracted Markdown Content (from OCR)", markdown_content, height=200) # Optional: Show intermediate markdown

            with st.spinner("Generando resumen usando Mistral..."):
                final_summary = get_final_summary(client, markdown_content)

            if final_summary:
                st.success("✅ Resumen generado correctamente.")
                st.text_area("Resumen Generado", final_summary, height=400)

                # Prepare text download
                output_filename_txt = f"resumen_{os.path.splitext(pdf_filename)[0]}.txt"
                st.download_button(
                    label="📥 Descargar Resumen (TXT)",
                    data=final_summary.encode('utf-8'), # Encode summary to bytes
                    file_name=output_filename_txt,
                    mime="text/plain"
                )
            else:
                st.error("❌ Error al generar el resumen.")
        else:
            st.error("❌ Error al extraer texto del PDF.")
