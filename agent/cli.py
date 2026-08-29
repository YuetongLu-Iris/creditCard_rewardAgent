"""
agent/cli.py
-------------
CLI chat interface for the credit card rewards agent.

Run:
    python -m agent.cli
"""
from . import chat


def main():
    print("\n" + "═" * 60)
    print("  💳  Credit Card Rewards Agent")
    print("  Powered by Claude")
    print("═" * 60)
    print("\nAsk me anything about your spending and rewards!")
    print("Examples:")
    print("  • Which card should I use at Whole Foods?")
    print("  • How much did I spend on dining last month?")
    print("  • Should I get the Amex Gold based on my spending?")
    print("  • Show me my full rewards report")
    print("\nType 'quit' to exit.\n")

    conversation_history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            print("Goodbye!")
            break

        print()  # spacing
        response, conversation_history = chat(user_input, conversation_history)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    main()
