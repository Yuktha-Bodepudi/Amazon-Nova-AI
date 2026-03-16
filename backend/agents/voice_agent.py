"""
WarehouseIQ — Voice Agent Node
LangGraph node: updates voice context after pipeline completes.
At query-time: uses LangChain message history for multi-turn conversations
with Amazon Nova Sonic (speech-to-speech) or Nova Pro (text fallback).

The message history uses LangGraph's add_messages reducer — state
accumulates turns without needing to manage it manually.
"""

import json, base64, boto3
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from state import WarehouseState


def _nova_pro() -> ChatBedrockConverse:
    return ChatBedrockConverse(
        model="amazon.nova-pro-v1:0",
        region_name="us-east-1",
        max_tokens=250,
        temperature=0.5,
    )


def _build_system(state: WarehouseState) -> str:
    s = state.get("stats", {})
    patterns = state.get("patterns", [])[:3]
    actions  = state.get("action_items", [])[:2]
    ctx = {
        "injuries":      s.get("safety",{}).get("injuries"),
        "qc_fail_pct":   s.get("qc",{}).get("fail_rate_pct"),
        "defect_ret_pct":s.get("returns",{}).get("defect_rate_pct"),
        "top_patterns":  [p.get("title") for p in patterns],
        "top_actions":   [a.get("title") for a in actions],
        "total_records": s.get("total_records"),
    }
    return (
        "You are WarehouseIQ, an AI assistant for Amazon Fulfillment Center supervisors. "
        f"You have analyzed {s.get('total_records',4000):,} records across "
        "shift reports, safety logs, QC inspections, and customer returns. "
        "Answer in 2-3 sentences maximum — this is a voice interface. Be direct and specific. "
        f"Current context: {json.dumps(ctx, separators=(',',':'))}"
    )


# ── LangGraph Node — runs once at end of pipeline to set context ───────────────

def voice_node(state: WarehouseState) -> dict:
    """
    LangGraph node: marks voice agent as ready, adds briefing to message history.
    The heavy lifting (Q&A) happens at query time via query_voice().
    """
    briefing = state.get("voice_briefing","")
    print(f"\n[Voice Agent] Context loaded — {state.get('stats',{}).get('total_records',0):,} records")

    return {
        "current_step": "voice",
        "progress":     95,
        "complete":     True,
        "messages":     [
            SystemMessage(content=_build_system(state)),
            AIMessage(content=briefing or "Voice agent ready."),
        ],
    }


# ── Query-time functions (called by API endpoints, not the graph) ──────────────

VOICE_CHAIN_PROMPT = ChatPromptTemplate.from_messages([
     ("human", "{question}"),
    MessagesPlaceholder(variable_name="history"),
    ("system", "{system}"), 
])


def query_text(question: str, state: WarehouseState) -> dict:
    """Multi-turn text Q&A using LangChain chain with message history."""
    llm     = _nova_pro()
    chain   = VOICE_CHAIN_PROMPT | llm | StrOutputParser()

    # Extract prior human/AI pairs from LangGraph message history
    history = [m for m in state.get("messages",[])
               if isinstance(m, (HumanMessage, AIMessage))][-8:]  # last 4 turns

    answer = chain.invoke({
        "system":   _build_system(state),
        "history":  history,
        "question": question,
    })

    return {
        "transcript":    question,
        "response_text": answer,
        "audio_bytes":   None,
    }


def query_audio(audio_bytes: bytes, state: WarehouseState) -> dict:
    """
    Nova Sonic speech-to-speech.
    Falls back to Nova Pro + Polly if Sonic is unavailable.
    """
    try:
        bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
        body = json.dumps({
            "system":  _build_system(state),
            "audio":   {
                "data":        base64.b64encode(audio_bytes).decode(),
                "format":      "pcm",
                "sample_rate": 16000,
            },
            "voice":      "talia",
            "max_tokens": 250,
            "inferenceConfig": {"temperature": 0.5},
        })
        resp = bedrock.invoke_model(
            modelId="amazon.nova-sonic-v1:0", body=body,
            contentType="application/json", accept="application/json")
        result = json.loads(resp["body"].read())
        return {
            "transcript":    result.get("input_transcript",""),
            "response_text": result.get("output_text",""),
            "audio_bytes":   base64.b64decode(result.get("output_audio","")),
            "audio_format":  "pcm",
            "model":         "nova-sonic",
        }
    except Exception as e:
        print(f"[Voice Agent] Nova Sonic unavailable ({e}), falling back to text")
        transcript = "[Voice input — use text fallback]"
        text_resp  = query_text(transcript, state)
        audio_out  = _tts_polly(text_resp["response_text"])
        return {
            "transcript":    transcript,
            "response_text": text_resp["response_text"],
            "audio_bytes":   audio_out,
            "audio_format":  "mp3",
            "fallback":      True,
            "model":         "nova-pro + polly",
        }


def _tts_polly(text: str) -> bytes:
    try:
        polly = boto3.client("polly", region_name="us-east-1")
        resp  = polly.synthesize_speech(
            Text=text, OutputFormat="mp3",
            VoiceId="Joanna", Engine="neural")
        return resp["AudioStream"].read()
    except Exception:
        return b""