# Investigation procedures by problem category, version 2 (switches ROUTING + PROC_V2, change C-020)

<!--
Read by ROUTING when PROC_V2 is on. Each "## <id>" section is one procedure, returned whole by
load_procedure(category="<id>"), with a scope header added in front by the code. The agent never sees this comment.

Why this format (docs/research/procedure-knowledge-format-2026-11-09.md):
- step 0 is a rule-out check and every step ends in IF branches, so a wrong category is left early (SREGym: agents
  anchor on the first plausible anomaly; D-Bot: backtracking when a step finds nothing);
- every step names one ready command (StepFly: model-written queries drift and break). Commands are single kubectl
  commands with no pipes, because exec_kubectl_guarded refuses pipes, redirection and compound commands;
- "Does not point here when" sharpens the menu line, which is how the category is picked (Agent Skills: the
  description decides);
- "Known noise" lists states that Kubernetes documents as normal, so they are not read as the fault;
- each section stays about one screen (RCACopilot, Du et al.: extra context lowers accuracy).

Rules for this file (leakage checklist, experiments/agent-change-log.md):
- Organised by the areas the Kubernetes documentation itself uses for debugging. Not by benchmark scenario.
- No fault name, no object, service or namespace name from any benchmark problem.
- Steps say how to look and how to decide, never what the answer is.
- Facts come from the kubernetes.io pages listed under each section (plus cert-manager.io for the optional
  certificate check).
-->

## startup

Points here when: pods are Pending or stay in ContainerCreating, pull errors (ImagePullBackOff, ErrImagePull), or a workload has fewer pods than it asks for.

Does not point here when: the pods were Pending only during start-up and are now Running and Ready; containers start and then restart (that is crash).

Known noise: ContainerCreating and image Pulling for the first minutes after a deploy; Pending until a WaitForFirstConsumer claim binds.

Steps:

0. Rule-out: exec_kubectl_guarded `kubectl get deployments,statefulsets,daemonsets -n <namespace>`.
   - IF every workload has READY equal to the desired count AND get_pod_status shows no Pending or Waiting pod → EXIT.
   - ELSE → 1.
1. describe the pod that is not running and read its Events (the newest ones).
   - IF FailedScheduling → 2.  IF the image cannot be pulled → 3.  IF there is no such pod at all → 4.
2. Read the scheduler's reason. IF it names cpu or memory → load capacity. IF it names a claim or volume → load storage.
   - IF it names a node selector, affinity or taint → compare the pod's nodeSelector/affinity/tolerations (get_resource on its Deployment, by name) with `kubectl get nodes --show-labels`; the mismatch is the finding.
3. Compare the image in the pod with the image in its Deployment (get_resource, by name) and with the previous revision (`kubectl rollout history deployment/<name> -n <namespace>`). A changed or misspelled image or tag is the finding.
4. describe the ReplicaSet or StatefulSet and read FailedCreate: it names what refused the pod (quota → capacity; policy or ServiceAccount → access; invalid field → that field).

Before you conclude: quote the event or field (with its step number) that blocks the pod now, and show it is newer than the pod or still repeating.

EXIT (wrong category): write "startup ruled out by step N: <observation>", then load the next most likely category.

Fix families: correct the field the event points at on the owning object, not on the pod; give the controller what it needs to create the pod; do not delete the controller.

Sources: kubernetes.io "Debug Pods", "Debug Running Pods", "Assigning Pods to Nodes", "Images".

## crash

Points here when: CrashLoopBackOff, a restart count that keeps rising, containers that exit with an error or are OOMKilled.

Does not point here when: restarts happened only during start-up and the count no longer rises; pods are Running with 0 restarts but not Ready (that is probes).

Known noise: a few restarts while a dependency was still starting; Completed is the normal end state of a Job's pod.

Steps:

0. Rule-out: get_pod_status twice, one or two actions apart.
   - IF no pod is in CrashLoopBackOff, Error or OOMKilled AND no restart count rose between the two looks → EXIT.
   - ELSE → 1.
1. describe the restarting pod: read Last State (reason, exit code, finished time) and the restart count.
   - IF reason is OOMKilled → load capacity.  IF the last finish time is old and the pod is now Ready → EXIT.  ELSE → 2.
2. get_logs with previous=true for that container; find the last error line before it exited.
   - IF the error names another service (connection refused, timeout, authentication failed, certificate) → the crash is a symptom: load network or config for that service.
   - IF it names a setting, file, key or environment variable → 3.  IF the log is empty → read the container's command and args (get_resource on its Deployment).
