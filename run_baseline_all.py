import json, os, sys
sys.path.insert(0, 'src')
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

from dotenv import load_dotenv
load_dotenv()
from providers import get_llm_provider
from prompts import CHATBOT_BASELINE_PROMPT

provider = get_llm_provider()
print("Provider:", provider.__class__.__name__)

with open('config/test_cases.json', encoding='utf-8') as f:
    tests = json.load(f)

for tc in tests:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"TEST CASE #{tc['id']} | {tc['category']}")
    print(f"CAU HOI: {tc['question']}")
    print("-" * 60)
    resp = provider.generate(tc['question'], system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"TRA LOI CHATBOT:\n{resp}")
    print(f"\nMONG DOI: {tc['expected_behavior']}")
