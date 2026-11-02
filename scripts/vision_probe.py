import urllib.request, json, base64, io, sys
from PIL import Image, ImageDraw

def make_challenge_png(kind="circle", color="red", text="42"):
    img = Image.new("RGB", (256, 256), color=(20, 30, 60))
    d = ImageDraw.Draw(img)
    col_map = {
        "red": (220, 30, 30),
        "green": (30, 200, 50),
        "blue": (40, 100, 240),
        "yellow": (240, 210, 30),
    }
    fill = col_map.get(color, (220, 30, 30))
    if kind == "circle":
        d.ellipse([70, 70, 186, 186], fill=fill, outline=(255, 255, 255), width=3)
    elif kind == "square":
        d.rectangle([70, 70, 186, 186], fill=fill, outline=(255, 255, 255), width=3)
    elif kind == "four_squares":
        # 4 distinct quadrants
        d.rectangle([30, 30, 110, 110], fill=(220, 30, 30))
        d.rectangle([146, 30, 226, 110], fill=(30, 200, 50))
        d.rectangle([30, 146, 110, 226], fill=(40, 100, 240))
        d.rectangle([146, 146, 226, 226], fill=(240, 210, 30))

    if text:
        d.text((80, 205), text, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    # Standard Base64 with padding
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def query_vision(b64_png, prompt, endpoint="http://127.0.0.1:8889/v1/chat/completions", model="DeepSeek-V4.1-Flash-TF"):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_png}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        "max_tokens": 512,
        "temperature": 0.0
    }
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "X-Priority": "high"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res["choices"][0]["message"]["content"]

def main():
    print("=== Running Synthetic Vision Challenge Probe ===")
    
    # Challenge 1: Shape & Color
    b64_c = make_challenge_png(kind="circle", color="red", text="TEST-CIRC")
    ans_c = query_vision(b64_c, "What geometric shape is in the center, and what color is it? Answer in format: Shape: <shape>, Color: <color>")
    print(f"[Challenge 1: Circle/Red]\n{ans_c}\n")

    # Challenge 2: Square & Green
    b64_s = make_challenge_png(kind="square", color="green", text="TEST-SQ")
    ans_s = query_vision(b64_s, "What geometric shape is in the center, and what color is it? Answer in format: Shape: <shape>, Color: <color>")
    print(f"[Challenge 2: Square/Green]\n{ans_s}\n")

    # Challenge 3: Four Quadrants Count
    b64_4 = make_challenge_png(kind="four_squares", text="")
    ans_4 = query_vision(b64_4, "How many colored squares/boxes are shown in this image? Reply with only the number.")
    print(f"[Challenge 3: Count Quadrants]\n{ans_4}\n")

    # Challenge 4: OCR Specific Token
    b64_ocr = make_challenge_png(kind="circle", color="blue", text="INVOICE-8899")
    ans_ocr = query_vision(b64_ocr, "What exact text is written at the bottom of the image? Reply with only the text.")
    print(f"[Challenge 4: OCR]\n{ans_ocr}\n")

if __name__ == "__main__":
    main()
