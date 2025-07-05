#!/usr/bin/env python3
"""
Monitoring Configuration Manager Ansible Module
Manages Prometheus and Grafana configuration for TaskFlow
"""

import json
import yaml
import base64
from ansible.module_utils.basic import AnsibleModule
from kubernetes import client, config
from kubernetes.client.rest import ApiException


DOCUMENTATION = '''
---
module: monitoring_config_manager
short_description: Manage monitoring configuration for TaskFlow
description:
    - Configures Prometheus for metrics collection
    - Sets up Grafana dashboards and data sources
    - Manages alerting rules
    - Creates monitoring infrastructure
version_added: "1.0.0"
options:
    namespace:
        description: Kubernetes namespace for monitoring
        required: true
        type: str
    app_name:
        description: Application name
        required: true
        type: str
    monitoring_config:
        description: Monitoring configuration
        required: true
        type: dict
    environment:
        description: Environment name
        required: true
        type: str
    prometheus_enabled:
        description: Enable Prometheus
        required: false
        default: true
        type: bool
    grafana_enabled:
        description: Enable Grafana
        required: false
        default: true
        type: bool
    create_monitoring_namespace:
        description: Create monitoring namespace
        required: false
        default: true
        type: bool
'''

EXAMPLES = '''
- name: Setup monitoring stack
  monitoring_config_manager:
    namespace: taskflow-monitoring
    app_name: taskflow
    environment: development
    monitoring_config:
      prometheus:
        enabled: true
        retention_time: "15d"
        scrape_interval: "30s"
      grafana:
        enabled: true
        admin_password: "admin123"
    prometheus_enabled: true
    grafana_enabled: true
'''

RETURN = '''
prometheus_config:
    description: Prometheus configuration status
    type: dict
    returned: always
grafana_config:
    description: Grafana configuration status
    type: dict
    returned: always
dashboards_created:
    description: List of created dashboards
    type: list
    returned: always
alerting_rules:
    description: Alerting rules configuration
    type: dict
    returned: always
'''


