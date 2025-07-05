#!/usr/bin/env python3
"""
Security Scanner Ansible Module
Comprehensive security scanning for TaskFlow application
"""

import json
import subprocess
import tempfile
import os
import yaml
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url


DOCUMENTATION = '''
---
module: security_scanner
short_description: Comprehensive security scanning for TaskFlow
description:
    - Runs multiple security scanning tools
    - Supports Trivy, Bandit, Safety, Semgrep, and OWASP ZAP
    - Aggregates results and provides actionable insights
version_added: "1.0.0"
options:
    namespace:
        description: Kubernetes namespace
        required: false
        type: str
    image:
        description: Container image to scan
        required: false
        type: str
    tools:
        description: List of security tools to run
        required: false
        default: ["trivy", "bandit", "safety"]
        type: list
    fail_on_critical:
        description: Fail on critical vulnerabilities
        required: false
        default: true
        type: bool
    scan_on_deploy:
        description: Run scan during deployment
        required: false
        default: false
        type: bool
    source_path:
        description: Path to source code
        required: false
        default: "/app"
        type: str
    output_format:
        description: Output format for results
        required: false
        default: "json"
        choices: ["json", "table", "sarif"]
        type: str
    severity_threshold:
        description: Minimum severity to report
        required: false
        default: "MEDIUM"
        choices: ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        type: str
    target_url:
        description: Target URL for DAST scanning
        required: false
        type: str
'''

EXAMPLES = '''
- name: Run comprehensive security scan
  security_scanner:
    namespace: taskflow-dev
    image: ghcr.io/taskflow/taskflow:latest
    tools:
      - trivy
      - bandit
      - safety
      - semgrep
    fail_on_critical: true
    severity_threshold: "HIGH"
    
- name: Run DAST scan on deployed application
  security_scanner:
    target_url: "https://taskflow-dev.local"
    tools:
      - zap
    fail_on_critical: false
'''

RETURN = '''
scan_results:
    description: Aggregated scan results
    type: dict
    returned: always
vulnerabilities:
    description: List of vulnerabilities found
    type: list
    returned: always
critical_count:
    description: Number of critical vulnerabilities
    type: int
    returned: always
high_count:
    description: Number of high severity vulnerabilities
    type: int
    returned: always
medium_count:
    description: Number of medium severity vulnerabilities
    type: int
    returned: always
low_count:
    description: Number of low severity vulnerabilities
    type: int
    returned: always
passed:
    description: Whether scan passed based on criteria
    type: bool
    returned: always
'''


