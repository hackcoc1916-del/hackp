import asyncio
import os
from models import EvidenceItem
from pdf_agent import PdfAgent
from image_agent import ImageAgent
from vehicle_agent import VehicleAgent
from audio_agent import AudioAgent

async def test_pdf_agent():
    print("Testing PDF Agent with a missing file...")
    agent = PdfAgent()
    ev = EvidenceItem(id="ev_missing_pdf", filename="missing.pdf", file_path="does_not_exist.pdf", mime_type="application/pdf", file_size=100)
    try:
        res = await agent.analyze(ev)
        print("PDF Agent Result:", res)
    except Exception as e:
        print("PDF Agent Crashed:", e)

    print("Testing PDF Agent with a corrupted file...")
    with open("corrupted.pdf", "wb") as f:
        f.write(b"not a real pdf file")
    ev2 = EvidenceItem(id="ev_corr_pdf", filename="corrupted.pdf", file_path="corrupted.pdf", mime_type="application/pdf", file_size=100)
    try:
        res = await agent.analyze(ev2)
        print("PDF Agent Result (corrupted):", res)
    except Exception as e:
        print("PDF Agent Crashed (corrupted):", e)


async def test_image_agent():
    print("Testing Image Agent with corrupted image...")
    with open("corrupted.jpg", "wb") as f:
        f.write(b"corrupted binary data")
    agent = ImageAgent()
    ev = EvidenceItem(id="ev_img", filename="corrupted.jpg", file_path="corrupted.jpg", mime_type="image/jpeg", file_size=100)
    try:
        res = await agent.analyze(ev)
        print("Image Agent Result:", res)
    except Exception as e:
        print("Image Agent Crashed:", e)


async def main():
    await test_pdf_agent()
    await test_image_agent()

if __name__ == "__main__":
    asyncio.run(main())
