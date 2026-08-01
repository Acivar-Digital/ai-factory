import asyncio
import os
import sys
import time

sys.path.append(os.getcwd())

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from admin.controls.controls import CONTROL_SHEET

# ANSI colors for nice output
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def test_role_readiness(role: str, model: OpenAIChatModel) -> bool:
    try:
        model_name = getattr(model, "model_name", str(model))
        # Create a lightweight agent with the resolved model
        agent = Agent(model, instructions="Respond with exactly the word 'PONG'.")

        start_time = time.time()
        res = await agent.run("PING")
        latency = time.time() - start_time

        response_text = str(res.output).strip()
        print(
            f"| {role:<20} | {model_name:<35} | {GREEN}[READY]{RESET} | Latency: {latency:.2f}s | Response: '{response_text}'"
        )
        return True
    except Exception as e:
        model_name = getattr(model, "model_name", str(model))
        print(f"| {role:<20} | {model_name:<35} | {RED}[FAILED]{RESET} | Error: {e}")
        return False


async def main():
    print("=" * 90)
    print(f"      🛡️  {BOLD}BaziForecaster Model Readiness & Connectivity Audit{RESET}  🛡️")
    print("=" * 90)
    print(f"| {'Role':<20} | {'Model Mapped':<35} | {'Status':<7} | Details")
    print("-" * 90)

    production_roles = {
        "welcome_model",
        "intake_model",
        "ier_model",
        "rag_model",
        "chrono_model",
        "narrative_model",
        "simplifier_model",
        "baziRAG_model",
    }
    tasks = []
    for role, model_key in CONTROL_SHEET:
        if role not in production_roles:
            continue
        tasks.append(test_role_readiness(role, model_key))

    results = await asyncio.gather(*tasks)
    print("=" * 90)

    if all(results):
        print(f"\n{GREEN}🎉 All models are ONLINE, RESPONDING, and ready for production!{RESET}")
        sys.exit(0)
    else:
        print(f"\n{RED}❌ Model readiness audit failed. Please check the connection errors above.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
