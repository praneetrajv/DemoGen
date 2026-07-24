"""
Action Planner Module
Converts LLM-generated action plans into structured executable steps
"""

import sys
from pathlib import Path
from typing import List, Dict
import json
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

logger = logging.getLogger(__name__)


class ActionPlanner:
    """Plans and structures automation actions"""
    
    VALID_ACTIONS = [
        "navigate", "click", "fill", "screenshot",
        "scroll", "wait", "press", "hover", "select"
    ]
    
    def __init__(self):
        """Initialize action planner"""
        self.actions = []
    
    def parse_llm_plan(self, llm_output: str) -> List[Dict]:
        """
        Parse LLM-generated plan into structured actions
        
        Args:
            llm_output: Raw text from LLM
            
        Returns:
            List of structured actions
        """
        try:
            # Try to extract JSON from LLM output
            actions = self._extract_actions_from_text(llm_output)
            
            # Validate and normalize actions
            validated_actions = []
            for action in actions:
                validated = self._validate_action(action)
                if validated:
                    validated_actions.append(validated)
            
            self.actions = validated_actions
            logger.info(f"Parsed {len(validated_actions)} actions from LLM output")
            
            return validated_actions
        except Exception as e:
            logger.error(f"Failed to parse LLM plan: {e}")
            return []
    
    def _extract_actions_from_text(self, text: str) -> List[Dict]:
        """Extract action objects from text"""
        # Try to parse JSON array first
        try:
            raw = text.strip()
            if raw.startswith("["):
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass

        # Try to extract a JSON array from mixed content
        try:
            import re
            json_match = re.search(r"\[[\s\S]*\]", text)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass

        actions = []
        lines = text.split('\n')
        
        # First try to find structured action definitions
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Look for action markers (navigate, click, fill, etc.)
            if any(action in line.lower() for action in self.VALID_ACTIONS):
                action = self._parse_action_line(line)
                if action:
                    actions.append(action)
        
        # If no structured actions found, convert text into steps
        if not actions:
            actions = self._convert_text_to_actions(text)
        
        return actions if actions else self._create_fallback_actions()
    
    def _convert_text_to_actions(self, text: str) -> List[Dict]:
        """Convert free-form text into action steps"""
        actions = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines and section headers
            if not line or line.startswith('#') or line.startswith('='):
                continue
            
            # Remove numbering/bullets
            clean_line = line
            for prefix in ['1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.',
                          'Step 1:', 'Step 2:', 'Step 3:', '- ', '* ']:
                if clean_line.startswith(prefix):
                    clean_line = clean_line[len(prefix):].strip()
                    break
            
            if not clean_line:
                continue
            
            # Determine action type from content
            action_type = 'click'  # default
            if 'navigate' in clean_line.lower() or 'go to' in clean_line.lower() or 'open' in clean_line.lower():
                action_type = 'navigate'
            elif 'fill' in clean_line.lower() or 'enter' in clean_line.lower() or 'type' in clean_line.lower():
                action_type = 'fill'
            elif 'scroll' in clean_line.lower():
                action_type = 'scroll'
            elif 'wait' in clean_line.lower():
                action_type = 'wait'
            elif 'screenshot' in clean_line.lower() or 'capture' in clean_line.lower():
                action_type = 'screenshot'
            
            # Create action
            action = {
                'action_type': action_type,
                'selector': '',
                'value': '',
                'description': clean_line[:100],  # Truncate long descriptions
                'wait_ms': 1000,
                'status': 'pending'
            }
            
            actions.append(action)
        
        return actions
    
    def _parse_action_line(self, line: str) -> Dict:
        """Parse a single action line"""
        try:
            # Try JSON first
            if line.startswith('{'):
                return json.loads(line)
            
            # Otherwise, try to extract key-value pairs
            action = {}
            
            for action_type in self.VALID_ACTIONS:
                if action_type in line.lower():
                    action['action_type'] = action_type
                    break
            
            if 'action_type' not in action:
                return None
            
            # Extract selector if present
            if 'selector:' in line:
                selector = line.split('selector:')[1].split(',')[0].strip().strip("'\"")
                action['selector'] = selector
            
            # Extract value if present
            if 'value:' in line:
                value = line.split('value:')[1].split(',')[0].strip().strip("'\"")
                action['value'] = value
            
            action['description'] = line
            action['wait_ms'] = 500
            
            return action
        except:
            return None
    
    def _validate_action(self, action: Dict) -> Dict:
        """Validate and normalize an action"""
        if not isinstance(action, dict):
            return None
        
        action_type = action.get('action_type', '').lower()
        
        if action_type not in self.VALID_ACTIONS:
            return None
        
        # Normalize action
        wait_ms_raw = action.get('wait_ms', action.get('wait_time', action.get('time', 500)))
        try:
            wait_ms = min(int(wait_ms_raw), 5000)
        except Exception:
            wait_ms = 500

        normalized = {
            'action_type': action_type,
            'selector': action.get('selector', ''),
            'value': action.get('value', ''),
            'description': action.get('description', action_type),
            'wait_ms': wait_ms,  # Cap at 5s
            'status': 'pending'
        }

        # Preserve fields the executor needs for specific action types.
        if action.get('url'):
            normalized['url'] = action['url']
        if action.get('key'):
            normalized['key'] = action['key']

        return normalized
    
    def _create_fallback_actions(self) -> List[Dict]:
        """Create fallback actions based on common demo scenarios"""
        return [
            {
                'action_type': 'navigate',
                'selector': '',
                'value': '',
                'description': 'Navigate to NeevCloud portal',
                'wait_ms': 2000,
                'status': 'pending'
            },
            {
                'action_type': 'click',
                'selector': '',
                'value': '',
                'description': 'Click on Projects section in the dashboard',
                'wait_ms': 1000,
                'status': 'pending'
            },
            {
                'action_type': 'click',
                'selector': '',
                'value': '',
                'description': 'Click on New Project button to create a new project',
                'wait_ms': 500,
                'status': 'pending'
            },
            {
                'action_type': 'fill',
                'selector': '',
                'value': 'My Demo Project',
                'description': 'Enter project name in the project name field',
                'wait_ms': 500,
                'status': 'pending'
            },
            {
                'action_type': 'fill',
                'selector': '',
                'value': 'This is a demonstration project created to show NeevCloud capabilities',
                'description': 'Enter project description in the description field',
                'wait_ms': 500,
                'status': 'pending'
            },
            {
                'action_type': 'click',
                'selector': '',
                'value': '',
                'description': 'Select project type from the dropdown menu',
                'wait_ms': 500,
                'status': 'pending'
            },
            {
                'action_type': 'click',
                'selector': '',
                'value': '',
                'description': 'Review project settings and configuration options',
                'wait_ms': 1000,
                'status': 'pending'
            },
            {
                'action_type': 'click',
                'selector': '',
                'value': '',
                'description': 'Click Create Project button to finalize project creation',
                'wait_ms': 2000,
                'status': 'pending'
            },
            {
                'action_type': 'screenshot',
                'selector': '',
                'value': '',
                'description': 'Project created successfully - showing project dashboard',
                'wait_ms': 1000,
                'status': 'pending'
            },
            {
                'action_type': 'click',
                'selector': '',
                'value': '',
                'description': 'View project settings and configuration options',
                'wait_ms': 500,
                'status': 'pending'
            }
        ]
    
    def add_action(self, action_type: str, selector: str = '', value: str = '',
                   description: str = '', wait_ms: int = 500) -> Dict:
        """Add a manual action"""
        action = {
            'action_type': action_type,
            'selector': selector,
            'value': value,
            'description': description or action_type,
            'wait_ms': min(wait_ms, 5000),
            'status': 'pending'
        }
        
        if self._validate_action(action):
            self.actions.append(action)
            return action
        
        return None
    
    def get_actions(self) -> List[Dict]:
        """Get all planned actions"""
        return self.actions
    
    def clear_actions(self):
        """Clear all actions"""
        self.actions = []
    
    def estimate_duration(self) -> float:
        """Estimate total execution time in seconds"""
        total_ms = sum(action.get('wait_ms', 500) for action in self.actions)
        # Add buffer for actual execution
        return (total_ms / 1000) + (len(self.actions) * 0.2)  # 0.2s per action
