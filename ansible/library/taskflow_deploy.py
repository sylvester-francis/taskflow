#!/usr/bin/env python3
"""
TaskFlow Deployment Ansible Module
Handles application deployment with health checks and rollback capabilities
"""

import json
import time
import yaml
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url
from kubernetes import client, config, utils
from kubernetes.client.rest import ApiException


DOCUMENTATION = '''
---
module: taskflow_deploy
short_description: Deploy TaskFlow application with health checks
description:
    - Deploys TaskFlow application to Kubernetes with health checks
    - Supports rollback on failure
    - Validates deployment readiness
version_added: "1.0.0"
options:
    namespace:
        description: Kubernetes namespace
        required: true
        type: str
    image:
        description: Container image to deploy
        required: true
        type: str
    replicas:
        description: Number of replicas
        required: false
        default: 1
        type: int
    resources:
        description: Resource requirements
        required: false
        type: dict
    environment:
        description: Environment name (dev/staging/prod)
        required: true
        type: str
    app_config:
        description: Application configuration
        required: false
        type: dict
    health_check:
        description: Health check configuration
        required: false
        type: dict
    deployment_strategy:
        description: Deployment strategy
        required: false
        default: "RollingUpdate"
        type: str
    wait_for_ready:
        description: Wait for deployment to be ready
        required: false
        default: true
        type: bool
    wait_timeout:
        description: Timeout for waiting (seconds)
        required: false
        default: 300
        type: int
    operation:
        description: Operation to perform (deploy/rollback)
        required: false
        default: "deploy"
        type: str
    rollback_revision:
        description: Revision to rollback to
        required: false
        type: int
'''

EXAMPLES = '''
- name: Deploy TaskFlow application
  taskflow_deploy:
    namespace: taskflow-dev
    image: ghcr.io/taskflow/taskflow:latest
    replicas: 2
    environment: development
    resources:
      requests:
        cpu: "100m"
        memory: "128Mi"
      limits:
        cpu: "200m"
        memory: "256Mi"
    health_check:
      path: "/docs"
      port: 8000
    wait_for_ready: true
    wait_timeout: 300
'''

RETURN = '''
status:
    description: Deployment status
    type: str
    returned: always
previous_revision:
    description: Previous deployment revision
    type: int
    returned: always
ready_replicas:
    description: Number of ready replicas
    type: int
    returned: always
conditions:
    description: Deployment conditions
    type: list
    returned: always
'''