class MonitoringConfigManager:
    def __init__(self, module):
        self.module = module
        self.namespace = module.params['namespace']
        self.app_name = module.params['app_name']
        self.monitoring_config = module.params['monitoring_config']
        self.environment = module.params['environment']
        self.prometheus_enabled = module.params['prometheus_enabled']
        self.grafana_enabled = module.params['grafana_enabled']
        self.create_monitoring_namespace = module.params['create_monitoring_namespace']
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
            
        self.k8s_core = client.CoreV1Api()
        self.k8s_apps = client.AppsV1Api()
        self.k8s_custom = client.CustomObjectsApi()
        
    def create_namespace(self):
        """Create monitoring namespace if it doesn't exist"""
        if not self.create_monitoring_namespace:
            return False
            
        namespace = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=self.namespace,
                labels={
                    'name': self.namespace,
                    'purpose': 'monitoring',
                    'app': self.app_name,
                    'environment': self.environment
                }
            )
        )
        
        try:
            self.k8s_core.create_namespace(body=namespace)
            return True
        except ApiException as e:
            if e.status == 409:  # Already exists
                return False
            else:
                raise
                
    def create_prometheus_config(self):
        """Create Prometheus configuration"""
        prometheus_config = {
            'global': {
                'scrape_interval': self.monitoring_config.get('prometheus', {}).get('scrape_interval', '30s'),
                'evaluation_interval': self.monitoring_config.get('prometheus', {}).get('evaluation_interval', '30s')
            },
            'rule_files': [
                '/etc/prometheus/rules/*.yml'
            ],
            'scrape_configs': [
                {
                    'job_name': 'prometheus',
                    'static_configs': [
                        {
                            'targets': ['localhost:9090']
                        }
                    ]
                },
                {
                    'job_name': f'{self.app_name}-{self.environment}',
                    'kubernetes_sd_configs': [
                        {
                            'role': 'pod',
                            'namespaces': {
                                'names': [f'{self.app_name}-{self.environment}']
                            }
                        }
                    ],
                    'relabel_configs': [
                        {
                            'source_labels': ['__meta_kubernetes_pod_annotation_prometheus_io_scrape'],
                            'action': 'keep',
                            'regex': 'true'
                        },
                        {
                            'source_labels': ['__meta_kubernetes_pod_annotation_prometheus_io_path'],
                            'action': 'replace',
                            'target_label': '__metrics_path__',
                            'regex': '(.+)'
                        },
                        {
                            'source_labels': ['__address__', '__meta_kubernetes_pod_annotation_prometheus_io_port'],
                            'action': 'replace',
                            'regex': '([^:]+)(?::\\d+)?;(\\d+)',
                            'replacement': '${1}:${2}',
                            'target_label': '__address__'
                        }
                    ]
                },
                {
                    'job_name': 'kubernetes-pods',
                    'kubernetes_sd_configs': [
                        {
                            'role': 'pod'
                        }
                    ],
                    'relabel_configs': [
                        {
                            'source_labels': ['__meta_kubernetes_pod_label_app'],
                            'action': 'keep',
                            'regex': self.app_name
                        }
                    ]
                }
            ],
            'alerting': {
                'alertmanagers': [
                    {
                        'static_configs': [
                            {
                                'targets': ['alertmanager:9093']
                            }
                        ]
                    }
                ]
            }
        }
        
        # Create ConfigMap for Prometheus configuration
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name='prometheus-config',
                namespace=self.namespace,
                labels={
                    'app': 'prometheus',
                    'component': 'config'
                }
            ),
            data={
                'prometheus.yml': yaml.dump(prometheus_config, default_flow_style=False)
            }
        )
        
        try:
            self.k8s_core.create_namespaced_config_map(
                namespace=self.namespace,
                body=configmap
            )
            created = True
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.k8s_core.patch_namespaced_config_map(
                    name='prometheus-config',
                    namespace=self.namespace,
                    body=configmap
                )
                created = False
            else:
                raise
                
        return {'created': created, 'config': prometheus_config}
        
    def create_prometheus_alerting_rules(self):
        """Create Prometheus alerting rules"""
        alerting_rules = {
            'groups': [
                {
                    'name': f'{self.app_name}-alerts',
                    'rules': [
                        {
                            'alert': f'{self.app_name.title()}HighErrorRate',
                            'expr': f'rate(http_requests_total{{job="{self.app_name}-{self.environment}",status=~"5.."}}[5m]) > 0.1',
                            'for': '5m',
                            'labels': {
                                'severity': 'critical',
                                'service': self.app_name,
                                'environment': self.environment
                            },
                            'annotations': {
                                'summary': f'{self.app_name.title()} high error rate',
                                'description': f'{self.app_name.title()} is experiencing high error rate (>10%) for more than 5 minutes'
                            }
                        },
                        {
                            'alert': f'{self.app_name.title()}HighResponseTime',
                            'expr': f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{job="{self.app_name}-{self.environment}"}}[5m])) > 0.5',
                            'for': '5m',
                            'labels': {
                                'severity': 'warning',
                                'service': self.app_name,
                                'environment': self.environment
                            },
                            'annotations': {
                                'summary': f'{self.app_name.title()} high response time',
                                'description': f'{self.app_name.title()} 95th percentile response time is above 500ms'
                            }
                        },
                        {
                            'alert': f'{self.app_name.title()}PodCrashLooping',
                            'expr': f'rate(kube_pod_container_status_restarts_total{{namespace="{self.app_name}-{self.environment}"}}[15m]) > 0',
                            'for': '5m',
                            'labels': {
                                'severity': 'critical',
                                'service': self.app_name,
                                'environment': self.environment
                            },
                            'annotations': {
                                'summary': f'{self.app_name.title()} pod crash looping',
                                'description': f'{self.app_name.title()} pod is crash looping in namespace {self.app_name}-{self.environment}'
                            }
                        },
                        {
                            'alert': f'{self.app_name.title()}HighMemoryUsage',
                            'expr': f'(container_memory_working_set_bytes{{namespace="{self.app_name}-{self.environment}"}}/container_spec_memory_limit_bytes) > 0.8',
                            'for': '10m',
                            'labels': {
                                'severity': 'warning',
                                'service': self.app_name,
                                'environment': self.environment
                            },
                            'annotations': {
                                'summary': f'{self.app_name.title()} high memory usage',
                                'description': f'{self.app_name.title()} memory usage is above 80% of limit'
                            }
                        },
                        {
                            'alert': f'{self.app_name.title()}HighCPUUsage',
                            'expr': f'(rate(container_cpu_usage_seconds_total{{namespace="{self.app_name}-{self.environment}"}}[5m])/container_spec_cpu_quota*container_spec_cpu_period) > 0.8',
                            'for': '10m',
                            'labels': {
                                'severity': 'warning',
                                'service': self.app_name,
                                'environment': self.environment
                            },
                            'annotations': {
                                'summary': f'{self.app_name.title()} high CPU usage',
                                'description': f'{self.app_name.title()} CPU usage is above 80% of limit'
                            }
                        }
                    ]
                }
            ]
        }
        
        # Create ConfigMap for alerting rules
        rules_configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name='prometheus-rules',
                namespace=self.namespace,
                labels={
                    'app': 'prometheus',
                    'component': 'rules'
                }
            ),
            data={
                f'{self.app_name}-rules.yml': yaml.dump(alerting_rules, default_flow_style=False)
            }
        )
        
        try:
            self.k8s_core.create_namespaced_config_map(
                namespace=self.namespace,
                body=rules_configmap
            )
            created = True
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.k8s_core.patch_namespaced_config_map(
                    name='prometheus-rules',
                    namespace=self.namespace,
                    body=rules_configmap
                )
                created = False
            else:
                raise
                
        return {'created': created, 'rules': alerting_rules}
        
    def create_grafana_datasources(self):
        """Create Grafana data sources configuration"""
        datasources = {
            'apiVersion': 1,
            'datasources': [
                {
                    'name': 'Prometheus',
                    'type': 'prometheus',
                    'access': 'proxy',
                    'url': f'http://prometheus.{self.namespace}.svc.cluster.local:9090',
                    'isDefault': True,
                    'editable': True
                }
            ]
        }
        
        # Create ConfigMap for Grafana data sources
        datasources_configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name='grafana-datasources',
                namespace=self.namespace,
                labels={
                    'app': 'grafana',
                    'component': 'datasources'
                }
            ),
            data={
                'datasources.yaml': yaml.dump(datasources, default_flow_style=False)
            }
        )
        
        try:
            self.k8s_core.create_namespaced_config_map(
                namespace=self.namespace,
                body=datasources_configmap
            )
            created = True
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.k8s_core.patch_namespaced_config_map(
                    name='grafana-datasources',
                    namespace=self.namespace,
                    body=datasources_configmap
                )
                created = False
            else:
                raise
                
        return {'created': created, 'datasources': datasources}
        
    def create_grafana_dashboards(self):
        """Create Grafana dashboards"""
        taskflow_dashboard = {
            'dashboard': {
                'id': None,
                'title': f'{self.app_name.title()} - {self.environment.title()} Dashboard',
                'uid': f'{self.app_name}-{self.environment}',
                'version': 1,
                'schemaVersion': 27,
                'time': {
                    'from': 'now-1h',
                    'to': 'now'
                },
                'timepicker': {
                    'refresh_intervals': ['5s', '10s', '30s', '1m', '5m', '15m', '30m', '1h']
                },
                'refresh': '30s',
                'panels': [
                    {
                        'id': 1,
                        'title': 'Request Rate',
                        'type': 'stat',
                        'targets': [
                            {
                                'expr': f'rate(http_requests_total{{job="{self.app_name}-{self.environment}"}}[5m])',
                                'legendFormat': 'Requests/sec'
                            }
                        ],
                        'gridPos': {'h': 8, 'w': 6, 'x': 0, 'y': 0}
                    },
                    {
                        'id': 2,
                        'title': 'Response Time (95th percentile)',
                        'type': 'stat',
                        'targets': [
                            {
                                'expr': f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{job="{self.app_name}-{self.environment}"}}[5m]))',
                                'legendFormat': '95th percentile'
                            }
                        ],
                        'gridPos': {'h': 8, 'w': 6, 'x': 6, 'y': 0},
                        'unit': 's'
                    },
                    {
                        'id': 3,
                        'title': 'Error Rate',
                        'type': 'stat',
                        'targets': [
                            {
                                'expr': f'rate(http_requests_total{{job="{self.app_name}-{self.environment}",status=~"5.."}}[5m])',
                                'legendFormat': 'Error rate'
                            }
                        ],
                        'gridPos': {'h': 8, 'w': 6, 'x': 12, 'y': 0}
                    },
                    {
                        'id': 4,
                        'title': 'Active Pods',
                        'type': 'stat',
                        'targets': [
                            {
                                'expr': f'kube_deployment_status_replicas_available{{deployment="{self.app_name}-{self.environment}"}}',
                                'legendFormat': 'Available pods'
                            }
                        ],
                        'gridPos': {'h': 8, 'w': 6, 'x': 18, 'y': 0}
                    },
                    {
                        'id': 5,
                        'title': 'HTTP Requests by Status',
                        'type': 'timeseries',
                        'targets': [
                            {
                                'expr': f'rate(http_requests_total{{job="{self.app_name}-{self.environment}"}}[5m])',
                                'legendFormat': '{{status}}'
                            }
                        ],
                        'gridPos': {'h': 8, 'w': 12, 'x': 0, 'y': 8}
                    },
                    {
                        'id': 6,
                        'title': 'Resource Usage',
                        'type': 'timeseries',
                        'targets': [
                            {
                                'expr': f'rate(container_cpu_usage_seconds_total{{namespace="{self.app_name}-{self.environment}"}}[5m])',
                                'legendFormat': 'CPU Usage'
                            },
                            {
                                'expr': f'container_memory_working_set_bytes{{namespace="{self.app_name}-{self.environment}"}}',
                                'legendFormat': 'Memory Usage'
                            }
                        ],
                        'gridPos': {'h': 8, 'w': 12, 'x': 12, 'y': 8}
                    }
                ]
            },
            'overwrite': True
        }
        
        # Create ConfigMap for Grafana dashboards
        dashboards_configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name='grafana-dashboards',
                namespace=self.namespace,
                labels={
                    'app': 'grafana',
                    'component': 'dashboards'
                }
            ),
            data={
                f'{self.app_name}-dashboard.json': json.dumps(taskflow_dashboard, indent=2)
            }
        )
        
        try:
            self.k8s_core.create_namespaced_config_map(
                namespace=self.namespace,
                body=dashboards_configmap
            )
            created = True
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.k8s_core.patch_namespaced_config_map(
                    name='grafana-dashboards',
                    namespace=self.namespace,
                    body=dashboards_configmap
                )
                created = False
            else:
                raise
                
        return {'created': created, 'dashboard': taskflow_dashboard}
        
    def setup_monitoring(self):
        """Setup complete monitoring stack"""
        results = {
            'namespace_created': False,
            'prometheus_config': {},
            'grafana_config': {},
            'dashboards_created': [],
            'alerting_rules': {}
        }
        
        # Create namespace
        results['namespace_created'] = self.create_namespace()
        
        # Setup Prometheus
        if self.prometheus_enabled:
            results['prometheus_config'] = self.create_prometheus_config()
            results['alerting_rules'] = self.create_prometheus_alerting_rules()
            
        # Setup Grafana
        if self.grafana_enabled:
            datasources = self.create_grafana_datasources()
            dashboards = self.create_grafana_dashboards()
            
            results['grafana_config'] = {
                'datasources': datasources,
                'dashboards': dashboards
            }
            results['dashboards_created'] = [f'{self.app_name}-dashboard']
            
        return results


def main():
    module = AnsibleModule(
        argument_spec=dict(
            namespace=dict(type='str', required=True),
            app_name=dict(type='str', required=True),
            monitoring_config=dict(type='dict', required=True),
            environment=dict(type='str', required=True),
            prometheus_enabled=dict(type='bool', default=True),
            grafana_enabled=dict(type='bool', default=True),
            create_monitoring_namespace=dict(type='bool', default=True)
        ),
        supports_check_mode=True
    )
    
    manager = MonitoringConfigManager(module)
    
    try:
        results = manager.setup_monitoring()
        module.exit_json(changed=True, **results)
        
    except Exception as e:
        module.fail_json(msg=f"Monitoring configuration failed: {str(e)}")


if __name__ == '__main__':
    main()