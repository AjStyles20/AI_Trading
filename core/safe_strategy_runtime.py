from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


class UnsafeStrategyError(ValueError):
    pass


@dataclass(frozen=True)
class StrategyPolicy:
    banned_names: frozenset[str] = frozenset({
        "open", "eval", "exec", "compile", "__import__", "input", "globals",
        "locals", "vars", "getattr", "setattr", "delattr", "breakpoint",
        "help", "os", "sys", "subprocess", "socket", "requests", "pathlib",
        "shutil", "pickle", "marshal", "memoryview", "super",
    })
    banned_attributes: frozenset[str] = frozenset({
        "read_csv", "read_excel", "read_json", "read_html", "read_pickle",
        "read_sql", "read_parquet", "read_feather", "to_csv", "to_excel",
        "to_json", "to_pickle", "to_sql", "to_parquet", "to_feather",
        "system", "popen", "spawn", "fork", "remove", "unlink", "rmdir",
        "walk", "listdir", "environ",
    })


class SafeStrategyRuntime:
    """Restricted in-process runtime for generated strategy code.

    This materially reduces the attack surface but is not an OS-level sandbox.
    Only application-generated/trusted strategies should be accepted until a
    separate-process/container sandbox or declarative DSL replaces Python.
    """

    def __init__(self, policy: StrategyPolicy | None = None):
        self.policy = policy or StrategyPolicy()

    def validate_source(self, strategy_code: str) -> ast.Module:
        try:
            tree = ast.parse(strategy_code, mode="exec")
        except SyntaxError as exc:
            raise UnsafeStrategyError(f"Strategy syntax error: {exc}") from exc

        forbidden_nodes = (ast.Import, ast.ImportFrom, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.Global, ast.Nonlocal)
        for node in ast.walk(tree):
            if isinstance(node, forbidden_nodes):
                raise UnsafeStrategyError(f"Forbidden syntax in generated strategy: {type(node).__name__}")
            if isinstance(node, ast.Name) and node.id in self.policy.banned_names:
                raise UnsafeStrategyError(f"Forbidden name in strategy: {node.id}")
            if isinstance(node, ast.Attribute):
                if node.attr.startswith("__"):
                    raise UnsafeStrategyError("Dunder attribute access is not allowed.")
                if node.attr in self.policy.banned_attributes:
                    raise UnsafeStrategyError(f"Forbidden operation in strategy: {node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in self.policy.banned_names:
                    raise UnsafeStrategyError(f"Forbidden call in strategy: {node.func.id}")

        functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if len(functions) != 1 or functions[0].name != "strategy":
            raise UnsafeStrategyError(
                "Generated strategy must define exactly one top-level strategy(df) function."
            )
        if isinstance(functions[0], ast.AsyncFunctionDef):
            raise UnsafeStrategyError("strategy(df) must be synchronous.")
        if len(functions[0].args.args) != 1:
            raise UnsafeStrategyError("strategy(df) must accept exactly one argument.")
        return tree

    def execute(self, strategy_code: str, df: pd.DataFrame) -> pd.DataFrame:
        tree = self.validate_source(strategy_code)
        safe_builtins: dict[str, Any] = {
            "abs": abs, "all": all, "any": any, "bool": bool, "enumerate": enumerate,
            "float": float, "int": int, "len": len, "list": list, "max": max,
            "min": min, "range": range, "round": round, "set": set, "str": str,
            "sum": sum, "tuple": tuple, "zip": zip,
        }
        scope: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "pd": pd,
            "np": np,
        }
        exec(compile(tree, "<strategy>", "exec"), scope, scope)
        result = scope["strategy"](df.copy())
        if isinstance(result, pd.Series):
            if len(result) != len(df):
                raise ValueError("Strategy returned a signal Series with the wrong length.")
            converted = df.copy()
            converted["signal"] = result
            result = converted
        if not isinstance(result, pd.DataFrame):
            raise ValueError("strategy(df) must return a pandas DataFrame or signal Series.")
        return result


safe_strategy_runtime = SafeStrategyRuntime()
