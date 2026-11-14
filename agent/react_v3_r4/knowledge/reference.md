# Reference entries (REF, C-023)

<!--
Content source = docs/research/k8s-failure-taxonomy-2026-11-09.md (102 failure modes; facts as cited there from
kubernetes.io, kubelet reason constants, cert-manager.io, coredns.io, etcd.io, vendor guides and k8s.af). Entry shape =
docs/research/reference-and-examples-design-2026-11-09.md section 6 and docs/plan/18-ref-excap-flow-proposal.md
section 2. Categories and their "Points here when" lines = agent/react_v2/knowledge/procedures_v2.md.
Written 9-10 Nov 2026, before any REF run. Placeholders only (<namespace>, <pod>, <deployment>, <service>, <secret>,
<ingress>, <node>, <claim>, <configmap>, ...). No benchmark material was opened while writing: no benchmark repo,
paper problem table or fault list, nothing under external/, experiments/ or results/, no run transcripts.
Illustrations are synthetic output shapes written from the docs, never copied from any run.
Commands are single read-only kubectl commands; write actions appear only as prose under "Fix family". Many commands
are marked [unverified] standard syntax in the taxonomy: smoke-test them once on the lab cluster before the frozen run.

Merged (taxonomy id -> entry): PS-01+PS-02+PS-03 -> startup/image-pull; SC-02+SC-03+SC-08 -> startup/node-selection;
SC-05+SC-06 -> startup/spread-or-hostport; DS-01+RO-04 (+ DS-02 caution) -> startup/statefulset-stalled;
CR-01+CR-03 -> crash/exit-error; CR-04+DP-01 -> crash/dependency-failure; DS-03+DS-04 -> crash/job-failed;
NS-01+RO-07 -> network/selector-mismatch; NS-03+DN-06+DP-02 -> network/network-policy;
DN-01+DN-02+DN-03+DN-07 -> network/cluster-dns; DN-04+DN-05 -> network/pod-dns-config;
IN-01+NS-07 -> network/ingress-class-address; IN-02+IN-03 -> network/ingress-backend-path;
IN-04+IN-05 (secret and expiry) -> network/ingress-cert; ST-01+SC-04 -> storage/pvc-pending;
SC-01+AS-05 -> capacity/insufficient-resources; RS-05+RS-06 -> capacity/quota-limitrange;
AS-01+AS-02+AS-03+AS-04+CP-05 -> capacity/hpa; CF-02+CF-04+RO-03 -> config/change-not-applied;
RO-02+RO-05 -> config/bad-revision-ready; IN-04 (server side)+DP-03 -> config/service-tls-cert;
IN-05 (controller side)+IN-06+IN-07 -> config/cert-renewal; PR-03+PR-05 -> probes/probe-timing;
PR-04+DP-04 -> probes/cascading-restarts; RS-02+RS-03+RS-04+RS-07 -> node/resource-pressure;
PS-06+ND-03 -> node/pod-network-cni; NS-06+DN-08 -> node/conntrack-dns-stalls; CP-01+CP-02+CP-03+CP-04 ->
node/control-plane-stall. All other modes have their own entry.
Skipped: NS-08 (hairpin; needs node access, escalate only); RO-06 (API removed after an upgrade; manifest change,
escalate); CP-06 (operator / custom controller bugs; cluster-wide, no single-namespace check); DS-02 (stateful
replication / split-brain; escalate only; its cautions are kept under Never in startup/statefulset-stalled).
-->

## startup/image-pull

Signals: waiting reason `ErrImagePull` then `ImagePullBackOff` (also `InvalidImageName`, `ImageInspectError`, `ErrImageNeverPull`); kubelet events `Pulling`, `Failed`, `BackOff`. The message tells the cause: not found / manifest error (wrong name, tag or registry) or "pull access denied, repository does not exist or may require authorization" (credentials).
Not this when: `FailedCreatePodSandBox` about the pause image (node/pod-network-cni); one ErrImagePull that succeeds on retry (noise); the container starts, then exits (crash/exit-error).
Check:
1. describe(<namespace>, pod, <pod>)  IF not found or manifest error → 2; IF authorization or access denied → 3; IF ErrImageNeverPull → 4.
2. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  IF the newest ReplicaSet's image differs from the older one → the changed image or tag is the finding.
3. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.imagePullSecrets}'`, then `kubectl get secret <secret> -n <namespace> -o jsonpath='{.type}'`  IF absent from the pod's namespace, or type not kubernetes.io/dockercfg or kubernetes.io/dockerconfigjson → that reference is the finding.
4. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].imagePullPolicy}'`  IF Never and the image is not on the node → the policy is the finding.
Evidence to quote: the event message with the exact image reference, and the image on the new vs previous ReplicaSet (or the pull secret problem).
Fix family: roll back the owning Deployment or patch its image to the last good tag; patch imagePullSecrets on the template or ServiceAccount; patch imagePullPolicy (it does not follow later tag changes).
Never: switch to the latest tag; copy registry credentials into other namespaces; print secret data.
Illustration:
  Observation: <pod> 0/1 ImagePullBackOff ... Failed to pull image "<image>:<tag>": not found
  Reading: "not found" for a tag unlike the older ReplicaSet's means a changed tag; credentials are ruled out.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/ https://www.kubernetes.io/docs/concepts/containers/images/ https://pkg.go.dev/k8s.io/kubernetes/pkg/kubelet/images https://www.repost.aws/knowledge-center/eks-failed-create-pod-sandbox

## startup/missing-config-ref

Signals: container waiting reason `CreateContainerConfigError` ("... is waiting to start: CreateContainerConfigError"); causes: a referenced ConfigMap or Secret is missing, its name or key is mistyped, or it is in another namespace (a pod and its ConfigMap must be in the same namespace).
Not this when: the same object is referenced as a volume, which gives `FailedMount` and ContainerCreating (storage/configmap-secret-volume); the error names a user, permission or read-only file system (crash/security-context).
Check:
1. describe(<namespace>, pod, <pod>)  IF the event names a ConfigMap, Secret or key → 2.
2. exec_kubectl_guarded `kubectl get configmap,secret -n <namespace>`  IF the named object is not listed → the missing object is the finding; IF it is listed → 3.
3. exec_kubectl_guarded `kubectl get configmap <configmap> -n <namespace> -o yaml` (for a Secret: `kubectl describe secret <secret> -n <namespace>`, which shows key names only)  IF the key the pod references is absent → the missing key is the finding.
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  IF the newest revision is younger than the error and added the reference → that revision is the suspect.
Evidence to quote: the event text naming the object or key, and the get output showing it absent.
Fix family: restore the ConfigMap or Secret (or the key) from its last known version, or roll back the Deployment revision that introduced the reference.
Never: create an empty placeholder object just to make the pod start (hides the fault; the app may run with bad config); print Secret values.
Illustration:
  Observation: <pod>   0/1   CreateContainerConfigError ... <message naming configmap <configmap>>
  Reading: the pod waits on a reference, not on its own code; it rules out crash.
  Next: `kubectl get configmap,secret -n <namespace>`
Sources: https://www.groundcover.com/kubernetes-troubleshooting/createcontainerconfigerror-createcontainererror https://kubernetes.io/docs/concepts/configuration/configmap https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/

## startup/init-container

Signals: pod status `Init:Error`, `Init:CrashLoopBackOff`, or stuck at `Init:N/M`; describe shows the init container with `Last State: Terminated Reason: Error`.
Not this when: the init container keeps "waiting for" a Service without errors: the fault is upstream (network/selector-mismatch, network/cluster-dns, crash/dependency-failure); the main container restarts after init completed (crash/exit-error).
Check:
1. get_pod_status(<namespace>)  IF a pod shows Init:... → 2.
2. describe(<namespace>, pod, <pod>)  IF an init container has Last State Terminated Error → 3; IF it is Running with no error → 4.
3. get_logs(<namespace>, <pod>, <init-container>, previous=true)  IF the log shows the failing step → that step and the input it names are the finding.
4. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> -c <init-container> --since=5m`  IF it repeats waiting for a dependency → `kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service>`; no ready endpoints means the dependency is the fault (load its entry).
Evidence to quote: the init container's state line and the log line naming the failing step or the awaited dependency.
Fix family: fix the dependency the init container waits for (its own entry); roll back the init-container change on the owning workload.
Never: remove the init container (it may skip a migration or permission step).
Illustration:
  Observation: <pod>   0/2   Init:0/1   ... log: "waiting for <service> ..." repeated
  Reading: the init step waits, it does not fail; the cause is the awaited Service, not this pod.
  Next: `kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service>`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/_print

## startup/create-container-error

Signals: reasons `CreateContainerError`, `RunContainerError`; listed causes: missing entrypoint, duplicate container names, volume or runtime problems; exec errors look like `exec: "<command>": executable file not found in $PATH`; exit code 128 points at an invalid entrypoint or command. The process never started, so there are usually no application logs.
Not this when: the app starts, logs, then exits (crash/exit-error); reason CreateContainerConfigError (startup/missing-config-ref); the error names a user, permission or read-only file system (crash/security-context).
Check:
1. describe(<namespace>, pod, <pod>)  IF the event names a command, path or entrypoint → 2.
2. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].command}'` and the same for `args`  IF the command names a path the runtime reports missing → 3.
3. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`, then `kubectl get replicaset <replicaset> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].command}'` on the older ReplicaSet  IF command or args differ from the last working revision → that change is the finding.
Evidence to quote: the runtime's event message naming the command or path, and the changed command/args field.
Fix family: roll back the owning Deployment, or patch command/args on its template back to the last working value.
Never: patch the entrypoint to a shell "to keep it alive"; edit application code.
Illustration:
  Observation: <pod>   0/1   RunContainerError ... exec: "<command>": executable file not found in $PATH
  Reading: the runtime cannot start the command, so the template, not the process, is wrong.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://pkg.go.dev/k8s.io/kubernetes@v1.31.1/pkg/kubelet/container https://www.groundcover.com/kubernetes-troubleshooting/createcontainerconfigerror-createcontainererror https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/ https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/crashloopbackoff-events

## startup/stuck-terminating

Signals: a pod stays Terminating long after its grace period (default 30s): "a deletion has been issued for the Pod, but the control plane is unable to delete the Pod object"; likely cause: a finalizer plus a webhook that blocks its removal (webhooks on UPDATE of pods); Job pods can be held by finalizer `batch.kubernetes.io/job-tracking`; pods on a lost node linger.
Not this when: normal graceful termination still inside the grace period; the node is NotReady or Unknown (node/unreachable).
Check:
1. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.metadata.deletionTimestamp} {.metadata.finalizers}'`  IF deletionTimestamp is older than the grace period and a finalizer is listed → 2.
2. exec_kubectl_guarded `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`  IF one targets pods → access/webhook-unavailable.
3. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o wide`, then `kubectl get node <node>`  IF the node is NotReady or Unknown → node/unreachable.
Evidence to quote: the deletionTimestamp with the finalizer still present, and the webhook or node state that holds it.
Fix family: fix the webhook backend or the node; for a Deployment pod, let the replacement pod serve.
Never: force delete with grace period 0 (the resource "may continue to run on the cluster indefinitely"); force-delete StatefulSet pods without fencing; strip finalizers by hand.
Illustration:
  Observation: <pod>   1/1   Terminating   12m ... finalizers: [<finalizer>]
  Reading: twelve minutes is far past a 30s grace period, so something holds the deletion; it is not a normal shutdown.
  Next: `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/ https://kubernetes.io/docs/tasks/debug/debug-application/_print https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle https://kubernetes.io/docs/concepts/Workloads/controllers/job/

## startup/node-selection

Signals: pod Pending with `FailedScheduling` naming a node selector or affinity (`MatchNodeSelector`; "a label selector matches no nodes"), an untolerated taint (`PodToleratesNodeTaints`; `NoSchedule` blocks new pods, `NoExecute` evicts running ones), or nodes shown `SchedulingDisabled` (cordoned, `spec.unschedulable`). The scheduler checks taints, not node conditions.
Not this when: the reason names cpu or memory (capacity/insufficient-resources) or a claim (storage/pvc-pending); the taint is a condition taint such as memory-pressure, disk-pressure or not-ready (node/resource-pressure, node/not-ready); the control-plane node's NoSchedule taint (noise).
Check:
1. describe(<namespace>, pod, <pod>)  IF FailedScheduling names a selector or affinity → 2; IF it names a taint or unschedulable nodes → 3.
2. exec_kubectl_guarded `kubectl get nodes --show-labels`, then `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.nodeSelector}{.spec.affinity}'`  IF the required label or value is on no schedulable node → the selector is the finding.
3. exec_kubectl_guarded `kubectl describe nodes`  IF every candidate node has a taint the pod does not tolerate, or Unschedulable true → that taint or cordon is the finding.
Evidence to quote: the scheduler message, and the label, taint or Unschedulable line that does not match the pod.
Fix family: roll back or patch the nodeSelector/affinity on the owning workload; remove an erroneous manual taint, or uncordon a node once it is healthy; add a toleration only if the dedication is intended.
Never: relabel nodes to satisfy a typo (attracts other workloads); remove condition taints by hand (the controller re-adds them); uncordon a node that was cordoned for a real fault.
Illustration:
  Observation: Warning FailedScheduling ... 0/<n> nodes available ... <message naming the node selector (MatchNodeSelector)>
  Reading: no node carries the label the pod requires; resources are not the issue.
  Next: `kubectl get nodes --show-labels`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/ https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/ https://www.kubernetes.io/docs/reference/node/node-status/

