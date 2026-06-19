import zipfile
import xml.etree.ElementTree as ET

def extract_docx_text(docx_path):
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml_content = z.read('word/document.xml')
            root = ET.fromstring(xml_content)
            
            # Namespaces
            namespaces = {
                'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
            }
            
            # Find all paragraphs
            paragraphs = []
            for paragraph in root.findall('.//w:p', namespaces):
                texts = []
                for run in paragraph.findall('.//w:r', namespaces):
                    text_node = run.find('w:t', namespaces)
                    if text_node is not None and text_node.text:
                        texts.append(text_node.text)
                if texts:
                    paragraphs.append("".join(texts))
            return "\n\n".join(paragraphs)
    except Exception as e:
        return f"Error: {e}"

if __name__ == '__main__':
    import os
    docx_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ConfigSync_Documentation (1).docx')
    print("Extracting text from:", docx_file)
    text = extract_docx_text(docx_file)
    with open('extracted_docx_content.txt', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Extraction completed! Saved to extracted_docx_content.txt.")