3. Check that input: the environment variable in the Deployment, the ConfigMap or Secret key it reads (`kubectl get configmap <name> -n <namespace> -o yaml`), the mounted path.

Before you conclude: quote the log line and the input it names, with step numbers, and show the input is wrong or missing.

EXIT (wrong category): write "crash ruled out by step N: <observation>", then load the next most likely category.

Fix families: correct the input the process reads; fix the dependency it waits for; a restart alone is not a fix unless the cause was transient and is gone.

Sources: kubernetes.io "Debug Pods", "Determine the Reason for Pod Failure", "Debug Running Pods".

## network

Points here when: a client gets connection refused, timeouts, 502/503/404 from a proxy or ingress, or name resolution errors while the backend pods look healthy.

Does not point here when: the backend pods themselves crash or are not Ready (crash or probes); the error is a TLS or certificate error between two services that connect fine (config).

Known noise: a Service without a selector has no endpoints by design; a headless Service (ClusterIP None) has no cluster IP by design.

Steps:

0. Rule-out: exec_kubectl_guarded `kubectl get endpoints -n <namespace>`, then get_logs of the client that fails (the entry service, or the one named in the error).
   - IF every Service that has a selector lists endpoints AND the client logs show no connection, timeout, 5xx or resolution error → EXIT.
   - ELSE → 1.
1. IF a Service has no endpoints → compare its selector with the pod labels key by key (`kubectl get service <name> -n <namespace> -o yaml` and `kubectl get pods -n <namespace> --show-labels`). A mismatch is the finding.
   - ELSE → 2.
2. Check the Service ports: port, targetPort against the containerPort (or the named port on the pods), protocol.
   - IF they disagree → that is the finding.  ELSE → 3.
3. IF the error is name resolution → read the client pod's dnsPolicy/dnsConfig and check the DNS pods: `kubectl get pods -n kube-system -l k8s-app=kube-dns`.
   - ELSE → 4.
4. `kubectl get networkpolicy -n <namespace>`. IF a policy selects the target pods → read its ingress/egress rules against the client's labels and port.
   - ELSE → 5.
5. For an Ingress: `kubectl describe ingress -n <namespace>`. Each backend must name an existing Service and a port it exposes; a tls section must name an existing Secret of type kubernetes.io/tls (`kubectl get secret <name> -n <namespace>`). IF the Secret's certificate is suspect → load config.

Before you conclude: name the broken link (client → name, name → Service, Service → endpoints, endpoints → pod port, policy, Ingress → Service or Secret) and quote the observation that shows it, with its step number.

EXIT (wrong category): write "network ruled out by step N: <observation>", then load the next most likely category.

Fix families: make the two sides of the broken link agree (selector and labels, port and targetPort, backend and Service, DNS settings); change the side that differs from the rest of the application.

Sources: kubernetes.io "Debug Services", "Debugging DNS Resolution", "Service", "Ingress", "Network Policies".

## storage

Points here when: pods wait on volumes (FailedMount, FailedAttachVolume, a PersistentVolumeClaim that stays Pending), or an application reports read-only, missing or full data.

Does not point here when: every claim is Bound and the pods that use them are Running and Ready; the only volume events are older than the pods that are now healthy.

Known noise: a claim stays Pending with WaitForFirstConsumer until a pod uses it (StorageClass volumeBindingMode); "waiting for a volume to be created" while the provisioner works; scheduling warnings about a claim during the first minutes of an install.

Steps:

0. Rule-out: exec_kubectl_guarded `kubectl get pvc -n <namespace>`, and get_pod_status.
   - IF every claim is Bound AND no pod is Pending or in ContainerCreating → EXIT.
   - ELSE → 1.
1. describe the claim that is not Bound and read its events.
   - IF it names a StorageClass that does not exist or has no provisioner → `kubectl get storageclass`; that is the finding.
   - IF it waits for a matching volume → 2.
2. Compare the claim's size, accessModes and storageClassName with the volumes: `kubectl get pv`. A claim no volume can satisfy is the finding.
3. IF claims are Bound but a pod shows FailedMount → describe the pod: each volume and volumeMount must name an existing claim, ConfigMap or Secret (and key).
4. IF the application reports read-only, missing or full data → read the pod's volumeMounts (readOnly, mountPath, subPath) against what its logs say it writes.

Before you conclude: name which link in pod → claim → volume → class is missing or does not match, and quote the observation with its step number.

EXIT (wrong category): write "storage ruled out by step N: <observation>", then load the next most likely category.

Fix families: make the reference resolve (create or correct it); never delete a claim or volume that holds data.