## startup/spread-or-hostport

Signals: pods Pending because topology spread with `whenUnsatisfiable: DoNotSchedule` or (anti-)affinity cannot be met (nodes missing the topology key are bypassed); "didn't have free ports for the requested pod ports" (`PodFitsHostPorts`; with hostPort at most one such pod runs per node); "Node didn't have enough resource: pods, requested: 1, used: 32, capacity: 32". Inverse failure: all replicas placed on one node that then fails; scale-down does not rebalance.
Not this when: the reason names cpu or memory (capacity/insufficient-resources); a selector, taint or cordon (startup/node-selection).
Check:
1. describe(<namespace>, pod, <pod>)  IF the message cites topology or affinity → 2; free ports → 3; pods capacity → 4.
2. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.template.spec.topologySpreadConstraints}'` and `kubectl get pods -n <namespace> -o wide`  IF the constraint cannot be met by the nodes and their labels, or a recent revision added it → the constraint is the finding.
3. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].ports}'`  IF a hostPort is set and replicas exceed the nodes that can host it → the hostPort is the finding.
4. exec_kubectl_guarded `kubectl describe node <node>`  IF the pods count equals capacity → node pod limit.
Evidence to quote: the scheduler message and the constraint, hostPort or pod count it refers to.
Fix family: relax to ScheduleAnyway or raise maxSkew; roll back the constraint change; remove an unnecessary hostPort (use a Service); add nodes is outside the agent (escalate).
Never: delete other services' pods to make room.
Illustration:
  Observation: Warning FailedScheduling ... didn't have free ports for the requested pod ports
  Reading: replicas compete for one hostPort per node; cpu and memory are not the cause.
  Next: `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].ports}'`
Sources: https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/ https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads https://k8s.af/

## startup/statefulset-stalled

Signals: StatefulSet with `OrderedReady`: ordinal N+1 is not created before ordinal N is Running and Ready; a template that never becomes Running and Ready stops the rollout, and reverting the template is not enough: "you must also delete any Pods that StatefulSet had already attempted to run with the bad configuration". A StatefulSet needs a headless Service that the user creates.
Not this when: the stuck ordinal's claim cannot bind (storage/pvc-pending); the stuck ordinal crashes (crash/exit-error) or fails readiness (probes/readiness-failing); handle that first through its entry.
Check:
1. get_pod_status(<namespace>)  IF ordinals stop at one that is not Ready → that lowest non-ready ordinal explains the stall → 2.
2. describe(<namespace>, statefulset, <statefulset>)  IF the highest updated pod is not Ready while lower ones run the old revision → the rollout is stuck on the new template.
3. exec_kubectl_guarded `kubectl get statefulset <statefulset> -n <namespace> -o jsonpath='{.spec.serviceName}'`, then `kubectl get service -n <namespace>`  IF no Service of that name with ClusterIP None exists → the missing headless Service is the finding.
Evidence to quote: the ordinal and its state, and the template difference or the missing Service.
Fix family: fix the stuck ordinal through its own entry; revert the template, then delete the pods that already ran with the bad template (documented forced rollback); recreate the headless Service.
Never: delete a StatefulSet's PVCs (data loss); force-delete stateful pods; attempt data repair, replication fixes or snapshot restore yourself (escalate).
Illustration:
  Observation: <statefulset>-0 1/1 Running; <statefulset>-1 0/1 CrashLoopBackOff; no <statefulset>-2
  Reading: ordinal 2 waits for ordinal 1 by design; ordinal 1 is the one to examine.
  Next: describe(<namespace>, pod, <statefulset>-1)
Sources: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset https://kubernetes.io/docs/tasks/debug/debug-application/_print https://k8s.af/

## crash/exit-error

Signals: `State: Waiting Reason: CrashLoopBackOff`, `Last State: Terminated Reason: Error Exit Code: 1`, rising Restart Count; event "Back-off restarting failed container" (reason `BackOff`). `Reason: Completed, Exit Code: 0` under a Deployment is "unexpected for a long-running service" (one-shot command or entrypoint). 
Not this when: Last State is OOMKilled (capacity/oom-killed); `Unhealthy` liveness events precede each restart (probes/liveness-mismatch); the previous log names another service (crash/dependency-failure); a Job's pod is Completed (normal); a few old restarts with a stable recent history (noise).
Check:
1. describe(<namespace>, pod, <pod>)  read Last State reason, exit code, finished time. IF OOMKilled → capacity/oom-killed; IF Completed with exit 0 → 4; ELSE → 2.
2. get_logs(<namespace>, <pod>, <container>, previous=true)  IF the last error names a setting, key or file → 3; IF it names another service → crash/dependency-failure; IF empty → `kubectl get pod <pod> -n <namespace> -o jsonpath='{.status.containerStatuses[*].lastState.terminated.message}'`, then 4.
3. exec_kubectl_guarded `kubectl get configmap <configmap> -n <namespace> -o yaml`  IF the key is missing or holds the value the error rejects → config/bad-config-value.
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  IF the image, command or args changed with the newest revision and the restarts began then → that change is the finding.
Evidence to quote: the last log line (or termination message) before exit, the input it names, and onset time against the change time.
Fix family: roll back the revision or the ConfigMap/Secret change; restart only after the input is fixed.
Never: raise limits or delete pods without a cause; edit application code.
Illustration:
  Observation: Last State: Terminated  Reason: Error  Exit Code: 1 ... previous log: "missing required setting <key>"
  Reading: the process rejects its own input; no Unhealthy events, so probes are ruled out.
  Next: `kubectl get configmap <configmap> -n <namespace> -o yaml`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/ https://kubernetes.io/docs/tasks/debug/debug-application/_print https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/crashloopbackoff-events

## crash/dependency-failure

Signals: CrashLoopBackOff whose previous log shows connection refused, timeout or name-resolution failure to a database or another service ("failed dependency connections"); or pods stay Running while their logs show timeouts or 5xx naming a dependency; restarts or errors line up with the dependency's outage.
Not this when: the error is the process's own setting (crash/exit-error); the dependency has ready endpoints but the path to it is broken (network entries); every name fails to resolve (network/cluster-dns); connection errors only in the first seconds, followed by a serving line (start-up noise).
Check:
1. get_logs(<namespace>, <pod>, <container>, previous=true), or `kubectl logs <pod> -n <namespace> --since=5m` for a Running pod  IF an error names a dependency → 2.
2. exec_kubectl_guarded `kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service>`  IF the dependency has no ready endpoints → the dependency is unhealthy: load the entry for its own state (crash, probes, startup); IF it has ready endpoints → load network.
3. get_events(<namespace>)  order failures by time; the earliest failing component is the root, the others are victims.
Evidence to quote: the client's log line naming the dependency, and the dependency's endpoint or pod state at the same time.
Fix family: fix the deepest failing component first; restart upstream services afterwards only if they do not recover; a restart of the crashing service is pointless before that.
Never: roll back or restart upstream services that are only victims.
Illustration:
  Observation: previous log: "connect to <service>:<port>: connection refused"; EndpointSlice for <service>: no ready endpoints
  Reading: this pod is a victim; the fault sits in <service>, which has nothing ready to serve.
  Next: describe(<namespace>, pod, <dependency-pod>)
Sources: https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/crashloopbackoff-events https://kubernetes.io/docs/tasks/debug/debug-application/debug-service https://kubernetes.io/docs/concepts/workloads/pods/probes/ https://par.nsf.gov//servlets/purl/10429072

## crash/lifecycle-hook

Signals: kubelet events `FailedPostStartHook`, `FailedPreStopHook`; a preStop hook that outlasts the grace period gets a one-off 2s extension, then the container is killed.
Not this when: the container fails on its own with no hook event (crash/exit-error); errors appear only while pods terminate during rollouts (network/termination-gap).
Check:
1. describe(<namespace>, pod, <pod>)  IF a FailedPostStartHook or FailedPreStopHook event is present and newer than the pod → 2.
2. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].lifecycle}'`  read the hook command → 3.
3. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`, then `kubectl get replicaset <replicaset> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].lifecycle}'` on the older ReplicaSet  IF the hook differs from the last working revision → the hook change is the finding.
Evidence to quote: the hook event message and the hook field on the current vs previous template.
Fix family: roll back the owning Deployment, or patch the hook or terminationGracePeriodSeconds on its template.
Never: edit application code; delete pods repeatedly without changing the hook.
Illustration:
  Observation: Warning FailedPostStartHook ... <container> ... exited with <code>
  Reading: the container is killed because its hook fails, not because the main process fails.
  Next: `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].lifecycle}'`
Sources: https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/

## crash/security-context

Signals: the container fails to start or crashes when its securityContext (for example runAsNonRoot, a read-only root filesystem, dropped capabilities) conflicts with what the image needs; the error text references a user, a permission or a read-only file system; the securityContext changed in the last revision. (Mostly engineering inference in the taxonomy; treat as a hypothesis to check.)
Not this when: pods are never created and the ReplicaSet's FailedCreate names PodSecurity (access/pod-security-admission); the entrypoint is missing (startup/create-container-error); the error names a setting value (crash/exit-error).
Check:
1. describe(<namespace>, pod, <pod>)  IF the event or Last State mentions user, permission or read-only → 2.
2. get_logs(<namespace>, <pod>, <container>, previous=true)  IF the last line is a permission or read-only error → 3.
3. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.securityContext}{.spec.containers[*].securityContext}'`, and the same path on the older ReplicaSet (`kubectl get replicaset <replicaset> -n <namespace> -o jsonpath='{.spec.template.spec.securityContext}'`)  IF the setting changed in the newest revision → that change is the finding.
Evidence to quote: the permission or read-only error line and the securityContext field that changed.
Fix family: roll back the template change on the owning workload.
Never: weaken the securityContext or the namespace's security policy without human approval.
Illustration:
  Observation: previous log: "open <path>: read-only file system"; securityContext: readOnlyRootFilesystem true (new revision)
  Reading: the new setting removed write access the process needs; the process itself is unchanged.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/ https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/

## crash/job-failed

Signals: Job condition `Failed` after `backoffLimit` (default 6) retries, or `reason: DeadlineExceeded` when `activeDeadlineSeconds` passed (it takes precedence); pod re-creation back-off 10s, 20s, 40s... capped at ten minutes; no automatic restart after Failed. CronJob: Warning `TooManyMissedTimes` ("too many missed start times. Set or decrease .spec.startingDeadlineSeconds or check clock skew"), `suspend` true, or Jobs piling up under `concurrencyPolicy: Allow` (the default).
Not this when: Job pods are Completed (normal end state); a CronJob keeps 3 successful and 1 failed Job by default (noise).
Check:
1. exec_kubectl_guarded `kubectl get jobs -n <namespace> --sort-by=.metadata.creationTimestamp`  IF a Job is not complete → 2; IF Jobs pile up or are missing → 4.
2. describe(<namespace>, job, <job>)  IF the condition is Failed or DeadlineExceeded → 3.
3. exec_kubectl_guarded `kubectl logs job/<job> -n <namespace>`  IF the error names a dependency or setting → load that entry (crash/dependency-failure, config/bad-config-value).
4. exec_kubectl_guarded `kubectl get cronjob <cronjob> -n <namespace> -o yaml`  IF suspend is true, lastScheduleTime is stale, or many Jobs run at once under Allow → that field is the finding.
Evidence to quote: the Job condition and reason, the failing log line, or the CronJob field.
Fix family: fix the dependency or config, then re-create the Job (or suspend and resume); patch concurrencyPolicy, startingDeadlineSeconds or suspend on the CronJob.
Never: re-create the Job before the cause is fixed; delete Jobs that hold the only failure logs before reading them.
Illustration:
  Observation: <job>   0/1   ... Conditions: Failed True ... reason DeadlineExceeded
  Reading: the Job ran past activeDeadlineSeconds; the pod log says what it was waiting on.
  Next: `kubectl logs job/<job> -n <namespace>`
Sources: https://kubernetes.io/docs/concepts/Workloads/controllers/job/ https://kubernetes.io/docs/concepts/jobs/cron-jobs/ https://k8s.af/

## network/selector-mismatch

