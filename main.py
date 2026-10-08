"""
Salon Payments Ops Agent - Unified Application Entrypoint.
Provides command-line routing for running services, benchmarks, and tests.
"""

import sys
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="Salon Payments Ops Agent: Google ADK on Cloud Run"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="info",
        choices=["info", "payments-api", "approval-service", "evals", "live-test"],
        help="Command to run: 'payments-api', 'approval-service', 'evals', 'live-test', or 'info'",
    )
    parser.add_argument("--port", type=int, default=8000, help="Port to bind API service")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface")

    args = parser.parse_args()

    if args.command == "info":
        print("=" * 80)
        print(" SALON PAYMENTS OPS AGENT (Google ADK on Cloud Run)")
        print("=" * 80)
        print("Available operational commands:")
        print("  • uv run python main.py payments-api       # Run Payments & Webhook API")
        print("  • uv run python main.py approval-service   # Run Human Approval Gate Service")
        print("  • uv run python main.py evals              # Run 35-Case Benchmark Evals")
        print("  • uv run python main.py live-test          # Run Live Gemini & ADK E2E Test")
        print("  • uv run pytest -v                         # Run 28 Unit & Integration Tests")
        print("=" * 80)

    elif args.command == "payments-api":
        print(f"Starting Payments API on http://{args.host}:{args.port}...")
        uvicorn.run("services.payments_api.main:app", host=args.host, port=args.port, reload=True)

    elif args.command == "approval-service":
        port = args.port if args.port != 8000 else 8001
        print(f"Starting Approval Service on http://{args.host}:{port}...")
        uvicorn.run("services.approval_service.main:app", host=args.host, port=port, reload=True)

    elif args.command == "evals":
        from evals.runner import run_benchmark
        run_benchmark()

    elif args.command == "live-test":
        from tests.live.test_live_e2e import run_live_test_suite
        run_live_test_suite()


if __name__ == "__main__":
    main()
