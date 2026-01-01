"""
Fibridge Algorithm: Core Implementation

This module implements the Fibridge elimination operators and state space framework.
"""

from abc import ABC, abstractmethod
from typing import Set, Callable, List, Tuple, Optional, Any
import numpy as np
from dataclasses import dataclass


@dataclass
class IterationResult:
    """Results from one iteration of Fibridge elimination"""
    iteration: int
    state_count: int
    states_removed: int
    converged: bool
    metadata: dict


class StateSpace(ABC):
    """Abstract base class for state spaces"""
    
    @abstractmethod
    def get_all_states(self) -> Set[Any]:
        """Return all possible states in the space"""
        pass
    
    @abstractmethod
    def state_to_string(self, state: Any) -> str:
        """Convert state to human-readable string"""
        pass
    
    def state_count(self) -> int:
        """Return total number of states"""
        return len(self.get_all_states())


class DiscreteStateSpace(StateSpace):
    """Discrete state space implementation"""
    
    def __init__(self, states: Set[Any]):
        self.states = states
    
    def get_all_states(self) -> Set[Any]:
        return self.states
    
    def state_to_string(self, state: Any) -> str:
        return str(state)


class ContinuousStateSpace(StateSpace):
    """Continuous state space with discretization"""
    
    def __init__(self, bounds: List[Tuple[float, float]], resolution: int = 50):
        """
        Args:
            bounds: List of (min, max) for each dimension
            resolution: Number of grid points per dimension
        """
        self.bounds = bounds
        self.resolution = resolution
        self.dimension = len(bounds)
        self._generate_grid()
    
    def _generate_grid(self):
        """Generate discretized grid of states"""
        grids = [np.linspace(b[0], b[1], self.resolution) for b in self.bounds]
        mesh = np.meshgrid(*grids, indexing='ij')
        points = np.stack([m.flatten() for m in mesh], axis=1)
        self.states = set(map(tuple, points))
    
    def get_all_states(self) -> Set[Tuple[float, ...]]:
        return self.states
    
    def state_to_string(self, state: Tuple[float, ...]) -> str:
        return f"({', '.join(f'{x:.3f}' for x in state)})"


class ForbiddenSetRule:
    """Encodes a rule for identifying forbidden states"""
    
    def __init__(self, predicate: Callable[[Any], bool], name: str = ""):
        """
        Args:
            predicate: Function that returns True if state is forbidden
            name: Human-readable name for this rule
        """
        self.predicate = predicate
        self.name = name or "UnnamedRule"
    
    def is_forbidden(self, state: Any) -> bool:
        """Check if a state is forbidden by this rule"""
        return self.predicate(state)
    
    def get_forbidden_set(self, states: Set[Any]) -> Set[Any]:
        """Return all forbidden states from a given set"""
        return {s for s in states if self.is_forbidden(s)}


class TransitionRelation:
    """Defines transitions between states for reachability analysis"""
    
    def __init__(self, transition_fn: Callable[[Any, Any], bool]):
        """
        Args:
            transition_fn: Returns True if transition from state1 to state2 is possible
        """
        self.transition_fn = transition_fn
    
    def can_reach(self, from_state: Any, to_state: Any) -> bool:
        """Check if to_state is reachable from from_state in one step"""
        return self.transition_fn(from_state, to_state)
    
    def forward_reachable(self, states: Set[Any], forbidden: Set[Any]) -> Set[Any]:
        """Return states that can reach forbidden states in one step"""
        reachable = set()
        for s in states:
            for f in forbidden:
                if self.can_reach(s, f):
                    reachable.add(s)
                    break
        return reachable
    
    def backward_reachable(self, states: Set[Any], forbidden: Set[Any]) -> Set[Any]:
        """Return states from which forbidden states are reachable in one step"""
        return self.forward_reachable(states, forbidden)


