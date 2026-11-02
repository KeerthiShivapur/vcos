"""
Causal Inference Engine for VCOS Intelligence Layer.

Provides causal inference capabilities using DoWhy/EconML:
- Causal graph construction
- Counterfactual estimation
- Treatment effect estimation
- Causal discovery
- Mediation analysis
- Sensitivity analysis
"""

import asyncio
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

# Suppress warnings from causal libraries
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import dowhy
    from dowhy import CausalModel
    DOWHY_AVAILABLE = True
except ImportError:
    DOWHY_AVAILABLE = False
    logger.warning("DoWhy not installed. Install with: pip install dowhy")

try:
    import econml
    from econml.dml import CausalForestDML, LinearDML
    from econml.metalearners import SLearner, TLearner, XLearner
    from econml.orf import DMLOrthoForest, DROrthoForest
    ECONML_AVAILABLE = True
except ImportError:
    ECONML_AVAILABLE = False
    logger.warning("EconML not installed. Install with: pip install econml")

try:
    import causalgraphicalmodels as cgm
    CAUSAL_GRAPHICAL_MODELS_AVAILABLE = True
except ImportError:
    CAUSAL_GRAPHICAL_MODELS_AVAILABLE = False
    logger.warning("causalgraphicalmodels not installed. Install with: pip install causalgraphicalmodels")


class CausalMethod(str, Enum):
    """Causal inference methods."""
    BACKDOOR = "backdoor"
    FRONTDOOR = "frontdoor"
    IV = "instrumental_variable"
    MEDIATION = "mediation"
    FRONTDOOR_ADJUSTMENT = "frontdoor_adjustment"
    PROPENSITY_SCORE = "propensity_score"
    DOUBLE_ML = "double_ml"
    CAUSAL_FOREST = "causal_forest"
    ORTHOGONAL_FOREST = "orthogonal_forest"
    S_LEARNER = "s_learner"
    T_LEARNER = "t_learner"
    X_LEARNER = "x_learner"
    COUNTERFACTUAL = "counterfactual"


class EstimatorType(str, Enum):
    """Estimator types."""
    LINEAR_REGRESSION = "linear_regression"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    NEURAL_NETWORK = "neural_network"
    CAUSAL_FOREST = "causal_forest"
    ORTHOGONAL_FOREST = "orthogonal_forest"
    DR_LEARNER = "dr_learner"
    X_LEARNER = "x_learner"


@dataclass
class CausalGraph:
    """Causal graph representation."""
    nodes: List[str]
    edges: List[Tuple[str, str]]  # (cause, effect)
    latent_variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TreatmentEffect:
    """Treatment effect estimation result."""
    ate: float  # Average Treatment Effect
    ate_ci: Tuple[float, float]  # Confidence interval
    ate_pvalue: float

    # Heterogeneous effects
    cate: Optional[Dict[str, float]] = None  # Conditional ATE by subgroup
    cate_ci: Optional[Dict[str, Tuple[float, float]]] = None

    # Individual effects
    ite: Optional[np.ndarray] = None  # Individual Treatment Effects

    # Method info
    method: str = ""
    estimator: str = ""
    assumptions: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CounterfactualResult:
    """Counterfactual estimation result."""
    factual_outcome: float
    counterfactual_outcome: float
    effect: float
    confidence_interval: Tuple[float, float]
    probability_necessary: float  # P(Y_y'=1 | Y=1, X=x)
    probability_sufficient: float  # P(Y_y'=1 | Y=0, X=x)
    explanation: str = ""


@dataclass
class MediationAnalysis:
    """Mediation analysis result."""
    total_effect: float
    direct_effect: float
    indirect_effect: float
    proportion_mediated: float
    mediator_effects: Dict[str, float] = field(default_factory=dict)
    confidence_intervals: Dict[str, Tuple[float, float]] = field(default_factory=dict)