Signals: a Service's EndpointSlice shows no endpoints (`ENDPOINTS <none>`) while the intended pods are Ready; the docs' example: the Service selects one label while the pods carry another; "the number of endpoints should match the expected Pod count"; an ingress usually answers 503 for a backend with no endpoints. Label drift can also make controllers lose or over-adopt pods (pods with no owner, more pods matching a selector than replicas).
Not this when: endpoints exist but are `ready: false` (probes/readiness-failing); endpoints are ready but connections fail (network/port-mismatch, network/network-policy); a Service with no selector or a headless Service (by design).
Check:
1. exec_kubectl_guarded `kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service>`  IF no endpoints → 2.
2. exec_kubectl_guarded `kubectl get service <service> -n <namespace> -o yaml` and `kubectl get pods -n <namespace> --show-labels`  IF a selector key or value matches no Ready pod → that selector or label is the finding.
3. exec_kubectl_guarded `kubectl get pods -n <namespace> -l <key>=<value>`  confirms the count the selector returns; IF more pods than replicas, or pods with no owner (`kubectl get pod <pod> -n <namespace> -o jsonpath='{.metadata.ownerReferences}'`) → label drift on the template.
Evidence to quote: the Service's spec.selector, the pod labels that differ, and the empty EndpointSlice.
Fix family: patch the Service selector (or the pod template labels) back to the value the rest of the application uses.
Never: change a Deployment's selector (immutable; recreating the Deployment deletes its pods by default); delete the Service.
Illustration:
  Observation: Service <service> selector <key>=<value-a>; pods show <key>=<value-b>; EndpointSlice: no endpoints
  Reading: the pods are healthy but not selected; it rules out readiness.
  Next: patch the side that differs from the rest of the application, after quoting both values.
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-service https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/ https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ https://dsn2024uq.github.io/Proceedings/pdfs/DSN2024-6rvE3SSpzFYmysif75Dkid/410500a001/410500a001.pdf https://docs-static.daocloud.io/en/network/modules/ingress-nginx/troubleshooting/

## network/port-mismatch

Signals: endpoints exist and are ready, but connections are refused or time out; the docs' checklist: is the port in spec.ports[], does targetPort equal the port the pod listens on, numeric vs named port, does the named port exist on the pods, does the protocol match; "Verify that the pod's containerPort matches the Service's targetPort".
Not this when: the EndpointSlice is empty (network/selector-mismatch); timeouts while ports agree and a policy selects the pods (network/network-policy); the backend crashes or is not Ready (crash, probes).
Check:
1. exec_kubectl_guarded `kubectl get service <service> -n <namespace> -o yaml`  note port, targetPort, protocol → 2.
2. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].ports}'`  IF targetPort (or the named port) is not a containerPort of the pod → the mismatch is the finding; IF they agree → 3.
3. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  IF the start-up line names a listening port different from targetPort → the Service side differs; IF the pod's port changed in the newest ReplicaSet → the template side differs.
Evidence to quote: the Service's targetPort and the pod's containerPort (or the listening-port log line) side by side.
Fix family: patch the Service targetPort, port or protocol (or the pod template port) so both sides agree, changing the side that differs from the rest of the application.
Never: delete and recreate the Service; expose the pod on a hostPort to bypass the Service.
Illustration:
  Observation: Service <service> targetPort <port-a>; pod containerPort <port-b>; EndpointSlice ready: true
  Reading: traffic reaches a port nothing listens on; endpoints are fine, so the selector is ruled out.
  Next: `kubectl logs <pod> -n <namespace> --since=5m`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-service https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/ https://kubernetes.io/docs/concepts/services-networking/service/

## network/network-policy

Signals: a pod becomes isolated for ingress or egress as soon as any policy of that type selects it; a flow needs the source's egress and the destination's ingress to allow it; blocked connections are not logged; a default deny-all egress policy also blocks DNS, so only the selected pods fail to resolve while DNS is healthy; calls leaving the cluster can fail through an egress policy (ipBlock behaviour with NAT is implementation-defined).
Not this when: failures follow one node (node/pod-network-cni); ports disagree (network/port-mismatch); every pod fails to resolve (network/cluster-dns); a policy exists but the network plugin does not enforce policies (it then has no effect).
Check:
1. exec_kubectl_guarded `kubectl get networkpolicy -n <namespace>`  IF a policy's podSelector matches the target or the client → 2; IF none → network ruled out for policy.
2. exec_kubectl_guarded `kubectl get networkpolicy <policy> -n <namespace> -o yaml`  IF its rules do not admit the client's labels, namespace or port (or, for egress, port 53 to the cluster DNS) → that policy is the finding.
3. exec_kubectl_guarded `kubectl get namespace <namespace> --show-labels` and `kubectl get pods -n <namespace> --show-labels`  confirm the labels the rule would need.
Evidence to quote: the policy's selector and the rule that does not admit the failing flow, plus its creation or change time against the onset.
Fix family: revert or patch the offending policy to its last known-good spec; add an allow-DNS egress rule when an egress default-deny blocks DNS.
Never: delete all policies in the namespace (security regression; needs approval).
Illustration:
  Observation: NetworkPolicy <policy> podSelector <key>=<value>; policyTypes [Egress]; egress rules: none for port 53
  Reading: the selected pods cannot reach DNS, so name errors come from the policy, not from the DNS pods.
  Next: `kubectl get pods -n kube-system -l k8s-app=kube-dns`
Sources: https://kubernetes.io/docs/concepts/services-networking/network-policies/ https://kubernetes.io/docs/tasks/debug/debug-application/debug-service https://k8s.af/

## network/traffic-policy-local

Signals: "If the traffic policy is Local and there are no node-local endpoints, traffic is dropped by kube-proxy" (internalTrafficPolicy) or "does not forward any traffic" (externalTrafficPolicy); a load balancer health check returns 200 only on nodes with a local endpoint; pods stay healthy.
Not this when: there are no endpoints anywhere (network/selector-mismatch); failures follow one node's data path while the policy is Cluster (node/pod-network-cni); the Service works by pod IP but not by cluster IP on any node (node/kube-proxy).
Check:
1. exec_kubectl_guarded `kubectl get service <service> -n <namespace> -o jsonpath='{.spec.externalTrafficPolicy} {.spec.internalTrafficPolicy}'`  IF either is Local → 2.
2. exec_kubectl_guarded `kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service> -o yaml`  read nodeName per ready endpoint → 3.
3. exec_kubectl_guarded `kubectl get pods -n <namespace> -o wide`  IF the failing clients or receiving nodes are exactly the nodes without a ready endpoint → the Local policy is the finding.
Evidence to quote: the traffic policy field and the list of nodes that hold ready endpoints against the failing nodes.
Fix family: patch the policy to Cluster (loses source-IP preservation) or spread replicas so every receiving node has a ready endpoint.
Never: delete the Service; drain all serving nodes at once.
Illustration:
  Observation: externalTrafficPolicy: Local; endpoints on <node-a> only; errors from requests entering <node-b>
  Reading: <node-b> has no local endpoint, so traffic there is dropped; the selector is fine.
  Next: `kubectl get pods -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/reference/networking/_print https://k8s.af/

## network/cluster-dns

Signals: `nslookup: can't resolve 'kubernetes.default'`; DNS pods (label `k8s-app=kube-dns`) not 1/1 Running, scaled to 0, OOMKilled or in CrashLoopBackOff; the kube-dns Service or its EndpointSlice missing; log `plugin/loop: Loop (127.0.0.1:<port> -> :<port>) detected for zone "."` (node resolv.conf points at a local resolver); query log `SERVFAIL` for cluster names when the DNS ClusterRole `system:coredns` lacks list/watch on endpoints, endpointslices, namespaces, pods or services; external names fail while cluster names work after a Corefile change (changes take a minute or two).
Not this when: only some pods fail to resolve (network/network-policy, network/pod-dns-config); periodic 5-second stalls with clean DNS metrics (node/conntrack-dns-stalls).
Check:
1. exec_kubectl_guarded `kubectl get pods -n kube-system -l k8s-app=kube-dns`  IF none Ready → 2; IF all Ready → 3.
2. exec_kubectl_guarded `kubectl get deployments -n kube-system` and `kubectl get endpointslices -n kube-system -l kubernetes.io/service-name=kube-dns`  IF replicas 0 or no ready endpoints → scale or crash is the finding; IF crashing → 3.
3. exec_kubectl_guarded `kubectl logs -n kube-system -l k8s-app=kube-dns --since=5m`  IF Loop detected or forward errors → 4; IF permission errors → `kubectl describe clusterrole system:coredns`.
4. exec_kubectl_guarded `kubectl get configmap -n kube-system -o yaml`  compare the Corefile's forward and stub zones with the last known value.
Evidence to quote: the DNS pod or endpoint state, or the loop, SERVFAIL or permission log line.
Fix family: scale the DNS Deployment back up, restart it or roll back its last change; give it more memory if OOMKilled; revert the Corefile; restore the missing ClusterRole rule.
Never: scale cluster DNS to 0; point application pods at external resolvers (breaks cluster names).
Illustration:
  Observation: kube-system DNS pods: none (replicas 0); name-resolution errors across services
  Reading: no DNS server runs, so every service fails to resolve.
  Next: `kubectl get deployments -n kube-system`
Sources: https://www.kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/ https://coredns.io/plugins/loop/ https://dsn2024uq.github.io/Proceedings/pdfs/DSN2024-6rvE3SSpzFYmysif75Dkid/410500a001/410500a001.pdf https://k8s.af/

## network/pod-dns-config

Signals: a short Service name works only inside the same namespace (cross-namespace needs `<service>.<namespace>`); a relative name fails while the FQDN works; `dnsPolicy: Default` is not the default (it inherits the node's resolver, so cluster names fail); hostNetwork pods need `ClusterFirstWithHostNet`; `None` requires a dnsConfig with at least one nameserver; search list limits 32 entries / 2048 characters.
Not this when: nothing resolves anywhere (network/cluster-dns); an egress policy selects the failing pods (network/network-policy); the configured host name is simply wrong in the app's config (config/bad-config-value).
Check:
1. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.dnsPolicy} {.spec.hostNetwork} {.spec.dnsConfig}'`  IF the policy is Default, None without nameservers, or hostNetwork without ClusterFirstWithHostNet → the DNS setting is the finding; ELSE → 2.
2. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  note the exact host name that fails → 3.
3. exec_kubectl_guarded `kubectl get services -A`  IF that name has no Service in the namespace the search path implies → the name or namespace in the config is the finding.
Evidence to quote: the pod's dnsPolicy/dnsConfig, or the failing host name next to the namespace where the Service really is.
Fix family: patch dnsPolicy or dnsConfig on the owning workload back to the last working value; patch the config to the FQDN (`<service>.<namespace>.svc.cluster.local`) or the correct name.
Never: change cluster DNS for one client's error; point pods at external resolvers.
Illustration:
  Observation: dnsPolicy: Default; log: name-resolution error for <service>; DNS pods Ready
  Reading: the pod uses the node's resolver, so cluster names cannot resolve; cluster DNS itself is healthy.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-service https://www.kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/ https://www.kubernetes.io/docs/concepts/services-networking/dns-pod-service/

## network/ingress-class-address

Signals: "Only creating an Ingress resource has no effect" without a running controller; an Ingress without ingressClassName uses the default IngressClass, and with more than one default new class-less Ingresses are rejected; the Ingress ADDRESS stays empty. A LoadBalancer Service's address appears in `.status.loadBalancer.ingress` asynchronously; NodePorts (30000-32767) may need local firewall rules.
Not this when: the controller serves but routes wrong (network/ingress-backend-path); TLS errors at the entry (network/ingress-cert).
Check:
1. exec_kubectl_guarded `kubectl get ingress -n <namespace>`  IF ADDRESS is empty → 2.
2. exec_kubectl_guarded `kubectl get ingressclass`  IF the Ingress's class is not listed or no class exists → the class reference is the finding; ELSE → 3.
3. exec_kubectl_guarded `kubectl get pods -A -l app.kubernetes.io/component=controller`  IF the controller pod is missing or not Ready → the controller is the finding; IF Ready → get_logs on it: IF it never mentions this Ingress → the class does not match.
4. For a LoadBalancer Service: `kubectl get service <service> -n <namespace> -o jsonpath='{.status.loadBalancer}'`  IF empty → read `kubectl describe service <service> -n <namespace>` events.
Evidence to quote: the Ingress class and the IngressClass list, or the controller pod state, or the empty load-balancer status.
Fix family: patch ingressClassName to the class the controller serves; restart or scale the controller if it is down; cloud load-balancer provisioning is outside the agent (escalate).
Never: delete the Ingress; replace the entry with a NodePort or hostPort to bypass it.
Illustration:
  Observation: <ingress>  class <class-a>  ADDRESS (empty); ingressclass list: <class-b>
  Reading: no controller serves <class-a>, so the rules were never applied.
  Next: `kubectl get pods -A -l app.kubernetes.io/component=controller`
Sources: https://kubernetes.io/docs/concepts/services-networking/Ingress/ https://docs-static.daocloud.io/en/network/modules/ingress-nginx/troubleshooting/ https://kubernetes.io/docs/concepts/services-networking/service/ https://kubernetes.io/docs/reference/networking/_print

## network/ingress-backend-path

Signals: 503 from the controller when a backend has no endpoints; 404 or the default backend when no rule matches; describing the Ingress shows each path's backend and its endpoints. Path rules: pathType is required; Exact is case-sensitive and exact (/foo is not /foo/); Prefix matches by path element (/aaa/bbb does not match /aaa/bbbxyz); the longest path wins.
Not this when: the backend Service has pods but no ready endpoints (network/selector-mismatch, probes/readiness-failing); ADDRESS is empty (network/ingress-class-address); the 404 comes from the application itself (check the controller log).
Check:
1. exec_kubectl_guarded `kubectl describe ingress <ingress> -n <namespace>`  IF a backend names a Service that does not exist or a port it does not expose → that backend is the finding; IF the backend shows no endpoints → 2; IF backends are sound → 3.
2. exec_kubectl_guarded `kubectl get endpoints <service> -n <namespace>`  IF empty → load network/selector-mismatch or probes/readiness-failing.
3. exec_kubectl_guarded `kubectl get ingress <ingress> -n <namespace> -o yaml`  IF the requested host or path matches no rule (pathType, trailing slash, case) → the rule is the finding.
4. get_logs on the controller pod  IF errors name this Ingress, host or backend → quote them.
Evidence to quote: the backend line from describe, the Service's ports, or the rule that does not match the failing path.
Fix family: patch the Ingress backend Service name or port, or revert the rule change; fix the backend through its own entry.
Never: delete the Ingress; point the backend at an unrelated Service to get a 200.
Illustration:
  Observation: Rules: <host> /<path>  <service>:<port>  (<none>)
  Reading: the backend has no endpoints, so the 503 comes from the Service, not the routing rule.
  Next: `kubectl get endpoints <service> -n <namespace>`