Sources: kubernetes.io "Persistent Volumes", "Storage Classes" (Volume Binding Mode), "Volumes", "Debug Pods".

## capacity

Points here when: pods are Pending for cpu or memory, evicted or preempted, OOMKilled, slow under CPU throttling, or a namespace refuses pods with a quota error.

Does not point here when: pods are Pending for a volume (storage), a node selector or taint (startup); the node itself is NotReady (node).

Known noise: `kubectl top` returns "Metrics API not available" when metrics-server is not installed; that is not a fault.

Steps:

0. Rule-out: get_pod_status and get_events.
   - IF no pod is Pending, Evicted or OOMKilled AND no event says Insufficient, Preempted, Evicted or exceeded quota → EXIT.
   - ELSE → 1.
1. describe the waiting, evicted or killed pod; note the exact reason. IF exceeded quota → 3. IF preempted → 4. ELSE → 2.
2. Compare each container's requests and limits (get_resource on its Deployment) with node allocatable: `kubectl describe nodes` (Allocatable and Allocated resources sections).
   - IF a request is larger than any node's free allocatable, or usage hits the limit (OOMKilled) → that setting is the finding.
3. `kubectl get resourcequota,limitrange -n <namespace>` and describe the quota: used against hard.
4. `kubectl get priorityclass` and the priorityClassName of the pods that won and lost.
5. Check what changed: `kubectl rollout history deployment/<name> -n <namespace>` and the replica counts. A recent change to a request, limit, replicas or quota is the suspect.

Before you conclude: show the numbers (request against free capacity, usage against limit, used against quota) and the object that set them, with step numbers.

EXIT (wrong category): write "capacity ruled out by step N: <observation>", then load the next most likely category.

Fix families: correct the setting that is out of line with the rest of the application; restore the previous value when a recent change caused it; scale only if demand, not a setting, is the cause.

Sources: kubernetes.io "Resource Management for Pods and Containers", "Pod Priority and Preemption", "Resource Quotas", "Limit Ranges", "Node-pressure Eviction".

## config

Points here when: the application runs but refuses or fails work: authentication or authorization errors between services, wrong endpoints or behaviour, certificate or TLS errors, missing keys or settings.

Does not point here when: the process crashes before it can serve (start at crash); the client cannot reach the service at all (network).

Known noise: environment variables taken from a ConfigMap do not change in a running pod until it restarts; a ConfigMap mounted as a volume updates after a delay.

Steps:

0. Rule-out: get_logs of the component the symptom points to (and of its client), tail 200.
   - IF neither log shows an authentication, authorization, TLS/certificate/x509, missing key, unknown setting or wrong address error AND the error responses are not coming from it → EXIT.
   - ELSE → 1.
1. Classify the error line. IF TLS, certificate or x509 → 4. IF credentials (auth failed, 401, wrong password or token) → 3. ELSE → 2.
2. Read the component's configuration: get_resource on its Deployment (env, envFrom, volumes), then each ConfigMap or Secret it references (`kubectl get configmap <name> -n <namespace> -o yaml`, `kubectl describe secret <name> -n <namespace>` for key names). Every referenced object and key must exist and hold the value the error expects.
3. Credentials: find the setting on both sides (the client that sends and the server that checks). They must match; compare both, not one.
4. TLS: find which object holds the certificate: the Ingress tls section (`kubectl describe ingress -n <namespace>`), or a Secret of type kubernetes.io/tls mounted by the server (keys tls.crt and tls.key). Read the error words: expired / not yet valid → the certificate dates; unknown authority → the CA bundle on the client; name mismatch → the names in the certificate against the host called.
   - IF cert-manager is installed (`kubectl get certificates -n <namespace>` works) → read READY and the expiry time in `kubectl describe certificate <name> -n <namespace>`.
5. Compare with the previous revision: `kubectl rollout history deployment/<name> -n <namespace>`; a recent template change is the suspect.

Before you conclude: name the setting or certificate, its current value or state, and the value or state the other side expects; quote the error line and the object with their step numbers.

EXIT (wrong category): write "config ruled out by step N: <observation>", then load the next most likely category.

Fix families: restore the setting or certificate to one consistent with the other side; prefer a known previous value over a new one; do not weaken security to make an error go away.

Sources: kubernetes.io "ConfigMaps", "Secrets" (TLS Secrets), "Ingress" (TLS), "Debug Running Pods"; cert-manager.io "Certificate resource".

## probes

Points here when: pods are Running but not Ready, restart with no crash in their logs, or a rollout stalls because new pods never become available.

Does not point here when: the logs show the process failing (crash); every pod is Ready and the Unhealthy events are older than the pods.

