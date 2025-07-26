"""
Template Engine module for the RQA automation tool.
Uses Jinja2 to generate test scripts from templates and test data.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
from .utils import format_timestamp, sanitize_filename

logger = logging.getLogger(__name__)


class TemplateEngine:
    """
    Handles template loading and rendering for test script generation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize template engine with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.templates_path = "templates"
        self.output_path = config.get('templates', {}).get('output_path', 'tests/generated')
        
        # Ensure directories exist
        os.makedirs(self.templates_path, exist_ok=True)
        os.makedirs(self.output_path, exist_ok=True)
        
        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(self.templates_path),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )
        
        # Add custom filters
        self._register_custom_filters()
        
        logger.info("Template engine initialized")
    
    def _register_custom_filters(self) -> None:
        """Register custom Jinja2 filters for template processing."""
        
        def sanitize_name(text: str) -> str:
            """Sanitize text for use as filename or identifier."""
            return sanitize_filename(text)
        
        def to_snake_case(text: str) -> str:
            """Convert text to snake_case."""
            import re
            # Replace spaces and special chars with underscores
            text = re.sub(r'[^\w\s]', '', text)
            text = re.sub(r'\s+', '_', text)
            # Convert camelCase to snake_case
            text = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', text)
            return text.lower()
        
        def to_pascal_case(text: str) -> str:
            """Convert text to PascalCase."""
            import re
            text = re.sub(r'[^\w\s]', '', text)
            words = text.split()
            return ''.join(word.capitalize() for word in words)
        
        def format_json(value: Any) -> str:
            """Format value as JSON string."""
            import json
            return json.dumps(value, indent=2)
        
        def extract_path_segments(url: str) -> Dict[str, str]:
            """Extract segments from URL path."""
            from urllib.parse import urlparse
            parsed = urlparse(url)
            segments = [seg for seg in parsed.path.split('/') if seg]
            return {
                'path': parsed.path,
                'segments': segments,
                'last_segment': segments[-1] if segments else '',
                'first_segment': segments[0] if segments else ''
            }
        
        def format_http_method(method: str) -> str:
            """Format HTTP method for display."""
            return method.upper()
        
        def extract_locator_strategy(text: str) -> Dict[str, str]:
            """Extract locator strategy from text."""
            # Simple heuristics for determining locator strategy
            if text.startswith('#'):
                return {'type': 'ID', 'value': text[1:]}
            elif text.startswith('.'):
                return {'type': 'CLASS_NAME', 'value': text[1:]}
            elif text.startswith('//'):
                return {'type': 'XPATH', 'value': text}
            elif '[' in text and ']' in text:
                return {'type': 'CSS_SELECTOR', 'value': text}
            else:
                return {'type': 'NAME', 'value': text}
        
        # Register filters
        self.env.filters['sanitize_name'] = sanitize_name
        self.env.filters['to_snake_case'] = to_snake_case
        self.env.filters['to_pascal_case'] = to_pascal_case
        self.env.filters['format_json'] = format_json
        self.env.filters['extract_path_segments'] = extract_path_segments
        self.env.filters['format_http_method'] = format_http_method
        self.env.filters['extract_locator_strategy'] = extract_locator_strategy
    
    def load_template(self, template_name: str) -> Template:
        """
        Load a template by name.
        
        Args:
            template_name: Name of the template file
            
        Returns:
            Loaded Jinja2 template
            
        Raises:
            TemplateNotFound: If template file doesn't exist
        """
        try:
            template = self.env.get_template(template_name)
            logger.info(f"Loaded template: {template_name}")
            return template
        except TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            raise
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render a template with provided context.
        
        Args:
            template_name: Name of the template file
            context: Template context data
            
        Returns:
            Rendered template content
        """
        template = self.load_template(template_name)
        
        # Add common context variables
        enhanced_context = {
            **context,
            'timestamp': format_timestamp(),
            'generator': 'RQA Automation Tool'
        }
        
        try:
            rendered = template.render(enhanced_context)
            logger.info(f"Successfully rendered template: {template_name}")
            return rendered
        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {str(e)}")
            raise
    
    def generate_test_script(self, test_type: str, test_data: Dict[str, Any]) -> str:
        """
        Generate test script based on test type and data.
        
        Args:
            test_type: Type of test (api, ui, database)
            test_data: Test case data
            
        Returns:
            Generated test script content
        """
        template_mapping = {
            'api': 'api_test_template.py.j2',
            'ui': 'ui_test_template.py.j2',
            'database': 'db_test_template.py.j2'
        }
        
        template_name = template_mapping.get(test_type)
        if not template_name:
            raise ValueError(f"No template found for test type: {test_type}")
        
        # Enhance test data with type-specific context
        enhanced_data = self._enhance_test_data(test_type, test_data)
        
        return self.render_template(template_name, enhanced_data)
    
    def _enhance_test_data(self, test_type: str, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance test data with type-specific context.
        
        Args:
            test_type: Type of test
            test_data: Original test data
            
        Returns:
            Enhanced test data
        """
        enhanced_data = test_data.copy()
        
        if test_type == 'api':
            enhanced_data.update(self._enhance_api_data(test_data))
        elif test_type == 'ui':
            enhanced_data.update(self._enhance_ui_data(test_data))
        elif test_type == 'database':
            enhanced_data.update(self._enhance_db_data(test_data))
        
        return enhanced_data
    
    def _enhance_api_data(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance API test data with additional context."""
        api_config = self.config.get('api_testing', {})
        
        enhancements = {
            'base_url': test_data.get('base_url') or api_config.get('base_url', 'https://api.example.com'),
            'timeout': api_config.get('timeout', 30),
            'verify_ssl': api_config.get('verify_ssl', True),
            'auth_token': api_config.get('auth_token', ''),
        }
        
        # Enhance individual test cases
        if 'test_cases' in test_data:
            for test_case in test_data['test_cases']:
                if 'expected_status_code' not in test_case:
                    method = test_case.get('method', 'GET').upper()
                    test_case['expected_status_code'] = 201 if method == 'POST' else 200
                
                if 'description' not in test_case:
                    test_case['description'] = f"Test {test_case.get('method', 'GET')} {test_case.get('endpoint', '')}"
        
        return enhancements
    
    def _enhance_ui_data(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance UI test data with additional context."""
        ui_config = self.config.get('ui_testing', {})
        
        enhancements = {
            'base_url': test_data.get('base_url') or 'https://example.com',
            'browser': ui_config.get('browser', 'chrome'),
            'headless': ui_config.get('headless', False),
            'timeout': ui_config.get('timeout', 30),
            'screenshot_on_failure': ui_config.get('screenshot_on_failure', True),
        }
        
        # Enhance test case steps
        if 'test_cases' in test_data:
            for test_case in test_data['test_cases']:
                if 'steps' in test_case:
                    for step in test_case['steps']:
                        # Ensure all steps have required fields
                        if 'locator_type' not in step:
                            step['locator_type'] = 'ID'
                        if 'locator' not in step:
                            step['locator'] = 'element'
                        if 'description' not in step:
                            step['description'] = f"Perform {step.get('action', 'action')}"
        
        return enhancements
    
    def _enhance_db_data(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance database test data with additional context."""
        db_config = self.config.get('database', {})
        
        enhancements = {
            'db_type': test_data.get('db_type') or db_config.get('type', 'postgresql'),
            'host': db_config.get('host', 'localhost'),
            'port': db_config.get('port', 5432),
            'database': db_config.get('database', 'test_db'),
            'username': db_config.get('username', 'test_user'),
            'password': db_config.get('password', 'password'),
        }
        
        return enhancements
    
    def save_generated_script(self, script_content: str, filename: str, test_type: str) -> str:
        """
        Save generated test script to file.
        
        Args:
            script_content: Generated script content
            filename: Output filename
            test_type: Type of test
            
        Returns:
            Path to saved file
        """
        # Create type-specific subdirectory
        type_dir = os.path.join(self.output_path, test_type)
        os.makedirs(type_dir, exist_ok=True)
        
        # Ensure filename has .py extension
        if not filename.endswith('.py'):
            filename += '.py'
        
        # Sanitize filename
        filename = sanitize_filename(filename)
        
        file_path = os.path.join(type_dir, filename)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            logger.info(f"Saved generated script to: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save script to {file_path}: {str(e)}")
            raise
    
    def generate_and_save_script(self, test_type: str, test_data: Dict[str, Any], 
                                custom_filename: str = None) -> str:
        """
        Generate and save test script in one operation.
        
        Args:
            test_type: Type of test
            test_data: Test case data
            custom_filename: Custom filename (optional)
            
        Returns:
            Path to saved file
        """
        # Generate script content
        script_content = self.generate_test_script(test_type, test_data)
        
        # Determine filename
        if custom_filename:
            filename = custom_filename
        else:
            test_name = test_data.get('test_name', 'unnamed_test')
            jira_key = test_data.get('jira_key', '')
            if jira_key:
                filename = f"{jira_key}_{test_name}"
            else:
                filename = test_name
        
        # Save script
        return self.save_generated_script(script_content, filename, test_type)
    
    def list_available_templates(self) -> Dict[str, str]:
        """
        List all available templates.
        
        Returns:
            Dictionary mapping template names to their purposes
        """
        templates = {}
        template_files = {
            'api_test_template.py.j2': 'API/REST testing with PyTest',
            'ui_test_template.py.j2': 'UI testing with Selenium',
            'db_test_template.py.j2': 'Database testing (SQL/MongoDB)'
        }
        
        for template_file, description in template_files.items():
            template_path = os.path.join(self.templates_path, template_file)
            if os.path.exists(template_path):
                templates[template_file] = description
            else:
                logger.warning(f"Template file not found: {template_path}")
        
        return templates
    
    def validate_template_syntax(self, template_name: str) -> bool:
        """
        Validate template syntax.
        
        Args:
            template_name: Name of template to validate
            
        Returns:
            True if syntax is valid, False otherwise
        """
        try:
            template = self.load_template(template_name)
            # Try to render with minimal context to check syntax
            template.render({})
            return True
        except Exception as e:
            logger.error(f"Template syntax validation failed for {template_name}: {str(e)}")
            return False
    
    def create_custom_template(self, template_name: str, template_content: str) -> str:
        """
        Create a custom template file.
        
        Args:
            template_name: Name for the new template
            template_content: Template content
            
        Returns:
            Path to created template file
        """
        if not template_name.endswith('.j2'):
            template_name += '.j2'
        
        template_path = os.path.join(self.templates_path, template_name)
        
        try:
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(template_content)
            
            logger.info(f"Created custom template: {template_path}")
            return template_path
            
        except Exception as e:
            logger.error(f"Failed to create template {template_path}: {str(e)}")
            raise