Sources: https://kubernetes.io/docs/concepts/services-networking/Ingress/ https://gitea.cncfstack.com/kubernetes/ingress-nginx/raw/commit/c9d069e64d643eb185ab41588f23d26f9b782488/docs/troubleshooting.md https://docs-static.daocloud.io/en/network/modules/ingress-nginx/troubleshooting/

## network/ingress-cert

Signals: clients of the Ingress fail TLS or get an unexpected certificate while the pods are healthy; the TLS Secret must exist in the Ingress's namespace and contain `tls.crt` and `tls.key`; `tls.hosts` must match `rules[].host` explicitly ("TLS will not work on the default rule"); a certificate past its expiry date fails handshakes client-side.
Not this when: the TLS error is between two services inside the application (config/service-tls-cert); a Certificate resource is not Ready and is not being reissued (config/cert-renewal explains why); ADDRESS is empty (network/ingress-class-address).
Check:
1. exec_kubectl_guarded `kubectl get ingress <ingress> -n <namespace> -o jsonpath='{.spec.tls}'`  note each secretName and host → 2.
2. exec_kubectl_guarded `kubectl get secret <secret> -n <namespace> -o jsonpath='{.type}'`  IF not found, or not kubernetes.io/tls → the reference is the finding; ELSE → 3.
3. inspect_tls_secret(<namespace>, <secret>)  IF expired is true or not-after is in the past, not-before is in the future, or the DNS names do not include the Ingress host → that certificate is the finding.
4. get_logs on the controller pod  IF errors name this Ingress's Secret or host → quote them.
Evidence to quote: the inspect_tls_secret line with not-after (or the DNS names) next to the Ingress host and the current time.
Fix family: point the Ingress at the correct Secret, or replace the certificate with a valid one for the same hosts; if none is available, say so in the diagnosis.
Never: remove the tls section or serve plain HTTP; read or print `tls.key`; issue a self-signed replacement to production clients.
Illustration:
  Observation: inspect_tls_secret: subject CN=<host> ... not after <date in the past> ... expired: true
  Reading: the certificate the Ingress serves has expired; host names match, so the secret reference is right.
  Next: `kubectl get certificates -n <namespace>`
Sources: https://kubernetes.io/docs/concepts/services-networking/Ingress/ https://cert-manager.io/docs/usage/certificate/ https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads

## network/termination-gap

Signals: short bursts of 502/503 that line up exactly with pod terminations (rollouts, scale-down), not with errors in new pods; endpoint removal on deletion goes through EndpointSlice conditions; default grace period 30s, TERM then KILL; recurring and invisible in pod status.
Not this when: the new version itself returns errors after the rollout completes (config/bad-revision-ready); new pods never become Ready (probes/rollout-deadline); constant churn from autoscaler flapping (capacity/hpa).
Check:
1. get_events(<namespace>)  IF error bursts coincide with Killing / ScalingReplicaSet events and stop between them → 2.
2. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.template.spec.terminationGracePeriodSeconds} {.spec.template.spec.containers[*].lifecycle}'`  IF there is no preStop delay or the grace period is shorter than in-flight requests need → the termination settings are the suspect.
3. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m` on the client or ingress side  IF 502/503 timestamps match the terminating pods → confirmed.
Evidence to quote: error timestamps next to the Killing events, and the grace/preStop fields.
Fix family: patch a preStop delay or terminationGracePeriodSeconds on the owning template; reduce churn.
Never: roll back a healthy version because of termination-only errors; disable readiness.
Illustration:
  Observation: 503 at <t1>, <t2>; events: Killing <pod-a> at <t1>, Killing <pod-b> at <t2>; no errors between
  Reading: errors appear only while pods stop, so the new pods are not the cause.
  Next: `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.template.spec.terminationGracePeriodSeconds}'`
Sources: https://k8s.af/ https://kubernetes.io/docs/concepts/workloads/pods/probes/ https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle https://kubernetes.io/docs/reference/networking/_print

## storage/pvc-pending

Signals: a PersistentVolumeClaim stays Pending and its pod is Pending with an unbound claim; "Claims will remain unbound indefinitely if a matching volume does not exist"; `storageClassName: ""` binds only to class-less volumes; the default StorageClass carries annotation `storageclass.kubernetes.io/is-default-class`; "Failed to provision volume with StorageClass"; a bound volume's node affinity can exclude every schedulable node.
Not this when: the claim is Pending only until a pod uses it under WaitForFirstConsumer (noise); claims are Bound and the pod shows FailedMount (storage/attach-mount-failure, storage/configmap-secret-volume).
Check:
1. exec_kubectl_guarded `kubectl get pvc -n <namespace>`  IF a claim is not Bound → 2; IF all Bound but a pod is Pending → 4.
2. exec_kubectl_guarded `kubectl describe pvc <claim> -n <namespace>`  IF events name a provisioning failure or a class → 3.
3. exec_kubectl_guarded `kubectl get storageclass` and `kubectl get pv`  IF the claim's class does not exist, or no volume matches its size, accessModes and class → that is the finding.
4. exec_kubectl_guarded `kubectl get pv`, then `kubectl describe pv <volume>`  IF the volume's node affinity excludes every schedulable node → the placement is the finding.
Evidence to quote: the claim's events and its storageClassName, size and accessModes against the classes and volumes that exist.
Fix family: patch the claim template to a valid StorageClass (a new claim); restart a failing provisioner.
Never: delete a Bound claim or volume with reclaim policy Delete (it deletes the backing storage); delete claims that hold data.
Illustration:
  Observation: <claim>   Pending   storageclass <class>; events name <class>; the class list has no <class>
  Reading: the claim names a class that does not exist, so no volume is provisioned; the pod only waits.
  Next: `kubectl get storageclass`
Sources: https://kubernetes.io/docs/concepts/storage/persistent-volumes/ https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/vmware/docs/troubleshooting/storage

## storage/configmap-secret-volume

Signals: pod stuck `ContainerCreating` with kubelet event `FailedMount` naming a configMap, secret or projected volume; "You must create a ConfigMap before you can use it" (same for Secret volumes); a pod and its ConfigMap must be in the same namespace.
Not this when: the event names a persistent volume or claim (storage/attach-mount-failure, storage/pvc-pending); the object is used as environment variables, which gives CreateContainerConfigError (startup/missing-config-ref); sandbox or network setup errors also leave ContainerCreating (node/pod-network-cni).
Check:
1. describe(<namespace>, pod, <pod>)  IF a FailedMount event names a volume of a ConfigMap or Secret → 2.
2. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.volumes}'`  note the object name and items/keys → 3.
3. exec_kubectl_guarded `kubectl get configmap,secret -n <namespace>`  IF the object is not listed → it is the finding; IF listed → `kubectl get configmap <configmap> -n <namespace> -o yaml` and check that every key in items exists.
Evidence to quote: the FailedMount message and the volume entry naming the object or key that does not exist.
Fix family: restore the object (or key) from its last known version, or roll back the revision that changed the volume reference.
Never: delete the pod repeatedly (it does not fix a missing object); create an empty placeholder object to get past the mount.
Illustration:
  Observation: Warning FailedMount ... volume "<volume>" ... <message naming configmap <configmap>>
  Reading: the mount waits on a missing object, not on storage; persistent volumes are not involved.
  Next: `kubectl get configmap,secret -n <namespace>`
Sources: https://v1-34.docs.kubernetes.io/docs/concepts/storage/volumes https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events https://kubernetes.io/docs/concepts/configuration/configmap

## storage/multi-attach

Signals: event "Multi-Attach error for volume ... exclusively attached to one node", often after a node was shut down, deleted or failed; a ReadWriteOnce volume is mountable read-write by a single node.
Not this when: the attach fails for other reasons such as the storage driver (storage/attach-mount-failure); the claim is not Bound (storage/pvc-pending).
Check:
1. describe(<namespace>, pod, <pod>)  IF the event says Multi-Attach → 2.
2. exec_kubectl_guarded `kubectl get volumeattachments`  IF the attachment for the volume still points at the old node → 3.
3. exec_kubectl_guarded `kubectl get pods -n <namespace> -o wide` and `kubectl get nodes`  IF the old pod still exists on that node, or the node is NotReady or Unknown → the old attachment is the finding (see node/unreachable).
Evidence to quote: the Multi-Attach event and the VolumeAttachment's node name next to the new pod's node.
Fix family: make sure the old pod and node are really gone, then let the detach complete; for a node that is down follow node/unreachable.
Never: remove VolumeAttachment finalizers while the old node might still write; force-delete the old pod; delete the claim or volume.
Illustration:
  Observation: Warning ... Multi-Attach error for volume "<volume>" ... exclusively attached to one node
  Reading: the volume is still held by <node-a>; the new pod on <node-b> waits for detach.
  Next: `kubectl get volumeattachments`
Sources: https://kubernetes.io/docs/concepts/storage/persistent-volumes/ https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/vmware/docs/troubleshooting/storage

## storage/attach-mount-failure

Signals: kubelet events `FailedAttachVolume`, `FailedMount`, `FailedMapVolume`, `FailedMountOnFilesystemMismatch` for a persistent volume; VolumeAttachment `detachError` messages; the storage (CSI) driver pods are unhealthy at the same time.
Not this when: the event names a ConfigMap or Secret volume (storage/configmap-secret-volume); the message says Multi-Attach (storage/multi-attach); the claim is Pending (storage/pvc-pending).
Check:
1. describe(<namespace>, pod, <pod>)  IF a FailedAttachVolume or FailedMount event names a persistent volume → 2.
2. exec_kubectl_guarded `kubectl get volumeattachments -o=custom-columns=NAME:metadata.name,DETACH_ERROR:status.detachError.message`  note errors → 3.
3. exec_kubectl_guarded `kubectl get csidrivers`, then `kubectl get pods -A -o wide`  IF the driver's controller or node pods are not Ready (on the pod's node) → the driver is the finding.
Evidence to quote: the attach or mount event, and the unhealthy driver pod or the detachError message.
Fix family: restart the storage driver pods (one node at a time).
Never: delete the claim or volume; remove VolumeAttachment finalizers; restart driver pods on all nodes at once.
Illustration:
  Observation: Warning FailedMount ... <volume>; storage driver node pod on <node> CrashLoopBackOff
  Reading: the mount fails because the node's storage driver is down, not because the claim is wrong.
  Next: describe(<driver-namespace>, pod, <driver-pod>)
Sources: https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/vmware/docs/troubleshooting/storage

## storage/volume-full

Signals: pods Running and Ready but the application logs "no space left on device" or read-only file system errors; kubelet events `VolumeResizeFailed`, `FileSystemResizeFailed`; an expansion that is too large retries forever; shrinking a volume is not supported.
Not this when: the node itself has DiskPressure (node/resource-pressure); the read-only error comes from a securityContext setting (crash/security-context); the volume mount is marked readOnly in the pod spec on purpose.
Check:
1. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  IF "no space left on device" or read-only errors appear → 2.
2. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].volumeMounts}'`  IF the path in the error is on a claim-backed mount → 3; IF the mount is readOnly → that setting is the finding.
3. exec_kubectl_guarded `kubectl describe pvc <claim> -n <namespace>`  read capacity, conditions and resize events; IF a resize failed → that event is the finding.
4. exec_kubectl_guarded `kubectl get storageclass`  check allowVolumeExpansion before proposing an expansion.
Evidence to quote: the log line with the path, the mount that holds it, and the claim's capacity or resize event.
Fix family: expand the claim if its StorageClass allows it; after a failed expansion retry with a smaller size that is still larger than the current one.
Never: delete data files from the application volume; delete or recreate the claim.
Illustration:
  Observation: log: "write <path>: no space left on device"; <path> is on volume <volume> from claim <claim>
  Reading: the claim's file system is full; the pod and node are healthy.
  Next: `kubectl describe pvc <claim> -n <namespace>`
Sources: https://kubernetes.io/docs/concepts/storage/persistent-volumes/ https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events

## storage/pvc-terminating

