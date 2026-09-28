"""
One-off spike for specs/002-gpt-live-interview (tasks T006, quickstart S1/S4).

S4: does the installed openai SDK expose the `live` resource?
S1: can a trusted server attach a sideband WebSocket to a running GPT-Live session?

It starts a GPT-Live session over a plain WebSocket (no audio) and tries to attach a
sideband to it (expected to 404: sidebands are for WebRTC sessions), then closes it.
Each session costs a few seconds of GPT-Live time.

Run: .venv/bin/python scripts/spike_live.py [offer.sdp]

With an SDP offer file (e.g. from a browser RTCPeerConnection with an audio track and an
`oai-events` data channel), S1 is also run against a WebRTC session created with
client.live.create, which is how the app creates sessions.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openai  # noqa: E402

from src.config import OPENAI_API_KEY, OPENAI_LIVE_MODEL  # noqa: E402


async def attach_and_probe(client: openai.AsyncOpenAI, session_id: str, label: str) -> bool:
    try:
        async with client.live.sideband.connect(session_id=session_id) as sideband:
            seen: list[str] = []
            await sideband.send({"type": "session.instructions.append", "delegation_id": None,
                                 "content": "Say the word 'ready'."})

            async def collect() -> None:
                async for event in sideband:
                    seen.append(event.type)
                    if len(seen) >= 5:
                        return
            try:
                await asyncio.wait_for(collect(), timeout=15)
            except asyncio.TimeoutError:
                pass
            print(f"S1 ({label}): sideband attached; first events: {seen or '(none within 15 s)'}")
            await sideband.send({"type": "session.close"})
            return True
    except Exception as exc:  # the result we're probing for
        print(f"S1 ({label}): sideband attach FAILED: {type(exc).__name__}: {exc}")
        return False


async def webrtc_probe(client: openai.AsyncOpenAI, offer_path: str) -> None:
    created = await client.live.create(
        session={"model": OPENAI_LIVE_MODEL, "instructions": "Say hello.", "delegation": {"type": "client"}},
        transport={"type": "webrtc", "sdp": Path(offer_path).read_text()},
    )
    print(f"  live.create -> session {created.session.id[:12]}…, answer SDP {len(created.transport.sdp)} bytes")
    await attach_and_probe(client, created.session.id, "webrtc")


async def main() -> int:
    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    print(f"S4: openai {openai.__version__}, live resource: {hasattr(client, 'live')}")
    if not OPENAI_API_KEY:
        print("S1: skipped (OPENAI_API_KEY is not set)")
        return 1

    async with client.live.connect() as primary:
        await primary.send({
            "type": "session.start",
            "session": {
                "model": OPENAI_LIVE_MODEL,
                "instructions": "Say hello in one short sentence.",
                "delegation": {"type": "client"},
            },
        })
        session_id = None
        async for event in primary:
            print(f"  primary <- {event.type}")
            if event.type == "session.started":
                session_id = event.session.id
                break
            if event.type == "error":
                print(f"S1: session.start failed: {event.error.code}")
                return 1

        await attach_and_probe(client, session_id, "websocket")

        await primary.send({"type": "session.close"})
        async for event in primary:
            if event.type == "session.closed":
                print(f"  primary <- session.closed ({event.reason}, {event.usage.seconds} s billed)")
                break

    if len(sys.argv) > 1:
        await webrtc_probe(client, sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