class FibridgeOperator:
    """Implements Fibridge elimination operators"""
    
    def __init__(
        self,
        state_space: StateSpace,
        forbidden_rules: List[ForbiddenSetRule],
        transition: Optional[TransitionRelation] = None,
        variant: str = "fixed"
    ):
        """
        Args:
            state_space: The state space to operate on
            forbidden_rules: List of rules defining forbidden states
            transition: Transition relation for reachability (required for evolving variant)
            variant: "fixed" or "evolving"
        """
        self.state_space = state_space
        self.forbidden_rules = forbidden_rules
        self.transition = transition
        self.variant = variant
        
        if variant == "evolving" and transition is None:
            raise ValueError("Evolving variant requires a TransitionRelation")
        
        # Initialize with all states
        self.current_states = state_space.get_all_states()
        self.iteration = 0
        self.history: List[IterationResult] = []
    
    def get_forbidden_states(self, states: Set[Any]) -> Set[Any]:
        """Get all states forbidden by any rule"""
        forbidden = set()
        for rule in self.forbidden_rules:
            forbidden.update(rule.get_forbidden_set(states))
        return forbidden
    
    def iterate_fixed(self) -> IterationResult:
        """Perform one iteration of fixed variant (viability kernel)"""
        initial_count = len(self.current_states)
        
        # Get base forbidden set
        forbidden = self.get_forbidden_states(self.current_states)
        
        # Remove states that can reach forbidden states
        if self.transition:
            reachable_to_forbidden = self.transition.backward_reachable(
                self.current_states, forbidden
            )
            to_remove = forbidden.union(reachable_to_forbidden)
        else:
            to_remove = forbidden
        
        self.current_states = self.current_states - to_remove
        
        removed_count = initial_count - len(self.current_states)
        converged = removed_count == 0
        
        result = IterationResult(
            iteration=self.iteration,
            state_count=len(self.current_states),
            states_removed=removed_count,
            converged=converged,
            metadata={"forbidden_count": len(forbidden)}
        )
        
        self.iteration += 1
        self.history.append(result)
        return result
    
    def iterate_evolving(self) -> IterationResult:
        """Perform one iteration of evolving variant"""
        initial_count = len(self.current_states)
        
        # Get currently forbidden states
        forbidden = self.get_forbidden_states(self.current_states)
        
        # Expand forbidden set by forward reachability
        new_forbidden = self.transition.forward_reachable(
            self.current_states, forbidden
        )
        
        total_forbidden = forbidden.union(new_forbidden)
        self.current_states = self.current_states - total_forbidden
        
        removed_count = initial_count - len(self.current_states)
        converged = removed_count == 0
        
        result = IterationResult(
            iteration=self.iteration,
            state_count=len(self.current_states),
            states_removed=removed_count,
            converged=converged,
            metadata={
                "base_forbidden": len(forbidden),
                "newly_forbidden": len(new_forbidden)
            }
        )
        
        self.iteration += 1
        self.history.append(result)
        return result
    
    def iterate(self) -> IterationResult:
        """Perform one iteration using selected variant"""
        if self.variant == "fixed":
            return self.iterate_fixed()
        elif self.variant == "evolving":
            return self.iterate_evolving()
        else:
            raise ValueError(f"Unknown variant: {self.variant}")
    
    def run_until_convergence(self, max_iterations: int = 1000) -> List[IterationResult]:
        """Run iterations until convergence or max_iterations reached"""
        results = []
        for _ in range(max_iterations):
            result = self.iterate()
            results.append(result)
            
            if result.converged:
                print(f"Converged after {result.iteration + 1} iterations")
                break
            
            if len(self.current_states) == 0:
                print("All states eliminated!")
                break
        else:
            print(f"Max iterations ({max_iterations}) reached without convergence")
        
        return results
    
    def get_final_states(self) -> Set[Any]:
        """Return the current allowed state set S*"""
        return self.current_states
    
    def get_statistics(self) -> dict:
        """Return statistics about the elimination process"""
        if not self.history:
            return {}
        
        initial_states = self.state_space.state_count()
        final_states = len(self.current_states)
        
        return {
            "initial_state_count": initial_states,
            "final_state_count": final_states,
            "states_eliminated": initial_states - final_states,
            "elimination_ratio": (initial_states - final_states) / initial_states,
            "iterations": len(self.history),
            "converged": self.history[-1].converged if self.history else False
        }


def analyze_emergence(
    final_states: Set[Any],
    dimension: int,
    tolerance: float = 0.01
) -> dict:
    """
    Analyze emergent structure in final state set.
    
    Returns information about manifold structure, conservation laws, etc.
    """
    if not final_states:
        return {"emergent_structure": "empty"}
    
    # Convert to numpy array for analysis
    states_array = np.array([list(s) if isinstance(s, tuple) else [s] for s in final_states])
    
    if len(states_array.shape) == 1:
        states_array = states_array.reshape(-1, 1)
    
    analysis = {}
    
    # Check for manifold structure (via PCA)
    if states_array.shape[0] > dimension:
        cov = np.cov(states_array.T)
        eigenvalues = np.linalg.eigvalsh(cov)
        eigenvalues = eigenvalues[::-1]  # Sort descending
        
        # Intrinsic dimensionality
        total_var = eigenvalues.sum()
        explained_var = np.cumsum(eigenvalues) / total_var
        intrinsic_dim = np.argmax(explained_var > 0.95) + 1
        
        analysis["intrinsic_dimension"] = int(intrinsic_dim)
        analysis["eigenvalues"] = eigenvalues.tolist()
        analysis["ambient_dimension"] = dimension
    
    # Check for conservation laws (constant functions)
    if states_array.shape[0] > 1:
        means = states_array.mean(axis=0)
        stds = states_array.std(axis=0)
        
        conserved_dims = []
        for i, std in enumerate(stds):
            if std < tolerance:
                conserved_dims.append({
                    "dimension": i,
                    "conserved_value": float(means[i]),
                    "variance": float(std**2)
                })
        
        analysis["conserved_quantities"] = conserved_dims
    
    return analysis
