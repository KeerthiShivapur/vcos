"""Intelligence package exports."""

# Register all submodules to avoid relative import issues
import sys
import importlib.util
import os

_intelligence_dir = os.path.dirname(__file__)

_submodules = [
    f[:-3] for f in os.listdir(_intelligence_dir) if f.endswith(".py") and f != "__init__.py"
]

for name in _submodules:
    module_path = os.path.join(_intelligence_dir, f"{name}.py")
    if os.path.exists(module_path):
        spec = importlib.util.spec_from_file_location(
            f"app.intelligence.{name}", module_path
        )
        if spec:
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"app.intelligence.{name}"] = module
            spec.loader.exec_module(module)

# Import key services for convenience - get from sys.modules after dynamic load
company_brain_module = sys.modules.get("app.intelligence.company_brain")
company_brain = getattr(company_brain_module, "company_brain", None)

company_context_module = sys.modules.get("app.intelligence.company_context")
resolve_caller_access = getattr(company_context_module, "resolve_caller_access", None)

__all__ = [
    "company_brain",
    "resolve_caller_access",
]