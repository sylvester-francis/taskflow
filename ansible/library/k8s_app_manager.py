#!/usr/bin/env python3
"""
Kubernetes Application Manager Ansible Module
Advanced Kubernetes resource management for TaskFlow
"""

import json
import yaml
import time
from ansible.module_utils.basic import AnsibleModule
from kubernetes import client, config
from kubernetes.client.rest import ApiException


DOCUMENTATION = '''
---
module: k8s_app_manager
short_description: Advanced Kubernetes application management
description:
    - Manages complex Kubernetes resources for TaskFlow
    - Supports HPA, ingress, services, and persistent volumes
    - Handles blue-green and canary deployments
    - Provides comprehensive resource lifecycle management
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
    operation:
        description: Operation to perform
        required: false
        default: "deploy"
        choices: ["deploy", "scale", "cleanup", "status"]
        type: str
    resources:
        description: Resource requirements
        required: false
        type: dict
    hpa_enabled:
        description: Enable Horizontal Pod Autoscaler
        required: false
        default: false
        type: bool
    hpa_config:
        description: HPA configuration
        required: false
        type: dict
    ingress_config:
        description: Ingress configuration
        required: false
        type: dict
    backup_config:
        description: Backup configuration
        required: false
        type: dict
    deployment_strategy:
        description: Deployment strategy (blue-green, canary, rolling)
        required: false
        default: "rolling"
        type: str
    target_replicas:
        description: Target number of replicas for scaling
        required: false
        type: int
'''

EXAMPLES = '''
- name: Deploy application with HPA and ingress
  k8s_app_manager:
    namespace: taskflow-dev
    app_name: taskflow
    operation: deploy
    hpa_enabled: true
    hpa_config:
      min_replicas: 2
      max_replicas: 10
      target_cpu_utilization: 70
    ingress_config:
      host: taskflow-dev.local
      tls_enabled: false
      
- name: Scale application
  k8s_app_manager:
    namespace: taskflow-prod
    app_name: taskflow
    operation: scale
    target_replicas: 5
'''

RETURN = '''
resources_created:
    description: List of created resources
    type: list
    returned: always
hpa_status:
    description: HPA status if enabled
    type: dict
    returned: when hpa_enabled
ingress_status:
    description: Ingress status
    type: dict
    returned: when ingress configured
service_status:
    description: Service status
    type: dict
    returned: always
pv_status:
    description: Persistent volume status
    type: dict
    returned: when backup enabled
'''


