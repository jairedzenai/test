"""
Script Generator module for the RQA automation tool.
Orchestrates the test script generation process from JIRA issues to test files.
"""

import logging
import os
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from .jira_reader import JiraReader
from .template_engine import TemplateEngine
from .utils import TestCaseBuilder, validate_test_data, write_json_file

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """
    Main class for generating test scripts from JIRA issues.
    Coordinates between JIRA reader, template engine, and output generation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize script generator with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.jira_reader = JiraReader(config)
        self.template_engine = TemplateEngine(config)
        
        # Setup output directories
        self.output_path = config.get('templates', {}).get('output_path', 'tests/generated')
        self.reports_path = config.get('reports', {}).get('output_path', 'reports')
        
        os.makedirs(self.output_path, exist_ok=True)
        os.makedirs(self.reports_path, exist_ok=True)
        
        # Generation statistics
        self.stats = {
            'total_issues': 0,
            'successful_generations': 0,
            'failed_generations': 0,
            'generated_files': [],
            'errors': []
        }
        
        logger.info("Script generator initialized")
    
    def generate_from_jira_issue(self, issue_key: str, 
                                custom_data: Dict[str, Any] = None) -> Optional[str]:
        """
        Generate test script from a single JIRA issue.
        
        Args:
            issue_key: JIRA issue key (e.g., 'PROJ-123')
            custom_data: Optional custom data to override/enhance issue data
            
        Returns:
            Path to generated file or None if generation failed
        """
        try:
            # Get JIRA issue
            issue = self.jira_reader.get_issue(issue_key)
            if not issue:
                logger.error(f"Failed to retrieve JIRA issue: {issue_key}")
                self.stats['failed_generations'] += 1
                return None
            
            # Parse issue for test generation
            test_data = self.jira_reader.parse_issue_for_test_generation(issue)
            
            # Apply custom data if provided
            if custom_data:
                test_data.update(custom_data)
            
            # Generate and save test script
            generated_file = self._generate_test_script(test_data)
            
            if generated_file:
                self.stats['successful_generations'] += 1
                self.stats['generated_files'].append(generated_file)
                logger.info(f"Successfully generated test script for {issue_key}: {generated_file}")
            else:
                self.stats['failed_generations'] += 1
            
            return generated_file
            
        except Exception as e:
            error_msg = f"Failed to generate script for {issue_key}: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            self.stats['failed_generations'] += 1
            return None
    
    def generate_from_jira_query(self, jql_filters: Dict[str, Any] = None,
                                custom_config: Dict[str, Any] = None) -> List[str]:
        """
        Generate test scripts from multiple JIRA issues using query filters.
        
        Args:
            jql_filters: JQL query filters
            custom_config: Custom configuration for generation
            
        Returns:
            List of paths to generated files
        """
        try:
            # Get test data from JIRA
            test_data_list = self.jira_reader.get_bulk_test_data(jql_filters)
            self.stats['total_issues'] = len(test_data_list)
            
            generated_files = []
            
            for test_data in test_data_list:
                try:
                    # Apply custom configuration if provided
                    if custom_config:
                        test_data.update(custom_config)
                    
                    # Generate test script
                    generated_file = self._generate_test_script(test_data)
                    
                    if generated_file:
                        generated_files.append(generated_file)
                        self.stats['successful_generations'] += 1
                        self.stats['generated_files'].append(generated_file)
                    else:
                        self.stats['failed_generations'] += 1
                
                except Exception as e:
                    error_msg = f"Failed to generate script for {test_data.get('jira_key', 'unknown')}: {str(e)}"
                    logger.error(error_msg)
                    self.stats['errors'].append(error_msg)
                    self.stats['failed_generations'] += 1
            
            logger.info(f"Bulk generation completed: {len(generated_files)} files generated")
            return generated_files
            
        except Exception as e:
            logger.error(f"Bulk generation failed: {str(e)}")
            return []
    
    def generate_from_custom_data(self, test_data: Dict[str, Any]) -> Optional[str]:
        """
        Generate test script from custom test data (not from JIRA).
        
        Args:
            test_data: Custom test case data
            
        Returns:
            Path to generated file or None if generation failed
        """
        try:
            # Validate test data
            test_type = test_data.get('test_type', 'manual')
            if not validate_test_data(test_data, test_type):
                logger.error("Invalid test data provided")
                return None
            
            # Generate test script
            generated_file = self._generate_test_script(test_data)
            
            if generated_file:
                self.stats['successful_generations'] += 1
                self.stats['generated_files'].append(generated_file)
                logger.info(f"Successfully generated test script from custom data: {generated_file}")
            else:
                self.stats['failed_generations'] += 1
            
            return generated_file
            
        except Exception as e:
            error_msg = f"Failed to generate script from custom data: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            self.stats['failed_generations'] += 1
            return None
    
    def _generate_test_script(self, test_data: Dict[str, Any]) -> Optional[str]:
        """
        Internal method to generate test script from test data.
        
        Args:
            test_data: Test case data
            
        Returns:
            Path to generated file or None if generation failed
        """
        test_type = test_data.get('test_type', 'manual')
        
        # Skip manual tests as they don't have automated scripts
        if test_type == 'manual':
            logger.info(f"Skipping manual test: {test_data.get('test_name', 'unnamed')}")
            return None
        
        try:
            # Generate script using template engine
            generated_file = self.template_engine.generate_and_save_script(
                test_type, test_data
            )
            
            # Save test metadata
            self._save_test_metadata(test_data, generated_file)
            
            return generated_file
            
        except Exception as e:
            logger.error(f"Failed to generate {test_type} test script: {str(e)}")
            raise
    
    def _save_test_metadata(self, test_data: Dict[str, Any], script_path: str) -> None:
        """
        Save test metadata alongside generated script.
        
        Args:
            test_data: Test case data
            script_path: Path to generated script
        """
        try:
            metadata = {
                'test_name': test_data.get('test_name'),
                'test_type': test_data.get('test_type'),
                'jira_key': test_data.get('jira_key'),
                'source': test_data.get('source'),
                'generated_at': datetime.now().isoformat(),
                'script_path': script_path,
                'description': test_data.get('description'),
                'priority': test_data.get('priority'),
                'assignee': test_data.get('assignee'),
                'test_cases_count': len(test_data.get('test_cases', []))
            }
            
            # Create metadata file path
            metadata_path = script_path.replace('.py', '_metadata.json')
            write_json_file(metadata_path, metadata)
            
            logger.debug(f"Saved test metadata: {metadata_path}")
            
        except Exception as e:
            logger.warning(f"Failed to save test metadata: {str(e)}")
    
    def create_test_builder(self, test_type: str) -> TestCaseBuilder:
        """
        Create a test case builder for programmatic test creation.
        
        Args:
            test_type: Type of test (api, ui, database)
            
        Returns:
            TestCaseBuilder instance
        """
        return TestCaseBuilder(test_type)
    
    def generate_api_test(self, test_name: str, jira_key: str = '') -> TestCaseBuilder:
        """
        Create API test builder with basic configuration.
        
        Args:
            test_name: Name of the test
            jira_key: Related JIRA key
            
        Returns:
            Configured TestCaseBuilder for API tests
        """
        builder = self.create_test_builder('api')
        builder.add_basic_info(test_name, f"API test for {test_name}", jira_key)
        
        # Add API-specific configuration
        api_config = self.config.get('api_testing', {})
        builder.test_data.update({
            'base_url': api_config.get('base_url', 'https://api.example.com'),
            'timeout': api_config.get('timeout', 30)
        })
        
        return builder
    
    def generate_ui_test(self, test_name: str, jira_key: str = '') -> TestCaseBuilder:
        """
        Create UI test builder with basic configuration.
        
        Args:
            test_name: Name of the test
            jira_key: Related JIRA key
            
        Returns:
            Configured TestCaseBuilder for UI tests
        """
        builder = self.create_test_builder('ui')
        builder.add_basic_info(test_name, f"UI test for {test_name}", jira_key)
        
        # Add UI-specific configuration
        ui_config = self.config.get('ui_testing', {})
        builder.test_data.update({
            'base_url': 'https://example.com',
            'browser': ui_config.get('browser', 'chrome'),
            'headless': ui_config.get('headless', False),
            'timeout': ui_config.get('timeout', 30)
        })
        
        return builder
    
    def generate_database_test(self, test_name: str, jira_key: str = '') -> TestCaseBuilder:
        """
        Create database test builder with basic configuration.
        
        Args:
            test_name: Name of the test
            jira_key: Related JIRA key
            
        Returns:
            Configured TestCaseBuilder for database tests
        """
        builder = self.create_test_builder('database')
        builder.add_basic_info(test_name, f"Database test for {test_name}", jira_key)
        
        # Add database-specific configuration
        db_config = self.config.get('database', {})
        builder.test_data.update({
            'db_type': db_config.get('type', 'postgresql'),
            'host': db_config.get('host', 'localhost'),
            'port': db_config.get('port', 5432),
            'database': db_config.get('database', 'test_db'),
            'username': db_config.get('username', 'test_user'),
            'password': db_config.get('password', 'password')
        })
        
        return builder
    
    def generate_test_suite(self, suite_name: str, 
                           test_builders: List[TestCaseBuilder]) -> List[str]:
        """
        Generate multiple test scripts as a test suite.
        
        Args:
            suite_name: Name of the test suite
            test_builders: List of configured test builders
            
        Returns:
            List of paths to generated files
        """
        generated_files = []
        
        try:
            for i, builder in enumerate(test_builders):
                test_data = builder.build()
                
                # Add suite information
                test_data['suite_name'] = suite_name
                test_data['suite_index'] = i + 1
                
                # Generate script
                generated_file = self._generate_test_script(test_data)
                
                if generated_file:
                    generated_files.append(generated_file)
                    self.stats['successful_generations'] += 1
                    self.stats['generated_files'].append(generated_file)
                else:
                    self.stats['failed_generations'] += 1
            
            # Generate suite metadata
            self._save_suite_metadata(suite_name, generated_files)
            
            logger.info(f"Generated test suite '{suite_name}' with {len(generated_files)} test files")
            return generated_files
            
        except Exception as e:
            logger.error(f"Failed to generate test suite '{suite_name}': {str(e)}")
            return generated_files
    
    def _save_suite_metadata(self, suite_name: str, generated_files: List[str]) -> None:
        """
        Save test suite metadata.
        
        Args:
            suite_name: Name of the test suite
            generated_files: List of generated file paths
        """
        try:
            suite_metadata = {
                'suite_name': suite_name,
                'generated_at': datetime.now().isoformat(),
                'test_files': generated_files,
                'total_tests': len(generated_files)
            }
            
            metadata_path = os.path.join(self.reports_path, f"{suite_name}_suite_metadata.json")
            write_json_file(metadata_path, suite_metadata)
            
            logger.info(f"Saved suite metadata: {metadata_path}")
            
        except Exception as e:
            logger.warning(f"Failed to save suite metadata: {str(e)}")
    
    def get_generation_statistics(self) -> Dict[str, Any]:
        """
        Get generation statistics.
        
        Returns:
            Dictionary containing generation statistics
        """
        stats = self.stats.copy()
        stats['success_rate'] = (
            (stats['successful_generations'] / max(stats['total_issues'] or 1, 1)) * 100
            if stats['total_issues'] > 0 else 0
        )
        
        return stats
    
    def reset_statistics(self) -> None:
        """Reset generation statistics."""
        self.stats = {
            'total_issues': 0,
            'successful_generations': 0,
            'failed_generations': 0,
            'generated_files': [],
            'errors': []
        }
    
    def generate_requirements_file(self, test_types: List[str] = None) -> str:
        """
        Generate requirements.txt file based on test types.
        
        Args:
            test_types: List of test types to include dependencies for
            
        Returns:
            Path to generated requirements file
        """
        if test_types is None:
            test_types = ['api', 'ui', 'database']
        
        dependencies = set([
            'pytest>=7.0.0',
            'pytest-html>=3.1.0',
            'pytest-xdist>=2.5.0',
            'requests>=2.28.0',
            'pyyaml>=6.0',
            'jinja2>=3.1.0'
        ])
        
        # Add type-specific dependencies
        if 'ui' in test_types:
            dependencies.update([
                'selenium>=4.8.0',
                'webdriver-manager>=3.8.0'
            ])
        
        if 'database' in test_types:
            dependencies.update([
                'sqlalchemy>=1.4.0',
                'psycopg2-binary>=2.9.0',
                'pymongo>=4.3.0',
                'pymysql>=1.0.0'
            ])
        
        if 'api' in test_types:
            dependencies.add('jsonschema>=4.17.0')
        
        # Write requirements file
        requirements_path = os.path.join(self.output_path, 'requirements.txt')
        
        try:
            with open(requirements_path, 'w') as f:
                for dep in sorted(dependencies):
                    f.write(f"{dep}\n")
            
            logger.info(f"Generated requirements file: {requirements_path}")
            return requirements_path
            
        except Exception as e:
            logger.error(f"Failed to generate requirements file: {str(e)}")
            raise
    
    def generate_conftest_file(self) -> str:
        """
        Generate pytest conftest.py file with common fixtures.
        
        Returns:
            Path to generated conftest file
        """
        conftest_content = '''"""