Known noise: a few Unhealthy readiness events while a pod starts, before initialDelaySeconds or the startup probe has passed.

Steps:

0. Rule-out: get_pod_status and get_events.
   - IF every pod is READY n/n AND no Unhealthy or rollout ProgressDeadlineExceeded event is newer than the pods → EXIT.
   - ELSE → 1.
1. describe the not-Ready pod: read the liveness, readiness and startup probes (type, path, port, delays, periods, timeouts, thresholds) and the Unhealthy event text.
   - IF the event says connection refused or 404 → 2.  IF it says timeout → 3.
2. Check the probe's port and path against the containerPort and what the process serves (its logs at start-up say which port it listens on).
3. Compare initialDelaySeconds, timeoutSeconds and failureThreshold with how long the process takes to start and to answer (pod start time against the first log lines).
4. For a stalled rollout: describe the Deployment and compare the new and old ReplicaSet templates (`kubectl rollout history deployment/<name> -n <namespace> --revision=<n>`); the difference is the suspect.

Before you conclude: quote the probe setting and the observation that it does not fit (wrong port or path, start time longer than the delay), with step numbers.

EXIT (wrong category): write "probes ruled out by step N: <observation>", then load the next most likely category.

Fix families: make the probe match what the process serves and how fast it starts; or roll back the template change that broke readiness.

Sources: kubernetes.io "Configure Liveness, Readiness and Startup Probes", "Deployments" (failed deployment), "Debug Pods".

## node

Points here when: pods on one node fail together, a node is NotReady or under memory, disk or PID pressure, pods are evicted for node reasons, or the problem follows a node rather than a workload.

Does not point here when: the failing pods are spread over several healthy nodes (look at the workload instead).

Known noise: the control-plane node carries the taint node-role.kubernetes.io/control-plane:NoSchedule, so ordinary pods never run there.

Steps:

0. Rule-out: exec_kubectl_guarded `kubectl get nodes -o wide`, and `kubectl get pods -n <namespace> -o wide` to see where the failing pods run.
   - IF every node is Ready AND the failing pods do not share one node → EXIT.
   - ELSE → 1.
1. describe the suspect node: Conditions (Ready, MemoryPressure, DiskPressure, PIDPressure, NetworkUnavailable), Taints, Unschedulable, recent events.
2. IF the node is cordoned or tainted → compare with the pods' tolerations and nodeSelector.
3. IF healthy copies of the same workload run on other nodes and only this node's copies fail → the node is the finding.

Before you conclude: show that the failure follows the node (same node, a condition or taint) and not the workload, with step numbers.

EXIT (wrong category): write "node ruled out by step N: <observation>", then load the next most likely category.

Fix families: move the workload off the faulty node (cordon and reschedule) or remove the condition's cause; do not delete nodes.

Sources: kubernetes.io "Troubleshooting Clusters", "Taints and Tolerations", "Node-pressure Eviction", "Nodes".

## access

Points here when: requests are forbidden (403, "cannot get/list"), a controller cannot create pods for policy reasons, pods violate a security policy, or a webhook rejects or times out.

Does not point here when: the 401/403 comes from the application's own login between services (config); the forbidden message names your own tool rather than a workload's ServiceAccount.

Known noise: none specific; read who the error names before acting.

Steps:

0. Rule-out: get_events, and get_logs of the failing component.
   - IF no event or log line says forbidden, cannot get/list/create, violates PodSecurity, or webhook denied/timed out → EXIT.
   - ELSE → 1.
1. Read the exact error: which identity (user or system:serviceaccount:<namespace>:<name>), which verb, which resource.
   - IF a ServiceAccount is denied → 2.  IF PodSecurity → 3.  IF a webhook → 4.
2. `kubectl get rolebindings,clusterrolebindings -o wide -A` for that ServiceAccount, then describe the bound Role or ClusterRole: the verb and resource must be granted. You can test with `kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<namespace>:<name> -n <namespace>`.
3. `kubectl get namespace <namespace> --show-labels` (pod-security labels) and the FailedCreate message: it names the policy level and the field that violates it.
4. `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`; describe the one named and check its Service has endpoints.

Before you conclude: name the identity, the permission or policy, and the field that does not satisfy it, with step numbers.

EXIT (wrong category): write "access ruled out by step N: <observation>", then load the next most likely category.

Fix families: change the workload so it satisfies the policy, or restore the permission it had; do not disable security policies or grant cluster-wide rights.

Sources: kubernetes.io "Using RBAC Authorization", "Pod Security Admission", "Dynamic Admission Control", "kubectl auth can-i".
