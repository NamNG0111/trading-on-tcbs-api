"""
Signal generation system for combining multiple indicators
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Union, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from .base import BaseIndicator, Signal, SignalType, CompositeIndicator, IndicatorResult


class CombinationLogic(Enum):
    """Logic for combining multiple signals"""
    AND = "AND"  # All conditions must be true
    OR = "OR"    # Any condition must be true
    WEIGHTED = "WEIGHTED"  # Weighted combination
    MAJORITY = "MAJORITY"  # Majority vote


@dataclass
class SignalRule:
    """Rule for generating trading signals"""
    name: str
    indicators: List[str]  # Indicator names
    conditions: Dict[str, any]  # Conditions for each indicator
    logic: CombinationLogic = CombinationLogic.AND
    weights: Dict[str, float] = None  # Weights for WEIGHTED logic
    min_strength: float = 0.3  # Minimum signal strength
    
    def __post_init__(self):
        if self.weights is None:
            # Equal weights by default
            self.weights = {ind: 1.0 for ind in self.indicators}


class SignalGenerator:
    """Generate trading signals from multiple indicators"""
    
    def __init__(self):
        self.indicators: Dict[str, BaseIndicator] = {}
        self.rules: List[SignalRule] = []
        self.signal_history: List[Signal] = []
        
    def add_indicator(self, name: str, indicator: BaseIndicator):
        """Add an indicator to the generator"""
        self.indicators[name] = indicator
        
    def add_rule(self, rule: SignalRule):
        """Add a signal generation rule"""
        # Validate that all required indicators are available
        for indicator_name in rule.indicators:
            if indicator_name not in self.indicators:
                raise ValueError(f"Indicator '{indicator_name}' not found")
        self.rules.append(rule)
        
    def generate_signals(self, data: Dict[str, Union[np.ndarray, pd.Series, List[float]]], 
                        current_price: float) -> List[Signal]:
        """
        Generate signals based on current data and rules
        
        Args:
            data: Dictionary mapping indicator names to their input data
            current_price: Current market price
            
        Returns:
            List of generated signals
        """
        # Calculate all indicators
        indicator_results = {}
        for name, indicator in self.indicators.items():
            if name in data:
                result = indicator.calculate(data[name])
                indicator_results[name] = result
        
        # Apply rules to generate signals
        generated_signals = []
        for rule in self.rules:
            signals = self._apply_rule(rule, indicator_results, current_price)
            generated_signals.extend(signals)
            
        # Store in history
        self.signal_history.extend(generated_signals)
        
        return generated_signals
    
    def _apply_rule(self, rule: SignalRule, indicator_results: Dict[str, IndicatorResult], 
                   current_price: float) -> List[Signal]:
        """Apply a specific rule to generate signals"""
        # Get signals from each required indicator
        indicator_signals = {}
        for indicator_name in rule.indicators:
            if indicator_name in indicator_results:
                result = indicator_results[indicator_name]
                indicator_signals[indicator_name] = result.signals
            else:
                indicator_signals[indicator_name] = []
        
        # Check conditions for each indicator
        condition_results = {}
        for indicator_name in rule.indicators:
            condition_results[indicator_name] = self._check_conditions(
                indicator_name, 
                rule.conditions.get(indicator_name, {}),
                indicator_results.get(indicator_name),
                indicator_signals.get(indicator_name, [])
            )
        
        # Combine results based on logic
        return self._combine_conditions(rule, condition_results, current_price)
    
    def _check_conditions(self, indicator_name: str, conditions: Dict[str, any], 
                         result: Optional[IndicatorResult], signals: List[Signal]) -> Dict[str, any]:
        """Check conditions for a specific indicator"""
        if not result or not signals:
            return {'satisfied': False, 'signals': [], 'strength': 0.0}
        
        satisfied_signals = []
        total_strength = 0.0
        
        for signal in signals:
            signal_satisfied = True
            
            # Check signal type condition
            if 'signal_type' in conditions:
                expected_type = conditions['signal_type']
                if isinstance(expected_type, str):
                    expected_type = SignalType(expected_type)
                if signal.signal_type != expected_type:
                    signal_satisfied = False
            
            # Check minimum strength condition
            if 'min_strength' in conditions:
                if signal.strength < conditions['min_strength']:
                    signal_satisfied = False
            
            # Check indicator value conditions (for RSI, etc.)
            if 'value_conditions' in conditions:
                value_conditions = conditions['value_conditions']
                indicator_values = result.values
                
                if isinstance(indicator_values, dict):
                    # Multi-value indicators (like MACD)
                    for key, condition in value_conditions.items():
                        if key in indicator_values:
                            current_value = indicator_values[key][-1] if len(indicator_values[key]) > 0 else 0
                            if not self._evaluate_condition(current_value, condition):
                                signal_satisfied = False
                                break
                else:
                    # Single-value indicators
                    if len(indicator_values) > 0 and not np.isnan(indicator_values[-1]):
                        current_value = indicator_values[-1]
                        if not self._evaluate_condition(current_value, value_conditions):
                            signal_satisfied = False
            
            if signal_satisfied:
                satisfied_signals.append(signal)
                total_strength += signal.strength
        
        return {
            'satisfied': len(satisfied_signals) > 0,
            'signals': satisfied_signals,
            'strength': total_strength / len(satisfied_signals) if satisfied_signals else 0.0
        }
    
    def _evaluate_condition(self, value: float, condition: Dict[str, float]) -> bool:
        """Evaluate a value condition"""
        if 'gt' in condition and value <= condition['gt']:
            return False
        if 'gte' in condition and value < condition['gte']:
            return False
        if 'lt' in condition and value >= condition['lt']:
            return False
        if 'lte' in condition and value > condition['lte']:
            return False
        if 'eq' in condition and value != condition['eq']:
            return False
        return True
    
    def _combine_conditions(self, rule: SignalRule, condition_results: Dict[str, Dict], 
                           current_price: float) -> List[Signal]:
        """Combine condition results based on rule logic"""
        if rule.logic == CombinationLogic.AND:
            return self._combine_and(rule, condition_results, current_price)
        elif rule.logic == CombinationLogic.OR:
            return self._combine_or(rule, condition_results, current_price)
        elif rule.logic == CombinationLogic.WEIGHTED:
            return self._combine_weighted(rule, condition_results, current_price)
        elif rule.logic == CombinationLogic.MAJORITY:
            return self._combine_majority(rule, condition_results, current_price)
        else:
            return []
    
    def _combine_and(self, rule: SignalRule, condition_results: Dict[str, Dict], 
                    current_price: float) -> List[Signal]:
        """Combine using AND logic - all conditions must be satisfied"""
        # Check if all conditions are satisfied
        all_satisfied = all(result['satisfied'] for result in condition_results.values())
        
        if not all_satisfied:
            return []
        
        # Determine overall signal type (majority vote)
        signal_types = []
        total_strength = 0.0
        
        for result in condition_results.values():
            for signal in result['signals']:
                signal_types.append(signal.signal_type)
                total_strength += signal.strength
        
        if not signal_types:
            return []
        
        # Get most common signal type
        from collections import Counter
        most_common_type = Counter(signal_types).most_common(1)[0][0]
        avg_strength = total_strength / len(signal_types)
        
        if avg_strength >= rule.min_strength:
            return [Signal(
                signal_type=most_common_type,
                strength=avg_strength,
                price=current_price,
                timestamp=pd.Timestamp.now(),
                indicator_name=rule.name,
                metadata={
                    'rule_logic': 'AND',
                    'component_signals': len(signal_types),
                    'avg_strength': avg_strength
                }
            )]
        
        return []
    
    def _combine_or(self, rule: SignalRule, condition_results: Dict[str, Dict], 
                   current_price: float) -> List[Signal]:
        """Combine using OR logic - any condition can be satisfied"""
        satisfied_results = [result for result in condition_results.values() if result['satisfied']]
        
        if not satisfied_results:
            return []
        
        # Get the strongest signal
        best_strength = 0.0
        best_signal_type = SignalType.HOLD
        
        for result in satisfied_results:
            if result['strength'] > best_strength:
                best_strength = result['strength']
                for signal in result['signals']:
                    if signal.strength == result['strength']:
                        best_signal_type = signal.signal_type
                        break
        
        if best_strength >= rule.min_strength:
            return [Signal(
                signal_type=best_signal_type,
                strength=best_strength,
                price=current_price,
                timestamp=pd.Timestamp.now(),
                indicator_name=rule.name,
                metadata={
                    'rule_logic': 'OR',
                    'best_strength': best_strength,
                    'satisfied_conditions': len(satisfied_results)
                }
            )]
        
        return []
    
    def _combine_weighted(self, rule: SignalRule, condition_results: Dict[str, Dict], 
                         current_price: float) -> List[Signal]:
        """Combine using weighted logic"""
        weighted_scores = {SignalType.BUY: 0.0, SignalType.SELL: 0.0, SignalType.HOLD: 0.0}
        total_weight = 0.0
        
        for indicator_name, result in condition_results.items():
            if result['satisfied']:
                weight = rule.weights.get(indicator_name, 1.0)
                for signal in result['signals']:
                    weighted_scores[signal.signal_type] += signal.strength * weight
                total_weight += weight
        
        if total_weight == 0:
            return []
        
        # Normalize scores
        for signal_type in weighted_scores:
            weighted_scores[signal_type] /= total_weight
        
        # Get the highest scoring signal type
        best_type = max(weighted_scores, key=weighted_scores.get)
        best_score = weighted_scores[best_type]
        
        if best_score >= rule.min_strength:
            return [Signal(
                signal_type=best_type,
                strength=best_score,
                price=current_price,
                timestamp=pd.Timestamp.now(),
                indicator_name=rule.name,
                metadata={
                    'rule_logic': 'WEIGHTED',
                    'weighted_scores': weighted_scores,
                    'total_weight': total_weight
                }
            )]
        
        return []
    
    def _combine_majority(self, rule: SignalRule, condition_results: Dict[str, Dict], 
                         current_price: float) -> List[Signal]:
        """Combine using majority vote logic"""
        signal_votes = {SignalType.BUY: 0, SignalType.SELL: 0, SignalType.HOLD: 0}
        total_strength = 0.0
        vote_count = 0
        
        for result in condition_results.values():
            if result['satisfied']:
                for signal in result['signals']:
                    signal_votes[signal.signal_type] += 1
                    total_strength += signal.strength
                    vote_count += 1
        
        if vote_count == 0:
            return []
        
        # Get majority vote
        max_votes = max(signal_votes.values())
        if max_votes <= vote_count // 2:  # No clear majority
            return []
        
        majority_type = max(signal_votes, key=signal_votes.get)
        avg_strength = total_strength / vote_count
        
        if avg_strength >= rule.min_strength:
            return [Signal(
                signal_type=majority_type,
                strength=avg_strength,
                price=current_price,
                timestamp=pd.Timestamp.now(),
                indicator_name=rule.name,
                metadata={
                    'rule_logic': 'MAJORITY',
                    'votes': signal_votes,
                    'majority_votes': max_votes,
                    'total_votes': vote_count
                }
            )]
        
        return []
    
    def get_signal_history(self, limit: int = 100) -> List[Signal]:
        """Get recent signal history"""
        return self.signal_history[-limit:] if limit else self.signal_history
    
    def clear_history(self):
        """Clear signal history"""
        self.signal_history.clear()


# Predefined signal rules for common strategies
class CommonSignalRules:
    """Common signal generation rules"""
    
    @staticmethod
    def rsi_oversold_overbought(rsi_period: int = 14, oversold: float = 30, 
                               overbought: float = 70) -> SignalRule:
        """RSI oversold/overbought rule"""
        return SignalRule(
            name=f"RSI_{rsi_period}_OB_OS",
            indicators=["RSI"],
            conditions={
                "RSI": {
                    "signal_type": [SignalType.BUY, SignalType.SELL],
                    "min_strength": 0.3,
                    "value_conditions": {
                        "lte": overbought,  # For sell signals
                        "gte": oversold     # For buy signals
                    }
                }
            },
            logic=CombinationLogic.OR,
            min_strength=0.3
        )
    
    @staticmethod
    def rsi_ma_combo(rsi_period: int = 14, ma_period: int = 20, 
                     rsi_oversold: float = 30, rsi_overbought: float = 70) -> SignalRule:
        """RSI + Moving Average combination rule"""
        return SignalRule(
            name=f"RSI_{rsi_period}_MA_{ma_period}_COMBO",
            indicators=["RSI", "SMA"],
            conditions={
                "RSI": {
                    "signal_type": [SignalType.BUY, SignalType.SELL],
                    "min_strength": 0.2
                },
                "SMA": {
                    "signal_type": [SignalType.BUY, SignalType.SELL],
                    "min_strength": 0.2
                }
            },
            logic=CombinationLogic.AND,
            min_strength=0.4
        )
    
    @staticmethod
    def macd_signal_line_cross() -> SignalRule:
        """MACD signal line crossover rule"""
        return SignalRule(
            name="MACD_SIGNAL_CROSS",
            indicators=["MACD"],
            conditions={
                "MACD": {
                    "signal_type": [SignalType.BUY, SignalType.SELL],
                    "min_strength": 0.3
                }
            },
            logic=CombinationLogic.OR,
            min_strength=0.3
        )
