# Investigation procedures by problem category (switch ROUTING)

<!--
Read by the ROUTING switch. Each "## <id>" section is one procedure, returned whole by the read action
load_procedure(category="<id>"). The agent never sees this comment.

Rules for this file (leakage checklist, experiments/agent-change-log.md):
- Organised by the areas the Kubernetes documentation itself uses for debugging (pods, services, DNS, storage,
  scheduling and resources, configuration, probes, nodes, access). Not by benchmark scenario.
- No fault name, no object, service or namespace name from any benchmark problem.
- Steps say how to look and how to confirm, never what the answer is.
- Sources: kubernetes.io task pages listed under each section.
-->

## startup
Points here when: pods are Pending, ContainerCreating, ImagePullBackOff/ErrImagePull, or a Deployment has fewer pods than it asks for (some pods do not exist at all).
1. get_pod_status, then describe the pod that is not running and read its Events: the scheduler, the kubelet or the image puller says why.
2. Pending: the event names the reason (resources, node selector or affinity, taints, a volume that cannot bind). Follow that reason; if it is resources, load the capacity procedure; if it is a volume, load storage.
3. Waiting on the image: check the image name and tag in the pod spec against the controller's spec; a changed or mistyped image is a configuration problem.
4. Fewer pods than replicas and no pod to describe: describe the ReplicaSet (or StatefulSet/DaemonSet) and read its Events. A FailedCreate event says what refused to create the pod (a quota, an admission policy, a missing ServiceAccount, an invalid field).
Before you conclude: name the event or field that blocks the pod, and say why it blocks it now.
Fix families: correct the field the event points at on the owning object (not on the pod); give the controller what it needs to create the pod; do not delete the controller.
Sources: kubernetes.io "Debug Pods" (Pending, Waiting), "Debug Running Pods".

## crash
Points here when: containers restart (CrashLoopBackOff, rising restart count), exit with an error, are OOMKilled, or run but are not Ready.
1. describe the pod: last state, exit code, reason (OOMKilled, Error, Completed), restart count, Ready condition.
2. get_logs with previous=true for the crashed container; read the last error the process printed before it exited.
3. Link the error to its input: an environment variable, a mounted ConfigMap or Secret, a dependency it connects to, a file path, a memory limit.
4. If the logs blame another service (connection refused, timeout, authentication failed), the crash is a symptom: go to that service and load network or config for it.
5. OOMKilled: compare the container's memory limit with what it uses; load capacity.
Before you conclude: the error in the log must explain the restart, and you must have checked the input it names.
Fix families: correct the input the process reads; fix the dependency it waits for; a restart alone is not a fix unless the cause was transient and is gone.
Sources: kubernetes.io "Debug Pods" (crashing or unhealthy), "Determine the Reason for Pod Failure", "Debug Running Pods".

## network
Points here when: a client cannot reach a service (connection refused, timeouts, 502/503/404 from a proxy or ingress, name resolution errors), while the backend pods look healthy.
Follow the Kubernetes "Debug Services" order; stop at the first check that fails:
1. Does the Service exist (get_resource kind=service)?
2. Is there a NetworkPolicy in the namespace that selects the target pods? Read its rules.
3. Name resolution: does the client resolve the service name? Check the pod's DNS settings (dnsPolicy, dnsConfig) and that the cluster DNS pods in kube-system are running.
4. Is the Service defined correctly: the port is listed, targetPort matches the containerPort (or the named port exists on the pods), the protocol is right.
5. Does the Service have endpoints? If none: the Service selector must match the pod labels exactly; compare them key by key.
6. Do the pods answer on their own port (exec_in_pod or logs of the backend)?
7. For an Ingress: each backend must name an existing Service and a port that Service exposes; a TLS section must name an existing Secret.
Before you conclude: name the exact link in the chain that is broken (client to name, name to Service, Service to endpoints, endpoints to pod port, Ingress to Service), with the observation that shows it.
Fix families: make the two sides of the broken link agree (selector and labels, port and targetPort, backend and Service, DNS settings and cluster DNS); change the side that differs from the rest of the application.
Sources: kubernetes.io "Debug Services", "Debugging DNS Resolution".

## storage
Points here when: pods wait on volumes (FailedMount, FailedAttachVolume, unbound PersistentVolumeClaim), or an application reports read-only, missing or full data.
1. get_resource kind=persistentvolumeclaim: status Bound or Pending; describe a Pending claim and read its events.
2. Check the claim's storageClassName exists and has a provisioner; check requested size and access mode against the volume it should bind to.
3. For a bound claim, check the PersistentVolume it binds to (status, reclaim policy, node affinity).
4. Read the pod's volumes and volumeMounts: the claim, ConfigMap or Secret each mount names must exist.
Before you conclude: name which object in pod to claim to volume to class is missing or does not match.
Fix families: make the reference resolve (create or correct the reference); never delete a claim or volume that holds data.
Sources: kubernetes.io "Persistent Volumes", "Debug Pods".