Signals: a claim or volume shows `Status: Terminating` with `Finalizers: [kubernetes.io/pvc-protection]`; removal is postponed while a pod uses it. This is protective behaviour, not a fault, unless the deletion was intended.
Not this when: a pod is stuck Terminating (startup/stuck-terminating); the claim is Pending (storage/pvc-pending).
Check:
1. exec_kubectl_guarded `kubectl describe pvc <claim> -n <namespace>`  IF Terminating with pvc-protection → 2.
2. exec_kubectl_guarded `kubectl get pods -n <namespace> -o wide`  IF a pod still mounts the claim → protection is working as designed; IF no pod uses it and it still remains → report it.
3. get_events(<namespace>)  IF the deletion came from no intended change → say so in the diagnosis.
Evidence to quote: the Status and Finalizers lines and the pod that still uses the claim.
Fix family: none needed; if the deletion was intended, remove the consuming pod deliberately (with approval) so protection can finish.
Never: strip the finalizer; delete the volume to make the claim go away.
Illustration:
  Observation: <claim>  Status: Terminating  Finalizers: [kubernetes.io/pvc-protection]  Used By: <pod>
  Reading: the claim is protected because <pod> still uses it; this is designed behaviour.
  Next: conclude, quoting step 1 and step 2.
Sources: https://kubernetes.io/docs/concepts/storage/persistent-volumes/

## capacity/insufficient-resources

Signals: pod Pending with `FailedScheduling ... 0/<n> nodes are available: insufficient cpu` (or memory); older wording "Node didn't have enough resource: CPU, requested: ..., used: ..., capacity: ..."; pods Pending while the node pool is at the autoscaler's maximum or cloud quota is exceeded.
Not this when: Pending for a claim (storage/pvc-pending) or a selector, taint or spread rule (startup/node-selection, startup/spread-or-hostport); Pending pods have no scheduler events at all (node/control-plane-stall); transient while nodes are being added (noise).
Check:
1. describe(<namespace>, pod, <pod>)  IF the message says insufficient cpu or memory → 2.
2. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].resources}'`  note requests → 3.
3. exec_kubectl_guarded `kubectl describe nodes`  read Allocatable and Allocated resources  IF the request is larger than any node's allocatable, or the sum of requests leaves no room → 4.
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide` and `kubectl get pods -A --field-selector status.phase=Pending`  IF a recent revision raised requests or replicas → that change is the finding.
Evidence to quote: the request against the node's free allocatable, and the object that set the request.
Fix family: restore the previous requests (roll back) if a recent change inflated them; scale down low-value workloads; adding nodes or raising cloud quota is outside the agent (escalate).
Never: delete other services' pods to make room without a priority policy; remove requests to squeeze pods in.
Illustration:
  Observation: Warning FailedScheduling ... 0/<n> nodes are available: <n> Insufficient memory; request memory <large value>
  Reading: one pod asks for more memory than any node offers; selectors and claims are ruled out.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/ https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/ https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/ https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads

## capacity/oom-killed

Signals: `Last State: Terminated Reason: OOMKilled Exit Code: 137` with restarts; memory limits are enforced reactively by kernel OOM kills; an emptyDir with `medium: Memory` counts against the writer's memory limit.
Not this when: the pod is Evicted and replaced rather than restarted in place (node/resource-pressure); several unrelated pods on one node are killed while under their own limits (node/resource-pressure, system OOM); exit 137 after Unhealthy liveness events or a grace-period expiry (probes/liveness-mismatch).
Check:
1. describe(<namespace>, pod, <pod>)  IF Last State reason is OOMKilled → 2.
2. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].resources}'`  note the memory limit → 3.
3. exec_kubectl_guarded `kubectl top pod <pod> -n <namespace> --containers`  IF usage climbs to the limit before each kill → 4. ("Metrics API not available" is not a fault.)
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  IF the limit was lowered, or the image changed, in the newest revision → that change is the finding.
Evidence to quote: the OOMKilled line with exit code 137 and the memory limit, plus the change that set it.
Fix family: restore the previous memory limit or raise limit and request moderately if the app behaves as expected; roll back if a new version leaks.
Never: remove limits entirely (shifts the risk to node OOM); raise the limit so far that the pod becomes unschedulable.
Illustration:
  Observation: Last State: Terminated  Reason: OOMKilled  Exit Code: 137  Restart Count: <n>; limits memory <value>
  Reading: the container hit its own limit; no Unhealthy events, so probes are ruled out.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/ https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction https://v1-34.docs.kubernetes.io/docs/concepts/storage/volumes

## capacity/cpu-throttling

Signals: pods stay Running and Ready with no restarts while latency rises; "cpu limits are enforced by CPU throttling ... a hard limit the kernel enforces"; usage pinned at the CPU limit during the slow window.
Not this when: a dependency is slow (crash/dependency-failure); periodic 5-second stalls (node/conntrack-dns-stalls); the HPA is pinned at its maximum (capacity/hpa); probes time out under the same load (probes/probe-timing); low-level throttling on bursty services (noise).
Check:
1. exec_kubectl_guarded `kubectl top pod -n <namespace> --containers`  IF a container's cpu sits at its limit → 2. ("Metrics API not available" is not a fault; then use step 2 and 3 only.)
2. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].resources}'`  note the cpu limit → 3.
3. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`, then the same resources path on the older ReplicaSet  IF the cpu limit was lowered in the newest revision → that change is the finding.
Evidence to quote: usage against the cpu limit for the slow container, and the revision that set the limit.
Fix family: restore or raise the cpu limit on the owning template; scale out if demand, not a setting, is the cause.
Never: lower requests to fit more pods; restart pods as a fix for throttling.
Illustration:
  Observation: top: <pod> <container> cpu <value>m; limits cpu <same value>m; restarts 0; latency high
  Reading: the container is capped at its limit, so slowness is throttling; crashes are ruled out.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/ https://k8s.af/

## capacity/quota-limitrange

Signals: 403 Forbidden on pod creation naming a quota: Deployment condition `ReplicaFailure True FailedCreate`, message like `pods "<pod>" is forbidden: exceeded quota: <quota>, requested: pods=1, used: pods=3, limited: pods=2`; the Deployment itself is created; with cpu/memory quota, pods without requests/limits may be rejected. LimitRange: 403 on min/max/ratio violation, or defaults that clash, e.g. `spec.containers[0].resources.requests: Invalid value: "700m": must be less than or equal to cpu limit`; applies only at admission.
Not this when: the FailedCreate message names PodSecurity (access/pod-security-admission) or a webhook (access/webhook-unavailable).
Check:
1. describe(<namespace>, replicaset, <replicaset>)  IF FailedCreate says exceeded quota → 2; IF it quotes min, max, ratio or request vs limit → 3.
2. exec_kubectl_guarded `kubectl describe resourcequota -n <namespace>`  IF used equals hard for the named resource → 4.
3. exec_kubectl_guarded `kubectl describe limitrange -n <namespace>`  IF the template's requests/limits fall outside it, or its defaults conflict → that rule or field is the finding.
4. exec_kubectl_guarded `kubectl get deployments -n <namespace>`  IF one workload's replicas or requests rose recently → that change used up the quota.
Evidence to quote: the FailedCreate message and the quota's used/hard line (or the LimitRange line it breaks).
Fix family: scale down the controller that grew, restore the previous replicas or requests, or patch the template to fit the LimitRange; raising the quota needs approval.
Never: delete other workloads to free quota; delete the quota or LimitRange.
Illustration:
  Observation: ReplicaFailure True FailedCreate ... exceeded quota: <quota>, requested: pods=1, used: pods=<n>, limited: pods=<n>
  Reading: the namespace is at its pod quota; the template is otherwise valid.
  Next: `kubectl describe resourcequota -n <namespace>`
Sources: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ https://kubernetes.io/docs/concepts/policy/_print

## capacity/preemption

Signals: event reason `Preempting`; the preemptor gets `nominatedNodeName`; victims get graceful termination; PodDisruptionBudgets are respected only best-effort; "Pods are preempted unnecessarily" when a high priority is given by mistake; cascading evictions from pod priorities.
Not this when: the kubelet evicted pods for node pressure (reason Evicted, node/resource-pressure); a voluntary drain moved them (node/drain-blocked-pdb).
Check:
1. get_events(<namespace>)  IF Preempting events or victims' deletions appear → 2.
2. exec_kubectl_guarded `kubectl get priorityclasses`  note values → 3.
3. exec_kubectl_guarded `kubectl get pods -n <namespace> -o jsonpath='{range .items[*]}{.metadata.name} {.spec.priorityClassName} {.status.nominatedNodeName}{end}'`  IF a workload that should be ordinary carries a high priorityClassName, and the victims were deleted when its pods were nominated → that priorityClassName is the finding.
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  IF the priorityClassName arrived with a recent revision → that revision is the suspect.
Evidence to quote: the Preempting event, the winner's priorityClassName and nominatedNodeName, and the victims' deletion time.
Fix family: patch priorityClassName of the mistaken workload (empty means priority 0) or roll back the revision that set it.
Never: delete PriorityClasses that other workloads use; give every workload the highest priority.
Illustration:
  Observation: Normal Preempting ... <pod-high> nominated on <node>; <pod-a>, <pod-b> terminated at the same time
  Reading: the victims were preempted by a higher-priority pod, not evicted by the node.
  Next: `kubectl get priorityclasses`
Sources: https://kubernetes.io/docs/concepts/configuration/pod-priority-preemption/ https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events https://k8s.af/

## capacity/hpa

Signals: `ScalingActive False` ("generally indicates problems with fetching metrics", targets `<unknown>`; resource metrics need the metrics APIService; a container without the resource request makes the HPA ignore that metric; a target scaled to 0 while minReplicas > 0 stops the HPA); `ScalingLimited True` (capped by min/max) with utilisation above target; replicas flipping when an applied manifest keeps `spec.replicas`.
Not this when: pods Pending for cpu or memory (capacity/insufficient-resources); a slow dependency is the bottleneck (crash/dependency-failure); throttling makes utilisation look capped (capacity/cpu-throttling).
Check:
1. exec_kubectl_guarded `kubectl describe hpa <hpa> -n <namespace>`  IF ScalingActive False → 2; IF ScalingLimited True at maxReplicas → 4; IF replicas flip → 5.
2. exec_kubectl_guarded `kubectl get apiservices`  IF the metrics APIService is not Available → restore its backing deployment; ELSE → 3.
3. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.replicas} {.spec.template.spec.containers[*].resources}'`  IF replicas is 0, or a container has no request for the metric → that is the finding.
4. Compare current replicas with maxReplicas and utilisation with target in the describe output  IF at max and above target while latency rises → the max is the limit.
5. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o yaml --show-managed-fields`  IF two managers alternate on spec.replicas → manifest vs HPA thrash.
Evidence to quote: the HPA condition line with its message, and the field that explains it.
Fix family: restore metrics-server; add requests to the template; scale the target back up to reactivate the HPA; raise maxReplicas within quota and capacity.
Never: raise maxReplicas beyond what quota or the downstream can absorb; delete the HPA.
Illustration:
  Observation: ScalingActive False ... <message about fetching metrics>; targets <unknown> / <target>%
  Reading: the HPA cannot read metrics, so it cannot scale; the workload itself is not at fault.
  Next: `kubectl get apiservices`
Sources: https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough

## config/bad-config-value

Signals: errors or crashes start right after a ConfigMap or Secret edit followed by a restart or rollout; application logs name the bad key or value (a wrong host name surfaces as a DNS or connection error). Misconfiguration was the largest cause class in a field study of Kubernetes failures (33 of 81).
Not this when: the image or template changed last (config/bad-revision-ready, crash/exit-error); the value is right but not yet in effect (config/change-not-applied); credentials are rejected (config/credentials-rejected).
Check:
1. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  IF the error names a key, value or address → 2.
2. get_resource(<namespace>, deployment, <deployment>)  find env, envFrom and volumes that carry that key → 3.
3. exec_kubectl_guarded `kubectl get configmap <configmap> -n <namespace> -o yaml`  read the value and metadata.managedFields (last writer and time)  IF the value is the one the error rejects and its change time matches the onset → it is the finding.
4. get_events(<namespace>)  IF a restart or rollout followed the change → confirms the timeline.
Evidence to quote: the error line, the key with its current value, and the change time against the onset.
Fix family: restore the previous ConfigMap value (patch_configmap_key or set_env), then restart the consumers so they read it.
Never: guess new values (prefer the known-good prior state); print Secret values.
Illustration:
  Observation: log: "cannot connect to <host-a>:<port>"; ConfigMap <configmap> key <key>=<host-a>, changed after the pod's previous start
  Reading: the setting changed just before the errors; network objects are not implicated yet.
  Next: get_resource(<namespace>, deployment, <deployment>)
Sources: https://dsn2024uq.github.io/Proceedings/pdfs/DSN2024-6rvE3SSpzFYmysif75Dkid/410500a001/410500a001.pdf https://k8s.af/ https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

## config/change-not-applied

Signals: the stored config is right but pods behave as before, or pods disagree: "ConfigMaps consumed as environment variables are not updated automatically and require a pod restart"; mounted ConfigMaps update after a delay; subPath mounts never update; immutable ConfigMaps must be recreated with the pods. A paused Deployment does not roll out template changes (and allows no rollback until resumed); a StatefulSet partition above the replica count never propagates updates. A misspelled manifest field (e.g. `commnd`) is accepted but ignored.
Not this when: the value itself is wrong (config/bad-config-value); the newest revision is live and wrong (config/bad-revision-ready).
Check:
1. exec_kubectl_guarded `kubectl get pods -n <namespace> -l <key>=<value> -o jsonpath='{range .items[*]}{.metadata.name} {.metadata.creationTimestamp} {end}'`  IF pods were created before the config change → 2.
2. get_resource(<namespace>, deployment, <deployment>)  IF the key comes through env or a subPath mount → those pods still hold the old value.
3. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o jsonpath='{.spec.paused}'` (StatefulSet: `kubectl get statefulset <statefulset> -n <namespace> -o jsonpath='{.spec.updateStrategy}'`)  IF paused is true or partition exceeds replicas → that is the finding.
4. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o yaml`  IF the intended field is missing from the stored object → a mistyped field was dropped.
Evidence to quote: pod creation times against the change time, the paused/partition field, or the missing field.
Fix family: restart the consumers (restart_deployment); resume the rollout or fix the partition; patch the correctly spelled field.
Never: change the value again to "force" a reload; delete pods of a StatefulSet to skip its order.
Illustration:
  Observation: pods created <t0>; ConfigMap changed <t1> later than <t0>; key consumed through env
  Reading: the running pods never read the new value; the stored value is not the problem.
  Next: get_resource(<namespace>, deployment, <deployment>)
Sources: https://kubernetes.io/docs/concepts/configuration/configmap https://v1-34.docs.kubernetes.io/docs/concepts/storage/volumes https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ https://kubernetes.io/docs/concepts/workloads/controllers/statefulset https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/

## config/credentials-rejected

Signals: pods Running while container logs show 401 Unauthorized or 403 Forbidden from a database, another service or a cloud API; errors begin at the time a Secret was rotated or changed; a 403 can also mean the pod's identity lacks permission at that service.
Not this when: the 403 comes from the Kubernetes API (`Forbidden` / "cannot <verb> resource", access/rbac-forbidden); the connection itself fails (crash/dependency-failure, network entries).
Check:
1. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  IF 401/403 or authentication failed names a dependency → 2.
2. get_resource(<namespace>, deployment, <deployment>)  find the Secret and key the client uses → 3.
3. exec_kubectl_guarded `kubectl get secret <secret> -n <namespace> -o jsonpath='{.metadata.resourceVersion} {.metadata.creationTimestamp}'` (metadata only)  IF the Secret changed just before the onset → 4.
4. Find the same setting on the server side (its Deployment and Secret)  IF client and server reference different Secrets or keys → that mismatch is the finding; compare both sides, not one.
Evidence to quote: the 401/403 line with the dependency name, and the Secret metadata or references on both sides with their change times.
Fix family: restore the previous Secret version (if available) and restart the consumers; make client and server reference the same credential.
Never: read or print secret values; disable authentication on the server.
Illustration:
  Observation: log: "authentication failed for <dependency>"; Secret <secret> resourceVersion changed after the client pod started
  Reading: the credential changed under a running client; the network path works, since the server answers.
  Next: get_resource(<namespace>, deployment, <server-deployment>)
Sources: https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/crashloopbackoff-events

## config/bad-revision-ready

Signals: error rate or latency rises when a new ReplicaSet becomes available, while pods are Running and Ready (probes test liveness, not correctness); insufficient health signals during deployments are a frequent incident factor. Mixed versions: tags can move while digests are fixed, so replicas with the same tag can run different `imageID`s and only some fail.
Not this when: a dependency changed at the same time (crash/dependency-failure); new pods never become Ready (probes/rollout-deadline); errors only during terminations (network/termination-gap).
Check:
1. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  IF the newest ReplicaSet's creation time matches the symptom onset → 2.
2. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m` on a new pod, and on an old pod if any remain  IF only new pods log the errors → the new revision is the finding.
3. exec_kubectl_guarded `kubectl get pods -n <namespace> -l <key>=<value> -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[*].imageID} {end}'`  IF the same tag shows different digests and errors follow one digest → mixed versions are the finding.
Evidence to quote: the new ReplicaSet's creation time next to the first error, and the image or digest that differs.
Fix family: roll back the Deployment (rollback_deployment); pin the image by digest and roll out.
Never: roll back services that only call the bad one; edit application code.
Illustration:
  Observation: ReplicaSet <deployment>-<hash-new> created <t1>; first 5xx at <t1>+<seconds>; pods Ready
  Reading: errors began with the new revision; readiness passes, so probes are ruled out.
  Next: `kubectl logs <pod> -n <namespace> --since=5m`
