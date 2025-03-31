import zipfile
import xml.etree.ElementTree as ET
from typing import Union, IO

# Namespace dictionary for XML parsing
W_NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def docx_to_xml(docx_source: Union[str, IO[bytes]], output_xml_path: str = None) -> str:
    """
    Extracts the main document XML from a .docx file or file-like object.

    Parameters:
        docx_source (Union[str, IO[bytes]]): Path to the .docx file or a file-like object containing the docx data.
        output_xml_path (str, optional): If provided, writes the XML to this file. Requires docx_source to be a path if used.

    Returns:
        str: The XML content of word/document.xml as a UTF-8 string.
    """
    try:
        with zipfile.ZipFile(docx_source, 'r') as docx_zip:
            xml_content = docx_zip.read('word/document.xml')
    except Exception as e:
        raise ValueError(f"Could not process docx_source: {e}") from e

    # Optionally, write the XML content to an output file
    if output_xml_path:
        if isinstance(docx_source, str): # Can only write if we have an output path
             with open(output_xml_path, 'wb') as f:
                f.write(xml_content)
        else:
            print("Warning: output_xml_path specified, but docx_source is not a file path. Cannot write XML to file.")


    return xml_content.decode('utf-8')


def check_consent_from_docx(docx_source: Union[str, IO[bytes]]) -> str:
    """
    Checks for a specific consent text within the XML structure of a DOCX file.

    Parameters:
        docx_source (Union[str, IO[bytes]]): Path to the .docx file or a file-like object containing the docx data.

    Returns:
        str: "SI" if consent text is found, "NO" otherwise.
    """
    try:
        with zipfile.ZipFile(docx_source, 'r') as docx_zip:
            xml_content = docx_zip.read('word/document.xml')
        root = ET.fromstring(xml_content)
    except Exception as e:
        print(f"Error reading or parsing XML from docx_source: {e}")
        return "NO" # Or raise an error, depending on desired behavior

    consent_text = "Consiento expresamente y autorizo la cesión de mis datos médicos a mi Entidad Aseguradora para la valoración del daño corporal."

    for paragraph in root.findall('.//w:p', W_NS):
        para_text = "".join(node.text for node in paragraph.findall('.//w:t', W_NS) if node.text)
        if consent_text in para_text:
            # Check for a checked checkbox (w:val="1") within the same paragraph or related structure
            # This simplified check looks for any checked box in the paragraph, adjust if more specific logic is needed
            for checkbox in paragraph.findall('.//w:checkBox', W_NS):
                val_element = checkbox.find('.//w:val', W_NS)
                if val_element is not None and val_element.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') == "1":
                    return "SI"
            # Fallback check if checkbox structure might differ (e.g., legacy checkbox)
            for legacy_checkbox in paragraph.findall('.//w:ffData', W_NS):
                 checked_element = legacy_checkbox.find('.//w:checked', W_NS)
                 if checked_element is not None and checked_element.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', "0") == "1": # Default to "0" if val attribute is missing
                     return "SI"


    return "NO"


