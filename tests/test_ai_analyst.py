import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from ai_analyst import AIAnalyst

class TestAIAnalyst(unittest.TestCase):
    def setUp(self):
        self.config = {
            'enabled': True,
            'model': 'gemini-2.0-flash-exp',
            'min_confidence': 0.7
        }
        # Mock os.environ
        self.env_patcher = patch.dict(os.environ, {'GEMINI_KEY': 'fake_key'})
        self.env_patcher.start()
        
        # Mock genai in the module
        self.genai_patcher = patch('ai_analyst.genai')
        self.mock_genai = self.genai_patcher.start()
        
        self.analyst = AIAnalyst(self.config)

    def tearDown(self):
        self.env_patcher.stop()
        self.genai_patcher.stop()

    def test_analyze_performance(self):
        """Test the analysis flow with mocked Gemini response."""
        # Mock the model instance and response
        mock_model = self.mock_genai.GenerativeModel.return_value
        mock_response = MagicMock()
        mock_response.text = '''
        ```json
        {
            "strategy": "mean_reversion",
            "confidence": 0.85,
            "reasoning": "Market is ranging with low volatility, favoring mean reversion."
        }
        ```
        '''
        mock_model.generate_content.return_value = mock_response

        # Test data
        performance_data = {
            'momentum': {'win_rate': 0.4, 'total_pnl': -10},
            'mean_reversion': {'win_rate': 0.8, 'total_pnl': 50}
        }
        market_context = {'regime': 'ranging', 'volatility': 'low'}

        # Run analysis
        result = self.analyst.analyze_performance(performance_data, market_context)

        self.assertEqual(result['strategy'], 'mean_reversion')
        self.assertEqual(result['confidence'], 0.85)
        self.assertIn('ranging', result['reasoning'])

    def test_construct_prompt(self):
        """Test prompt construction."""
        performance_data = {'momentum': {'win_rate': 0.5}}
        market_context = {'regime': 'trending'}
        
        prompt = self.analyst._construct_prompt(performance_data, market_context)
        
        self.assertIn('momentum', prompt)
        self.assertIn('trending', prompt)
        self.assertIn('JSON', prompt)

    def test_parse_response(self):
        """Test parsing of valid and invalid JSON responses."""
        # Valid JSON
        valid_response = '```json\n{"strategy": "momentum", "confidence": 0.9, "reasoning": "test"}\n```'
        result = self.analyst._parse_response(valid_response)
        self.assertEqual(result['strategy'], 'momentum')

        # Invalid JSON (should return None)
        invalid_response = 'This is not JSON'
        result = self.analyst._parse_response(invalid_response)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
