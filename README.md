# WarehouseIQ — Agentic AI for Amazon Fulfillment Centers

> *"Nothing gets lost in the noise."*

Built for the **Amazon Nova AI Hackathon** #AmazonNova

---

## Overview

WarehouseIQ is a 5-agent agentic AI system built on LangGraph and Amazon Nova that analyzes Amazon Fulfillment Center operational data across 4,000+ records from shift debriefs, safety logs, QC inspections, and customer returns. It autonomously discovers cross-source causal patterns and delivers specific, evidence-backed root cause insights tied to exact warehouses, areas, equipment, and shifts.

---

## Amazon Nova Models Used

| Model | Role |
|-------|------|
| Amazon Nova Pro | Root Cause Agent — autonomous ReAct tool-calling loop |
| Amazon Nova Lite | Analysis Agent — record enrichment, sentiment, anomaly detection |
| Amazon Nova Sonic | Voice Agent — speech-to-speech supervisor Q&A |

---

## 5-Agent Pipeline
```
START → Ingestion → Analysis → Root Cause → Action → Voice → END
```

### 1. Ingestion Agent
Normalizes 4,000+ records from 4 data sources into a unified schema. Transcribes voice memos via Amazon Transcribe.

### 2. Analysis Agent — Nova Lite
Enriches every record with sentiment analysis, anomaly detection, and issue theme extraction.

### 3. Root Cause Agent — Nova Pro
Runs an autonomous ReAct tool-calling loop across 10 warehouse tools. Nova Pro decides which tools to call, sees results, and discovers causal chains like:
> *"21 fire hazards in WH-305 Packing Zone involving Pallet Jacks → 82 injuries → 320 days lost"*

### 4. Action Agent
Converts patterns into prioritized remediation plans with owners, deadlines, and measurable KPIs.

### 5. Voice Agent — Nova Sonic
Lets shift supervisors query findings verbally and receive spoken, evidence-backed answers in real time.

---

## Technology Stack

- **Backend:** Python, FastAPI, LangGraph, LangChain
- **Frontend:** Next.js, TypeScript, Tailwind CSS
- **AWS:** Amazon Bedrock, Amazon Transcribe, Amazon Polly, Amazon S3
- **Models:** Amazon Nova Pro, Nova Lite, Nova Sonic

---

## Setup & Running

### Prerequisites
- Python 3.10+ (3.12+ for Nova Sonic)
- Node.js 18+
- AWS account with Bedrock model access enabled in `us-east-1`
- AWS credentials configured via `aws configure`

### Enable Bedrock Models
AWS Console → Bedrock → Model Access → us-east-1 → Enable:
- Amazon Nova Pro
- Amazon Nova Lite
- Amazon Nova Sonic

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## Usage

1. Open `http://localhost:3000`
2. Upload the 4 warehouse data files (shift debriefs, safety logs, QC flags, customer returns)
3. Click **▶ RUN AGENTIC PIPELINE**
4. Explore: Overview → Patterns → Actions → Records → Voice AI

---

## Sample Results (3,003 Records)

- **601 injuries** identified across 5 warehouses, **1,837 days lost**
- **7 root cause patterns** including fire hazard concentration in WH-305 Packing Zone
- **Forklift collision clustering** in WH-203 Receiving Dock: 28 incidents, 73 injuries
- **83% QC failure rate** traced to specific warehouses and defect categories
- **3 prioritized action items** with 1-day, 7-day, and 30-day deadlines

---

## Project Structure
```
backend/
  main.py                  ← FastAPI + upload endpoints
  graph.py                 ← LangGraph StateGraph
  state.py                 ← WarehouseState TypedDict
  agents/
    ingestion_agent.py     ← Node 1
    analysis_agent.py      ← Node 2 (Nova Lite)
    root_cause_agent.py    ← Node 3 (Nova Pro ReAct)
    action_agent.py        ← Node 4
    voice_agent.py         ← Node 5 (Nova Sonic)
  tools/
    warehouse_tools.py     ← 10 LangChain tools
frontend/
  app/                     ← Next.js App Router
  components/tabs/         ← Overview, Patterns, Actions, Records, Voice AI
```

---

*Built for the Amazon Nova AI Hackathon · #AmazonNova*