def check_proxima_visita_checkbox(docx_source: Union[str, IO[bytes]]) -> list[str]:
    """
    Checks checkboxes associated with "Próxima visita" entries in a DOCX file.

    Parameters:
        docx_source (Union[str, IO[bytes]]): Path to the .docx file or a file-like object containing the docx data.

    Returns:
        list[str]: A list of "SI" or "NO" strings corresponding to each found "Próxima visita".
                   Returns an empty list if no "Próxima visita" sections are found or if there's an error.
    """
    results = []
    try:
        with zipfile.ZipFile(docx_source, 'r') as docx_zip:
            xml_content = docx_zip.read('word/document.xml')
        root = ET.fromstring(xml_content)
    except Exception as e:
        print(f"Error reading or parsing XML from docx_source: {e}")
        return [] # Return empty list on error

    # Flag to indicate if we are inside a potential "Próxima visita" section
    in_proxima_visita_section = False
    # Track paragraphs belonging to the current section
    current_section_paragraphs = []

    for element in root.find('.//w:body', W_NS):
        # Check paragraphs for the trigger text
        if element.tag == f'{{{W_NS["w"]}}}p':
            para_text = "".join(node.text for node in element.findall('.//w:t', W_NS) if node.text).strip()

            # Check if this paragraph marks the start of a relevant section
            if "Próxima visita" in para_text:
                # Process the previous section before starting a new one
                if in_proxima_visita_section:
                     results.append(_process_proxima_visita_section(current_section_paragraphs))

                # Start a new section
                in_proxima_visita_section = True
                current_section_paragraphs = [element] # Start with the current paragraph
            elif in_proxima_visita_section:
                 # If we are already in a section, add the paragraph to it
                 current_section_paragraphs.append(element)
                 # Define stop conditions (e.g., encountering another specific heading or a table)
                 # Example: Stop if we hit "Aclaraciones:" or "Solicitud para la autorización"
                 if "Aclaraciones:" in para_text or "Solicitud para la autorización" in para_text:
                     results.append(_process_proxima_visita_section(current_section_paragraphs))
                     in_proxima_visita_section = False
                     current_section_paragraphs = []


        # Check tables as potential section terminators or if they contain relevant info
        elif element.tag == f'{{{W_NS["w"]}}}tbl':
             if in_proxima_visita_section:
                 # Decide if a table terminates the section
                 # For now, let's assume it does, process the paragraphs collected so far
                 results.append(_process_proxima_visita_section(current_section_paragraphs))
                 in_proxima_visita_section = False
                 current_section_paragraphs = []
        # Add checks for other element types (like sdt for content controls) if needed

    # Process the last section if the document ends while still in a section
    if in_proxima_visita_section:
         results.append(_process_proxima_visita_section(current_section_paragraphs))


    # If no "Próxima visita" sections were explicitly found and processed,
    # perform a fallback check across the whole document for any checked box
    # near "Próxima visita". This is less precise.
    if not results:
         checked_found_anywhere = False
         for paragraph in root.findall('.//w:p', W_NS):
            para_text = "".join(node.text for node in paragraph.findall('.//w:t', W_NS) if node.text).strip()
            if "Próxima visita" in para_text:
                 # Checkbox check logic (simplified) - may need refinement based on actual structure
                 for checkbox in paragraph.findall('.//w:checkBox', W_NS):
                     val_element = checkbox.find('.//w:val', W_NS)
                     if val_element is not None and val_element.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') == "1":
                         checked_found_anywhere = True
                         break
                 if checked_found_anywhere: break

                 for legacy_checkbox in paragraph.findall('.//w:ffData', W_NS):
                    checked_element = legacy_checkbox.find('.//w:checked', W_NS)
                    if checked_element is not None and checked_element.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', "0") == "1":
                         checked_found_anywhere = True
                         break
                 if checked_found_anywhere: break

         # If only one vague check was done, return a single result
         # This part might need adjustment based on how many "Próxima visita" are expected even without clear sectioning
         if checked_found_anywhere:
              # Heuristic: If we found a check somewhere near the text, but didn't parse sections,
              # return one "SI". This assumes there's likely only one relevant checkbox if sections aren't clear.
              # Adjust this logic if multiple independent "Próxima visita" checkboxes can exist without clear sections.
               return ["SI"]
              # If you expect potentially multiple visits even without clear sections, this fallback is ambiguous.
              # Consider returning [] or raising a warning/error if sections aren't found but checks are.


    return results if results else []


def _process_proxima_visita_section(paragraphs: list) -> str:
    """
    Helper function to check for a checked checkbox within a list of paragraph elements.
    """
    for paragraph in paragraphs:
        # Check for modern checkboxes
        for checkbox in paragraph.findall('.//w:checkBox', W_NS):
            val_element = checkbox.find('.//w:val', W_NS)
            if val_element is not None and val_element.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') == "1":
                return "SI"
        # Check for legacy checkboxes
        for legacy_checkbox in paragraph.findall('.//w:ffData', W_NS):
            checked_element = legacy_checkbox.find('.//w:checked', W_NS)
            if checked_element is not None and checked_element.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', "0") == "1":
                return "SI"
    return "NO"


# Example usage:
if __name__ == '__main__':
    # Assume xml_output contains your document's XML (from the docx_to_xml function)
    docx_path = "/Users/alejandrodelacruz/Work/personal/upwork_process_docx/data/46430.1 surname surname1 namex (Allianz).docx"


    # Example with file path
    print("--- Processing with file path ---")
    consent_status = check_consent_from_docx(docx_path)
    print(f"Consent Status: {consent_status}")
    visit_results = check_proxima_visita_checkbox(docx_path)
    print("Próxima visita results:", visit_results)

    # Example with file-like object
    print("\n--- Processing with file-like object ---")
    try:
        with open(docx_path, "rb") as f:
            # Pass the file handle directly
            consent_status_f = check_consent_from_docx(f)
            print(f"Consent Status (from file object): {consent_status_f}")
            # Important: Need to reset the file pointer if reading again from the same handle
            f.seek(0)
            visit_results_f = check_proxima_visita_checkbox(f)
            print("Próxima visita results (from file object):", visit_results_f)
            f.seek(0)
            xml_data = docx_to_xml(f)
            # print("XML Data Snippet:", xml_data[:500]) # Print first 500 chars
    except FileNotFoundError:
        print(f"Error: File not found at {docx_path}")
    except Exception as e:
        print(f"An error occurred: {e}")
