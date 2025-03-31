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
        st.error(f"Error uploading file to Mistral: {e}")
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
        st.error(f"Error getting signed URL from Mistral: {e}")
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
        st.error(f"Error processing OCR with Mistral: {e}")
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
        st.error(f"Error extracting markdown from OCR result: {e}")
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
        st.error(f"Error getting summary from Mistral: {e}")
        return None

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("Document Processor")

# --- Create Tabs ---
tab1, tab2 = st.tabs(["DOCX Report Processor", "PDF Summarizer"])

# --- DOCX Processor Tab ---
with tab1:
    st.header("Process DOCX File")
    uploaded_docx_file = st.file_uploader("Choose a .docx file", type="docx", key="docx_uploader")

    if uploaded_docx_file is not None:
        # To read the file content into memory
        file_bytes_docx = uploaded_docx_file.getvalue()
        original_filename_docx = uploaded_docx_file.name

        # Use BytesIO to treat the bytes as a file for processing
        docx_file_like_object_processor = io.BytesIO(file_bytes_docx)
        docx_file_like_object_xml = io.BytesIO(file_bytes_docx) # Create a second one for XML functions

        st.write(f"Processing DOCX: {original_filename_docx}")

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
                st.warning(f"Found {len(proxima_visita_list)} 'Próxima visita' checkbox results but {num_visits} visits parsed. Using results for the first {num_visits} visits.")
                proxima_visita_list = proxima_visita_list[:num_visits]

            base_df = doc.df.reset_index(drop=True)
            if base_df.empty:
                 st.error("Could not extract base information (Compañia, fechas, etc.). Check table 1 structure.")

            for i, visit_df in enumerate(visits):
                if visit_df is None or visit_df.empty:
                    st.warning(f"Visit {i+1} data is missing or empty. Skipping.")
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

                st.write("### Processed DOCX Data Preview")
                st.dataframe(final_df)

                # --- Prepare Excel download ---
                output_excel = io.BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name='Processed Data')
                excel_data = output_excel.getvalue()

                output_filename_excel = f"processed_{os.path.splitext(original_filename_docx)[0]}.xlsx"

                st.download_button(
                    label="📥 Download DOCX Results (Excel)",
                    data=excel_data,
                    file_name=output_filename_excel,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                 st.warning("No visit data could be processed for this DOCX document.")

        except Exception as e:
            st.error(f"An error occurred during DOCX processing: {e}")
            # import traceback
            # st.exception(e) # Uncomment for detailed traceback

        finally:
            # Close the BytesIO objects
            docx_file_like_object_processor.close()
            docx_file_like_object_xml.close()

# --- PDF Summarizer Tab ---
with tab2:
    st.header("Summarize PDF File using Mistral AI")

    # Check for API Key before showing uploader
    if not MISTRAL_API_KEY:
        st.warning("⚠️ MISTRAL_API_KEY is not configured. Please set it as an environment variable or Streamlit secret.")
        st.stop() # Stop execution in this tab if key is missing

    # Initialize client only if key exists
    try:
        client = Mistral(api_key=MISTRAL_API_KEY)
    except Exception as e:
        st.error(f"Failed to initialize Mistral client: {e}")
        st.stop()


    uploaded_pdf_file = st.file_uploader("Choose a .pdf file", type="pdf", key="pdf_uploader")

    if uploaded_pdf_file is not None:
        pdf_bytes = uploaded_pdf_file.getvalue()
        pdf_filename = uploaded_pdf_file.name
        st.write(f"Processing PDF: {pdf_filename}")

        with st.spinner("Extracting text from PDF using Mistral OCR..."):
            markdown_content = get_pdf_markdown(client, pdf_filename, pdf_bytes)

        if markdown_content:
            st.success("✅ Text extracted successfully.")
            # st.text_area("Extracted Markdown Content (from OCR)", markdown_content, height=200) # Optional: Show intermediate markdown

            with st.spinner("Generating summary using Mistral..."):
                final_summary = get_final_summary(client, markdown_content)

            if final_summary:
                st.success("✅ Summary generated successfully.")
                st.text_area("Generated Summary", final_summary, height=400)

                # Prepare text download
                output_filename_txt = f"summary_{os.path.splitext(pdf_filename)[0]}.txt"
                st.download_button(
                    label="📥 Download Summary (TXT)",
                    data=final_summary.encode('utf-8'), # Encode summary to bytes
                    file_name=output_filename_txt,
                    mime="text/plain"
                )
            else:
                st.error("❌ Failed to generate summary.")
        else:
            st.error("❌ Failed to extract text from the PDF.")
