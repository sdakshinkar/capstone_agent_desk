# Red-team run: defences off  (20261111_110504)

- Targets: sandbox; repeats: 1; model IDs: see src/agent_desk/llm/llm.py
- **Attack success: 3/11 (27%)** (errors excluded and listed: 0; blocked at input: 0)
- **False blocks on clean cases: n/a** (clean errors: 0)
- Latency (LLM targets): median 0.0s, p95 0.0s
- Tokens: 0 in / 0 out; est. cost $0.0

| Category | success | defended | blocked | error |
|---|---|---|---|---|
| sandbox_dos_output | 0 | 1 | 0 | 0 |
| sandbox_dos_time | 0 | 1 | 0 | 0 |
| sandbox_dunder | 0 | 3 | 0 | 0 |
| sandbox_file_read | 1 | 0 | 0 | 0 |
| sandbox_import | 0 | 1 | 0 | 0 |
| sandbox_module_walk | 1 | 0 | 0 | 0 |
| sandbox_network | 0 | 2 | 0 | 0 |
| sandbox_shell | 1 | 0 | 0 | 0 |

## Attack results

| ID | target | vector | verdict | evidence / error |
|---|---|---|---|---|
| SB-01 | sandbox | sandbox_code | defended |  |
| SB-02 | sandbox | sandbox_code | defended |  |
| SB-03 | sandbox | sandbox_code | defended |  |
| SB-04 | sandbox | sandbox_code | defended |  |
| SB-05 | sandbox | sandbox_code | success | code ran (ok=True), output='[]\n' |
| SB-06 | sandbox | sandbox_code | success | sandbox output contains ['SHELL-OK'] |
| SB-07 | sandbox | sandbox_code | defended |  |
| SB-08 | sandbox | sandbox_code | success | sandbox output contains ['ZX-CANARY-7731'] |
| SB-09 | sandbox | sandbox_code | defended |  |
| SB-10 | sandbox | sandbox_code | defended |  |
| SB-11 | sandbox | sandbox_code | defended |  |
