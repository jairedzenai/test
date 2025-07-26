"""
Utility functions for the RQA automation tool.
Provides common functionality including logging, configuration, and helper methods.
"""

import logging
import yaml
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import json


def setup_logging(config: Dict[str, Any]) -> None:
    """
    Setup logging configuration based on config settings.
    
    Args:
        config: Configuration dictionary containing logging settings
    """
    log_config = config.get('logging', {})
    
    # Create logs directory if it doesn't exist
    log_file = log_config.get('file', 'logs/rqa.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_config.get('level', 'INFO')),
        format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully")


def load_config(config_path: str = "config/settings.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        
        # Validate required sections
        required_sections = ['jira', 'logging']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in configuration file: {e}")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing/replacing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)
    filename = filename.strip('.')
    
    # Ensure filename is not empty
    if not filename:
        filename = "unnamed_file"
    
    return filename


def generate_class_name(test_name: str) -> str:
    """
    Generate a valid Python class name from test name.
    
    Args:
        test_name: Original test name
        
    Returns:
        Valid Python class name
    """
    # Remove special characters and convert to PascalCase
    class_name = re.sub(r'[^\w\s]', '', test_name)
    class_name = ''.join(word.capitalize() for word in class_name.split())
    
    # Ensure it starts with a letter
    if class_name and not class_name[0].isalpha():
        class_name = 'Test' + class_name
    elif not class_name:
        class_name = 'TestCase'
    
    return class_name


def parse_jira_description(description: str) -> Dict[str, Any]:
    """
    Parse JIRA description to extract test case information.
    
    Args:
        description: JIRA issue description
        
    Returns:
        Dictionary containing parsed test case information
    """
    parsed_data = {
        'test_cases': [],
        'test_type': 'manual',
        'priority': 'medium',
        'environment': 'test'
    }
    
    # Extract test type
    if any(keyword in description.lower() for keyword in ['api', 'rest', 'endpoint']):
        parsed_data['test_type'] = 'api'
    elif any(keyword in description.lower() for keyword in ['ui', 'selenium', 'browser', 'web']):
        parsed_data['test_type'] = 'ui'
    elif any(keyword in description.lower() for keyword in ['database', 'sql', 'mongo', 'db']):
        parsed_data['test_type'] = 'database'
    
    # Extract test steps (simple parsing)
    steps_match = re.search(r'test steps?:?\s*(.*?)(?=expected|$)', description, re.IGNORECASE | re.DOTALL)
    if steps_match:
        steps_text = steps_match.group(1).strip()
        steps = [step.strip() for step in re.split(r'\d+\.|\n\*|\n-', steps_text) if step.strip()]
        parsed_data['steps'] = steps
    
    # Extract expected result
    expected_match = re.search(r'expected.*?:?\s*(.*?)(?=\n\n|$)', description, re.IGNORECASE | re.DOTALL)
    if expected_match:
        parsed_data['expected_result'] = expected_match.group(1).strip()
    
    return parsed_data


def create_directory_structure(base_path: str, directories: List[str]) -> None:
    """
    Create directory structure if it doesn't exist.
    
    Args:
        base_path: Base directory path
        directories: List of directory paths to create
    """
    for directory in directories:
        full_path = os.path.join(base_path, directory)
        os.makedirs(full_path, exist_ok=True)


def validate_test_data(test_data: Dict[str, Any], test_type: str) -> bool:
    """
    Validate test data structure based on test type.
    
    Args:
        test_data: Test data dictionary
        test_type: Type of test (api, ui, database)
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['test_name', 'description']
    
    # Check required fields
    for field in required_fields:
        if field not in test_data or not test_data[field]:
            return False
    
    # Type-specific validation
    if test_type == 'api':
        if 'test_cases' not in test_data or not test_data['test_cases']:
            return False
        for test_case in test_data['test_cases']:
            if 'method' not in test_case or 'endpoint' not in test_case:
                return False
    
    elif test_type == 'ui':
        if 'test_cases' not in test_data or not test_data['test_cases']:
            return False
        for test_case in test_data['test_cases']:
            if 'steps' not in test_case or not test_case['steps']:
                return False
    
    elif test_type == 'database':
        if 'test_cases' not in test_data or not test_data['test_cases']:
            return False
        for test_case in test_data['test_cases']:
            if test_data.get('db_type') in ['postgresql', 'mysql']:
                if 'query' not in test_case:
                    return False
            elif test_data.get('db_type') == 'mongodb':
                if 'collection' not in test_case or 'operation_type' not in test_case:
                    return False
    
    return True


def format_timestamp() -> str:
    """
    Get formatted timestamp for file generation.
    
    Returns:
        Formatted timestamp string
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json_file(file_path: str) -> Dict[str, Any]:
    """
    Read and parse JSON file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Parsed JSON data
        
    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in file {file_path}: {e}")


def write_json_file(file_path: str, data: Dict[str, Any]) -> None:
    """
    Write data to JSON file.
    
    Args:
        file_path: Path to output JSON file
        data: Data to write
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=2, default=str)


def extract_test_metadata(jira_issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract test metadata from JIRA issue.
    
    Args:
        jira_issue: JIRA issue data
        
    Returns:
        Extracted metadata
    """
    metadata = {
        'jira_key': jira_issue.get('key', ''),
        'summary': jira_issue.get('fields', {}).get('summary', ''),
        'description': jira_issue.get('fields', {}).get('description', ''),
        'priority': jira_issue.get('fields', {}).get('priority', {}).get('name', 'Medium'),
        'status': jira_issue.get('fields', {}).get('status', {}).get('name', ''),
        'assignee': jira_issue.get('fields', {}).get('assignee', {}).get('displayName', 'Unassigned'),
        'reporter': jira_issue.get('fields', {}).get('reporter', {}).get('displayName', ''),
        'created': jira_issue.get('fields', {}).get('created', ''),
        'labels': jira_issue.get('fields', {}).get('labels', [])
    }
    
    return metadata


class TestCaseBuilder:
    """Builder class for creating test case data structures."""
    
    def __init__(self, test_type: str):
        self.test_type = test_type
        self.test_data = {
            'test_type': test_type,
            'test_cases': [],
            'timestamp': format_timestamp()
        }
    
    def add_basic_info(self, test_name: str, description: str, jira_key: str = '') -> 'TestCaseBuilder':
        """Add basic test information."""
        self.test_data.update({
            'test_name': test_name,
            'description': description,
            'jira_key': jira_key,
            'test_class_name': generate_class_name(test_name)
        })
        return self
    
    def add_api_test_case(self, name: str, method: str, endpoint: str, **kwargs) -> 'TestCaseBuilder':
        """Add API test case."""
        if self.test_type != 'api':
            raise ValueError("Can only add API test cases to API test builder")
        
        test_case = {
            'name': name,
            'method': method,
            'endpoint': endpoint,
            'description': kwargs.get('description', ''),
            'expected_status_code': kwargs.get('expected_status_code', 200),
            'request_data': kwargs.get('request_data', {}),
            'expected_response_fields': kwargs.get('expected_response_fields', []),
            'assertions': kwargs.get('assertions', []),
            'expected_result': kwargs.get('expected_result', 'Request should succeed')
        }
        
        self.test_data['test_cases'].append(test_case)
        return self
    
    def add_ui_test_case(self, name: str, steps: List[Dict], **kwargs) -> 'TestCaseBuilder':
        """Add UI test case."""
        if self.test_type != 'ui':
            raise ValueError("Can only add UI test cases to UI test builder")
        
        test_case = {
            'name': name,
            'description': kwargs.get('description', ''),
            'steps': steps,
            'page_path': kwargs.get('page_path', '/'),
            'url': kwargs.get('url', ''),
            'final_assertion': kwargs.get('final_assertion', ''),
            'expected_result': kwargs.get('expected_result', 'Test should complete successfully')
        }
        
        self.test_data['test_cases'].append(test_case)
        return self
    
    def add_db_test_case(self, name: str, **kwargs) -> 'TestCaseBuilder':
        """Add database test case."""
        if self.test_type != 'database':
            raise ValueError("Can only add database test cases to database test builder")
        
        test_case = {
            'name': name,
            'description': kwargs.get('description', ''),
            'expected_result': kwargs.get('expected_result', 'Query should execute successfully')
        }
        
        # Add SQL or MongoDB specific fields
        if kwargs.get('query'):
            test_case.update({
                'query': kwargs['query'],
                'query_params': kwargs.get('query_params', {}),
                'setup_queries': kwargs.get('setup_queries', []),
                'cleanup_queries': kwargs.get('cleanup_queries', [])
            })
        
        if kwargs.get('collection'):
            test_case.update({
                'collection': kwargs['collection'],
                'operation_type': kwargs.get('operation_type', 'find'),
                'query': kwargs.get('mongo_query', {}),
                'projection': kwargs.get('projection', {}),
                'pipeline': kwargs.get('pipeline', [])
            })
        
        # Common fields
        test_case.update({
            'expected_row_count': kwargs.get('expected_row_count'),
            'expected_fields': kwargs.get('expected_fields', []),
            'expected_values': kwargs.get('expected_values', {}),
            'custom_assertions': kwargs.get('custom_assertions', [])
        })
        
        self.test_data['test_cases'].append(test_case)
        return self
    
    def build(self) -> Dict[str, Any]:
        """Build and return the test data."""
        if not validate_test_data(self.test_data, self.test_type):
            raise ValueError(f"Invalid test data for {self.test_type} test")
        
        return self.test_data