Sources: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ https://par.nsf.gov//servlets/purl/10429072 https://blog.acolyer.org/2019/06/21/what-bugs-cause-cloud-production-incidents/ https://www.kubernetes.io/docs/concepts/containers/images/

## config/service-tls-cert

Signals: two services connect but the TLS handshake fails (expired or not yet valid, unknown authority, or a name that does not match the host called) while pods are healthy; a TLS Secret holds `tls.crt` and `tls.key`; an ExternalName target can cause a certificate-hostname mismatch.
Not this when: the TLS failure is at the Ingress entry (network/ingress-cert); the certificate controller fails to issue or renew (config/cert-renewal); the client cannot connect at all (network entries).
Check:
1. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m` on client and server  IF a TLS or certificate error names a host → 2.
2. get_resource(<namespace>, deployment, <server-deployment>)  find the Secret mounted for the certificate → 3.
3. inspect_tls_secret(<namespace>, <secret>)  IF expired, not-before in the future, or the DNS names miss the host the client calls → that certificate is the finding; IF unknown authority → 4.
4. Find the CA bundle the client mounts (get_resource on its Deployment, then inspect_tls_secret on that Secret)  IF its issuer differs from the server certificate's issuer → the bundle or the certificate is the finding.
5. For an ExternalName Service: `kubectl get service <service> -n <namespace> -o yaml`  compare externalName with the certificate's names.
Evidence to quote: the error line and the inspect_tls_secret fields (dates, names, issuer) that contradict it.
Fix family: restore a valid certificate for the same names (a known previous Secret), or point the client at the correct CA bundle; patch the ExternalName Service or the client's host.
Never: disable TLS or certificate verification; read or print `tls.key`.
Illustration:
  Observation: client log: TLS handshake error naming <host-a>; inspect_tls_secret DNS names: <host-b>; dates valid
  Reading: the server presents a certificate for another name; dates are fine.
  Next: get_resource(<namespace>, deployment, <server-deployment>)
Sources: https://kubernetes.io/docs/concepts/services-networking/Ingress/ https://kubernetes.io/docs/concepts/services-networking/service/ https://cert-manager.io/docs/usage/certificate/

## config/cert-renewal

Signals: a Certificate resource shows READY False (reasons such as `DoesNotExist`, "Issuing certificate as Secret does not exist"); chain Certificate → CertificateRequest → Order → Challenge; default duration 90 days, renewal at 2/3 of the lifetime unless renewBefore is set; Challenges run a self-check (HTTP-01 404 → solver pod or solver Ingress; DNS-01 "Waiting for dns-01 challenge propagation"); Issuer or ClusterIssuer Ready False with an account error such as `invalidEmail`.
Not this when: the Ingress points at the wrong Secret (network/ingress-cert); Issuing/Pending during a normal renewal (noise); the solver Ingress is not picked up by any controller (network/ingress-class-address).
Check:
1. exec_kubectl_guarded `kubectl get certificates -n <namespace>`  IF READY False → 2.
2. exec_kubectl_guarded `kubectl describe certificate <certificate> -n <namespace>`  read the Ready reason and renewal time → 3.
3. exec_kubectl_guarded `kubectl get certificaterequests -n <namespace>`, then `kubectl describe issuer <issuer> -n <namespace>` (or `kubectl describe clusterissuer <issuer>`)  IF the issuer is not Ready → its error is the finding; ELSE → 4.
4. exec_kubectl_guarded `kubectl get challenges -n <namespace>`, then `kubectl describe challenge <challenge> -n <namespace>`  IF the self-check fails → the solver pod or Ingress is the finding.
5. inspect_tls_secret(<namespace>, <secret>)  shows whether the served certificate already expired.
Evidence to quote: the failing child resource's status line and the certificate's not-after.
Fix family: fix the issuer config or restore its referenced Secret; fix routing for the solver; then let the controller reissue.
Never: delete and recreate Certificates repeatedly (rate limits); delete the Secret as routine rotation; issue a self-signed replacement.
Illustration:
  Observation: <certificate>  READY False; CertificateRequest: issuer not ready; Issuer <issuer> Ready False ... <account error>
  Reading: renewal stops at the issuer, so the certificate will expire; the Ingress is not the cause.
  Next: `kubectl describe issuer <issuer> -n <namespace>`
Sources: https://cert-manager.io/docs/troubleshooting/ https://cert-manager.io/docs/faq/acme https://cert-manager.io/docs/usage/certificate/

## probes/liveness-mismatch

Signals: events `Unhealthy` and `Killing`; "Container probe failed liveness probe, will be restarted"; a liveness (or startup) failure makes the kubelet kill the container. Success means HTTP 200-399, TCP port open, exec exit 0, gRPC SERVING; defaults timeoutSeconds 1, periodSeconds 10, failureThreshold 3.
Not this when: the app crashes by itself with no Unhealthy events before the restart (crash/exit-error); the probe is right but times out under load or slow start (probes/probe-timing); many services restart together when one dependency degrades (probes/cascading-restarts).
Check:
1. describe(<namespace>, pod, <pod>)  read the liveness probe (type, path, port) and the Unhealthy text  IF connection refused or 404 → 2; IF timeout → probes/probe-timing.
2. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].ports}'`  IF the probe port or path is not what the container serves → 3.
3. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  IF the app logs normal work until it is killed and its start-up line names another port or path → the probe is the finding.
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`, then `kubectl get replicaset <replicaset> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].livenessProbe}'` on the older one  IF the probe changed → that revision is the suspect.
Evidence to quote: the probe's port/path next to the containerPort or listening-port line, and the Unhealthy event text.
Fix family: patch the probe port, path or thresholds on the owning template, or roll back the revision that changed it.
Never: delete the liveness probe permanently without noting it (removes self-healing).
Illustration:
  Observation: Warning Unhealthy ... liveness probe failed ... <ip>:<port-a> ... connection refused; containerPort <port-b>
  Reading: the probe checks a port nothing listens on; the app itself runs.
  Next: `kubectl logs <pod> -n <namespace> --since=5m`
Sources: https://kubernetes.io/docs/concepts/workloads/pods/probes/ https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/crashloopbackoff-events

## probes/readiness-failing

Signals: pod Running but `0/1 READY` (`Ready=False`), not restarted; on readiness failure "the EndpointSlice controller removes the Pod's IP address from the EndpointSlices of all Services that match the Pod"; EndpointSlice endpoints show `ready: false`; readiness `Unhealthy` events.
Not this when: the Service selects no pods and the pods are Ready (network/selector-mismatch); the readiness check includes a backend that is down, which is designed to fail (crash/dependency-failure); not-ready only before the first success (noise).
Check:
1. get_pod_status(<namespace>)  IF a pod is Running with READY 0/1 → 2.
2. describe(<namespace>, pod, <pod>)  read the readiness probe and Unhealthy text  IF connection refused or 404 → 3; IF it names a dependency → crash/dependency-failure; IF timeout → probes/probe-timing.
3. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[*].ports}'` and `kubectl logs <pod> -n <namespace> --since=5m`  IF the probe port or path differs from what the process serves → the probe is the finding.
4. exec_kubectl_guarded `kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service> -o yaml`  IF exactly the failing pods are `ready: false` → confirmed.
Evidence to quote: the readiness probe setting, the Unhealthy event, and the endpoint marked `ready: false`.
Fix family: patch the readiness probe on the owning template, fix the dependency it checks, or roll back the revision that changed it.
Never: turn readiness off (traffic would reach pods that cannot serve).
Illustration:
  Observation: <pod>  0/1  Running  0 restarts; Warning Unhealthy ... readiness probe failed ... 404
  Reading: the pod runs but its readiness path is not served; crash is ruled out (no restarts).
  Next: `kubectl logs <pod> -n <namespace> --since=5m`
Sources: https://kubernetes.io/docs/concepts/workloads/pods/probes/ https://kubernetes.io/docs/tasks/debug/debug-application/debug-service

## probes/probe-timing

Signals: restarts with liveness `Unhealthy` events during start-up (if start-up usually takes longer than initialDelaySeconds + failureThreshold × periodSeconds, a startup probe is needed); `Unhealthy` with timeout messages under load (default timeout 1s; heavy CPU or disk I/O can cause probe timeouts; exec probes fork a process each time).
Not this when: the probe checks the wrong port or path (probes/liveness-mismatch, probes/readiness-failing); usage sits at the CPU limit with no probe failures (capacity/cpu-throttling); a few Unhealthy events during normal start-up (noise).
Check:
1. describe(<namespace>, pod, <pod>)  read initialDelaySeconds, periodSeconds, timeoutSeconds, failureThreshold and any startupProbe  IF Unhealthy says timeout, or kills happen during start-up → 2.
2. get_logs(<namespace>, <pod>, <container>, previous=true)  IF start-up was still in progress when the container was killed and kill time ≈ initialDelay + threshold × period → the start-up timing is the finding; ELSE → 3.
3. exec_kubectl_guarded `kubectl top pod -n <namespace> --containers` and `kubectl describe node <node>`  IF probe failures coincide with CPU at the limit or a saturated node → load is the cause.
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  IF delays, timeouts or cpu limits were lowered in the newest revision → that change is the suspect.
Evidence to quote: the probe's timing fields, the kill time against the last start-up log line, or the timeout event next to cpu usage.
Fix family: patch a startup probe or the thresholds/timeout; raise the cpu request/limit if throttled; scale out under load.
Never: remove probes to stop the restarts.
Illustration:
  Observation: initialDelaySeconds 5, periodSeconds 10, failureThreshold 3; previous log ends "loading ..." at 30s; killed at 35s
  Reading: the container is killed before it finishes starting; the probe path is right.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://kubernetes.io/docs/concepts/workloads/pods/probes/ https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/crashloopbackoff-events https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/