class TaskFlowDeployer:
    def __init__(self, module):
        self.module = module
        self.namespace = module.params['namespace']
        self.image = module.params['image']
        self.replicas = module.params['replicas']
        self.resources = module.params['resources'] or {}
        self.environment = module.params['environment']
        self.app_config = module.params['app_config'] or {}
        self.health_check = module.params['health_check'] or {}
        self.deployment_strategy = module.params['deployment_strategy']
        self.wait_for_ready = module.params['wait_for_ready']
        self.wait_timeout = module.params['wait_timeout']
        self.operation = module.params['operation']
        self.rollback_revision = module.params['rollback_revision']
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        self.k8s_apps = client.AppsV1Api()
        self.k8s_core = client.CoreV1Api()
        
    def create_configmap(self):
        """Create ConfigMap for application configuration"""
        configmap_data = {
            'DATABASE_PATH': self.app_config.get('database_path', '/app/data/taskflow.db'),
            'LOG_LEVEL': self.app_config.get('log_level', 'INFO'),
            'DEBUG': str(self.app_config.get('debug', False)).lower(),
            'ENVIRONMENT': self.environment,
        }
        
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name=f"taskflow-config-{self.environment}",
                namespace=self.namespace,
                labels={
                    'app': 'taskflow',
                    'environment': self.environment,
                    'managed-by': 'ansible'
                }
            ),
            data=configmap_data
        )
        
        try:
            self.k8s_core.create_namespaced_config_map(
                namespace=self.namespace,
                body=configmap
            )
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.k8s_core.patch_namespaced_config_map(
                    name=f"taskflow-config-{self.environment}",
                    namespace=self.namespace,
                    body=configmap
                )
            else:
                raise
                
    def create_deployment(self):
        """Create or update deployment"""
        # Container configuration
        container = client.V1Container(
            name="taskflow",
            image=self.image,
            ports=[client.V1ContainerPort(container_port=8000)],
            env_from=[client.V1EnvFromSource(
                config_map_ref=client.V1ConfigMapEnvSource(
                    name=f"taskflow-config-{self.environment}"
                )
            )],
            resources=client.V1ResourceRequirements(
                requests=self.resources.get('requests', {}),
                limits=self.resources.get('limits', {})
            ),
            liveness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(
                    path=self.health_check.get('path', '/docs'),
                    port=self.health_check.get('port', 8000)
                ),
                initial_delay_seconds=self.health_check.get('initial_delay_seconds', 10),
                period_seconds=self.health_check.get('period_seconds', 10),
                timeout_seconds=self.health_check.get('timeout_seconds', 5),
                failure_threshold=self.health_check.get('failure_threshold', 3)
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(
                    path=self.health_check.get('path', '/docs'),
                    port=self.health_check.get('port', 8000)
                ),
                initial_delay_seconds=5,
                period_seconds=5,
                timeout_seconds=3,
                failure_threshold=3
            ),
            security_context=client.V1SecurityContext(
                run_as_non_root=True,
                run_as_user=1000,
                run_as_group=1000,
                allow_privilege_escalation=False,
                read_only_root_filesystem=False,
                capabilities=client.V1Capabilities(
                    drop=["ALL"],
                    add=["NET_BIND_SERVICE"]
                )
            )
        )
        
        # Deployment specification
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    'app': 'taskflow',
                    'environment': self.environment,
                    'version': self.image.split(':')[-1]
                }
            ),
            spec=client.V1PodSpec(
                containers=[container],
                security_context=client.V1PodSecurityContext(
                    run_as_non_root=True,
                    run_as_user=1000,
                    run_as_group=1000,
                    fs_group=1000
                )
            )
        )
        
        spec = client.V1DeploymentSpec(
            replicas=self.replicas,
            selector=client.V1LabelSelector(
                match_labels={'app': 'taskflow', 'environment': self.environment}
            ),
            template=template,
            strategy=client.V1DeploymentStrategy(
                type=self.deployment_strategy,
                rolling_update=client.V1RollingUpdateDeployment(
                    max_surge=1,
                    max_unavailable=0
                ) if self.deployment_strategy == "RollingUpdate" else None
            )
        )
        
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=f"taskflow-{self.environment}",
                namespace=self.namespace,
                labels={
                    'app': 'taskflow',
                    'environment': self.environment,
                    'managed-by': 'ansible'
                }
            ),
            spec=spec
        )
        
        try:
            # Check if deployment exists
            existing = self.k8s_apps.read_namespaced_deployment(
                name=f"taskflow-{self.environment}",
                namespace=self.namespace
            )
            # Update existing deployment
            deployment.metadata.resource_version = existing.metadata.resource_version
            result = self.k8s_apps.patch_namespaced_deployment(
                name=f"taskflow-{self.environment}",
                namespace=self.namespace,
                body=deployment
            )
            return result, False  # Not created, updated
            
        except ApiException as e:
            if e.status == 404:  # Not found, create new
                result = self.k8s_apps.create_namespaced_deployment(
                    namespace=self.namespace,
                    body=deployment
                )
                return result, True  # Created
            else:
                raise
                
    def wait_for_deployment_ready(self, deployment_name):
        """Wait for deployment to be ready"""
        start_time = time.time()
        timeout = self.wait_timeout
        
        while time.time() - start_time < timeout:
            try:
                deployment = self.k8s_apps.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=self.namespace
                )
                
                if (deployment.status.ready_replicas == self.replicas and
                    deployment.status.updated_replicas == self.replicas and
                    deployment.status.available_replicas == self.replicas):
                    return True, deployment
                    
            except ApiException:
                pass
                
            time.sleep(5)
            
        return False, None
        
    def rollback_deployment(self):
        """Rollback deployment to previous revision"""
        if not self.rollback_revision:
            self.module.fail_json(msg="rollback_revision required for rollback operation")
            
        # Get deployment
        try:
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"taskflow-{self.environment}",
                namespace=self.namespace
            )
        except ApiException as e:
            self.module.fail_json(msg=f"Failed to get deployment: {e}")
            
        # Add rollback annotation
        if not deployment.metadata.annotations:
            deployment.metadata.annotations = {}
            
        deployment.metadata.annotations['deployment.kubernetes.io/revision'] = str(self.rollback_revision)
        
        try:
            result = self.k8s_apps.patch_namespaced_deployment(
                name=f"taskflow-{self.environment}",
                namespace=self.namespace,
                body=deployment
            )
            return result
        except ApiException as e:
            self.module.fail_json(msg=f"Failed to rollback deployment: {e}")
            
    def get_deployment_status(self):
        """Get current deployment status"""
        try:
            deployment = self.k8s_apps.read_namespaced_deployment(
                name=f"taskflow-{self.environment}",
                namespace=self.namespace
            )
            
            return {
                'ready_replicas': deployment.status.ready_replicas or 0,
                'updated_replicas': deployment.status.updated_replicas or 0,
                'available_replicas': deployment.status.available_replicas or 0,
                'replicas': deployment.status.replicas or 0,
                'conditions': [
                    {
                        'type': condition.type,
                        'status': condition.status,
                        'reason': condition.reason,
                        'message': condition.message
                    }
                    for condition in (deployment.status.conditions or [])
                ],
                'revision': deployment.metadata.annotations.get('deployment.kubernetes.io/revision', '1')
            }
        except ApiException:
            return {}
            
    def deploy(self):
        """Main deployment logic"""
        changed = False
        
        # Create ConfigMap
        self.create_configmap()
        
        # Create/update deployment
        deployment, created = self.create_deployment()
        changed = True
        
        # Wait for deployment to be ready
        if self.wait_for_ready:
            ready, final_deployment = self.wait_for_deployment_ready(f"taskflow-{self.environment}")
            if not ready:
                self.module.fail_json(
                    msg=f"Deployment not ready within {self.wait_timeout} seconds",
                    **self.get_deployment_status()
                )
                
        status = self.get_deployment_status()
        
        return {
            'changed': changed,
            'status': 'success',
            'created': created,
            'previous_revision': int(status.get('revision', 1)) - 1,
            **status
        }
        
    def rollback(self):
        """Rollback deployment"""
        self.rollback_deployment()
        
        # Wait for rollback to complete
        if self.wait_for_ready:
            ready, _ = self.wait_for_deployment_ready(f"taskflow-{self.environment}")
            if not ready:
                self.module.fail_json(
                    msg=f"Rollback not completed within {self.wait_timeout} seconds"
                )
                
        return {
            'changed': True,
            'status': 'rollback_success',
            'rollback_revision': self.rollback_revision,
            **self.get_deployment_status()
        }


def main():
    module = AnsibleModule(
        argument_spec=dict(
            namespace=dict(type='str', required=True),
            image=dict(type='str', required=True),
            replicas=dict(type='int', default=1),
            resources=dict(type='dict', default={}),
            environment=dict(type='str', required=True),
            app_config=dict(type='dict', default={}),
            health_check=dict(type='dict', default={}),
            deployment_strategy=dict(type='str', default='RollingUpdate'),
            wait_for_ready=dict(type='bool', default=True),
            wait_timeout=dict(type='int', default=300),
            operation=dict(type='str', default='deploy', choices=['deploy', 'rollback']),
            rollback_revision=dict(type='int')
        ),
        supports_check_mode=True
    )
    
    deployer = TaskFlowDeployer(module)
    
    try:
        if module.params['operation'] == 'deploy':
            result = deployer.deploy()
        elif module.params['operation'] == 'rollback':
            result = deployer.rollback()
        else:
            module.fail_json(msg=f"Unknown operation: {module.params['operation']}")
            
        module.exit_json(**result)
        
    except Exception as e:
        module.fail_json(msg=f"Deployment failed: {str(e)}")


if __name__ == '__main__':
    main()