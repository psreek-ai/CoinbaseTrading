import logging
import os
import json
import requests
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class AIAnalyst:
    """
    AI Analyst that uses OpenRouter (Grok, etc.) to analyze trading performance and recommend strategies.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize AI Analyst.
        
        Args:
            config: AI analysis configuration
        """
        self.config = config
        self.api_key = os.environ.get('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1"
        self.model_name = config.get('model', 'x-ai/grok-4.1-fast')
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not found in environment variables. AI analysis will be disabled.")
            self.enabled = False
        else:
            self.enabled = config.get('enabled', True)
            logger.info(f"AI Analyst initialized with model: {self.model_name}")

    def analyze_performance(self, performance_data: Dict, market_context: Dict) -> Optional[Dict]:
        """
        Analyze strategy performance and market context to recommend a strategy.
        
        Args:
            performance_data: Dictionary of strategy performance metrics
            market_context: Dictionary of current market conditions (volatility, trend, etc.)
            
        Returns:
            Dictionary containing recommendation (strategy_name, confidence, reasoning)
        """
        if not self.enabled:
            return None
            
        try:
            prompt = self._construct_prompt(performance_data, market_context)
            
            logger.info(f"Requesting AI analysis from {self.model_name}...")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/coinbase-trading-bot", # Optional, for OpenRouter rankings
                "X-Title": "Coinbase Trading Bot" # Optional
            }
            
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert algorithmic trading analyst. Output ONLY valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 1000
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # Parse response
                recommendation = self._parse_response(content)
                
                if recommendation:
                    logger.info(f"AI Recommendation: {recommendation.get('strategy')} (Confidence: {recommendation.get('confidence')})")
                    logger.info(f"Reasoning: {recommendation.get('reasoning')}")
                    
                return recommendation
            else:
                logger.error(f"OpenRouter API Error: {response.status_code} - {response.text}")
                return None
            
        except Exception as e:
            logger.error(f"Error during AI analysis: {e}")
            return None

    def _construct_prompt(self, performance_data: Dict, market_context: Dict) -> str:
        """Construct the prompt for the AI."""
        
        return f"""
        Analyze the following strategy performance data and market context to recommend the best trading strategy for the current market regime.
        
        Current Market Context:
        {json.dumps(market_context, indent=2)}
        
        Strategy Performance (Recent):
        {json.dumps(performance_data, indent=2, default=str)}
        
        Available Strategies:
        - momentum: Trend following, good for strong trends.
        - mean_reversion: Good for ranging/choppy markets.
        - breakout: Good for volatility expansion.
        - hybrid: Combines multiple signals.
        
        Task:
        1. Analyze which strategy is performing best given the current market conditions.
        2. Recommend ONE strategy to be the active strategy.
        3. Provide a confidence score (0.0 to 1.0).
        4. Explain your reasoning briefly.
        
        Output Format (JSON only):
        {{
            "strategy": "strategy_name",
            "confidence": 0.85,
            "reasoning": "Explanation here..."
        }}
        """

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse the JSON response from the AI."""
        try:
            # Clean up markdown code blocks if present
            cleaned_text = response_text.replace('```json', '').replace('```', '').strip()
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse AI response: {response_text}")
            return None