## probes/cascading-restarts

Signals: "Incorrect implementation of liveness probes can lead to cascading failures ... restarting of container under high load ... increased workload on remaining pods"; many services restart together when one shared dependency degrades; retries and restarts amplify load (overload → high latency).
Not this when: a single service's probe is wrong (probes/liveness-mismatch); a dependency is down and only readiness fails, which is the correct non-restarting behaviour (crash/dependency-failure).
Check:
1. get_events(<namespace>)  IF Unhealthy liveness events and Killing appear across several workloads in the same window → 2.
2. exec_kubectl_guarded `kubectl get deployments -n <namespace> -o yaml`  IF their liveness probes call a path that checks a shared dependency → 3.
3. get_pod_status(<namespace>) and `kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service>`  IF the shared dependency degraded first → it is the root and the liveness design is the amplifier.
4. exec_kubectl_guarded `kubectl top pod -n <namespace>` and `kubectl get hpa -n <namespace>`  note the overloaded component.
Evidence to quote: the time order (dependency degraded, then restarts across services) and the liveness probe that checks the dependency.
Fix family: fix the dependency first; patch liveness to check only the process (local endpoint, higher failureThreshold); scale the bottleneck; scale down noisy batch load.
Never: scale up the restarting services (adds load to the dependency); restart everything at once (sheds more capacity).
Illustration:
  Observation: Unhealthy (liveness) on <deployment-a>, <deployment-b>, <deployment-c> from <t1>; <service> endpoints not ready from <t0> before <t1>
  Reading: the restarts follow one dependency's degradation; the restarting services are victims.
  Next: describe(<namespace>, pod, <dependency-pod>)
Sources: https://kubernetes.io/docs/concepts/workloads/pods/probes/ https://k8s.af/ https://par.nsf.gov//servlets/purl/10429072

## probes/rollout-deadline

Signals: Deployment condition `Progressing False ProgressDeadlineExceeded`; rollout status prints "exceeded its progress deadline"; Kubernetes takes no automatic action; listed causes: insufficient quota, readiness failures, image pull errors, insufficient permissions, limit ranges, runtime misconfiguration. The old ReplicaSet usually keeps serving (default 25% maxUnavailable/maxSurge).
Not this when: the new version passes probes but serves errors (config/bad-revision-ready); the Deployment is paused (no deadline checks, config/change-not-applied).
Check:
1. describe(<namespace>, deployment, <deployment>)  IF ProgressDeadlineExceeded → 2.
2. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`  find the new ReplicaSet → 3.
3. get_pod_status(<namespace>) and describe one new pod  IF ImagePullBackOff → startup/image-pull; IF Running but not Ready → probes/readiness-failing; IF CrashLoopBackOff → crash/exit-error; IF no new pods → describe(<namespace>, replicaset, <replicaset>) for FailedCreate (capacity/quota-limitrange, access/pod-security-admission).
4. Compare the new and old ReplicaSet templates (`kubectl get replicaset <replicaset> -n <namespace> -o yaml`)  the difference is the suspect.
Evidence to quote: the Progressing condition, the new pods' failing state, and the template field that differs.
Fix family: roll back the Deployment (rollback_deployment); then fix the field through its own entry.
Never: delete the Deployment.
Illustration:
  Observation: Progressing False ProgressDeadlineExceeded; new ReplicaSet <replicaset> 0/<n> ready; old ReplicaSet <n>/<n>
  Reading: the new revision never became available; the old one still serves.
  Next: `kubectl get replicaset <replicaset> -n <namespace> -o yaml`
Sources: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

## node/not-ready

Signals: node condition `Ready=False`; event `NodeNotReady`; taint `node.kubernetes.io/not-ready`; a crashing kubelet cannot start new pods, the node is marked unhealthy and controllers start replacement pods elsewhere; often the kubelet's reason names the runtime, PLEG or the network plugin.
Not this when: `Ready=Unknown` (node/unreachable); the node is Ready but its pod network is broken (node/pod-network-cni); a brief NotReady during an upgrade or reboot with Rebooted/Starting events (noise).
Check:
1. exec_kubectl_guarded `kubectl get nodes -o wide`  IF a node is NotReady → 2.
2. exec_kubectl_guarded `kubectl describe node <node>`  read Conditions (Ready reason and message), Taints and recent events → 3.
3. exec_kubectl_guarded `kubectl get pods -A -o wide --field-selector spec.nodeName=<node>`  IF the failing pods are exactly the ones on that node → the node is the finding.
4. exec_kubectl_guarded `kubectl get lease <node> -n kube-node-lease -o yaml`  note renewTime.
Evidence to quote: the Ready condition with its reason and message, and the pods that fail only on that node.
Fix family: cordon and drain the node so workloads move; restarting the kubelet or runtime is host-level (escalate).
Never: delete the Node object while pods with local data run there; drain many nodes at once.
Illustration:
  Observation: <node>  NotReady ... Ready False ... reason <kubelet reason>: container runtime is down
  Reading: the node, not the workload, fails; copies on other nodes are healthy.
  Next: `kubectl get pods -A -o wide --field-selector spec.nodeName=<node>`
Sources: https://kubernetes.io/docs/tasks/debug/debug-cluster https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/ https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events https://www.kubernetes.io/docs/reference/node/node-status/ https://k8s.af/

## node/unreachable

Signals: `Ready=Unknown` after node-monitor-grace-period (default 50s); taint `node.kubernetes.io/unreachable`; pods tolerate not-ready/unreachable for 300s by default, then are evicted and replaced (a pod is never rescheduled, it is replaced); StatefulSet pods may sit Unknown or Terminating; Lease renewals stop.
Not this when: `Ready=False` with a kubelet reason (node/not-ready); every node looks stale at once (node/control-plane-stall); a stale lastHeartbeatTime alone (node status updates only every 5 minutes; Lease renews every 10s).
Check:
1. exec_kubectl_guarded `kubectl get nodes`  IF a node is NotReady with Ready Unknown → 2.
2. exec_kubectl_guarded `kubectl get lease <node> -n kube-node-lease -o jsonpath='{.spec.renewTime}'`  IF renewTime stopped advancing (read twice) → the node is unreachable.
3. exec_kubectl_guarded `kubectl get pods -A -o wide --field-selector spec.nodeName=<node>`  IF pods there are Unknown or Terminating → they are lost with the node.
Evidence to quote: the Ready Unknown condition and the Lease renewTime that no longer moves.
Fix family: wait for the 300s taint eviction or drain; for StatefulSets follow the documented delete procedure only after confirming the node is really down.
Never: force-delete StatefulSet pods on a partitioned node (two writers); delete the Node object.
Illustration:
  Observation: <node>  NotReady; Ready Unknown; lease renewTime unchanged across two reads
  Reading: the control plane has lost the node; the workloads on it are not themselves faulty.
  Next: `kubectl get pods -A -o wide --field-selector spec.nodeName=<node>`
Sources: https://kubernetes.io/docs/tasks/debug/debug-cluster https://kubernetes.io/docs/tasks/debug/debug-application/_print https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/ https://www.kubernetes.io/docs/reference/node/node-status/

## node/resource-pressure

Signals: node condition `MemoryPressure` (memory.available, default hard threshold < 100Mi), `DiskPressure` (nodefs.available < 10%, imagefs.available < 15%, inodes < 5%) or `PIDPressure` (pid.available); evicted pods get phase Failed, reason `Evicted`, and are replaced (PDBs ignored); matching pressure taints; kubelet events `ImageGCFailed`, `FreeDiskSpaceFailed`, `ContainerGCFailed`; fork errors "resource temporarily unavailable". System OOM: if the node runs out before the kubelet reacts, the kernel kills by oom_score_adj (BestEffort first), possibly pods under their own limits.
Not this when: a container is OOMKilled and restarted in place (capacity/oom-killed); a claim is full (storage/volume-full); preemption (capacity/preemption); the condition can lag 5 minutes after the pressure ends (noise).
Check:
1. exec_kubectl_guarded `kubectl describe node <node>`  IF a pressure condition is True → 2.
2. exec_kubectl_guarded `kubectl get pods -A -o wide --field-selector spec.nodeName=<node>`  find Evicted or repeatedly killed pods → 3.
3. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.status.reason} {.status.message}'`  IF the message names the resource → 4.
4. exec_kubectl_guarded `kubectl top pod -n <namespace> --containers` and the pods' resources (get_resource on the Deployment)  IF one workload uses far more than its request, or has no requests/limits → it is the finding.
Evidence to quote: the pressure condition, the eviction message, and the noisy pod's usage against its request.
Fix family: set or raise requests/limits (memory, ephemeral-storage) on the noisy workload; restart a leaking workload; cordon the node and let pods move.
Never: delete evicted pod objects as a "fix" (only cleanup); delete files on the host from a privileged pod; remove pressure taints by hand.
Illustration:
  Observation: <node> MemoryPressure True; <pod> Failed Evicted <message naming memory>
  Reading: the kubelet evicted the pod for the node; the pod's own limit is not the trigger.
  Next: `kubectl top pod -n <namespace> --containers`
Sources: https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction https://kubernetes.io/docs/concepts/configuration/taint-and-toleration/ https://www.kubernetes.io/docs/reference/node/node-status/ https://kubernetes.io/docs/concepts/policy/_print https://www.repost.aws/knowledge-center/eks-failed-create-pod-sandbox

## node/pod-network-cni

Signals: kubelet events `FailedCreatePodSandBox`, `NetworkNotReady`, `SandboxChanged`; messages such as "network plugin cni failed to set up pod network", "failed to assign an IP address to container", "failed to setup network for sandbox" (pod IP exhaustion is one cause); node condition `NetworkUnavailable`; or pods Running on one Ready node that cannot reach Services, other pods or external endpoints; the network agent pod on that node restarts; small packets pass, large transfers hang (MTU).
Not this when: a NetworkPolicy blocks selected pods on all nodes (network/network-policy); the sandbox fails with fork errors (node/resource-pressure); ContainerCreating for a missing ConfigMap/Secret volume (storage/configmap-secret-volume); one SandboxChanged after a node restart (noise).
Check:
1. get_events(<namespace>)  IF FailedCreatePodSandBox appears → 2.
2. exec_kubectl_guarded `kubectl get pods -n <namespace> -o wide`  IF failing pods share one node → 3.
3. exec_kubectl_guarded `kubectl get pods -n kube-system -o wide --field-selector spec.nodeName=<node>`  IF the network agent pod there is crashing or missing → it is the finding.
4. exec_kubectl_guarded `kubectl describe node <node>`  read NetworkUnavailable and events.
Evidence to quote: the sandbox error message, the shared node, and the network agent pod's state on that node.
Fix family: restart the network agent pod on the affected node only; cordon and drain the node so workloads move.
Never: restart the network agent on all nodes at once; edit network config files on the host.
Illustration:
  Observation: Warning FailedCreatePodSandBox ... failed to setup network for sandbox; all on <node>; agent pod on <node> CrashLoopBackOff
  Reading: the failures follow the node's network agent, not the workload.
  Next: describe(kube-system, pod, <agent-pod>)
Sources: https://pkg.go.dev/k8s.io/kubernetes@v1.29.9/pkg/kubelet/events https://www.kubernetes.io/docs/reference/node/node-status/ https://www.repost.aws/knowledge-center/eks-failed-create-pod-sandbox https://www.netdata.cloud/guides/kubernetes/kubernetes-pod-network-isolation/

## node/kube-proxy

Signals: a Service works by pod IP but not by its cluster IP; the kube-proxy log lacks "Setting endpoints for ..." or shows errors contacting the API server; service rules are missing on the node; `nslookup kubernetes.default` failing can also point to kube-proxy.
Not this when: endpoints are empty (network/selector-mismatch); ports disagree (network/port-mismatch); a Local traffic policy with no local endpoint (network/traffic-policy-local); the whole pod network on one node is broken (node/pod-network-cni).
Check:
1. exec_kubectl_guarded `kubectl get daemonsets -n kube-system`  IF the kube-proxy DaemonSet has fewer ready pods than desired → 2.
2. exec_kubectl_guarded `kubectl get pods -n kube-system -l k8s-app=kube-proxy -o wide`  IF the pod on the affected node is down or crashing → it is the finding; IF Running → 3.
3. exec_kubectl_guarded `kubectl logs <kube-proxy-pod> -n kube-system --since=5m`  IF it never received this Service's endpoints, or shows API errors → it is the finding.
Evidence to quote: the kube-proxy pod state on the affected node, or the log showing the endpoints were never set.
Fix family: restart the kube-proxy pod on the affected node(s), one at a time.
Never: run kube-proxy cleanup (not an official feature); restart kube-proxy on all nodes at once; inspect host rules (needs node access, escalate).
Illustration:
  Observation: kube-proxy pod on <node>  0/1  CrashLoopBackOff; clients on <node> time out on <service>'s cluster IP
  Reading: the node's service proxy is down, so cluster IPs fail there only; endpoints are fine.
  Next: `kubectl logs <kube-proxy-pod> -n kube-system --since=5m`
