"""CLI entry point for the Battery Materials Agent."""

import argparse
import json
import sys
from .agent import BatteryMaterialsAgent
from .config import get_config, ensure_project_root


def main():
    parser = argparse.ArgumentParser(description="Battery Materials AI Agent")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    subparsers.add_parser("serve", help="Start the API server")
    subparsers.add_parser("mcp-manifest", help="Print MCP tool manifest")
    subparsers.add_parser("tools", help="List available tools")

    route_parser = subparsers.add_parser("route", help="Route a material")
    route_parser.add_argument("--name", default="")
    route_parser.add_argument("--smiles", default="")
    route_parser.add_argument("--psmiles", default="")
    route_parser.add_argument("--formula", default="")

    discover_parser = subparsers.add_parser("discover", help="Run ECML discovery")
    discover_parser.add_argument("--target", default="")
    discover_parser.add_argument("--property", default="ionic_conductivity")
    discover_parser.add_argument("--iterations", type=int, default=3)

    crystal_parser = subparsers.add_parser("discover-crystal", help="Discover crystal candidates")
    crystal_parser.add_argument("--elements", nargs="+", default=[])
    crystal_parser.add_argument("--num", type=int, default=10)

    polymer_parser = subparsers.add_parser("discover-polymer", help="Discover polymer candidates")
    polymer_parser.add_argument("--num", type=int, default=10)

    synth_parser = subparsers.add_parser("synthesis", help="Check synthesis feasibility")
    synth_parser.add_argument("smiles")

    verify_parser = subparsers.add_parser("verify", help="Verify material properties")
    verify_parser.add_argument("smiles")
    verify_parser.add_argument("--property", default="total_energy")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # CLI 同样强制从项目根目录运行，统一配置与数据路径
    ensure_project_root()
    config = get_config()
    agent = BatteryMaterialsAgent(config)

    if args.command == "serve":
        import uvicorn
        from .api import app
        uvicorn.run(app, host="0.0.0.0", port=8000)

    elif args.command == "mcp-manifest":
        print(json.dumps(agent.get_mcp_manifest(), indent=2))

    elif args.command == "tools":
        for tool in agent.tools.list_tools():
            print(f"  {tool.name}: {tool.description}")

    elif args.command == "route":
        from .router.router import MaterialInput
        mi = MaterialInput(name=args.name, smiles=args.smiles, psmiles=args.psmiles, formula=args.formula)
        result = agent.route(mi)
        print(json.dumps(result.model_dump(), indent=2))

    elif args.command == "discover":
        state = agent.discover(args.target, args.property, args.iterations)
        print(json.dumps(agent.ecml.get_summary(state), indent=2))

    elif args.command == "discover-crystal":
        result = agent.discover_crystal(args.elements, num_candidates=args.num)
        print(json.dumps(result, indent=2))

    elif args.command == "discover-polymer":
        result = agent.discover_polymer(num_candidates=args.num)
        print(json.dumps(result, indent=2))

    elif args.command == "synthesis":
        score = agent.check_synthesis(args.smiles)
        print(json.dumps({"smiles": args.smiles, "feasibility_score": score}, indent=2))

    elif args.command == "verify":
        result = agent.verify(args.smiles, args.property)
        print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