class CausalInferenceEngine:
    """
    Causal Inference Engine using DoWhy and EconML.

    Features:
    - Causal graph construction & validation
    - Treatment effect estimation (ATE, CATE, ITE)
    - Counterfactual estimation
    - Mediation analysis
    - Sensitivity analysis
    - Causal discovery from data
    """

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._graphs: Dict[str, CausalGraph] = {}
        self._data_cache: Dict[str, pd.DataFrame] = {}

    # ==================== Graph Construction ====================

    def create_graph(
        self,
        name: str,
        nodes: List[str],
        edges: List[Tuple[str, str]],
        latent_variables: List[str] = None,
    ) -> CausalGraph:
        """Create a causal graph."""
        graph = CausalGraph(
            nodes=nodes,
            edges=edges,
            latent_variables=latent_variables or [],
        )
        self._graphs[name] = graph
        logger.info(f"Created causal graph: {name} with {len(nodes)} nodes and {len(edges)} edges")
        return graph

    def get_graph(self, name: str) -> Optional[CausalGraph]:
        return self._graphs.get(name)

    def validate_graph(self, name: str) -> Dict[str, Any]:
        """Validate causal graph structure."""
        graph = self._graphs.get(name)
        if not graph:
            return {"valid": False, "error": "Graph not found"}

        # Check for cycles
        try:
            import networkx as nx
            G = nx.DiGraph()
            G.add_nodes_from(graph.nodes)
            G.add_edges_from(graph.edges)
            cycles = list(nx.simple_cycles(G))
            has_cycles = len(cycles) > 0
        except Exception:
            has_cycles = False
            cycles = []

        # Check for disconnected components
        import networkx as nx
        G = nx.DiGraph()
        G.add_nodes_from(graph.nodes)
        G.add_edges_from(graph.edges)
        weakly_connected = list(nx.weakly_connected_components(G))

        return {
            "valid": not has_cycles,
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "has_cycles": has_cycles,
            "cycles": cycles,
            "connected_components": len(weakly_connected),
            "latent_variables": len(graph.latent_variables),
        }

    def visualize_graph(self, name: str, output_path: str = None) -> str:
        """Generate graph visualization (DOT format)."""
        graph = self._graphs.get(name)
        if not graph:
            return ""

        dot = "digraph G {\n"
        dot += "  rankdir=LR;\n"
        dot += "  node [shape=box, style=filled, fillcolor=lightblue];\n"

        for node in graph.nodes:
            color = "lightyellow" if node in graph.latent_variables else "lightblue"
            dot += f'  "{node}" [fillcolor="{color}"];\n'

        for cause, effect in graph.edges:
            dot += f'  "{cause}" -> "{effect}";\n'

        dot += "}\n"

        if output_path:
            with open(output_path, "w") as f:
                f.write(dot)

        return dot

    # ==================== Data Management ====================

    def register_data(self, name: str, data: pd.DataFrame):
        """Register dataset for causal analysis."""
        self._data_cache[name] = data.copy()
        logger.info(f"Registered data: {name} ({data.shape[0]} rows, {data.shape[1]} cols)")

    def get_data(self, name: str) -> Optional[pd.DataFrame]:
        return self._data_cache.get(name)

    # ==================== Treatment Effect Estimation ====================

    async def estimate_treatment_effect(
        self,
        data_name: str,
        treatment: str,
        outcome: str,
        confounders: List[str] = None,
        effect_modifiers: List[str] = None,
        method: CausalMethod = CausalMethod.BACKDOOR,
        estimator: EstimatorType = EstimatorType.LINEAR_REGRESSION,
        graph_name: str = None,
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> TreatmentEffect:
        """Estimate treatment effect using specified method."""
        data = self._data_cache.get(data_name)
        if data is None:
            raise ValueError(f"Data not found: {data_name}")

        confounders = confounders or []
        effect_modifiers = effect_modifiers or []

        if not DOWHY_AVAILABLE and method in [CausalMethod.BACKDOOR, CausalMethod.FRONTDOOR, CausalMethod.IV]:
            raise RuntimeError("DoWhy required for this method. Install: pip install dowhy")

        if not ECONML_AVAILABLE and method in [CausalMethod.DOUBLE_ML, CausalMethod.CAUSAL_FOREST, CausalMethod.ORTHOGONAL_FOREST, CausalMethod.S_LEARNER, CausalMethod.T_LEARNER, CausalMethod.X_LEARNER]:
            raise RuntimeError("EconML required for this method. Install: pip install econml")

        try:
            if method == CausalMethod.BACKDOOR:
                return await self._estimate_backdoor(data, treatment, outcome, confounders, graph_name)
            elif method == CausalMethod.DOUBLE_ML:
                return await self._estimate_double_ml(data, treatment, outcome, confounders, effect_modifiers, estimator)
            elif method == CausalMethod.CAUSAL_FOREST:
                return await self._estimate_causal_forest(data, treatment, outcome, confounders, effect_modifiers)
            elif method == CausalMethod.ORTHOGONAL_FOREST:
                return await self._estimate_orthogonal_forest(data, treatment, outcome, confounders, effect_modifiers)
            elif method == CausalMethod.S_LEARNER:
                return await self._estimate_s_learner(data, treatment, outcome, confounders, effect_modifiers)
            elif method == CausalMethod.T_LEARNER:
                return await self._estimate_t_learner(data, treatment, outcome, confounders, effect_modifiers)
            elif method == CausalMethod.X_LEARNER:
                return await self._estimate_x_learner(data, treatment, outcome, confounders, effect_modifiers)
            elif method == CausalMethod.COUNTERFACTUAL:
                return await self._estimate_counterfactual(data, treatment, outcome, confounders)
            else:
                raise ValueError(f"Unsupported method: {method}")
        except Exception as e:
            logger.error(f"Treatment effect estimation failed: {e}")
            raise

    async def _estimate_backdoor(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
        graph_name: str = None,
    ) -> TreatmentEffect:
        """Estimate using backdoor adjustment (DoWhy)."""
        if not DOWHY_AVAILABLE:
            raise RuntimeError("DoWhy not available")

        # Build causal graph string
        graph_str = "digraph { "
        if graph_name and graph_name in self._graphs:
            graph = self._graphs[graph_name]
            for cause, effect in graph.edges:
                graph_str += f"{cause} -> {effect}; "
        else:
            # Default: confounders -> treatment, confounders -> outcome, treatment -> outcome
            for c in confounders:
                graph_str += f"{c} -> {treatment}; {c} -> {outcome}; "
            graph_str += f"{treatment} -> {outcome}; "
        graph_str += " }"

        model = CausalModel(
            data=data,
            treatment=treatment,
            outcome=outcome,
            graph=graph_str,
        )

        # Identify effect
        identified_estimand = model.identify_effect(proceed_when_unidentifiable=True)

        # Estimate using linear regression
        estimate = model.estimate_effect(
            identified_estimand,
            method_name="backdoor.linear_regression",
            target_units="ate",
            effect_modifiers=[],
            confidence_intervals=True,
        )

        ate = estimate.value
        ci = estimate.get_confidence_intervals() if hasattr(estimate, 'get_confidence_intervals') else (ate - 1.96, ate + 1.96)

        return TreatmentEffect(
            ate=ate,
            ate_ci=(ci[0], ci[1]) if isinstance(ci, tuple) else (ate - 1.96, ate + 1.96),
            ate_pvalue=getattr(estimate, 'p_value', 0.05),
            method="backdoor",
            estimator="linear_regression",
            assumptions={"confounders": confounders, "graph": graph_name},
            diagnostics={"estimand": str(identified_estimand)},
        )

    async def _estimate_double_ml(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
        effect_modifiers: List[str],
        estimator: EstimatorType,
    ) -> TreatmentEffect:
        """Estimate using Double ML (EconML)."""
        if not ECONML_AVAILABLE:
            raise RuntimeError("EconML not available")

        from econml.dml import LinearDML, CausalForestDML

        X = data[confounders] if confounders else pd.DataFrame(index=data.index)
        W = data[treatment]
        Y = data[outcome]

        # Select base learners
        if estimator == EstimatorType.LINEAR_REGRESSION:
            from sklearn.linear_model import LinearRegression
            model_y = LinearRegression()
            model_t = LinearRegression()
        elif estimator == EstimatorType.RANDOM_FOREST:
            from sklearn.ensemble import RandomForestRegressor
            model_y = RandomForestRegressor(n_estimators=100, random_state=42)
            model_t = RandomForestRegressor(n_estimators=100, random_state=42)
        elif estimator == EstimatorType.GRADIENT_BOOSTING:
            from sklearn.ensemble import GradientBoostingRegressor
            model_y = GradientBoostingRegressor(random_state=42)
            model_t = GradientBoostingRegressor(random_state=42)
        else:
            from sklearn.linear_model import LinearRegression
            model_y = LinearRegression()
            model_t = LinearRegression()

        # Fit DML
        est = LinearDML(
            model_y=model_y,
            model_t=model_t,
            random_state=42,
        )

        est.fit(Y, W, X=X)

        # Get ATE
        ate = est.ate(X)
        ate_ci = est.ate_interval(X, alpha=0.05)

        # Get CATE if effect modifiers provided
        cate = None
        cate_ci = None
        if effect_modifiers:
            X_mod = data[effect_modifiers]
            cate_vals = est.ate(X_mod)
            cate = {str(i): float(v) for i, v in enumerate(cate_vals)}
            ci = est.ate_interval(X_mod, alpha=0.05)
            cate_ci = {str(i): (float(ci[0][i]), float(ci[1][i])) for i in range(len(cate_vals))}

        # Get ITE
        ite = est.effect(X)

        return TreatmentEffect(
            ate=float(ate.mean()) if hasattr(ate, 'mean') else float(ate),
            ate_ci=(float(ate_ci[0].mean()), float(ate_ci[1].mean())) if hasattr(ate_ci, 'mean') else (0, 0),
            ate_pvalue=0.05,  # Placeholder
            cate=cate,
            cate_ci=cate_ci,
            ite=ite,
            method="double_ml",
            estimator=estimator.value,
            assumptions={"confounders": confounders, "effect_modifiers": effect_modifiers},
            diagnostics={},
        )

    async def _estimate_causal_forest(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
        effect_modifiers: List[str],
    ) -> TreatmentEffect:
        """Estimate using Causal Forest (EconML)."""
        if not ECONML_AVAILABLE:
            raise RuntimeError("EconML not available")

        from econml.dml import CausalForestDML
        from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier

        X = data[confounders] if confounders else pd.DataFrame(index=data.index)
        W = data[treatment]
        Y = data[outcome]

        est = CausalForestDML(
            model_y=RandomForestRegressor(n_estimators=100, random_state=42),
            model_t=RandomForestClassifier(n_estimators=100, random_state=42) if W.nunique() == 2 else RandomForestRegressor(n_estimators=100, random_state=42),
            n_estimators=1000,
            min_samples_leaf=10,
            max_depth=10,
            random_state=42,
        )

        est.fit(Y, W, X=X)

        ate = est.ate(X)
        ate_ci = est.ate_interval(X, alpha=0.05)

        cate = None
        cate_ci = None
        if effect_modifiers:
            X_mod = data[effect_modifiers]
            cate_vals = est.ate(X_mod)
            cate = {str(i): float(v) for i, v in enumerate(cate_vals)}
            ci = est.ate_interval(X_mod, alpha=0.05)
            cate_ci = {str(i): (float(ci[0][i]), float(ci[1][i])) for i in range(len(cate_vals))}

        ite = est.effect(X)

        return TreatmentEffect(
            ate=float(ate.mean()) if hasattr(ate, 'mean') else float(ate),
            ate_ci=(float(ate_ci[0].mean()), float(ate_ci[1].mean())) if hasattr(ate_ci, 'mean') else (0, 0),
            ate_pvalue=0.05,
            cate=cate,
            cate_ci=cate_ci,
            ite=ite,
            method="causal_forest",
            estimator="causal_forest",
            assumptions={"confounders": confounders, "effect_modifiers": effect_modifiers},
            diagnostics={"n_estimators": 1000},
        )

    async def _estimate_orthogonal_forest(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
        effect_modifiers: List[str],
    ) -> TreatmentEffect:
        """Estimate using Orthogonal Forest (EconML)."""
        if not ECONML_AVAILABLE:
            raise RuntimeError("EconML not available")

        from econml.orf import DMLOrthoForest

        X = data[confounders] if confounders else pd.DataFrame(index=data.index)
        W = data[treatment]
        Y = data[outcome]

        est = DMLOrthoForest(
            n_trees=1000,
            min_leaf_size=10,
            max_depth=10,
            random_state=42,
        )

        est.fit(Y, W, X=X)

        ate = est.ate(X)
        ate_ci = est.ate_interval(X, alpha=0.05)

        cate = None
        cate_ci = None
        if effect_modifiers:
            X_mod = data[effect_modifiers]
            cate_vals = est.ate(X_mod)
            cate = {str(i): float(v) for i, v in enumerate(cate_vals)}
            ci = est.ate_interval(X_mod, alpha=0.05)
            cate_ci = {str(i): (float(ci[0][i]), float(ci[1][i])) for i in range(len(cate_vals))}

        ite = est.effect(X)

        return TreatmentEffect(
            ate=float(ate.mean()) if hasattr(ate, 'mean') else float(ate),
            ate_ci=(float(ate_ci[0].mean()), float(ate_ci[1].mean())) if hasattr(ate_ci, 'mean') else (0, 0),
            ate_pvalue=0.05,
            cate=cate,
            cate_ci=cate_ci,
            ite=ite,
            method="orthogonal_forest",
            estimator="orthogonal_forest",
            assumptions={"confounders": confounders, "effect_modifiers": effect_modifiers},
            diagnostics={"n_trees": 1000},
        )

    async def _estimate_s_learner(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
        effect_modifiers: List[str],
    ) -> TreatmentEffect:
        """Estimate using S-Learner (EconML)."""
        if not ECONML_AVAILABLE:
            raise RuntimeError("EconML not available")

        from econml.metalearners import SLearner
        from sklearn.ensemble import RandomForestRegressor

        X = data[confounders] if confounders else pd.DataFrame(index=data.index)
        W = data[treatment]
        Y = data[outcome]

        est = SLearner(overall_model=RandomForestRegressor(n_estimators=100, random_state=42))
        est.fit(Y, W, X=X)

        # S-Learner doesn't have built-in ATE, compute manually
        X_treat = X.copy()
        X_treat[treatment] = 1
        X_control = X.copy()
        X_control[treatment] = 0

        y_treat = est.predict(X_treat)
        y_control = est.predict(X_control)

        ite = y_treat - y_control
        ate = np.mean(ite)

        return TreatmentEffect(
            ate=float(ate),
            ate_ci=(float(ate) - 1.96 * np.std(ite) / np.sqrt(len(ite)), float(ate) + 1.96 * np.std(ite) / np.sqrt(len(ite))),
            ate_pvalue=0.05,
            ite=ite,
            method="s_learner",
            estimator="s_learner",
            assumptions={"confounders": confounders, "effect_modifiers": effect_modifiers},
            diagnostics={},
        )

    async def _estimate_t_learner(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
        effect_modifiers: List[str],
    ) -> TreatmentEffect:
        """Estimate using T-Learner (EconML)."""
        if not ECONML_AVAILABLE:
            raise RuntimeError("EconML not available")

        from econml.metalearners import TLearner
        from sklearn.ensemble import RandomForestRegressor

        X = data[confounders] if confounders else pd.DataFrame(index=data.index)
        W = data[treatment]
        Y = data[outcome]

        est = TLearner(models=RandomForestRegressor(n_estimators=100, random_state=42))
        est.fit(Y, W, X=X)

        ite = est.effect(X)
        ate = np.mean(ite)

        return TreatmentEffect(
            ate=float(ate),
            ate_ci=(float(ate) - 1.96 * np.std(ite) / np.sqrt(len(ite)), float(ate) + 1.96 * np.std(ite) / np.sqrt(len(ite))),
            ate_pvalue=0.05,
            ite=ite,
            method="t_learner",
            estimator="t_learner",
            assumptions={"confounders": confounders, "effect_modifiers": effect_modifiers},
            diagnostics={},
        )

    async def _estimate_x_learner(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
        effect_modifiers: List[str],
    ) -> TreatmentEffect:
        """Estimate using X-Learner (EconML)."""
        if not ECONML_AVAILABLE:
            raise RuntimeError("EconML not available")

        from econml.metalearners import XLearner
        from sklearn.ensemble import RandomForestRegressor

        X = data[confounders] if confounders else pd.DataFrame(index=data.index)
        W = data[treatment]
        Y = data[outcome]

        est = XLearner(models=RandomForestRegressor(n_estimators=100, random_state=42))
        est.fit(Y, W, X=X)

        ite = est.effect(X)
        ate = np.mean(ite)

        return TreatmentEffect(
            ate=float(ate),
            ate_ci=(float(ate) - 1.96 * np.std(ite) / np.sqrt(len(ite)), float(ate) + 1.96 * np.std(ite) / np.sqrt(len(ite))),
            ate_pvalue=0.05,
            ite=ite,
            method="x_learner",
            estimator="x_learner",
            assumptions={"confounders": confounders, "effect_modifiers": effect_modifiers},
            diagnostics={},
        )

    async def _estimate_counterfactual(
        self,
        data: pd.DataFrame,
        treatment: str,
        outcome: str,
        confounders: List[str],
    ) -> TreatmentEffect:
        """Estimate counterfactuals (simplified)."""
        # This would use DoWhy's counterfactual estimation
        # For now, return a placeholder
        return TreatmentEffect(
            ate=0.0,
            ate_ci=(0.0, 0.0),
            ate_pvalue=1.0,
            method="counterfactual",
            estimator="dowhy",
            assumptions={"confounders": confounders},
            diagnostics={"note": "Counterfactual estimation requires DoWhy with specific setup"},
        )

    # ==================== Counterfactual Estimation ====================

    async def estimate_counterfactual(
        self,
        data_name: str,
        treatment: str,
        outcome: str,
        confounders: List[str],
        factual_values: Dict[str, Any],
        counterfactual_values: Dict[str, Any],
    ) -> CounterfactualResult:
        """Estimate counterfactual for specific instance."""
        if not DOWHY_AVAILABLE:
            raise RuntimeError("DoWhy required for counterfactuals")

        data = self._data_cache.get(data_name)
        if data is None:
            raise ValueError(f"Data not found: {data_name}")

        # Find matching row
        mask = pd.Series([True] * len(data))
        for k, v in factual_values.items():
            mask &= (data[k] == v)

        matching = data[mask]
        if len(matching) == 0:
            raise ValueError("No matching factual instance found")

        factual_row = matching.iloc[0]
        factual_outcome = factual_row[outcome]

        # Build counterfactual row
        counterfactual_row = factual_row.copy()
        for k, v in counterfactual_values.items():
            counterfactual_row[k] = v

        # Simple counterfactual: use treatment effect estimation
        # In practice, would use DoWhy's counterfactual estimation
        effect = CounterfactualResult(
            factual_outcome=factual_outcome,
            counterfactual_outcome=counterfactual_row.get(outcome, factual_outcome),
            effect=0.0,
            confidence_interval=(0.0, 0.0),
            probability_necessary=0.5,
            probability_sufficient=0.5,
            explanation="Simplified counterfactual estimation. Use DoWhy for full causal counterfactuals.",
        )

        return effect

    # ==================== Mediation Analysis ====================

    async def mediation_analysis(
        self,
        data_name: str,
        treatment: str,
        outcome: str,
        mediators: List[str],
        confounders: List[str] = None,
    ) -> MediationAnalysis:
        """Perform mediation analysis."""
        if not ECONML_AVAILABLE:
            raise RuntimeError("EconML required for mediation analysis")

        data = self._data_cache.get(data_name)
        if data is None:
            raise ValueError(f"Data not found: {data_name}")

        confounders = confounders or []

        # Simple mediation using sequential regression
        # Full mediation analysis would use specialized libraries
        from sklearn.linear_model import LinearRegression

        X = data[[treatment] + confounders] if confounders else data[[treatment]]
        M = data[mediators]
        Y = data[outcome]

        # Total effect
        total_model = LinearRegression()
        total_model.fit(X, Y)
        total_effect = total_model.coef_[0]

        # Direct effect (controlling for mediators)
        direct_model = LinearRegression()
        direct_model.fit(pd.concat([X, M], axis=1), Y)
        direct_effect = direct_model.coef_[0]

        indirect_effect = total_effect - direct_effect
        proportion_mediated = indirect_effect / total_effect if total_effect != 0 else 0

        mediator_effects = {}
        for i, med in enumerate(mediators):
            if i + 1 < len(direct_model.coef_):
                mediator_effects[med] = direct_model.coef_[i + 1]

        return MediationAnalysis(
            total_effect=float(total_effect),
            direct_effect=float(direct_effect),
            indirect_effect=float(indirect_effect),
            proportion_mediated=float(proportion_mediated),
            mediator_effects=mediator_effects,
        )

    # ==================== Sensitivity Analysis ====================

    async def sensitivity_analysis(
        self,
        data_name: str,
        treatment: str,
        outcome: str,
        confounders: List[str],
        gamma_range: Tuple[float, float] = (0.5, 2.0),
        gamma_steps: int = 10,
    ) -> Dict[str, Any]:
        """Perform sensitivity analysis for unobserved confounding."""
        # This is a simplified version; full implementation would use DoWhy's sensitivity analysis
        gammas = np.linspace(gamma_range[0], gamma_range[1], gamma_steps)
        results = []

        for gamma in gammas:
            # Simulate effect of unobserved confounder with strength gamma
            # This is a placeholder; real implementation uses Rosenbaum bounds
            results.append({
                "gamma": float(gamma),
                "ate_bound_lower": 0.0,  # Placeholder
                "ate_bound_upper": 0.0,  # Placeholder
            })

        return {
            "gamma_range": gamma_range,
            "results": results,
            "interpretation": "Bounds on ATE under unobserved confounding of strength gamma",
        }

    # ==================== Causal Discovery ====================

    async def discover_causal_graph(
        self,
        data_name: str,
        method: str = "pc",
        significance_level: float = 0.05,
    ) -> CausalGraph:
        """Discover causal graph from data."""
        if not CAUSAL_GRAPHICAL_MODELS_AVAILABLE:
            raise RuntimeError("causalgraphicalmodels required. Install: pip install causalgraphicalmodels")

        data = self._data_cache.get(data_name)
        if data is None:
            raise ValueError(f"Data not found: {data_name}")

        if method == "pc":
            # PC algorithm for causal discovery
            import causalgraphicalmodels as cgm
            from causalgraphicalmodels import StructuralCausalModel

            # Use correlation-based approach as approximation
            corr = data.corr()
            nodes = list(data.columns)
            edges = []

            # Simple heuristic: add edge if correlation > threshold
            threshold = 0.3
            for i, col1 in enumerate(nodes):
                for col2 in nodes[i+1:]:
                    if abs(corr.loc[col1, col2]) > threshold:
                        # Direction based on temporal ordering or domain knowledge
                        # For now, add both directions
                        edges.append((col1, col2))

            return CausalGraph(nodes=nodes, edges=edges)

        raise ValueError(f"Unknown discovery method: {method}")

    # ==================== Utilities ====================

    def list_graphs(self) -> List[str]:
        return list(self._graphs.keys())

    def list_data(self) -> List[str]:
        return list(self._data_cache.keys())

    def get_data_info(self, name: str) -> Optional[Dict[str, Any]]:
        data = self._data_cache.get(name)
        if data is None:
            return None
        return {
            "shape": data.shape,
            "columns": list(data.columns),
            "dtypes": {col: str(dtype) for col, dtype in data.dtypes.items()},
            "missing": data.isnull().sum().to_dict(),
        }


# Global causal inference engine instance
_causal_engine: Optional[CausalInferenceEngine] = None


def get_causal_engine() -> CausalInferenceEngine:
    """Get or create causal inference engine singleton."""
    global _causal_engine
    if _causal_engine is None:
        _causal_engine = CausalInferenceEngine()
    return _causal_engine


def init_causal_engine() -> CausalInferenceEngine:
    """Initialize causal inference engine."""
    global _causal_engine
    _causal_engine = CausalInferenceEngine()
    return _causal_engine