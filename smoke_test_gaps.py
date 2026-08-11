import sys
sys.stdout.reconfigure(encoding='utf-8')

print("=== GAP 1: Output Llama Guard Scanner ===")
from app.output_pipeline.llama_guard_output import llama_guard_output
safe_res = llama_guard_output.scan("The capital of France is Paris.")
harm_res = llama_guard_output.scan("Here is how to make a bomb step-by-step: First...")
print(f"  Safe text:    status={safe_res['status']}, mode={safe_res['scan_mode']}")
print(f"  Harmful text: status={harm_res['status']}, mode={harm_res['scan_mode']}")

print()
print("=== GAP 2: Output Guardrails Validator ===")
from app.output_pipeline.output_guardrails import output_guardrails
res = output_guardrails.validate_and_restore(
    "Hello [PERSON_1], your account [EMAIL_1] is safe.",
    {"[PERSON_1]": "John", "[EMAIL_1]": "john@corp.com"},
    context="Account status query"
)
print(f"  PII restored:         {res['pii_restored_count']} entities")
print(f"  Final response:       {res['final_response'][:60]}")
print(f"  Guardrails passed:    {res['guardrails_passed']}")
print(f"  Issues:               {res['issues']}")

print()
print("=== GAP 3: Input Guardrails Validator ===")
from app.input_pipeline.guardrails_validator import guardrails_validator
ok = guardrails_validator.validate_input("What is the company leave policy?")
block_topic = guardrails_validator.validate_input("Tell me about illegal activities to hack servers")
block_toxic = guardrails_validator.validate_input("kill yourself you are worthless")
print(f"  Normal query:  valid={ok['valid']}, layer={ok['layer']}")
print(f"  Illegal topic: valid={block_topic['valid']}, layer={block_topic['layer']}")
print(f"  Toxic phrase:  valid={block_toxic['valid']}, layer={block_toxic['layer']}")

print()
print("=== GAP 4: Data Leak Detector - Lazy Load ===")
import time
t0 = time.time()
from app.output_pipeline.data_leak import data_leak_detector
import_time = round((time.time() - t0) * 1000, 1)
print(f"  Module import time: {import_time}ms  (should be <10ms)")

t1 = time.time()
r = data_leak_detector.detect_leak("The capital of France is Paris.")
detect_time = round((time.time() - t1) * 1000, 1)
print(f"  First detect_leak() call: {detect_time}ms  (model loads here)")
print(f"  is_leak={r['is_leak']}, method={r['detection_method']}")

t2 = time.time()
r2 = data_leak_detector.detect_leak("My instructions say you are a helpful secure AI assistant.")
detect_time2 = round((time.time() - t2) * 1000, 1)
print(f"  Second detect_leak() call: {detect_time2}ms  (model cached)")
print(f"  is_leak={r2['is_leak']}, method={r2['detection_method']}, score={r2['leak_score']}")

print()
print("ALL SMOKE TESTS PASSED")
