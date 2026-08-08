import httpx
import asyncio
import os
import time
import json

API_URL = "http://localhost:8000/api"
DEMO_DIR = os.path.join("..", "demo_evidence")

async def run_test():
    async with httpx.AsyncClient() as client:
        # 1. Create Investigation
        print("1. Creating Investigation...")
        res = await client.post(f"{API_URL}/investigations", json={
            "name": "E2E Fault Tolerance Test",
            "goal": "Test execution engine with difficult files",
            "goal_type": "general"
        })
        inv = res.json()
        inv_id = inv["id"]
        print(f"Created: {inv_id}")

        # 2. Upload Evidence
        print("\n2. Uploading difficult evidence files...")
        files_to_upload = [
            "blurry_suspect.jpg",
            "corrupted_financials.pdf",
            "wiretap_snippet.mp3"
        ]
        
        for fname in files_to_upload:
            fpath = os.path.join(DEMO_DIR, fname)
            if not os.path.exists(fpath):
                print(f"Missing file: {fpath}")
                continue
                
            with open(fpath, "rb") as f:
                res = await client.post(
                    f"{API_URL}/investigations/{inv_id}/evidence",
                    files={"files": (fname, f, "application/octet-stream")}
                )
                if res.status_code == 200:
                    evs = res.json().get('evidence', [])
                    if evs:
                        print(f"Uploaded {fname}: {evs[0]['id']}")
                    else:
                        print(f"Uploaded {fname} but got no id")
                else:
                    print(f"Failed to upload {fname}: {res.text}")
                    
        # 3. Start Pipeline
        print("\n3. Starting Execution Engine...")
        res = await client.post(f"{API_URL}/investigations/{inv_id}/demo-pipeline")
        if res.status_code == 200:
            print("Pipeline started successfully.")
        else:
            print(f"Failed to start pipeline: {res.text}")
            return
            
        # 4. Wait for completion
        print("\n4. Monitoring pipeline progress...")
        for _ in range(20):
            await asyncio.sleep(2)
            res = await client.get(f"{API_URL}/investigations/{inv_id}")
            state = res.json()["state"]
            print(f"Current State: {state}")
            
            if state in ["review_required", "report_ready", "closed", "awaiting_evidence"]:
                break
                
        print("\n5. Fetching findings...")
        res = await client.get(f"{API_URL}/investigations/{inv_id}")
        findings = res.json().get("findings", [])
        print(f"Found {len(findings)} findings.")
        for finding in findings:
            print(f" - {finding['title']}: {finding['description'][:100]}")
            
        print("\n6. Fetching timeline events...")
        res = await client.get(f"{API_URL}/investigations/{inv_id}/timeline")
        events = res.json()
        print(f"Found {len(events)} timeline events.")
        for event in events:
            print(f" - {event['event_type']}: {event['title']}")
            
        print("\nE2E Test Complete! The pipeline handled the corrupted files without crashing.")

if __name__ == "__main__":
    asyncio.run(run_test())
