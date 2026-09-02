from PIL import Image
import pytesseract

# Tell pytesseract where Tesseract is installed
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Open image
image = Image.open("test.png")

# OCR
text = pytesseract.image_to_string(image)

print("===== OCR RESULT =====")
print(text)