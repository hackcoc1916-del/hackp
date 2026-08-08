import os

demo_dir = os.path.join("..", "demo_evidence")
os.makedirs(demo_dir, exist_ok=True)

# 1. Corrupted PDF
with open(os.path.join(demo_dir, "corrupted_financials.pdf"), "wb") as f:
    f.write(b"This is not a valid PDF file. It simulates a corrupted or encrypted document.")

# 2. Corrupted Image
with open(os.path.join(demo_dir, "blurry_suspect.jpg"), "wb") as f:
    f.write(os.urandom(1024)) # random noise

# 3. Corrupted Audio
with open(os.path.join(demo_dir, "wiretap_snippet.mp3"), "wb") as f:
    f.write(os.urandom(2048))

print("Created demo evidence files in 'demo_evidence' folder.")