Pytest configuration and fixtures for generated tests.
"""

import pytest
import logging
import os
from datetime import datetime


@pytest.fixture(scope="session", autouse=True)
def configure_logging():
    """Configure logging for test sessions."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f"test_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        ]
    )


@pytest.fixture(scope="session")
def test_config():
    """Load test configuration."""
    import yaml
    
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "settings.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


@pytest.fixture
def api_base_url(test_config):
    """Get API base URL from configuration."""
    return test_config.get('api_testing', {}).get('base_url', 'https://api.example.com')


@pytest.fixture
def db_connection_string(test_config):
    """Get database connection string from configuration."""
    db_config = test_config.get('database', {})
    return f"postgresql://{db_config.get('username', 'test')}:{db_config.get('password', 'test')}@{db_config.get('host', 'localhost')}:{db_config.get('port', 5432)}/{db_config.get('database', 'test')}"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Configure pytest."""
    # Create reports directory
    os.makedirs('reports', exist_ok=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Generate enhanced test reports."""
    outcome = yield
    report = outcome.get_result()
    
    if report.when == "call":
        # Add custom attributes to report
        if hasattr(item, 'jira_key'):
            report.jira_key = item.jira_key
        if hasattr(item, 'test_type'):
            report.test_type = item.test_type
'''
        
        conftest_path = os.path.join(self.output_path, 'conftest.py')
        
        try:
            with open(conftest_path, 'w') as f:
                f.write(conftest_content)
            
            logger.info(f"Generated conftest file: {conftest_path}")
            return conftest_path
            
        except Exception as e:
            logger.error(f"Failed to generate conftest file: {str(e)}")
            raise