Sources: https://kubernetes.io/docs/tasks/debug/debug-application/debug-service https://kubernetes.io/docs/reference/networking/_print

## node/conntrack-dns-stalls

Signals: intermittent connection drops, resets or 5-second stalls while pods look healthy; kernel log `nf_conntrack: table full, dropping packet` (conntrack use above 80% of max is a warning); parallel A/AAAA lookups race and give periodic 5s DNS stalls while DNS metrics look clean; default `options ndots:5` multiplies lookups; kernels before 6.1 can reset long-lived TCP connections to service IPs ("Connection reset by peer").
Not this when: DNS is really down, with failures on every query (network/cluster-dns); slowness without stalls at the resolver timeout (capacity/cpu-throttling); a dependency is slow (crash/dependency-failure).
Check:
1. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  IF lookups or requests take about 5s in bursts while most are fast → 2.
2. exec_kubectl_guarded `kubectl get pods -n <namespace> -o wide`  IF the slow clients share a node → 3.
3. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.dnsConfig}'`  note ndots and options → 4.
4. exec_kubectl_guarded `kubectl get --raw /api/v1/nodes/<node>/proxy/metrics`  (large output) look for conntrack counters near their limit.
Evidence to quote: the bimodal latency (fast plus spikes at the resolver timeout) and the node they share, or conntrack counters near max.
Fix family: patch dnsConfig (options single-request-reopen, lower ndots), use FQDNs with a trailing dot in config; spread load across nodes.
Never: change node sysctls from privileged pods without approval; restart cluster DNS for stalls it does not cause.
Illustration:
  Observation: client log: lookups mostly < 10ms, some ≈ 5000ms, all clients on <node>; DNS pods Ready, no errors
  Reading: 5-second spikes with a clean DNS server point at the node's connection tracking, not at DNS.
  Next: `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.dnsConfig}'`
Sources: https://www.netdata.cloud/guides/kubernetes/kubernetes-pod-network-isolation/ https://www.netdata.cloud/guides/coredns/coredns-5-second-dns-timeout/ https://kubernetes.io/docs/reference/networking/_print https://www.kubernetes.io/docs/concepts/services-networking/dns-pod-service/ https://k8s.af/

## node/drain-blocked-pdb

Signals: a node drain never completes because a PodDisruptionBudget allows zero voluntary evictions (`ALLOWED DISRUPTIONS 0`, `disruptionsAllowed: 0`); with the default `unhealthyPodEvictionPolicy: IfHealthyBudget`, CrashLoopBackOff pods guarded by a PDB can block eviction; pods covered by more than one PDB cannot be evicted.
Not this when: 0 allowed because the guarded app is already degraded (a real outage: load its entry first); node-pressure eviction (ignores PDBs, node/resource-pressure).
Check:
1. exec_kubectl_guarded `kubectl get poddisruptionbudgets -A`  IF ALLOWED DISRUPTIONS is 0 → 2.
2. exec_kubectl_guarded `kubectl get poddisruptionbudgets <pdb> -n <namespace> -o yaml`  IF currentHealthy ≤ desiredHealthy → 3.
3. get_pod_status(<namespace>)  IF the guarded pods are unhealthy → their own fault comes first (crash, probes); IF healthy but more than one PDB selects them (`kubectl get poddisruptionbudgets -n <namespace> -o wide`) → overlapping selectors are the finding.
Evidence to quote: disruptionsAllowed 0 with currentHealthy and desiredHealthy, and the state of the guarded pods.
Fix family: restore the guarded app's health first; scale up the guarded workload; fix overlapping PDB selectors.
Never: delete the PDB to force the drain (removes protection).
Illustration:
  Observation: <pdb>  MIN AVAILABLE <n>  ALLOWED DISRUPTIONS 0; guarded pods: <n> Ready of <n>
  Reading: the budget has no slack, so the drain waits by design; the node is not broken.
  Next: `kubectl get poddisruptionbudgets <pdb> -n <namespace> -o yaml`
Sources: https://kubernetes.io/docs/tasks/run-application/configure-pdb https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction

## node/control-plane-stall

Signals: the cluster is "unable to stop, update, or start new pods, services, replication controller" while "existing pods and services should continue to work normally unless they depend on the Kubernetes API"; writes fail with `etcdserver: mvcc: database space exceeded` (the store accepts only reads and deletes); new pods stay Pending with no scheduler events and ReplicaSets create no pods (scheduler or controller-manager down); control-plane client certificates expired (kubeadm default 1 year) or kubelet serving-cert CSRs left Pending.
Not this when: only some kinds of writes are rejected by a named webhook (access/webhook-unavailable); the forbidden message names your own identity (your tool's permissions, not the cluster); Pending pods with FailedScheduling events (capacity, startup).
Check:
1. exec_kubectl_guarded `kubectl get --raw /readyz?verbose`  IF checks fail → the API server or its store is the finding.
2. exec_kubectl_guarded `kubectl get pods -n kube-system`  IF scheduler, controller-manager, API server or etcd pods are not Running → that component is the finding.
3. exec_kubectl_guarded `kubectl get leases -n kube-system`  IF a leader lease is not renewed → that controller is stalled.
4. exec_kubectl_guarded `kubectl get csr`  IF serving-cert requests are Pending → note it (approval needs a human).
Evidence to quote: the readyz failure, the write error text, or the control-plane pod state.
Fix family: escalate (control-plane hosts and static pods are outside the agent); an HA control plane is the documented mitigation.
Never: run etcd compaction or defragmentation (old revisions become unreadable, defrag blocks the member); approve CSRs without a human; scale kube-system components to 0.
Illustration:
  Observation: every write: "etcdserver: mvcc: database space exceeded"; reads succeed; application pods Running
  Reading: the store refuses writes; workloads are fine, so no workload change can help.
  Next: conclude and escalate, quoting step 1.
Sources: https://kubernetes.io/docs/tasks/debug/debug-cluster https://etcd.io/docs/v3.5/op-guide/maintenance/ https://www.kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/ https://dsn2024uq.github.io/Proceedings/pdfs/DSN2024-6rvE3SSpzFYmysif75Dkid/410500a001/410500a001.pdf

## access/rbac-forbidden

Signals: a workload's logs show `Forbidden` / "cannot <verb> resource" from the Kubernetes API, naming `system:serviceaccount:<namespace>:<serviceaccount>`; message format like `pods "<pod>" is forbidden: User "<user>" cannot patch resource "<resource>" ...`; service accounts outside kube-system get no permissions beyond discovery by default; a binding's roleRef is immutable.
Not this when: the 401/403 comes from an application, database or cloud API (config/credentials-rejected); the message names your own tool rather than the workload's ServiceAccount; cluster DNS reports permission errors (network/cluster-dns).
Check:
1. exec_kubectl_guarded `kubectl logs <pod> -n <namespace> --since=5m`  read the identity, verb and resource → 2.
2. exec_kubectl_guarded `kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.serviceAccountName}'`  confirm the identity → 3.
3. exec_kubectl_guarded `kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<namespace>:<serviceaccount> -n <namespace>`  IF no → 4.
4. exec_kubectl_guarded `kubectl get rolebindings,clusterrolebindings -A -o wide`, then `kubectl describe role <role> -n <namespace>`  IF the binding is missing, points at another account, or the role lacks the verb → that object is the finding.
Evidence to quote: the forbidden line, the can-i answer, and the binding or rule that is missing.
Fix family: restore the RoleBinding or Role to its last known-good state; grant only the needed verb to the application's own service account.
Never: grant cluster-admin to a service account; grant escalate or bind; widen access to other namespaces.
Illustration:
  Observation: log: ... is forbidden: User "system:serviceaccount:<namespace>:<serviceaccount>" cannot list resource "<resource>" ...; can-i: no
  Reading: the workload's identity lacks one permission; the API server itself works.
  Next: `kubectl get rolebindings,clusterrolebindings -A -o wide`
Sources: https://kubernetes.io/docs/reference/access-authn-authz/rbac/ https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/

## access/pod-security-admission

Signals: a Deployment exists but its pods are never created: enforce mode rejects violating pods, and enforce applies only to the resulting pods ("A Deployment can therefore be created while the pods its controller creates are rejected"); Deployment shows `ReplicaFailure FailedCreate`; the ReplicaSet's event names a PodSecurity violation; namespace labels `pod-security.kubernetes.io/<mode>: <level>`; warn and audit modes do not block.
Not this when: FailedCreate names a quota or LimitRange (capacity/quota-limitrange) or a webhook (access/webhook-unavailable); the pod is created but crashes on a securityContext conflict (crash/security-context).
Check:
1. get_events(<namespace>)  IF FailedCreate names PodSecurity → 2.
2. describe(<namespace>, replicaset, <replicaset>)  read the violated level and fields → 3.
3. exec_kubectl_guarded `kubectl get namespace <namespace> --show-labels`  note the enforce level → 4.
4. exec_kubectl_guarded `kubectl get replicasets -n <namespace> -o wide`, then compare the securityContext of the new and old templates (`kubectl get replicaset <replicaset> -n <namespace> -o yaml`)  IF the new template added the violating setting → that change is the finding; IF the template is unchanged and the namespace label changed → report the label change for a human.
Evidence to quote: the FailedCreate message with the policy level and field, and the template field that violates it.
Fix family: roll back the pod-template change that violates the level.
Never: lower the namespace's enforce level or add exemptions (security trade-off, human approval only).
Illustration:
  Observation: Warning FailedCreate ... <message naming PodSecurity level <level> and field <field>>
  Reading: the policy rejects the new template; the controller and quota are fine.
  Next: `kubectl get replicasets -n <namespace> -o wide`
Sources: https://www.kubernetes.io/docs/concepts/security/pod-security-admission/ https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

## access/webhook-unavailable

Signals: create or update requests fail with errors naming an admission webhook; the default `failurePolicy` is `Fail`, so an error or timeout calling the webhook rejects the request (default timeout 10s, range 1-30); webhooks that intercept their own pods can deadlock; pods stuck Terminating when a webhook on pod UPDATE blocks finalizer removal.
Not this when: every API call fails (node/control-plane-stall); the rejection names PodSecurity (access/pod-security-admission); webhook and controller fight over a field without rejecting (access/webhook-mutation-fight).
Check:
1. get_events(<namespace>)  IF FailedCreate or an error names a webhook → 2.
2. exec_kubectl_guarded `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`  find the named one → 3.
3. exec_kubectl_guarded `kubectl get validatingwebhookconfigurations <webhook> -o yaml` (or the mutating kind)  note service, namespace, failurePolicy, timeoutSeconds, rules → 4.
4. exec_kubectl_guarded `kubectl get endpointslices -n <webhook-namespace> -l kubernetes.io/service-name=<webhook-service>`  IF no ready endpoints → the webhook backend is the finding.
Evidence to quote: the error naming the webhook, its failurePolicy, and the backend Service with no ready endpoints.
Fix family: restore the webhook backend (scale up or restart its deployment); scope the webhook with namespaceSelector/objectSelector only with approval.
Never: delete a validating webhook or flip it to Ignore (removes a security control; human approval only).
Illustration:
  Observation: Warning FailedCreate ... <message naming webhook <webhook>> ... timeout
  Reading: the webhook backend does not answer, so the API rejects the write; the pod template is not at fault.
  Next: `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`
Sources: https://www.kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/ https://kubernetes.io/docs/concepts/cluster-administration/admission-webhooks-good-practices https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/ https://k8s.af/

## access/webhook-mutation-fight

Signals: a field keeps flipping: a mutating webhook adds a value that another controller removes, in a loop; repeated identical patches or field flip-flops; mutation order is not stable; objects differ from what was applied without anyone editing them.
Not this when: requests are rejected or time out (access/webhook-unavailable); an HPA and an applied manifest alternate replicas (capacity/hpa).
Check:
1. exec_kubectl_guarded `kubectl get mutatingwebhookconfigurations`  IF a webhook's rules cover the flipping kind → 2.
2. exec_kubectl_guarded `kubectl get deployment <deployment> -n <namespace> -o yaml --show-managed-fields`  IF two managers alternate on the same field → 3.
3. get_events(<namespace>)  IF updates repeat in a short cycle → the fight is the finding.
Evidence to quote: the managedFields entries that alternate on one field, and the webhook whose rules cover that kind.
Fix family: scope the webhook (objectSelector) or revert the conflicting controller configuration, with approval.
Never: delete the webhook configuration; patch the field by hand repeatedly (it will be reverted).
Illustration:
  Observation: managedFields: <manager-a> set <field> at <t1>; <manager-b> removed it at <t2>; again at <t3>, <t4>
  Reading: two writers fight over one field; neither the workload nor the node is at fault.
  Next: `kubectl get mutatingwebhookconfigurations`
Sources: https://kubernetes.io/docs/concepts/cluster-administration/admission-webhooks-good-practices https://k8s.af/
