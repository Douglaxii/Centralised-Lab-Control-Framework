"""
Profile storage for optimization results.

Manages loading_profiles.json which stores optimal parameters
for each target ion number and configuration.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger("optimizer.storage")


@dataclass
class LoadingProfile:
    """Profile for a specific loading configuration."""
    # Metadata
    profile_id: str
    created_at: str
    updated_at: str
    
    # Target configuration
    target_be_count: int
    target_hd_present: bool
    
    # Optimal parameters (Phase I: Be+ Loading)
    be_loading_params: Dict[str, float]
    be_loading_cost: float
    be_loading_iterations: int
    
    # Optimal parameters (Phase II: Be+ Ejection)
    be_ejection_params: Optional[Dict[str, float]]
    be_ejection_cost: Optional[float]
    
    # Optimal parameters (Phase III: HD+ Loading)
    hd_loading_params: Optional[Dict[str, float]]
    hd_loading_cost: Optional[float]
    hd_loading_iterations: Optional[int]
    
    # Performance metrics
    success_rate: float
    avg_cycle_time_ms: float
    best_pi_duration_ms: float
    
    # Validation
    validated: bool = False
    validation_notes: str = ""


class ProfileStorage:
    """
    Manages loading profiles storage in JSON format.
    
    File structure (loading_profiles.json):
    {
        "version": "1.0",
        "last_updated": "2024-01-15T10:30:00",
        "profiles": {
            "be_1": {
                "target_be_count": 1,
                "target_hd_present": false,
                ...
            },
            "be_1_hd": {
                "target_be_count": 1,
                "target_hd_present": true,
                ...
            }
        }
    }
    """
    
    DEFAULT_FILENAME = "loading_profiles.json"
    
    def __init__(self, filepath: Optional[str] = None):
        """
        Initialize profile storage.
        
        Args:
            filepath: Path to JSON file (default: data/loading_profiles.json)
        """
        if filepath is None:
            # Default location in project data directory
            project_root = Path(__file__).parent.parent.parent
            filepath = project_root / "data" / self.DEFAULT_FILENAME
        
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        
        self._data: Dict[str, Any] = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "profiles": {}
        }
        
        self._load()
        
        logger.info(f"ProfileStorage initialized: {self.filepath}")
    
    def _load(self):
        """Load profiles from file."""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r') as f:
                    self._data = json.load(f)
                logger.info(f"Loaded {len(self._data.get('profiles', {}))} profiles")
            except Exception as e:
                logger.error(f"Failed to load profiles: {e}")
                self._data = {
                    "version": "1.0",
                    "last_updated": datetime.now().isoformat(),
                    "profiles": {}
                }
    
    def _save(self):
        """Save profiles to file."""
        self._data["last_updated"] = datetime.now().isoformat()
        
        try:
            with open(self.filepath, 'w') as f:
                json.dump(self._data, f, indent=2, default=str)
            logger.debug("Profiles saved")
        except Exception as e:
            logger.error(f"Failed to save profiles: {e}")
    
    def _make_key(self, be_count: int, hd_present: bool) -> str:
        """Create profile key from configuration."""
        if hd_present:
            return f"be_{be_count}_hd"
        else:
            return f"be_{be_count}"
    
    def get_profile(
        self,
        be_count: int,
        hd_present: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get profile for a specific configuration.
        
        Args:
            be_count: Target Be+ ion count
            hd_present: Whether HD+ should be present
            
        Returns:
            Profile dictionary or None if not found
        """
        key = self._make_key(be_count, hd_present)
        profile = self._data.get("profiles", {}).get(key)
        
        if profile:
            logger.debug(f"Found profile for {key}")
        else:
            logger.debug(f"No profile found for {key}")
        
        return profile
    
    def save_profile(
        self,
        be_count: int,
        hd_present: bool,
        phase: str,
        params: Dict[str, float],
        cost: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Save/update profile for a specific phase.
        
        Args:
            be_count: Target Be+ count
            hd_present: Whether HD+ is present
            phase: One of "be_loading", "be_ejection", "hd_loading"
            params: Optimal parameters
            cost: Best cost achieved
            metadata: Additional metadata
        """
        key = self._make_key(be_count, hd_present)
        
        # Get existing profile or create new
        profile = self._data.get("profiles", {}).get(key, {})
        
        # Update metadata
        now = datetime.now().isoformat()
        if "created_at" not in profile:
            profile["created_at"] = now
        profile["updated_at"] = now
        profile["target_be_count"] = be_count
        profile["target_hd_present"] = hd_present
        
        # Update phase-specific data
        if phase == "be_loading":
            profile["be_loading_params"] = params
            profile["be_loading_cost"] = cost
            profile["be_loading_iterations"] = metadata.get("iterations", 0) if metadata else 0
            profile["best_pi_duration_ms"] = params.get("be_pi_laser_duration_ms", 500.0)
            
        elif phase == "be_ejection":
            profile["be_ejection_params"] = params
            profile["be_ejection_cost"] = cost
            
        elif phase == "hd_loading":
            profile["hd_loading_params"] = params
            profile["hd_loading_cost"] = cost
            profile["hd_loading_iterations"] = metadata.get("iterations", 0) if metadata else 0
        
        # Update general metadata
        if metadata:
            if "success_rate" in metadata:
                profile["success_rate"] = metadata["success_rate"]
            if "avg_cycle_time_ms" in metadata:
                profile["avg_cycle_time_ms"] = metadata["avg_cycle_time_ms"]
            if "validated" in metadata:
                profile["validated"] = metadata["validated"]
            if "validation_notes" in metadata:
                profile["validation_notes"] = metadata["validation_notes"]
        
        # Save back
        if "profiles" not in self._data:
            self._data["profiles"] = {}
        self._data["profiles"][key] = profile
        
        self._save()
        logger.info(f"Saved profile for {key}, phase={phase}")
    
    def get_be_loading_params(
        self,
        be_count: int,
        hd_present: bool = False
    ) -> Optional[Dict[str, float]]:
        """Get Be+ loading parameters for a configuration."""
        profile = self.get_profile(be_count, hd_present)
        if profile:
            return profile.get("be_loading_params")
        return None
    
    def get_be_ejection_params(
        self,
        be_count: int
    ) -> Optional[Dict[str, float]]:
        """Get Be+ ejection parameters."""
        # Ejection is always from overload to target
        # Find a profile with more ions
        for key, profile in self._data.get("profiles", {}).items():
            if profile.get("target_be_count", 0) > be_count:
                return profile.get("be_ejection_params")
        return None
    
    def get_hd_loading_params(
        self,
        be_count: int = 1
    ) -> Optional[Dict[str, float]]:
        """Get HD+ loading parameters."""
        profile = self.get_profile(be_count, hd_present=True)
        if profile:
            return profile.get("hd_loading_params")
        return None
    
    def list_profiles(self) -> List[Dict[str, Any]]:
        """List all profiles."""
        return [
            {"key": k, **v}
            for k, v in self._data.get("profiles", {}).items()
        ]
    
    def delete_profile(self, be_count: int, hd_present: bool = False) -> bool:
        """Delete a profile."""
        key = self._make_key(be_count, hd_present)
        
        if key in self._data.get("profiles", {}):
            del self._data["profiles"][key]
            self._save()
            logger.info(f"Deleted profile {key}")
            return True
        return False
    
    def get_best_params_for_phase(
        self,
        phase: str,
        be_count: int = 1,
        hd_present: bool = False
    ) -> Optional[Dict[str, float]]:
        """
        Get best known parameters for a phase.
        
        Args:
            phase: One of "be_loading", "be_ejection", "hd_loading"
            be_count: Target Be+ count
            hd_present: Whether HD+ should be present
            
        Returns:
            Parameter dictionary or None
        """
        profile = self.get_profile(be_count, hd_present)
        
        if not profile:
            return None
        
        if phase == "be_loading":
            return profile.get("be_loading_params")
        elif phase == "be_ejection":
            return profile.get("be_ejection_params")
        elif phase == "hd_loading":
            return profile.get("hd_loading_params")
        
        return None
    
    def export_to_dict(self) -> Dict[str, Any]:
        """Export all data as dictionary."""
        return self._data.copy()
    
    def import_from_dict(self, data: Dict[str, Any]):
        """Import profiles from dictionary."""
        self._data = data
        self._save()
        logger.info("Profiles imported")