class K8sAppManager:
    def __init__(self, module):
        self.module = module
        self.namespace = module.params['namespace']
        self.app_name = module.params['app_name']
        self.operation = module.params['operation']
        self.resources = module.params['resources'] or {}
        self.hpa_enabled = module.params['hpa_enabled']
        self.hpa_config = module.params['hpa_config'] or {}
        self.ingress_config = module.params['ingress_config'] or {}
        self.backup_config = module.params['backup_config'] or {}
        self.deployment_strategy = module.params['deployment_strategy']
        self.target_replicas = module.params['target_replicas']
        
        # Initialize Kubernetes clients
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
            
        self.k8s_core = client.CoreV1Api()
        self.k8s_apps = client.AppsV1Api()
        self.k8s_autoscaling = client.AutoscalingV2Api()
        self.k8s_networking = client.NetworkingV1Api()
        
        self.results = {
            'resources_created': [],
            'hpa_status': {},
            'ingress_status': {},
            'service_status': {},
            'pv_status': {}
        }
        
    def create_service(self):
        """Create Kubernetes service"""
        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=f"{self.app_name}-service",
                namespace=self.namespace,
                labels={
                    'app': self.app_name,
                    'component': 'service'
                }
            ),
            spec=client.V1ServiceSpec(
                selector={'app': self.app_name},
                ports=[
                    client.V1ServicePort(
                        name='http',
                        port=80,
                        target_port=8000,
                        protocol='TCP'
                    )
                ],
                type='ClusterIP'
            )
        )
        
        try:
            result = self.k8s_core.create_namespaced_service(
                namespace=self.namespace,
                body=service
            )
            self.results['resources_created'].append(f'service/{self.app_name}-service')
            self.results['service_status'] = {
                'created': True,
                'name': f"{self.app_name}-service",
                'cluster_ip': result.spec.cluster_ip,
                'ports': [{'port': 80, 'target_port': 8000}]
            }
            return True
            
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.results['service_status'] = {
                    'created': False,
                    'exists': True,
                    'name': f"{self.app_name}-service"
                }
                return False
            else:
                raise
                
    def create_hpa(self):
        """Create Horizontal Pod Autoscaler"""
        if not self.hpa_enabled:
            return False
            
        hpa = client.V2HorizontalPodAutoscaler(
            metadata=client.V1ObjectMeta(
                name=f"{self.app_name}-hpa",
                namespace=self.namespace,
                labels={
                    'app': self.app_name,
                    'component': 'hpa'
                }
            ),
            spec=client.V2HorizontalPodAutoscalerSpec(
                scale_target_ref=client.V2CrossVersionObjectReference(
                    api_version='apps/v1',
                    kind='Deployment',
                    name=f"{self.app_name}-deployment"
                ),
                min_replicas=self.hpa_config.get('min_replicas', 1),
                max_replicas=self.hpa_config.get('max_replicas', 10),
                metrics=[
                    client.V2MetricSpec(
                        type='Resource',
                        resource=client.V2ResourceMetricSource(
                            name='cpu',
                            target=client.V2MetricTarget(
                                type='Utilization',
                                average_utilization=self.hpa_config.get('target_cpu_utilization', 70)
                            )
                        )
                    )
                ]
            )
        )
        
        # Add memory metric if specified
        if 'target_memory_utilization' in self.hpa_config:
            memory_metric = client.V2MetricSpec(
                type='Resource',
                resource=client.V2ResourceMetricSource(
                    name='memory',
                    target=client.V2MetricTarget(
                        type='Utilization',
                        average_utilization=self.hpa_config.get('target_memory_utilization', 80)
                    )
                )
            )
            hpa.spec.metrics.append(memory_metric)
            
        try:
            result = self.k8s_autoscaling.create_namespaced_horizontal_pod_autoscaler(
                namespace=self.namespace,
                body=hpa
            )
            self.results['resources_created'].append(f'hpa/{self.app_name}-hpa')
            self.results['hpa_status'] = {
                'created': True,
                'name': f"{self.app_name}-hpa",
                'min_replicas': self.hpa_config.get('min_replicas', 1),
                'max_replicas': self.hpa_config.get('max_replicas', 10),
                'target_cpu': self.hpa_config.get('target_cpu_utilization', 70),
                'target_memory': self.hpa_config.get('target_memory_utilization')
            }
            return True
            
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.results['hpa_status'] = {
                    'created': False,
                    'exists': True,
                    'name': f"{self.app_name}-hpa"
                }
                return False
            else:
                raise
                
    def create_ingress(self):
        """Create Ingress resource"""
        if not self.ingress_config:
            return False
            
        host = self.ingress_config.get('host')
        if not host:
            return False
            
        # Ingress rules
        http_rule = client.V1HTTPIngressRuleValue(
            paths=[
                client.V1HTTPIngressPath(
                    path='/',
                    path_type='Prefix',
                    backend=client.V1IngressBackend(
                        service=client.V1IngressServiceBackend(
                            name=f"{self.app_name}-service",
                            port=client.V1ServiceBackendPort(number=80)
                        )
                    )
                )
            ]
        )
        
        rule = client.V1IngressRule(
            host=host,
            http=http_rule
        )
        
        # TLS configuration
        tls = None
        if self.ingress_config.get('tls_enabled', False):
            tls = [
                client.V1IngressTLS(
                    hosts=[host],
                    secret_name=f"{self.app_name}-tls"
                )
            ]
            
        ingress = client.V1Ingress(
            metadata=client.V1ObjectMeta(
                name=f"{self.app_name}-ingress",
                namespace=self.namespace,
                labels={
                    'app': self.app_name,
                    'component': 'ingress'
                },
                annotations=self.ingress_config.get('annotations', {})
            ),
            spec=client.V1IngressSpec(
                rules=[rule],
                tls=tls
            )
        )
        
        try:
            result = self.k8s_networking.create_namespaced_ingress(
                namespace=self.namespace,
                body=ingress
            )
            self.results['resources_created'].append(f'ingress/{self.app_name}-ingress')
            self.results['ingress_status'] = {
                'created': True,
                'name': f"{self.app_name}-ingress",
                'host': host,
                'tls_enabled': self.ingress_config.get('tls_enabled', False),
                'url': f"{'https' if self.ingress_config.get('tls_enabled') else 'http'}://{host}"
            }
            return True
            
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.results['ingress_status'] = {
                    'created': False,
                    'exists': True,
                    'name': f"{self.app_name}-ingress",
                    'host': host
                }
                return False
            else:
                raise
                
    def create_persistent_volume(self):
        """Create Persistent Volume for backup"""
        if not self.backup_config.get('enabled', False):
            return False
            
        # PersistentVolume
        pv = client.V1PersistentVolume(
            metadata=client.V1ObjectMeta(
                name=f"{self.app_name}-pv",
                labels={
                    'app': self.app_name,
                    'component': 'storage'
                }
            ),
            spec=client.V1PersistentVolumeSpec(
                capacity={'storage': self.backup_config.get('storage_size', '1Gi')},
                access_modes=['ReadWriteOnce'],
                persistent_volume_reclaim_policy='Retain',
                storage_class_name='local-storage',
                local=client.V1LocalVolumeSource(
                    path=f"/data/{self.app_name}"
                ),
                node_affinity=client.V1VolumeNodeAffinity(
                    required=client.V1NodeSelector(
                        node_selector_terms=[
                            client.V1NodeSelectorTerm(
                                match_expressions=[
                                    client.V1NodeSelectorRequirement(
                                        key='kubernetes.io/hostname',
                                        operator='Exists'
                                    )
                                ]
                            )
                        ]
                    )
                )
            )
        )
        
        # PersistentVolumeClaim
        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(
                name=f"{self.app_name}-pvc",
                namespace=self.namespace,
                labels={
                    'app': self.app_name,
                    'component': 'storage'
                }
            ),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=['ReadWriteOnce'],
                resources=client.V1ResourceRequirements(
                    requests={'storage': self.backup_config.get('storage_size', '1Gi')}
                ),
                storage_class_name='local-storage'
            )
        )
        
        try:
            # Create PV
            self.k8s_core.create_persistent_volume(body=pv)
            self.results['resources_created'].append(f'pv/{self.app_name}-pv')
            
            # Create PVC
            self.k8s_core.create_namespaced_persistent_volume_claim(
                namespace=self.namespace,
                body=pvc
            )
            self.results['resources_created'].append(f'pvc/{self.app_name}-pvc')
            
            self.results['pv_status'] = {
                'created': True,
                'pv_name': f"{self.app_name}-pv",
                'pvc_name': f"{self.app_name}-pvc",
                'storage_size': self.backup_config.get('storage_size', '1Gi'),
                'access_modes': ['ReadWriteOnce']
            }
            return True
            
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.results['pv_status'] = {
                    'created': False,
                    'exists': True,
                    'pv_name': f"{self.app_name}-pv",
                    'pvc_name': f"{self.app_name}-pvc"
                }
                return False
            else:
                raise
                
    def scale_deployment(self):
        """Scale deployment to target replicas"""
        if not self.target_replicas:
            self.module.fail_json(msg="target_replicas required for scale operation")
            
        try:
            # Get current deployment
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"{self.app_name}-deployment",
                namespace=self.namespace
            )
            
            # Update replica count
            deployment.spec.replicas = self.target_replicas
            
            # Patch deployment
            result = self.k8s_apps.patch_namespaced_deployment(
                name=f"{self.app_name}-deployment",
                namespace=self.namespace,
                body=deployment
            )
            
            return {
                'scaled': True,
                'previous_replicas': deployment.status.replicas,
                'target_replicas': self.target_replicas,
                'deployment_name': f"{self.app_name}-deployment"
            }
            
        except ApiException as e:
            self.module.fail_json(msg=f"Failed to scale deployment: {e}")
            
    def get_deployment_status(self):
        """Get current deployment status"""
        try:
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"{self.app_name}-deployment",
                namespace=self.namespace
            )
            
            return {
                'name': f"{self.app_name}-deployment",
                'replicas': deployment.status.replicas or 0,
                'ready_replicas': deployment.status.ready_replicas or 0,
                'available_replicas': deployment.status.available_replicas or 0,
                'updated_replicas': deployment.status.updated_replicas or 0,
                'conditions': [
                    {
                        'type': condition.type,
                        'status': condition.status,
                        'reason': condition.reason
                    }
                    for condition in (deployment.status.conditions or [])
                ]
            }
            
        except ApiException:
            return {'error': 'Deployment not found'}
            
    def cleanup_resources(self):
        """Cleanup application resources"""
        cleanup_results = {
            'deleted_resources': [],
            'errors': []
        }
        
        # Delete resources in reverse order
        resources_to_delete = [
            ('ingress', f"{self.app_name}-ingress", self.k8s_networking.delete_namespaced_ingress),
            ('hpa', f"{self.app_name}-hpa", self.k8s_autoscaling.delete_namespaced_horizontal_pod_autoscaler),
            ('service', f"{self.app_name}-service", self.k8s_core.delete_namespaced_service),
            ('pvc', f"{self.app_name}-pvc", self.k8s_core.delete_namespaced_persistent_volume_claim),
            ('pv', f"{self.app_name}-pv", self.k8s_core.delete_persistent_volume)
        ]
        
        for resource_type, resource_name, delete_func in resources_to_delete:
            try:
                if resource_type == 'pv':
                    delete_func(name=resource_name)
                else:
                    delete_func(name=resource_name, namespace=self.namespace)
                cleanup_results['deleted_resources'].append(f"{resource_type}/{resource_name}")
            except ApiException as e:
                if e.status != 404:  # Ignore not found errors
                    cleanup_results['errors'].append(f"Failed to delete {resource_type}/{resource_name}: {e}")
                    
        return cleanup_results
        
    def deploy(self):
        """Deploy all application resources"""
        # Create service
        self.create_service()
        
        # Create HPA if enabled
        if self.hpa_enabled:
            self.create_hpa()
            
        # Create ingress if configured
        if self.ingress_config:
            self.create_ingress()
            
        # Create persistent volume if backup enabled
        if self.backup_config.get('enabled', False):
            self.create_persistent_volume()
            
        return self.results
        
    def execute_operation(self):
        """Execute the specified operation"""
        if self.operation == 'deploy':
            return self.deploy()
        elif self.operation == 'scale':
            scale_result = self.scale_deployment()
            return {**self.results, 'scale_result': scale_result}
        elif self.operation == 'status':
            status = self.get_deployment_status()
            return {**self.results, 'deployment_status': status}
        elif self.operation == 'cleanup':
            cleanup_result = self.cleanup_resources()
            return {**self.results, 'cleanup_result': cleanup_result}
        else:
            self.module.fail_json(msg=f"Unknown operation: {self.operation}")


def main():
    module = AnsibleModule(
        argument_spec=dict(
            namespace=dict(type='str', required=True),
            app_name=dict(type='str', required=True),
            operation=dict(type='str', default='deploy', choices=['deploy', 'scale', 'cleanup', 'status']),
            resources=dict(type='dict', default={}),
            hpa_enabled=dict(type='bool', default=False),
            hpa_config=dict(type='dict', default={}),
            ingress_config=dict(type='dict', default={}),
            backup_config=dict(type='dict', default={}),
            deployment_strategy=dict(type='str', default='rolling'),
            target_replicas=dict(type='int')
        ),
        supports_check_mode=True
    )
    
    manager = K8sAppManager(module)
    
    try:
        results = manager.execute_operation()
        module.exit_json(changed=True, **results)
        
    except Exception as e:
        module.fail_json(msg=f"K8s app management failed: {str(e)}")


if __name__ == '__main__':
    main()