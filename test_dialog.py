#!/usr/bin/env python3
"""
Interactive stress test runner for the CRM sales bot.
Runs a single turn and prints result clearly.
Usage: echo "message" | python3 test_dialog.py [session_file]
Or: python3 test_dialog.py --msg "message" [--session session.json] [--reset]
"""
import sys
import json
import os
import argparse

# Add project root to path
sys.path.insert(0, '/home/corta/crm-sales-bot-fork')

from src.bot import SalesBot

SESSION_FILE = '/tmp/bot_test_session.json'

def load_session(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def save_session(path, bot):
    """Save bot state for next turn."""
    # We can't pickle the bot easily, so we recreate each time
    # Instead save conversation history
    state = {
        'conversation': [],
        'turn': 0
    }
    if os.path.exists(path):
        with open(path) as f:
            state = json.load(f)
    return state

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--msg', type=str, help='User message')
    parser.add_argument('--session', type=str, default=SESSION_FILE)
    parser.add_argument('--reset', action='store_true', help='Reset session')
    parser.add_argument('--status', action='store_true', help='Show bot status')
    args = parser.parse_args()

    if args.reset and os.path.exists(args.session):
        os.remove(args.session)
        print("[SESSION RESET]")
        if not args.msg:
            return

    # Load conversation history
    history = []
    turn = 0
    if os.path.exists(args.session) and not args.reset:
        with open(args.session) as f:
            data = json.load(f)
            history = data.get('history', [])
            turn = data.get('turn', 0)

    if not args.msg:
        print("No message provided. Use --msg 'text'")
        return

    # Initialize bot fresh each time (stateless approach)
    print(f"\n{'='*60}")
    print(f"Turn {turn+1} | Клиент: {args.msg}")
    print('='*60)

    bot = SalesBot(flow='autonomous')

    # Replay history to restore state
    for h in history:
        bot.process(h['user'])

    # Process new message
    result = bot.process(args.msg)

    print(f"\nБот: {result.get('response', '[NO RESPONSE]')}")
    print(f"\n--- DEBUG ---")
    print(f"State: {result.get('state', '?')}")
    print(f"Action: {result.get('action', '?')}")
    print(f"SPIN: {result.get('spin_phase', '?')}")
    print(f"Tone: {result.get('tone', '?')}")
    print(f"Score: {result.get('lead_score', '?')}")
    print(f"Fallback: {result.get('fallback_used', False)} ({result.get('fallback_tier', '-')})")

    if args.status:
        print(f"\n--- FULL RESULT ---")
        for k, v in result.items():
            if k != 'response':
                print(f"  {k}: {v}")

    # Save history
    history.append({'user': args.msg, 'bot': result.get('response', '')})
    with open(args.session, 'w') as f:
        json.dump({'history': history, 'turn': turn+1}, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
