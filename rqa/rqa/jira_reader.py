"""
JIRA Reader module for the RQA automation tool.
Handles connection to JIRA and extraction of test case information from issues.
"""

import logging
import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, List, Any, Optional
import json
from urllib.parse import urljoin
from .utils import parse_jira_description, extract_test_metadata

logger = logging.getLogger(__name__)


class JiraReader:
    """
    Handles reading and parsing JIRA issues to extract test case information.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize JIRA reader with configuration.
        
        Args:
            config: Configuration dictionary containing JIRA settings
        """
        self.config = config.get('jira', {})
        self.server = self.config.get('server')
        self.username = self.config.get('username')
        self.password = self.config.get('password')
        self.project_key = self.config.get('project_key')
        self.max_results = self.config.get('max_results', 100)
        
        if not all([self.server, self.username, self.password]):
            raise ValueError("JIRA server, username, and password must be configured")
        
        self.auth = HTTPBasicAuth(self.username, self.password)
        self.session = requests.Session()
        self.session.auth = self.auth
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self) -> None:
        """
        Test connection to JIRA server.
        
        Raises:
            ConnectionError: If unable to connect to JIRA
        """
        try:
            url = urljoin(self.server, '/rest/api/2/serverInfo')
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            server_info = response.json()
            logger.info(f"Connected to JIRA server: {server_info.get('serverTitle', 'Unknown')}")
            
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to connect to JIRA server: {str(e)}")
    
    def search_issues(self, jql: str, fields: List[str] = None) -> List[Dict[str, Any]]:
        """
        Search for JIRA issues using JQL.
        
        Args:
            jql: JQL query string
            fields: List of fields to retrieve
            
        Returns:
            List of JIRA issues
            
        Raises:
            requests.RequestException: If API request fails
        """
        if fields is None:
            fields = ['summary', 'description', 'status', 'priority', 'assignee', 'reporter', 'created', 'labels']
        
        url = urljoin(self.server, '/rest/api/2/search')
        params = {
            'jql': jql,
            'fields': ','.join(fields),
            'maxResults': self.max_results,
            'startAt': 0
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            issues = data.get('issues', [])
            
            logger.info(f"Retrieved {len(issues)} issues from JIRA")
            return issues
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to search JIRA issues: {str(e)}")
            raise
    
    def get_issue(self, issue_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific JIRA issue by key.
        
        Args:
            issue_key: JIRA issue key (e.g., 'PROJ-123')
            
        Returns:
            JIRA issue data or None if not found
        """
        url = urljoin(self.server, f'/rest/api/2/issue/{issue_key}')
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            issue = response.json()
            logger.info(f"Retrieved JIRA issue: {issue_key}")
            return issue
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get JIRA issue {issue_key}: {str(e)}")
            return None
    
    def get_test_issues(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Get issues that should be converted to test cases.
        
        Args:
            filters: Additional filters for issue selection
            
        Returns:
            List of test-related JIRA issues
        """
        # Build JQL query
        jql_parts = []
        
        if self.project_key:
            jql_parts.append(f'project = {self.project_key}')
        
        # Add filters
        if filters:
            if filters.get('issue_type'):
                jql_parts.append(f'issuetype = "{filters["issue_type"]}"')
            
            if filters.get('status'):
                statuses = filters['status'] if isinstance(filters['status'], list) else [filters['status']]
                status_query = ', '.join(f'"{status}"' for status in statuses)
                jql_parts.append(f'status IN ({status_query})')
            
            if filters.get('labels'):
                labels = filters['labels'] if isinstance(filters['labels'], list) else [filters['labels']]
                for label in labels:
                    jql_parts.append(f'labels = "{label}"')
            
            if filters.get('assignee'):
                jql_parts.append(f'assignee = "{filters["assignee"]}"')
            
            if filters.get('created_after'):
                jql_parts.append(f'created >= "{filters["created_after"]}"')
        
        # Default filters for test cases
        if not filters or not filters.get('issue_type'):
            jql_parts.append('(issuetype = "Test" OR issuetype = "Story" OR issuetype = "Bug")')
        
        jql = ' AND '.join(jql_parts)
        jql += ' ORDER BY created DESC'
        
        logger.info(f"Searching for test issues with JQL: {jql}")
        return self.search_issues(jql)
    
    def parse_issue_for_test_generation(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a JIRA issue to extract information for test generation.
        
        Args:
            issue: JIRA issue data
            
        Returns:
            Parsed test case information
        """
        # Extract basic metadata
        metadata = extract_test_metadata(issue)
        
        # Parse description for test case details
        description = metadata.get('description', '')
        parsed_data = parse_jira_description(description)
        
        # Combine metadata and parsed data
        test_info = {
            **metadata,
            **parsed_data,
            'test_name': metadata['summary'],
            'source': 'jira',
            'source_id': metadata['jira_key']
        }
        
        # Determine test type from issue content
        test_info['test_type'] = self._determine_test_type(issue, description)
        
        # Extract additional test information
        test_info.update(self._extract_test_details(issue, description, test_info['test_type']))
        
        logger.info(f"Parsed JIRA issue {metadata['jira_key']} for {test_info['test_type']} test generation")
        return test_info
    
    def _determine_test_type(self, issue: Dict[str, Any], description: str) -> str:
        """
        Determine the type of test based on issue content.
        
        Args:
            issue: JIRA issue data
            description: Issue description
            
        Returns:
            Test type (api, ui, database, manual)
        """
        description_lower = description.lower()
        summary_lower = issue.get('fields', {}).get('summary', '').lower()
        labels = [label.lower() for label in issue.get('fields', {}).get('labels', [])]
        
        # Check labels first
        if 'api' in labels or 'rest' in labels:
            return 'api'
        elif 'ui' in labels or 'selenium' in labels or 'web' in labels:
            return 'ui'
        elif 'database' in labels or 'db' in labels or 'sql' in labels:
            return 'database'
        
        # Check summary and description
        api_keywords = ['api', 'rest', 'endpoint', 'service', 'http', 'json', 'xml']
        ui_keywords = ['ui', 'user interface', 'web', 'browser', 'selenium', 'frontend', 'click', 'button']
        db_keywords = ['database', 'sql', 'query', 'table', 'mongo', 'collection', 'data']
        
        content = f"{summary_lower} {description_lower}"
        
        api_score = sum(1 for keyword in api_keywords if keyword in content)
        ui_score = sum(1 for keyword in ui_keywords if keyword in content)
        db_score = sum(1 for keyword in db_keywords if keyword in content)
        
        if api_score > ui_score and api_score > db_score:
            return 'api'
        elif ui_score > db_score:
            return 'ui'
        elif db_score > 0:
            return 'database'
        else:
            return 'manual'
    
    def _extract_test_details(self, issue: Dict[str, Any], description: str, test_type: str) -> Dict[str, Any]:
        """
        Extract test-specific details based on test type.
        
        Args:
            issue: JIRA issue data
            description: Issue description
            test_type: Type of test
            
        Returns:
            Test-specific details
        """
        details = {}
        
        if test_type == 'api':
            details.update(self._extract_api_details(description))
        elif test_type == 'ui':
            details.update(self._extract_ui_details(description))
        elif test_type == 'database':
            details.update(self._extract_db_details(description))
        
        return details
    
    def _extract_api_details(self, description: str) -> Dict[str, Any]:
        """Extract API-specific test details."""
        import re
        
        details = {
            'base_url': '',
            'test_cases': []
        }
        
        # Extract base URL
        url_match = re.search(r'https?://[^\s]+', description)
        if url_match:
            details['base_url'] = url_match.group()
        
        # Extract HTTP methods and endpoints
        method_matches = re.findall(r'\b(GET|POST|PUT|DELETE|PATCH)\s+([^\s]+)', description, re.IGNORECASE)
        
        for i, (method, endpoint) in enumerate(method_matches):
            test_case = {
                'name': f'test_{method.lower()}_{endpoint.split("/")[-1] or "endpoint"}',
                'method': method.upper(),
                'endpoint': endpoint,
                'description': f'Test {method} request to {endpoint}',
                'expected_status_code': 200 if method.upper() == 'GET' else 201 if method.upper() == 'POST' else 200,
                'expected_result': f'{method} request should succeed'
            }
            details['test_cases'].append(test_case)
        
        # If no specific endpoints found, create a generic test case
        if not details['test_cases']:
            details['test_cases'].append({
                'name': 'test_api_endpoint',
                'method': 'GET',
                'endpoint': '/api/test',
                'description': 'Generic API test',
                'expected_status_code': 200,
                'expected_result': 'API request should succeed'
            })
        
        return details
    
    def _extract_ui_details(self, description: str) -> Dict[str, Any]:
        """Extract UI-specific test details."""
        import re
        
        details = {
            'base_url': '',
            'test_cases': []
        }
        
        # Extract base URL
        url_match = re.search(r'https?://[^\s]+', description)
        if url_match:
            details['base_url'] = url_match.group()
        
        # Parse test steps
        steps_section = re.search(r'(?:test steps?|steps):?\s*(.*?)(?=expected|$)', description, re.IGNORECASE | re.DOTALL)
        
        if steps_section:
            steps_text = steps_section.group(1)
            step_lines = [line.strip() for line in re.split(r'\d+\.|\n\*|\n-', steps_text) if line.strip()]
            
            ui_steps = []
            for step_text in step_lines:
                step = self._parse_ui_step(step_text)
                if step:
                    ui_steps.append(step)
            
            if ui_steps:
                details['test_cases'].append({
                    'name': 'test_ui_workflow',
                    'description': 'UI test workflow',
                    'steps': ui_steps,
                    'expected_result': 'UI workflow should complete successfully'
                })
        
        # If no specific steps found, create generic UI test
        if not details['test_cases']:
            details['test_cases'].append({
                'name': 'test_ui_interaction',
                'description': 'Generic UI test',
                'steps': [
                    {
                        'description': 'Navigate to page',
                        'action': 'wait',
                        'locator_type': 'TAG_NAME',
                        'locator': 'body'
                    }
                ],
                'expected_result': 'UI test should complete successfully'
            })
        
        return details
    
    def _parse_ui_step(self, step_text: str) -> Optional[Dict[str, Any]]:
        """Parse individual UI test step."""
        import re
        
        step_text = step_text.lower()
        
        # Click actions
        if 'click' in step_text:
            # Try to extract element identifier
            button_match = re.search(r'click.*?(?:button|link).*?"([^"]+)"', step_text)
            if button_match:
                return {
                    'description': f'Click {button_match.group(1)}',
                    'action': 'click',
                    'locator_type': 'XPATH',
                    'locator': f"//button[contains(text(), '{button_match.group(1)}')]"
                }
            else:
                return {
                    'description': 'Click element',
                    'action': 'click',
                    'locator_type': 'ID',
                    'locator': 'submit-button'
                }
        
        # Type/input actions
        elif any(word in step_text for word in ['type', 'enter', 'input', 'fill']):
            input_match = re.search(r'(?:type|enter|input|fill).*?"([^"]+)"', step_text)
            text_to_type = input_match.group(1) if input_match else 'test input'
            
            return {
                'description': f'Type "{text_to_type}"',
                'action': 'type',
                'locator_type': 'NAME',
                'locator': 'input-field',
                'text': text_to_type
            }
        
        # Wait/verify actions
        elif any(word in step_text for word in ['wait', 'verify', 'check', 'see']):
            return {
                'description': 'Verify element present',
                'action': 'assert_element_present',
                'locator_type': 'CLASS_NAME',
                'locator': 'success-message'
            }
        
        return None
    
    def _extract_db_details(self, description: str) -> Dict[str, Any]:
        """Extract database-specific test details."""
        import re
        
        details = {
            'db_type': 'postgresql',  # Default
            'test_cases': []
        }
        
        # Determine database type
        if any(keyword in description.lower() for keyword in ['mongo', 'mongodb']):
            details['db_type'] = 'mongodb'
        elif 'mysql' in description.lower():
            details['db_type'] = 'mysql'
        
        # Extract SQL queries
        sql_matches = re.findall(r'```sql\s*(.*?)\s*```', description, re.DOTALL | re.IGNORECASE)
        
        for i, sql_query in enumerate(sql_matches):
            test_case = {
                'name': f'test_database_query_{i+1}',
                'description': f'Database query test {i+1}',
                'query': sql_query.strip(),
                'expected_result': 'Query should execute successfully'
            }
            details['test_cases'].append(test_case)
        
        # If no SQL found, create generic database test
        if not details['test_cases']:
            if details['db_type'] == 'mongodb':
                details['test_cases'].append({
                    'name': 'test_mongodb_query',
                    'description': 'MongoDB query test',
                    'collection': 'test_collection',
                    'operation_type': 'find',
                    'query': {},
                    'expected_result': 'MongoDB query should execute successfully'
                })
            else:
                details['test_cases'].append({
                    'name': 'test_sql_query',
                    'description': 'SQL query test',
                    'query': 'SELECT COUNT(*) FROM test_table',
                    'expected_result': 'SQL query should execute successfully'
                })
        
        return details
    
    def get_bulk_test_data(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Get and parse multiple JIRA issues for bulk test generation.
        
        Args:
            filters: Filters for issue selection
            
        Returns:
            List of parsed test case information
        """
        issues = self.get_test_issues(filters)
        test_data_list = []
        
        for issue in issues:
            try:
                test_data = self.parse_issue_for_test_generation(issue)
                test_data_list.append(test_data)
            except Exception as e:
                logger.error(f"Failed to parse issue {issue.get('key', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Successfully parsed {len(test_data_list)} issues for test generation")
        return test_data_list