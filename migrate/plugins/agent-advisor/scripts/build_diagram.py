"""Deterministic architecture-diagram composer for agent-advisor.

Pure: (scoring-result, pass2) dicts -> {"mermaid": str, "ascii": str}.
Same input -> byte-identical output. No timestamps, no randomness.
"""
import json
import pathlib

RUNTIME_LABELS = {
    "agentcore": "AgentCore Runtime",
    "lambda_microvms": "Lambda MicroVMs",
    "ecs": "Amazon ECS (Fargate)",
    "eks": "Amazon EKS",
    "lambda": "AWS Lambda",
    "none": "No viable runtime",
}

SERVICE_LABELS = {
    "identity": "Identity",
    "observability": "Observability",
    "evaluations": "Evaluations",
    "optimization": "Optimization",
    "memory": "Memory",
    "gateway": "Gateway",
    "policy": "Policy",
    "managed_kb": "Managed KB",
    "code_interpreter": "Code Interpreter",
    "browser": "Browser",
    "web_search": "Web Search",
    "sandbox": "Sandbox",
}

HANDOFF_RUNTIMES = {"ecs", "eks", "lambda"}


def resolve_runtime(result, pass2):
    verdict = result.get("verdict")
    if verdict == "co_recommend":
        return pass2.get("chosen_runtime") or result.get("co_recommend", ["none"])[0]
    if verdict == "no_viable_runtime":
        return "none"
    return verdict


def resolve_services(result, pass2):
    services = pass2.get("agentcore_services") or result.get("agentcore_services", [])
    seen, out = set(), []
    for sid in services:
        if sid in SERVICE_LABELS and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def render_mermaid(runtime, services, model, deployment_model):
    label = RUNTIME_LABELS.get(runtime, runtime)
    if runtime == "agentcore" and deployment_model:
        label = f"{label}<br/>({deployment_model})"
    lines = ["flowchart TD"]
    lines.append(f'    user["User / Client"]')
    lines.append(f'    rt["{label}"]')
    lines.append(f'    model["Bedrock: {model}"]')
    lines.append("    user --> rt")
    lines.append("    rt --> model")
    for sid in services:
        lines.append(f'    svc_{sid}["{SERVICE_LABELS[sid]}"]')
        lines.append(f"    rt --> svc_{sid}")
    if runtime in HANDOFF_RUNTIMES:
        lines.append('    handoff["Compute configured by migration-to-aws"]')
        lines.append("    rt -.-> handoff")
    return "\n".join(lines)


def render_ascii(runtime, services, model, deployment_model):
    label = RUNTIME_LABELS.get(runtime, runtime)
    if runtime == "agentcore" and deployment_model:
        label = f"{label} ({deployment_model})"
    lines = [
        "User / Client",
        "    |",
        "    v",
        f"[ {label} ]",
        f"    |-- model --> Bedrock: {model}",
    ]
    for sid in services:
        lines.append(f"    |-- service --> {SERVICE_LABELS[sid]}")
    # bullet list mirror for easy scanning
    if services:
        lines.append("Services:")
        for sid in services:
            lines.append(f"  - {SERVICE_LABELS[sid]}")
    if runtime in HANDOFF_RUNTIMES:
        lines.append("Note: compute configured by migration-to-aws")
    return "\n".join(lines)


def build_diagram(result, pass2):
    runtime = resolve_runtime(result, pass2)
    if runtime == "none":
        msg = "No viable runtime — see blocking constraints"
        return {
            "mermaid": f'flowchart TD\n    n["{msg}"]',
            "ascii": f"[ {RUNTIME_LABELS['none']} ]\n{msg}",
        }
    services = resolve_services(result, pass2)
    model = result.get("model_recommendation", {}).get("model", "unknown")
    deployment_model = result.get("deployment_model")
    return {
        "mermaid": render_mermaid(runtime, services, model, deployment_model),
        "ascii": render_ascii(runtime, services, model, deployment_model),
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="agent-advisor diagram composer")
    parser.add_argument("result", type=pathlib.Path)
    parser.add_argument("pass2", type=pathlib.Path)
    args = parser.parse_args(argv)
    result = json.loads(args.result.read_text())
    pass2 = json.loads(args.pass2.read_text()) if args.pass2.exists() else {}
    diagram = build_diagram(result, pass2)
    out = (
        "```mermaid\n" + diagram["mermaid"] + "\n```\n\n"
        "<details><summary>ASCII (plain-text fallback)</summary>\n\n"
        "```\n" + diagram["ascii"] + "\n```\n\n</details>\n"
    )
    out_path = args.result.parent / "diagram.md"
    out_path.write_text(out)
    print(f"RESULT=ok RUNTIME={resolve_runtime(result, pass2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
