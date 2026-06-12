"""
Benchmark Suite - Comprehensive evaluation of model quality
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import yaml

logger = logging.getLogger(__name__)


class BenchmarkSuite:
    """Comprehensive benchmark suite for LLM evaluation"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize BenchmarkSuite
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        self.benchmarks_dir = Path("benchmarks")
        self.benchmarks_dir.mkdir(exist_ok=True)
        
        # Define test cases
        self.reasoning_tests = [
            {
                'prompt': 'A bat and a ball cost $1.10 in total. The bat costs $1 more than the ball. How much does the ball cost?',
                'expected_keywords': ['5 cents', '0.05', 'five cents', '$0.05'],
                'category': 'reasoning'
            },
            {
                'prompt': 'If it takes 5 machines 5 minutes to make 5 widgets, how long would it take 100 machines to make 100 widgets?',
                'expected_keywords': ['5 minutes', 'same time', '5 min'],
                'category': 'reasoning'
            },
            {
                'prompt': 'All roses are flowers. Some flowers fade quickly. Therefore, can we conclude that some roses fade quickly?',
                'expected_keywords': ['no', 'cannot', 'does not follow', 'invalid'],
                'category': 'reasoning'
            },
            {
                'prompt': 'What comes next in this sequence: 2, 4, 8, 16, 32, ?',
                'expected_keywords': ['64', 'sixty-four'],
                'category': 'reasoning'
            },
            {
                'prompt': 'If all Bloops are Razzies and all Razzies are Lazzies, are all Bloops definitely Lazzies?',
                'expected_keywords': ['yes', 'definitely', 'true', 'all bloops are lazzies'],
                'category': 'reasoning'
            }
        ]
        
        self.creative_tests = [
            {
                'prompt': 'Write the opening paragraph of a story that begins: "The last star went out at exactly 3:47 AM."',
                'expected_keywords': ['dark', 'night', 'sky', 'star', 'universe', 'silence', 'end'],
                'category': 'creative'
            },
            {
                'prompt': 'Write a four-line poem about coffee.',
                'expected_keywords': ['brew', 'morning', 'cup', 'aroma', 'steam', 'wake', 'dark'],
                'category': 'creative'
            },
            {
                'prompt': 'Write a dialogue between a detective and a suspect who is actually innocent.',
                'expected_keywords': ['detective', 'suspect', 'innocent', 'alibi', 'truth'],
                'category': 'creative'
            },
            {
                'prompt': 'Describe a futuristic city in exactly three sentences.',
                'expected_keywords': ['future', 'city', 'technology', 'towers', 'sky', 'neon'],
                'category': 'creative'
            },
            {
                'prompt': 'Write a tense scene where someone is waiting for important news.',
                'expected_keywords': ['wait', 'nervous', 'anxious', 'phone', 'door', 'heart', 'time'],
                'category': 'creative'
            }
        ]
        
        self.coding_tests = [
            {
                'prompt': 'Write a Python function that returns "Fizz" for multiples of 3, "Buzz" for multiples of 5, "FizzBuzz" for multiples of both, and the number otherwise.',
                'expected_keywords': ['def', 'fizzbuzz', 'if', '%', 'return'],
                'category': 'coding'
            },
            {
                'prompt': 'Write a Python function to perform binary search on a sorted list.',
                'expected_keywords': ['def', 'binary', 'search', 'mid', 'left', 'right', 'while'],
                'category': 'coding'
            },
            {
                'prompt': 'Implement a simple stack data structure in Python with push, pop, and peek methods.',
                'expected_keywords': ['class', 'stack', 'def', 'push', 'pop', 'peek', 'list'],
                'category': 'coding'
            },
            {
                'prompt': 'Write a Python function to reverse a string without using built-in reverse methods.',
                'expected_keywords': ['def', 'reverse', 'string', 'for', 'range', 'return'],
                'category': 'coding'
            },
            {
                'prompt': 'Design a simple REST API for a todo list application. Describe the endpoints and methods.',
                'expected_keywords': ['GET', 'POST', 'PUT', 'DELETE', 'endpoint', 'todo', 'api'],
                'category': 'coding'
            }
        ]
        
        self.instruction_tests = [
            {
                'prompt': 'List exactly 5 benefits of exercise. Format as a JSON array.',
                'expected_keywords': ['[', ']', 'health', 'fitness'],
                'category': 'instruction'
            },
            {
                'prompt': 'Explain quantum computing in exactly 50 words.',
                'expected_keywords': ['quantum', 'computing', 'qubit', 'superposition'],
                'category': 'instruction'
            },
            {
                'prompt': 'Summarize the water cycle in 3 steps, using numbered list format.',
                'expected_keywords': ['1', '2', '3', 'evaporation', 'condensation', 'precipitation'],
                'category': 'instruction'
            },
            {
                'prompt': 'Write a haiku about technology. Follow the 5-7-5 syllable pattern strictly.',
                'expected_keywords': ['technology', 'digital', 'code', 'screen'],
                'category': 'instruction'
            },
            {
                'prompt': 'Create a comparison table with 2 columns: "Advantages" and "Disadvantages" of remote work. Include at least 3 items in each column.',
                'expected_keywords': ['advantages', 'disadvantages', 'remote', 'work'],
                'category': 'instruction'
            }
        ]

        self.deepswe_tests = [
            {
                'prompt': 'Write a Python function `merge_intervals(intervals: List[List[int]]) -> List[List[int]]` that takes a list of possibly overlapping intervals and returns merged non-overlapping intervals sorted by start. Handle empty input, single intervals, and fully nested intervals.',
                'expected_keywords': ['def', 'merge_intervals', 'sort', 'overla', 'append', 'intervals', 'start', 'end'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Implement a Python LRU cache class with `get(key)` and `put(key, value)` both O(1). Use OrderedDict or doubly-linked list + hash map. It must evict the least recently used item when capacity is exceeded.',
                'expected_keywords': ['class', 'LRU', 'get', 'put', 'capacity', 'def', 'move_to_end', 'popitem', 'OrderedDict'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': "Write a Python function `topological_sort(graph: Dict[str, List[str]]) -> List[str]` that performs Kahn's algorithm topological sort on a directed acyclic graph represented as adjacency list. Return sorted order or raise ValueError if cycle detected.",
                'expected_keywords': ['def', 'topological', 'indegree', 'queue', 'append', 'graph', 'cycle', 'ValueError'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Implement a thread-safe Python rate limiter class using the token bucket algorithm. It should have `acquire()` that blocks until a token is available. Parameters: rate (tokens per second), capacity (max burst). Use threading.Lock.',
                'expected_keywords': ['class', 'rate', 'limiter', 'token', 'bucket', 'Lock', 'acquire', 'capacity', 'sleep', 'threading'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Write a Python function `parse_csv_line(line: str, delimiter = chr(44)) -> List[str]` that correctly handles quoted fields with embedded delimiters, escaped quotes (doubled quotes inside quoted fields), and trailing delimiters. Do not use the csv module.',
                'expected_keywords': ['def', 'parse_csv', 'quote', 'delimiter', 'split', 'append', 'field', 'strip'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Implement a Python function `flatten_json(data: dict, sep = chr(46)) -> dict` that flattens a nested dictionary. Example: dict with nested keys becomes dot-separated keys. Handle lists by using index as key. ',
                'expected_keywords': ['def', 'flatten', 'dict', 'sep', 'items', 'isinstance', 'list', 'enumerate', 'update'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Write a Python function `find_security_vulnerabilities(code: str) -> List[Dict]` that scans Python source code for: SQL injection (string formatting in execute calls), command injection (os.system/subprocess with user input), eval/exec on user input, and hardcoded secrets (password=, api_key=). Return list of findings with line number, type, and severity.',
                'expected_keywords': ['def', 'find_security', 'vuln', 'injection', 'eval', 'exec', 'severity', 'append', 'line'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Implement a Python ConnectionPool class that manages a fixed-size pool of database connections. Include get_connection() that blocks if pool is empty, release_connection(conn) that returns a connection, close_all() that closes every connection. Use threading.Condition for synchronization.',
                'expected_keywords': ['class', 'ConnectionPool', 'Condition', 'get_connection', 'release', 'close_all', 'wait', 'notify', 'pool', 'threading'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Write a Python function trie_insert(root: dict, word: str) -> None and trie_search(root: dict, word: str) -> bool and trie_starts_with(root: dict, prefix: str) -> bool for a trie prefix tree. Use nested dicts with an is_end key. Do not use a class.',
                'expected_keywords': ['def', 'trie', 'insert', 'search', 'starts_with', 'is_end', 'root', 'char', 'word'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
            {
                'prompt': 'Implement a Python function diff_strings(a: str, b: str) that computes a simple diff between two strings line by line. Return a list of tuples with tag equal, replace, insert, or delete plus index ranges. Do not use difflib.',
                'expected_keywords': ['def', 'diff', 'equal', 'replace', 'insert', 'delete', 'append', 'line', 'tuple'],
                'category': 'deepswe',
                'difficulty': 'hard'
            },
        ]

    def _load_config(self) -> Dict:
        """Load configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def score_response(self, response: str, expected_keywords: List[str]) -> Tuple[float, List[str]]:
        """
        Score a response based on keyword presence
        
        Args:
            response: Generated response
            expected_keywords: Keywords to look for
            
        Returns:
            Tuple of (score, found_keywords)
        """
        response_lower = response.lower()
        found_keywords = []
        
        for keyword in expected_keywords:
            if keyword.lower() in response_lower:
                found_keywords.append(keyword)
        
        # Score is percentage of keywords found
        if expected_keywords:
            score = (len(found_keywords) / len(expected_keywords)) * 10
        else:
            score = 5.0  # Neutral score if no keywords
        
        # Bonus points for length and structure
        word_count = len(response.split())
        if word_count > 50:
            score += 1.0
        if word_count > 100:
            score += 0.5
        
        # Cap at 10
        score = min(score, 10.0)
        
        return score, found_keywords
    
    def run_test_category(
        self,
        engine,
        tests: List[Dict],
        category_name: str
    ) -> Dict[str, Any]:
        """
        Run a category of tests
        
        Args:
            engine: InferenceEngine instance
            tests: List of test cases
            category_name: Category name
            
        Returns:
            Results dictionary
        """
        logger.info(f"Running {category_name} tests...")
        
        results = {
            'category': category_name,
            'tests': [],
            'average_score': 0.0,
            'total_tests': len(tests)
        }
        
        total_score = 0.0
        
        for i, test in enumerate(tests, 1):
            logger.info(f"Test {i}/{len(tests)}: {test['prompt'][:50]}...")
            
            try:
                # Generate response
                response = engine.generate(
                    test['prompt'],
                    max_tokens=512,
                    temperature=0.7
                )
                
                # Score response
                score, found_keywords = self.score_response(
                    response,
                    test['expected_keywords']
                )
                
                test_result = {
                    'prompt': test['prompt'],
                    'response': response,
                    'expected_keywords': test['expected_keywords'],
                    'found_keywords': found_keywords,
                    'score': score
                }
                
                results['tests'].append(test_result)
                total_score += score
                
                logger.info(f"Score: {score:.1f}/10")
                
            except Exception as e:
                logger.error(f"Test failed: {e}")
                results['tests'].append({
                    'prompt': test['prompt'],
                    'error': str(e),
                    'score': 0.0
                })
        
        results['average_score'] = total_score / len(tests) if tests else 0.0
        return results
    
    def run_full_benchmark(self, engine) -> Dict[str, Any]:
        """
        Run complete benchmark suite
        
        Args:
            engine: InferenceEngine instance
            
        Returns:
            Complete benchmark results
        """
        logger.info("Starting full benchmark suite...")
        
        benchmark_results = {
            'timestamp': datetime.now().isoformat(),
            'model': str(engine.model_path.name),
            'categories': {}
        }
        
        # Run each category
        categories = [
            ('Reasoning', self.reasoning_tests),
            ('Creative Writing', self.creative_tests),
            ('Coding', self.coding_tests),
            ('DeepSWE', self.deepswe_tests),
            ('Instruction Following', self.instruction_tests)
        ]
        
        for category_name, tests in categories:
            results = self.run_test_category(engine, tests, category_name)
            benchmark_results['categories'][category_name] = results
        
        # Calculate overall score
        total_score = 0.0
        total_categories = 0
        
        for category_results in benchmark_results['categories'].values():
            total_score += category_results['average_score']
            total_categories += 1
        
        benchmark_results['overall_score'] = total_score / total_categories if total_categories else 0.0
        
        logger.info(f"Benchmark complete! Overall score: {benchmark_results['overall_score']:.2f}/10")
        
        return benchmark_results
    
    def save_results(self, results: Dict[str, Any], filename: Optional[str] = None) -> Path:
        """
        Save benchmark results to file
        
        Args:
            results: Benchmark results
            filename: Optional filename
            
        Returns:
            Path to results file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"benchmark_{timestamp}.json"
        
        filepath = self.benchmarks_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results saved to: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise
    
    def format_results_table(self, results: Dict[str, Any]) -> str:
        """
        Format results as a text table
        
        Args:
            results: Benchmark results
            
        Returns:
            Formatted table string
        """
        lines = []
        lines.append("=" * 80)
        lines.append("BENCHMARK RESULTS")
        lines.append("=" * 80)
        lines.append(f"Model: {results['model']}")
        lines.append(f"Timestamp: {results['timestamp']}")
        lines.append(f"Overall Score: {results['overall_score']:.2f}/10")
        lines.append("=" * 80)
        lines.append("")
        
        for category_name, category_results in results['categories'].items():
            lines.append(f"{category_name}")
            lines.append("-" * 80)
            lines.append(f"Average Score: {category_results['average_score']:.2f}/10")
            lines.append("")
            
            for i, test in enumerate(category_results['tests'], 1):
                lines.append(f"  Test {i}: {test.get('score', 0):.1f}/10")
                lines.append(f"  Prompt: {test['prompt'][:60]}...")
                if 'found_keywords' in test:
                    lines.append(f"  Keywords found: {len(test['found_keywords'])}/{len(test.get('expected_keywords', []))}")
                lines.append("")
            
            lines.append("")
        
        lines.append("=" * 80)
        return "\n".join(lines)
