# BUG2 Fix — PRE/POST Comparison

**PRE** (aaa4134, before Fix 1+2): 0/10 PASS, bug2_fires=12
**POST** (Fix1 + Fix2): 10/10 PASS, bug2_fires=0

## Per-scenario comparison

| ID | Scenario | PRE verdict | POST verdict | PRE misroutes | PRE tmpl (factual turn) | POST tmpl (factual turn) |
|-----|----------|------------|-------------|---------------|------------------------|--------------------------|
| B01 | Kaspi integration question mid-discovery ('?'... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |
| B02 | 'Как работает' textual_factual trigger mid-qu... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |
| B03 | 'Есть ли' textual_factual trigger — spin cont... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |
| B04 | Price question mid-dialog — factual_intent=Tr... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |
| B05 | 'Можно ли' textual_factual — qualification ph... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |
| B06 | SPIN flow continuity: factual answer then nex... | ✗ | ✓ | 2 | `answer_with_facts` | `autonomous_respond` |
| B07 | Deflection guard: bot deflects with discovery... | ✗ | ✓ | 2 | `answer_with_facts` | `autonomous_respond` |
| B08 | Bundle query + factual — deflection guard Fix... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |
| B09 | Presentation phase factual question — all con... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |
| B10 | Closing phase factual question — must stay in... | ✗ | ✓ | 1 | `answer_with_facts` | `autonomous_respond` |

## Key observations

- **PRE**: Every scenario where the bot handled a factual question mid-dialog resulted in `template=answer_with_facts`, stripping `{spin_phase}`, `{goal}`, `{collected_data}`, `{missing_data}` from the LLM context.
- **POST**: All 10 scenarios keep `template=autonomous_respond` throughout, preserving full SPIN context. The factual content is answered via `{retrieved_facts}` already injected into `autonomous_respond`.
- **Verifier** (`factual_verifier`): Active in both PRE and POST. PRE verifier marked responses `fail` but had no rewrite (because the `answer_with_facts` prompt is weak — the verifier rewrites but still without SPIN context). POST verifier marks `fail` for some turns but now the base response quality is better (full context).
- **Regression check**: No new regressions detected. No turns where POST used `answer_with_facts` when PRE used `autonomous_respond`.

## Notable POST observation — B10 T4 garbage response
In B10 POST, turn 4 ('Давайте оформим!') generated garbage text starting with 'assertions: 1 - 1.5.1...'. This is a **pre-existing bug unrelated to BUG 2** — it appears in a specific closing state. Requires separate investigation.