## capacity
Points here when: pods are Pending for resources, are evicted or preempted, are OOMKilled, are throttled and slow, or a namespace refuses new pods with a quota error.
1. describe the waiting or evicted pod: the event says insufficient cpu or memory, preempted, evicted, or exceeded quota.
2. Compare each container's requests and limits with the node allocatable (get_resource kind=node) and with what it needs.
3. Check ResourceQuota and LimitRange objects in the namespace.
4. Check PriorityClasses: which pods have a higher priority, and whether they preempt the ones that fail.
5. Ask what changed: a request, a limit, a replica count, a priority, a quota. A capacity symptom with no change usually means a workload grew.
Before you conclude: show the numbers (request against free capacity, usage against limit, used against quota) and which object set them.
Fix families: correct the setting that is out of line with the rest of the application; restore the previous value when a recent change caused it; scaling is a fix only if demand, not a setting, is the cause.
Sources: kubernetes.io "Resource Management for Pods and Containers", "Pod Priority and Preemption", "Resource Quotas".

## config
Points here when: the application starts but misbehaves or refuses work: authentication or authorization errors between services, wrong endpoints or feature behaviour, certificate or TLS errors, missing keys.
1. Read the failing component's environment (get_resource on its Deployment) and the ConfigMaps and Secrets it references.
2. Check each reference resolves: the ConfigMap or Secret exists and holds the key named.
3. For credentials: the value one side sends must match what the other side expects; compare both sides' configuration, not just one.
4. For TLS: check the Secret the component uses, the certificate's validity dates and names, and which object points at it.
5. Compare the current configuration with the previous revision when there is one (rollout history, previous ReplicaSet template).
Before you conclude: name the setting, its current value or state, and the value or state the rest of the system expects.
Fix families: restore the setting to the value consistent with the other side; prefer restoring a known previous value over inventing a new one; do not weaken security to make an error go away.
Sources: kubernetes.io "ConfigMaps", "Secrets", "Certificates", "Debug Running Pods".

## probes
Points here when: pods are Running but not Ready, restart without a crash in the logs, or a rollout stalls (new pods never become available).
1. describe the pod: read the liveness, readiness and startup probes (path, port, delays, periods, timeouts, thresholds) and the Unhealthy events.
2. Check the probe's port and path exist in the container (the containerPort, what the process serves).
3. Compare the probe timing with how long the process takes to start and to answer.
4. For a stalled rollout, describe the Deployment: compare the new and old ReplicaSet templates; the difference is the suspect.
Before you conclude: show the probe setting and the observation that it does not fit (the wrong port, the unanswered path, the start time longer than the delay).
Fix families: make the probe match what the process serves and how fast it starts; or roll back the template change that broke readiness.
Sources: kubernetes.io "Configure Liveness, Readiness and Startup Probes", "Debug Pods".

## node
Points here when: pods on one node fail together, a node is NotReady or under memory, disk or PID pressure, pods are evicted with node reasons, or the problem follows a node rather than a workload.
1. get_resource kind=node (or get nodes): status, conditions, taints, allocatable.
2. describe the suspect node: conditions (Ready, MemoryPressure, DiskPressure, PIDPressure, NetworkUnavailable) and recent events.
3. Check where the failing pods run: if they share a node and healthy copies elsewhere work, the node is the suspect.
4. Check taints and cordons against the pods' tolerations and selectors.
Before you conclude: show that the failure follows the node (same node, condition or taint) and not the workload.
Fix families: move the workload off the faulty node (cordon and reschedule) or remove the condition's cause; do not delete nodes.
Sources: kubernetes.io "Troubleshooting Clusters", "Taints and Tolerations".

## access
Points here when: requests are forbidden (403, "cannot get/list"), a controller cannot create pods for policy reasons, pods violate a security policy, or a webhook rejects or times out.
1. Read the exact error: which user or ServiceAccount, which verb, which resource.
2. For RBAC: check the ServiceAccount the pod uses, the Roles or ClusterRoles bound to it, and whether the verb and resource are granted.
3. For admission: read the namespace labels and the FailedCreate or rejection message; it names the policy and the field that violates it.
4. For webhooks: check the webhook configurations and that their backing Service has endpoints.
Before you conclude: name the identity, the permission or policy, and the field that does not satisfy it.
Fix families: change the workload so it satisfies the policy, or restore the permission it had; do not disable security policies or grant cluster-wide rights.
Sources: kubernetes.io "Using RBAC Authorization", "Pod Security Admission", "Dynamic Admission Control".
