#!/usr/bin/env python3
"""
Infrastructure Validator Ansible Module
Validates TaskFlow infrastructure and compliance
"""

import json
import time
import requests
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url
from kubernetes import client, config
from kubernetes.client.rest import ApiException


DOCUMENTATION = '''
---
module: infrastructure_validator
short_description: Validate TaskFlow infrastructure and compliance
description:
    - Validates deployment readiness and health
    - Performs compliance checks
    - Tests performance thresholds
    - Validates security configurations
version_added: "1.0.0"
options:
    namespace:
        description: Kubernetes namespace
        required: true
        type: str
    app_name:
        description: Application name
        required: true
        type: str
    environment:
        description: Environment name
        required: true
        type: str
    expected_replicas:
        description: Expected number of replicas
        required: true
        type: int
    health_check_url:
        description: URL for health checks
        required: false
        type: str
    performance_thresholds:
        description: Performance thresholds to validate
        required: false
        type: dict
    compliance_checks:
        description: List of compliance checks to perform
        required: false
        default: ["security_context", "resource_limits", "health_checks"]
        type: list
    timeout:
        description: Timeout for validation checks (seconds)
        required: false
        default: 300
        type: int
'''

EXAMPLES = '''
- name: Validate infrastructure
  infrastructure_validator:
    namespace: taskflow-dev
    app_name: taskflow
    environment: development
    expected_replicas: 2
    health_check_url: "http://taskflow-dev.local/docs"
    performance_thresholds:
      response_time_ms: 200
      cpu_usage_percent: 80
      memory_usage_percent: 80
    compliance_checks:
      - security_context
      - resource_limits
      - health_checks
      - network_policies
'''

RETURN = '''
validation_results:
    description: Overall validation results
    type: dict
    returned: always
deployment_health:
    description: Deployment health status
    type: dict
    returned: always
performance_results:
    description: Performance test results
    type: dict
    returned: always
compliance_results:
    description: Compliance check results
    type: dict
    returned: always
passed:
    description: Whether all validations passed
    type: bool
    returned: always
'''


