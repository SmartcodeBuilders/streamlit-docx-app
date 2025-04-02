import zipfile
import xml.etree.ElementTree as ET

def docx_to_xml(docx_path, output_xml_path=None):
    """
    Extracts the main document XML from a .docx file.
    
    Parameters:
        docx_path (str): Path to the .docx file.
        output_xml_path (str, optional): If provided, writes the XML to this file.
        
    Returns:
        str: The XML content of word/document.xml as a UTF-8 string.
    """
    with zipfile.ZipFile(docx_path, 'r') as docx_zip:
        xml_content = docx_zip.read('word/document.xml')
    
    # Optionally, write the XML content to an output file
    if output_xml_path:
        with open(output_xml_path, 'wb') as f:
            f.write(xml_content)
    
    return xml_content.decode('utf-8')



def check_casilla9_state(xml_string):
    """
    Parses the XML string from a docx (e.g. from docx_to_xml())
    and checks all occurrences of a legacy form field named "Casilla9".
    
    The XML for a checkbox can be either:
    
      <w:ffData>
        <w:name w:val="Casilla9"/>
        <w:enabled/>
        <w:calcOnExit w:val="0"/>
        <w:checkBox>
          <w:sizeAuto/>
          <w:default w:val="0"/>
          <w:checked w:val="0"/>
        </w:checkBox>
      </w:ffData>
    
    or
    
      <w:ffData>
        <w:name w:val="Casilla9"/>
        <w:enabled/>
        <w:calcOnExit w:val="0"/>
        <w:checkBox>
          <w:sizeAuto/>
          <w:default w:val="0"/>
          <w:checked/>
        </w:checkBox>
      </w:ffData>
    
    The rule is:
      - If the first appearance of Casilla9 has a <w:checked> element
        with an attribute w:val="0", then return "NO".
      - If the second appearance is the one that has that (unchecked) value,
        then return "SI".
    
    Parameters:
        xml_string (str): The content of word/document.xml as a string.
    
    Returns:
        str: "NO" or "SI" depending on which occurrence shows w:checked w:val="0",
             or None if not found.
    """
    # Define the namespace (adjust if your XML uses a different prefix)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    
    root = ET.fromstring(xml_string)
    
    # Find all ffData elements that have a w:name with val="Casilla9"
    casilla9_fields = []
    for ffData in root.findall(".//w:ffData", ns):
        name_el = ffData.find("w:name", ns)
        if name_el is not None and name_el.attrib.get("{%s}val" % ns["w"]) == "Casilla9":
            casilla9_fields.append(ffData)
            
    
    # Process each occurrence in order.
    for idx, ffData in enumerate(casilla9_fields):
        checkBox = ffData.find("w:checkBox", ns)
        if checkBox is not None:
            checked = checkBox.find("w:checked", ns)
            if checked is not None:
                # Get the value if present; if not, it might be considered "checked" by default.
                val = checked.attrib.get("{%s}val" % ns["w"])
                # Our rule: if this <w:checked> explicitly has w:val="0",
                # then depending on whether it is the first or second occurrence,
                # we return "NO" or "SI".
                if val == "0":
                    if idx == 0:
                        return "SI"
                    elif idx == 1:
                        return "NO"
    return None


def check_consent_from_docx(docx_path):
    """
    Takes a docx file path and checks if consent is given by looking for "Consentimiento informado" text
    and checking if "Sí" or "No" is selected.
    
    Parameters:
        docx_path (str): Path to the .docx file
        
    Returns:
        str: "YES" if consent is given, "NO" if not given, None if unable to determine
    """ 
    
    xml_output = docx_to_xml(docx_path)
    result = check_casilla9_state(xml_output)
    return result


import xml.etree.ElementTree as ET

def check_proxima_visita_checkbox(docx_path):
    """
    Scans the XML for every occurrence of a <w:t> element containing
    "Próxima visita:" and then locates the next three <w:checkBox> elements.
    
    For each set of three checkboxes:
      - If the first checkbox is checked, append "Seguimiento".
      - If the second checkbox is checked, append "Final".
      - If the third checkbox is checked, append "Final definitive".
      
    A checkbox is considered checked if its <w:checkBox> element contains a 
    <w:checked> child element that is either empty (i.e. <w:checked/>) or has 
    an attribute (e.g., w:val) whose value is not "0". If the <w:checked> element 
    is absent, the checkbox is not checked.
    
    Parameters:
        xml_string (str): The XML content of word/document.xml as a string.
    
    Returns:
        list: A list of strings representing the visit type for each occurrence.
              For example: ["Seguimiento", "Final"]
    """
    xml_string = docx_to_xml(docx_path)
    
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ET.fromstring(xml_string)
    results = []
    
    # Create a list of all elements in document order.
    all_elements = list(root.iter())
    
    def checkbox_is_checked(checkbox_elem):
        """
        Determines if a given <w:checkBox> element is checked.
        It checks for the presence of a <w:checked> child element.
          - If the <w:checked> element is present:
              - If it has an attribute w:val and that attribute equals "0", then it is unchecked.
              - Otherwise, it is checked.
          - If the <w:checked> element is absent, the checkbox is considered not checked.
        """
        checked_elem = checkbox_elem.find("w:checked", ns)
        if checked_elem is None:
            return False
        val = checked_elem.attrib.get(f"{{{ns['w']}}}val")
        return not (val == "0")
    
    # Iterate over all elements to find <w:t> with "Próxima visita:"
    for idx, elem in enumerate(all_elements):
        if elem.tag == f"{{{ns['w']}}}t" and elem.text and elem.text.strip() == "Próxima visita:":
            # Found the marker; now look for the next three <w:checkBox> elements.
            checkboxes = []
            j = idx + 1
            while j < len(all_elements) and len(checkboxes) < 3:
                next_elem = all_elements[j]
                if next_elem.tag == f"{{{ns['w']}}}checkBox":
                    checkboxes.append(next_elem)
                j += 1
            
            # Ensure we have three checkboxes for this occurrence
            if len(checkboxes) < 3:
                continue
            
            # Determine which checkbox is checked
            if checkbox_is_checked(checkboxes[0]):
                results.append("Seguimiento")
            elif checkbox_is_checked(checkboxes[1]):
                results.append("Final")
            elif checkbox_is_checked(checkboxes[2]):
                results.append("Final definitive")
            else:
                # If none of the three is checked, you can choose to append None or skip.
                results.append(None)
    
    return results