class SecurityScanner:
    def __init__(self, module):
        self.module = module
        self.namespace = module.params['namespace']
        self.image = module.params['image']
        self.tools = module.params['tools']
        self.fail_on_critical = module.params['fail_on_critical']
        self.scan_on_deploy = module.params['scan_on_deploy']
        self.source_path = module.params['source_path']
        self.output_format = module.params['output_format']
        self.severity_threshold = module.params['severity_threshold']
        self.target_url = module.params['target_url']
        
        self.results = {
            'scan_results': {},
            'vulnerabilities': [],
            'critical_count': 0,
            'high_count': 0,
            'medium_count': 0,
            'low_count': 0,
            'passed': True
        }
        
    def run_command(self, command, timeout=300):
        """Run command and return output"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)
            
    def run_trivy_scan(self):
        """Run Trivy container vulnerability scan"""
        if not self.image:
            return {'error': 'No image specified for Trivy scan'}
            
        cmd = f"trivy image --format json --severity {self.severity_threshold} {self.image}"
        returncode, stdout, stderr = self.run_command(cmd)
        
        if returncode != 0:
            return {'error': f'Trivy scan failed: {stderr}'}
            
        try:
            trivy_results = json.loads(stdout)
            vulnerabilities = []
            
            for result in trivy_results.get('Results', []):
                for vuln in result.get('Vulnerabilities', []):
                    vulnerabilities.append({
                        'tool': 'trivy',
                        'type': 'container',
                        'severity': vuln.get('Severity', 'UNKNOWN'),
                        'title': vuln.get('Title', 'Unknown'),
                        'description': vuln.get('Description', ''),
                        'package': vuln.get('PkgName', 'unknown'),
                        'installed_version': vuln.get('InstalledVersion', 'unknown'),
                        'fixed_version': vuln.get('FixedVersion', 'unknown'),
                        'vulnerability_id': vuln.get('VulnerabilityID', 'unknown')
                    })
                    
            return {
                'vulnerabilities': vulnerabilities,
                'total_count': len(vulnerabilities),
                'scan_target': self.image
            }
            
        except json.JSONDecodeError:
            return {'error': 'Failed to parse Trivy JSON output'}
            
    def run_bandit_scan(self):
        """Run Bandit Python security scan"""
        if not os.path.exists(self.source_path):
            return {'error': f'Source path {self.source_path} does not exist'}
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name
            
        try:
            cmd = f"bandit -r {self.source_path} -f json -o {output_file} -ll"
            returncode, stdout, stderr = self.run_command(cmd)
            
            # Bandit returns 1 when issues are found, which is expected
            if returncode > 1:
                return {'error': f'Bandit scan failed: {stderr}'}
                
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    bandit_results = json.load(f)
                    
                vulnerabilities = []
                for result in bandit_results.get('results', []):
                    severity_map = {
                        'LOW': 'LOW',
                        'MEDIUM': 'MEDIUM', 
                        'HIGH': 'HIGH'
                    }
                    
                    vulnerabilities.append({
                        'tool': 'bandit',
                        'type': 'sast',
                        'severity': severity_map.get(result.get('issue_severity', 'MEDIUM'), 'MEDIUM'),
                        'title': result.get('test_name', 'Unknown'),
                        'description': result.get('issue_text', ''),
                        'file': result.get('filename', 'unknown'),
                        'line': result.get('line_number', 0),
                        'code': result.get('code', ''),
                        'test_id': result.get('test_id', 'unknown')
                    })
                    
                return {
                    'vulnerabilities': vulnerabilities,
                    'total_count': len(vulnerabilities),
                    'scan_target': self.source_path
                }
            else:
                return {'error': 'Bandit output file not found'}
                
        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)
                
    def run_safety_scan(self):
        """Run Safety dependency vulnerability scan"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name
            
        try:
            cmd = f"safety check --json --output {output_file}"
            returncode, stdout, stderr = self.run_command(cmd)
            
            if returncode != 0 and not os.path.exists(output_file):
                return {'error': f'Safety scan failed: {stderr}'}
                
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    safety_results = json.load(f)
                    
                vulnerabilities = []
                for vuln in safety_results:
                    vulnerabilities.append({
                        'tool': 'safety',
                        'type': 'dependency',
                        'severity': 'HIGH',  # Safety reports are generally high severity
                        'title': f"Vulnerability in {vuln.get('package', 'unknown')}",
                        'description': vuln.get('advisory', ''),
                        'package': vuln.get('package', 'unknown'),
                        'installed_version': vuln.get('installed_version', 'unknown'),
                        'vulnerability_id': vuln.get('vulnerability_id', 'unknown')
                    })
                    
                return {
                    'vulnerabilities': vulnerabilities,
                    'total_count': len(vulnerabilities),
                    'scan_target': 'dependencies'
                }
            else:
                return {'vulnerabilities': [], 'total_count': 0, 'scan_target': 'dependencies'}
                
        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)
                
    def run_semgrep_scan(self):
        """Run Semgrep SAST scan"""
        if not os.path.exists(self.source_path):
            return {'error': f'Source path {self.source_path} does not exist'}
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name
            
        try:
            cmd = f"semgrep --config=auto --json -o {output_file} {self.source_path}"
            returncode, stdout, stderr = self.run_command(cmd)
            
            if returncode != 0 and not os.path.exists(output_file):
                return {'error': f'Semgrep scan failed: {stderr}'}
                
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    semgrep_results = json.load(f)
                    
                vulnerabilities = []
                for result in semgrep_results.get('results', []):
                    severity_map = {
                        'ERROR': 'HIGH',
                        'WARNING': 'MEDIUM',
                        'INFO': 'LOW'
                    }
                    
                    vulnerabilities.append({
                        'tool': 'semgrep',
                        'type': 'sast',
                        'severity': severity_map.get(result.get('extra', {}).get('severity', 'MEDIUM'), 'MEDIUM'),
                        'title': result.get('check_id', 'Unknown'),
                        'description': result.get('extra', {}).get('message', ''),
                        'file': result.get('path', 'unknown'),
                        'line': result.get('start', {}).get('line', 0),
                        'rule_id': result.get('check_id', 'unknown')
                    })
                    
                return {
                    'vulnerabilities': vulnerabilities,
                    'total_count': len(vulnerabilities),
                    'scan_target': self.source_path
                }
            else:
                return {'vulnerabilities': [], 'total_count': 0, 'scan_target': self.source_path}
                
        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)
                
    def run_zap_scan(self):
        """Run OWASP ZAP DAST scan"""
        if not self.target_url:
            return {'error': 'No target URL specified for ZAP scan'}
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name
            
        try:
            cmd = f"zap-baseline.py -t {self.target_url} -J {output_file}"
            returncode, stdout, stderr = self.run_command(cmd, timeout=600)
            
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    zap_results = json.load(f)
                    
                vulnerabilities = []
                for site in zap_results.get('site', []):
                    for alert in site.get('alerts', []):
                        risk_map = {
                            'High': 'HIGH',
                            'Medium': 'MEDIUM',
                            'Low': 'LOW',
                            'Informational': 'INFO'
                        }
                        
                        vulnerabilities.append({
                            'tool': 'zap',
                            'type': 'dast',
                            'severity': risk_map.get(alert.get('riskdesc', 'MEDIUM'), 'MEDIUM'),
                            'title': alert.get('name', 'Unknown'),
                            'description': alert.get('desc', ''),
                            'url': alert.get('url', self.target_url),
                            'method': alert.get('method', 'GET'),
                            'param': alert.get('param', ''),
                            'attack': alert.get('attack', ''),
                            'evidence': alert.get('evidence', ''),
                            'solution': alert.get('solution', ''),
                            'reference': alert.get('reference', ''),
                            'cweid': alert.get('cweid', ''),
                            'wascid': alert.get('wascid', ''),
                            'confidence': alert.get('confidence', ''),
                            'pluginid': alert.get('pluginid', '')
                        })
                        
                return {
                    'vulnerabilities': vulnerabilities,
                    'total_count': len(vulnerabilities),
                    'scan_target': self.target_url
                }
            else:
                return {'vulnerabilities': [], 'total_count': 0, 'scan_target': self.target_url}
                
        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)
                
    def aggregate_results(self):
        """Aggregate results from all scans"""
        all_vulnerabilities = []
        
        for tool in self.tools:
            if tool == 'trivy':
                result = self.run_trivy_scan()
            elif tool == 'bandit':
                result = self.run_bandit_scan()
            elif tool == 'safety':
                result = self.run_safety_scan()
            elif tool == 'semgrep':
                result = self.run_semgrep_scan()
            elif tool == 'zap':
                result = self.run_zap_scan()
            else:
                result = {'error': f'Unknown tool: {tool}'}
                
            self.results['scan_results'][tool] = result
            
            if 'vulnerabilities' in result:
                all_vulnerabilities.extend(result['vulnerabilities'])
                
        # Count vulnerabilities by severity
        severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'INFO': 0}
        
        for vuln in all_vulnerabilities:
            severity = vuln.get('severity', 'MEDIUM').upper()
            if severity in severity_counts:
                severity_counts[severity] += 1
                
        self.results.update({
            'vulnerabilities': all_vulnerabilities,
            'critical_count': severity_counts['CRITICAL'],
            'high_count': severity_counts['HIGH'],
            'medium_count': severity_counts['MEDIUM'],
            'low_count': severity_counts['LOW'] + severity_counts['INFO'],
            'total_count': len(all_vulnerabilities)
        })
        
        # Determine if scan passed
        if self.fail_on_critical and severity_counts['CRITICAL'] > 0:
            self.results['passed'] = False
        elif self.severity_threshold == 'HIGH' and severity_counts['HIGH'] > 0:
            self.results['passed'] = False
        elif self.severity_threshold == 'MEDIUM' and (severity_counts['HIGH'] > 0 or severity_counts['MEDIUM'] > 0):
            self.results['passed'] = False
            
        return self.results
        
    def scan(self):
        """Run all security scans"""
        return self.aggregate_results()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            namespace=dict(type='str'),
            image=dict(type='str'),
            tools=dict(type='list', default=['trivy', 'bandit', 'safety']),
            fail_on_critical=dict(type='bool', default=True),
            scan_on_deploy=dict(type='bool', default=False),
            source_path=dict(type='str', default='/app'),
            output_format=dict(type='str', default='json', choices=['json', 'table', 'sarif']),
            severity_threshold=dict(type='str', default='MEDIUM', choices=['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']),
            target_url=dict(type='str')
        ),
        supports_check_mode=True
    )
    
    scanner = SecurityScanner(module)
    
    try:
        results = scanner.scan()
        
        if not results['passed'] and module.params['fail_on_critical']:
            module.fail_json(
                msg=f"Security scan failed: {results['critical_count']} critical vulnerabilities found",
                **results
            )
        else:
            module.exit_json(changed=True, **results)
            
    except Exception as e:
        module.fail_json(msg=f"Security scan failed: {str(e)}")


if __name__ == '__main__':
    main()