class InfrastructureValidator:
    def __init__(self, module):
        self.module = module
        self.namespace = module.params['namespace']
        self.app_name = module.params['app_name']
        self.environment = module.params['environment']
        self.expected_replicas = module.params['expected_replicas']
        self.health_check_url = module.params['health_check_url']
        self.performance_thresholds = module.params['performance_thresholds'] or {}
        self.compliance_checks = module.params['compliance_checks']
        self.timeout = module.params['timeout']
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
            
        self.k8s_core = client.CoreV1Api()
        self.k8s_apps = client.AppsV1Api()
        self.k8s_metrics = client.MetricsV1beta1Api()
        
        self.results = {
            'validation_results': {},
            'deployment_health': {},
            'performance_results': {},
            'compliance_results': {},
            'passed': True
        }
        
    def validate_deployment_readiness(self):
        """Validate deployment is ready and healthy"""
        try:
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"{self.app_name}-{self.environment}",
                namespace=self.namespace
            )
            
            # Check replica count
            ready_replicas = deployment.status.ready_replicas or 0
            available_replicas = deployment.status.available_replicas or 0
            updated_replicas = deployment.status.updated_replicas or 0
            
            replica_check = {
                'expected': self.expected_replicas,
                'ready': ready_replicas,
                'available': available_replicas,
                'updated': updated_replicas,
                'passed': ready_replicas >= self.expected_replicas
            }
            
            # Check deployment conditions
            conditions = []
            deployment_available = False
            deployment_progressing = False
            
            for condition in (deployment.status.conditions or []):
                conditions.append({
                    'type': condition.type,
                    'status': condition.status,
                    'reason': condition.reason,
                    'message': condition.message
                })
                
                if condition.type == 'Available' and condition.status == 'True':
                    deployment_available = True
                elif condition.type == 'Progressing' and condition.status == 'True':
                    deployment_progressing = True
                    
            condition_check = {
                'available': deployment_available,
                'progressing': deployment_progressing,
                'conditions': conditions,
                'passed': deployment_available and deployment_progressing
            }
            
            overall_passed = replica_check['passed'] and condition_check['passed']
            
            return {
                'deployment_name': f"{self.app_name}-{self.environment}",
                'replica_check': replica_check,
                'condition_check': condition_check,
                'passed': overall_passed
            }
            
        except ApiException as e:
            return {
                'error': f"Failed to validate deployment: {e}",
                'passed': False
            }
            
    def validate_pod_health(self):
        """Validate individual pod health"""
        try:
            pods = self.k8s_core.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app={self.app_name},environment={self.environment}"
            )
            
            pod_results = []
            healthy_pods = 0
            
            for pod in pods.items:
                pod_status = {
                    'name': pod.metadata.name,
                    'phase': pod.status.phase,
                    'ready': False,
                    'restarts': 0,
                    'conditions': []
                }
                
                # Check container statuses
                if pod.status.container_statuses:
                    for container in pod.status.container_statuses:
                        pod_status['ready'] = container.ready
                        pod_status['restarts'] = container.restart_count
                        
                # Check pod conditions
                if pod.status.conditions:
                    for condition in pod.status.conditions:
                        pod_status['conditions'].append({
                            'type': condition.type,
                            'status': condition.status,
                            'reason': condition.reason
                        })
                        
                if pod_status['phase'] == 'Running' and pod_status['ready']:
                    healthy_pods += 1
                    
                pod_results.append(pod_status)
                
            return {
                'total_pods': len(pods.items),
                'healthy_pods': healthy_pods,
                'expected_pods': self.expected_replicas,
                'pod_details': pod_results,
                'passed': healthy_pods >= self.expected_replicas
            }
            
        except ApiException as e:
            return {
                'error': f"Failed to validate pods: {e}",
                'passed': False
            }
            
    def validate_service_connectivity(self):
        """Validate service connectivity"""
        try:
            service = self.k8s_core.read_namespaced_service(
                name=f"{self.app_name}-service",
                namespace=self.namespace
            )
            
            # Get endpoints
            try:
                endpoints = self.k8s_core.read_namespaced_endpoints(
                    name=f"{self.app_name}-service",
                    namespace=self.namespace
                )
                
                endpoint_count = 0
                if endpoints.subsets:
                    for subset in endpoints.subsets:
                        if subset.addresses:
                            endpoint_count += len(subset.addresses)
                            
            except ApiException:
                endpoint_count = 0
                
            return {
                'service_name': f"{self.app_name}-service",
                'cluster_ip': service.spec.cluster_ip,
                'ports': [{'port': port.port, 'target_port': port.target_port} for port in service.spec.ports],
                'endpoint_count': endpoint_count,
                'expected_endpoints': self.expected_replicas,
                'passed': endpoint_count >= self.expected_replicas
            }
            
        except ApiException as e:
            return {
                'error': f"Failed to validate service: {e}",
                'passed': False
            }
            
    def validate_application_health(self):
        """Validate application health via HTTP"""
        if not self.health_check_url:
            return {'skipped': True, 'reason': 'No health check URL provided'}
            
        try:
            start_time = time.time()
            response = requests.get(
                self.health_check_url,
                timeout=10,
                verify=False  # For development/testing
            )
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            return {
                'url': self.health_check_url,
                'status_code': response.status_code,
                'response_time_ms': round(response_time, 2),
                'content_length': len(response.content),
                'passed': response.status_code == 200
            }
            
        except requests.RequestException as e:
            return {
                'url': self.health_check_url,
                'error': str(e),
                'passed': False
            }
            
    def validate_performance_thresholds(self):
        """Validate performance against thresholds"""
        results = {}
        
        # Response time check
        if 'response_time_ms' in self.performance_thresholds:
            if self.health_check_url:
                try:
                    # Test multiple requests for average
                    response_times = []
                    for _ in range(3):
                        start_time = time.time()
                        response = requests.get(self.health_check_url, timeout=5)
                        response_time = (time.time() - start_time) * 1000
                        response_times.append(response_time)
                        time.sleep(1)
                        
                    avg_response_time = sum(response_times) / len(response_times)
                    threshold = self.performance_thresholds['response_time_ms']
                    
                    results['response_time'] = {
                        'average_ms': round(avg_response_time, 2),
                        'threshold_ms': threshold,
                        'samples': response_times,
                        'passed': avg_response_time <= threshold
                    }
                    
                except Exception as e:
                    results['response_time'] = {
                        'error': str(e),
                        'passed': False
                    }
            else:
                results['response_time'] = {
                    'skipped': True,
                    'reason': 'No health check URL provided'
                }
                
        # Resource utilization checks
        if 'cpu_usage_percent' in self.performance_thresholds or 'memory_usage_percent' in self.performance_thresholds:
            try:
                # Get pod metrics
                pod_metrics = self.k8s_metrics.list_namespaced_pod_metrics(namespace=self.namespace)
                
                cpu_usage = []
                memory_usage = []
                
                for pod_metric in pod_metrics.items:
                    if pod_metric.metadata.labels.get('app') == self.app_name:
                        for container in pod_metric.containers:
                            # CPU usage in millicores
                            cpu_value = container.usage['cpu']
                            if cpu_value.endswith('n'):
                                cpu_millicores = float(cpu_value[:-1]) / 1000000
                            elif cpu_value.endswith('m'):
                                cpu_millicores = float(cpu_value[:-1])
                            else:
                                cpu_millicores = float(cpu_value) * 1000
                                
                            cpu_usage.append(cpu_millicores)
                            
                            # Memory usage in bytes
                            memory_value = container.usage['memory']
                            if memory_value.endswith('Ki'):
                                memory_bytes = float(memory_value[:-2]) * 1024
                            elif memory_value.endswith('Mi'):
                                memory_bytes = float(memory_value[:-2]) * 1024 * 1024
                            elif memory_value.endswith('Gi'):
                                memory_bytes = float(memory_value[:-2]) * 1024 * 1024 * 1024
                            else:
                                memory_bytes = float(memory_value)
                                
                            memory_usage.append(memory_bytes)
                            
                if cpu_usage and 'cpu_usage_percent' in self.performance_thresholds:
                    avg_cpu = sum(cpu_usage) / len(cpu_usage)
                    # Assuming 200m CPU limit for percentage calculation
                    cpu_limit_millicores = 200
                    cpu_percent = (avg_cpu / cpu_limit_millicores) * 100
                    
                    results['cpu_usage'] = {
                        'average_millicores': round(avg_cpu, 2),
                        'average_percent': round(cpu_percent, 2),
                        'threshold_percent': self.performance_thresholds['cpu_usage_percent'],
                        'passed': cpu_percent <= self.performance_thresholds['cpu_usage_percent']
                    }
                    
                if memory_usage and 'memory_usage_percent' in self.performance_thresholds:
                    avg_memory = sum(memory_usage) / len(memory_usage)
                    # Assuming 256Mi memory limit for percentage calculation
                    memory_limit_bytes = 256 * 1024 * 1024
                    memory_percent = (avg_memory / memory_limit_bytes) * 100
                    
                    results['memory_usage'] = {
                        'average_bytes': round(avg_memory, 2),
                        'average_mb': round(avg_memory / (1024 * 1024), 2),
                        'average_percent': round(memory_percent, 2),
                        'threshold_percent': self.performance_thresholds['memory_usage_percent'],
                        'passed': memory_percent <= self.performance_thresholds['memory_usage_percent']
                    }
                    
            except Exception as e:
                results['resource_metrics'] = {
                    'error': f"Failed to get metrics: {e}",
                    'passed': False
                }
                
        return results
        
    def validate_security_compliance(self):
        """Validate security compliance"""
        compliance_results = {}
        
        for check in self.compliance_checks:
            if check == 'security_context':
                compliance_results['security_context'] = self._check_security_context()
            elif check == 'resource_limits':
                compliance_results['resource_limits'] = self._check_resource_limits()
            elif check == 'health_checks':
                compliance_results['health_checks'] = self._check_health_checks()
            elif check == 'network_policies':
                compliance_results['network_policies'] = self._check_network_policies()
                
        return compliance_results
        
    def _check_security_context(self):
        """Check security context configuration"""
        try:
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"{self.app_name}-{self.environment}",
                namespace=self.namespace
            )
            
            pod_spec = deployment.spec.template.spec
            security_context = pod_spec.security_context
            
            checks = {
                'run_as_non_root': False,
                'run_as_user_set': False,
                'fs_group_set': False,
                'container_security_context': False
            }
            
            if security_context:
                checks['run_as_non_root'] = security_context.run_as_non_root is True
                checks['run_as_user_set'] = security_context.run_as_user is not None
                checks['fs_group_set'] = security_context.fs_group is not None
                
            # Check container security context
            for container in pod_spec.containers:
                if container.security_context:
                    if (container.security_context.allow_privilege_escalation is False and
                        container.security_context.capabilities and
                        container.security_context.capabilities.drop):
                        checks['container_security_context'] = True
                        
            passed = all(checks.values())
            
            return {
                'checks': checks,
                'passed': passed,
                'details': 'Security context properly configured' if passed else 'Security context needs improvement'
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'passed': False
            }
            
    def _check_resource_limits(self):
        """Check resource limits are set"""
        try:
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"{self.app_name}-{self.environment}",
                namespace=self.namespace
            )
            
            containers_with_limits = 0
            containers_with_requests = 0
            total_containers = len(deployment.spec.template.spec.containers)
            
            for container in deployment.spec.template.spec.containers:
                if container.resources:
                    if container.resources.limits:
                        containers_with_limits += 1
                    if container.resources.requests:
                        containers_with_requests += 1
                        
            return {
                'total_containers': total_containers,
                'containers_with_limits': containers_with_limits,
                'containers_with_requests': containers_with_requests,
                'passed': containers_with_limits == total_containers and containers_with_requests == total_containers,
                'details': f'{containers_with_limits}/{total_containers} containers have limits, {containers_with_requests}/{total_containers} have requests'
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'passed': False
            }
            
    def _check_health_checks(self):
        """Check health checks are configured"""
        try:
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"{self.app_name}-{self.environment}",
                namespace=self.namespace
            )
            
            containers_with_liveness = 0
            containers_with_readiness = 0
            total_containers = len(deployment.spec.template.spec.containers)
            
            for container in deployment.spec.template.spec.containers:
                if container.liveness_probe:
                    containers_with_liveness += 1
                if container.readiness_probe:
                    containers_with_readiness += 1
                    
            return {
                'total_containers': total_containers,
                'containers_with_liveness': containers_with_liveness,
                'containers_with_readiness': containers_with_readiness,
                'passed': containers_with_liveness == total_containers and containers_with_readiness == total_containers,
                'details': f'{containers_with_liveness}/{total_containers} containers have liveness probes, {containers_with_readiness}/{total_containers} have readiness probes'
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'passed': False
            }
            
    def _check_network_policies(self):
        """Check network policies exist"""
        try:
            network_policies = self.k8s_networking.list_namespaced_network_policy(
                namespace=self.namespace
            )
            
            policy_count = len(network_policies.items)
            
            return {
                'policy_count': policy_count,
                'passed': policy_count > 0,
                'details': f'{policy_count} network policies found'
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'passed': False
            }
            
    def validate_infrastructure(self):
        """Run all validation checks"""
        # Deployment readiness
        self.results['deployment_health'] = self.validate_deployment_readiness()
        
        # Pod health
        pod_health = self.validate_pod_health()
        self.results['deployment_health']['pod_health'] = pod_health
        
        # Service connectivity
        service_health = self.validate_service_connectivity()
        self.results['deployment_health']['service_health'] = service_health
        
        # Application health
        app_health = self.validate_application_health()
        self.results['deployment_health']['application_health'] = app_health
        
        # Performance validation
        self.results['performance_results'] = self.validate_performance_thresholds()
        
        # Compliance validation
        self.results['compliance_results'] = self.validate_security_compliance()
        
        # Overall validation status
        deployment_passed = self.results['deployment_health'].get('passed', False)
        pod_passed = pod_health.get('passed', False)
        service_passed = service_health.get('passed', False)
        app_passed = app_health.get('passed', True)  # True if skipped
        
        performance_passed = all(
            result.get('passed', True) for result in self.results['performance_results'].values()
        )
        
        compliance_passed = all(
            result.get('passed', True) for result in self.results['compliance_results'].values()
        )
        
        self.results['passed'] = all([
            deployment_passed,
            pod_passed,
            service_passed,
            app_passed,
            performance_passed,
            compliance_passed
        ])
        
        # Summary
        self.results['validation_results'] = {
            'deployment_health': deployment_passed,
            'pod_health': pod_passed,
            'service_health': service_passed,
            'application_health': app_passed,
            'performance': performance_passed,
            'compliance': compliance_passed,
            'overall_passed': self.results['passed']
        }
        
        return self.results


def main():
    module = AnsibleModule(
        argument_spec=dict(
            namespace=dict(type='str', required=True),
            app_name=dict(type='str', required=True),
            environment=dict(type='str', required=True),
            expected_replicas=dict(type='int', required=True),
            health_check_url=dict(type='str'),
            performance_thresholds=dict(type='dict', default={}),
            compliance_checks=dict(type='list', default=['security_context', 'resource_limits', 'health_checks']),
            timeout=dict(type='int', default=300)
        ),
        supports_check_mode=True
    )
    
    validator = InfrastructureValidator(module)
    
    try:
        results = validator.validate_infrastructure()
        
        if not results['passed']:
            module.fail_json(
                msg="Infrastructure validation failed",
                **results
            )
        else:
            module.exit_json(changed=False, **results)
            
    except Exception as e:
        module.fail_json(msg=f"Infrastructure validation failed: {str(e)}")


if __name__ == '__main__':
    main()