"""
UI Drift Detector
Detects UI changes that require video regeneration
"""

import sys
from pathlib import Path
from typing import Dict, List
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detects UI changes and determines regeneration necessity"""
    
    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize drift detector
        
        Args:
            similarity_threshold: Minimum similarity to avoid regeneration (0-1)
        """
        self.similarity_threshold = similarity_threshold
        self.detection_log = []
    
    def analyze_drift(self, drift_analysis: dict) -> dict:
        """
        Analyze drift and recommend action
        
        Args:
            drift_analysis: Output from compare_snapshots
            
        Returns:
            Action recommendation
        """
        recommendation = {
            "feature": drift_analysis.get("feature_name"),
            "drift_detected": drift_analysis.get("drift_detected"),
            "drift_items": drift_analysis.get("drift_items", []),
            "similarity_score": drift_analysis.get("similarity_score", 1.0),
            "action": None,
            "reason": None
        }
        
        if not drift_analysis.get("drift_detected"):
            recommendation["action"] = "no_action"
            recommendation["reason"] = "No drift detected"
        else:
            similarity_score = drift_analysis.get("similarity_score", 0)
            
            if similarity_score < self.similarity_threshold:
                recommendation["action"] = "regenerate_video"
                recommendation["reason"] = f"Similarity score {similarity_score:.2f} below threshold {self.similarity_threshold}"
                
                # Analyze severity
                high_severity = any(item.get("severity") == "high" for item in drift_analysis.get("drift_items", []))
                if high_severity:
                    recommendation["priority"] = "high"
                else:
                    recommendation["priority"] = "normal"
            else:
                recommendation["action"] = "monitor"
                recommendation["reason"] = "Minor changes detected, continue monitoring"
                recommendation["priority"] = "low"
        
        self.detection_log.append(recommendation)
        logger.info(f"Drift analysis: {recommendation['action']}")
        
        return recommendation
    
    def should_regenerate(self, drift_analysis: dict) -> bool:
        """
        Determine if video regeneration is needed
        
        Args:
            drift_analysis: Output from compare_snapshots
            
        Returns:
            True if regeneration needed
        """
        recommendation = self.analyze_drift(drift_analysis)
        return recommendation["action"] == "regenerate_video"
    
    def get_affected_elements(self, drift_items: List[Dict]) -> List[str]:
        """
        Extract affected element selectors from drift items
        
        Args:
            drift_items: List of drift detection items
            
        Returns:
            List of affected element selectors
        """
        affected = []
        
        for item in drift_items:
            if item.get("type") == "element_moved":
                affected.append(f"moved: {item.get('element', 'unknown')}")
            elif item.get("type") in ["element_removed", "element_added"]:
                affected.append(f"{item.get('type')}: {item.get('element', 'unknown')}")
        
        return affected
    
    def estimate_impact(self, drift_items: List[Dict]) -> str:
        """
        Estimate impact level of drift
        
        Args:
            drift_items: List of drift detection items
            
        Returns:
            Impact level: "low", "medium", "high", "critical"
        """
        if not drift_items:
            return "low"
        
        high_severity_count = sum(1 for item in drift_items if item.get("severity") == "high")
        medium_severity_count = sum(1 for item in drift_items if item.get("severity") == "medium")
        
        if high_severity_count > 0:
            return "critical" if high_severity_count > 2 else "high"
        elif medium_severity_count > 3:
            return "high"
        elif medium_severity_count > 0:
            return "medium"
        
        return "low"
    
    def generate_report(self, feature_name: str, old_snapshot: dict, 
                       new_snapshot: dict, drift_analysis: dict) -> dict:
        """
        Generate comprehensive drift report
        
        Args:
            feature_name: Feature name
            old_snapshot: Previous DOM snapshot
            new_snapshot: Current DOM snapshot
            drift_analysis: Drift analysis results
            
        Returns:
            Comprehensive report
        """
        recommendation = self.analyze_drift(drift_analysis)
        affected_elements = self.get_affected_elements(drift_analysis.get("drift_items", []))
        impact = self.estimate_impact(drift_analysis.get("drift_items", []))
        
        report = {
            "feature": feature_name,
            "timestamp": new_snapshot.get("timestamp"),
            "old_snapshot_hash": old_snapshot.get("dom_hash", ""),
            "new_snapshot_hash": new_snapshot.get("dom_hash", ""),
            "drift_detected": drift_analysis.get("drift_detected"),
            "similarity_score": drift_analysis.get("similarity_score", 1.0),
            "drift_count": len(drift_analysis.get("drift_items", [])),
            "affected_elements": affected_elements,
            "impact_level": impact,
            "recommendation": recommendation["action"],
            "priority": recommendation.get("priority", "normal"),
            "reason": recommendation["reason"]
        }
        
        return report
