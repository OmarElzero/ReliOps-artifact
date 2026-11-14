You are grading diagnoses written by an AI agent that was asked to find the root cause of a fault injected into a
Kubernetes application. You have no other context and need none. Work only from what is on this page.

For each fault below you get the ground truth: what was injected, the place a correct diagnosis must name, the cause it
must give, and what it must not blame. Then you get the agent's diagnoses for that fault, each with an id.

For every diagnosis answer two questions:
- place: does the text locate the fault where the ground truth does? (yes / no)
- cause: does the text give the ground-truth cause? (yes / no)
A diagnosis is Correct only when both are yes.

Rules:
- Judge only what the text says. Do not credit what the agent may have meant.
- Describing the symptom correctly is not the same as naming the cause.
- A text that blames something the ground truth lists under "must not blame" has the place or the cause wrong.
- Extra correct detail does not hurt. A missing detail hurts only if the place or the cause is then not stated.
- Decide each item on its own, and apply the same standard to every item of a fault.

Output exactly one line per diagnosis, in the order given, and nothing else before the lines:
ID | place yes/no | cause yes/no | Correct or Incorrect | one-sentence reason
After the 40 lines, add a short note listing the ids you were least sure about and why.


==================== FAULT: Expired HTTPS certificate (Hotel Reservation) ====================
What was injected: The website is served over HTTPS through an Ingress called `frontend-ingress`. The certificate it presents is stored in a Secret called `hotel-frontend-tls`, and that certificate has passed its expiry date. Browsers refuse the connection. Every pod is healthy.
Place a correct diagnosis names: The Ingress `frontend-ingress` and its TLS secret `hotel-frontend-tls`.
Cause a correct diagnosis gives: The certificate inside the secret is expired, so HTTPS connections fail.
Must not blame: The frontend pods, the network or the service.

Diagnoses:

[H02] The ingress TLS secret 'hotel-frontend-tls' in namespace 'hotel-reservation' contains an expired certificate (expired 1 day ago), causing TLS validation failures for incoming traffic to the frontend service.

[H27] The Ingress TLS secret 'hotel-frontend-tls' in the 'hotel-reservation' namespace contains an expired certificate (expired on 2026-11-08).

==================== FAULT: Wrong DNS setting on one service (Hotel Reservation) ====================
What was injected: Inside a cluster, services find each other by name (for example `mongodb-profile`) through the cluster's own DNS. The `profile` deployment was changed to ignore the cluster DNS (`dnsPolicy: None`) and ask an outside server (`8.8.8.8`). That server does not know internal names, so `profile` cannot find its database and crashes.
Place a correct diagnosis names: The `profile` deployment.
Cause a correct diagnosis gives: Its DNS policy is `None` with an external resolver (`8.8.8.8`), so cluster-internal names do not resolve.
Must not blame: CoreDNS, the network, the database or its storage. They are healthy.

Diagnoses:

[H03] Root cause diagnosis (Category: config, Step 2): The profile deployment was configured with dnsPolicy: None and a custom external nameserver (8.8.8.8) instead of ClusterFirst, which prevented DNS resolution of cluster-internal service names like mongodb-profile. Key evidence: the profile pod logs showed panic: 'no reachable servers' at cmd/profile/db.go:33 when trying to connect to mongodb-profile:27017. This explains why the profile pod entered an Error/CrashLoop state while all other workloads started successfully.

[H33] The profile service pods crash with a panic due to 'no reachable servers' because the corresponding mongodb-profile pod failed to schedule initially due to a missing PersistentVolumeClaim ('profile-pvc'), preventing the database from starting and accepting connections.

==================== FAULT: Storage and pod pinned to different nodes (Social Network) ====================
What was injected: The `user-service` pod needs a storage volume. The volume is tied to one machine (`kind-worker`). The pod is told it may only run on a different machine (`kind-worker2`). No machine satisfies both, so the pod stays Pending forever.
Place a correct diagnosis names: The `user-service` deployment.
Cause a correct diagnosis gives: The volume's node affinity and the pod's `nodeSelector` name different nodes, so the pod cannot be placed.
Must not blame: Cluster capacity or other services.

Diagnoses:

[H07] The user-service deployment cannot be scheduled because its PersistentVolume (temp-pv) has a node affinity constraint restricting it to node 'kind-worker', whereas the user-service pod template specifies a node selector for 'kind-worker2'. This causes a conflict where the scheduler cannot find a node satisfying both constraints.

[H16] The user-service deployment has a nodeSelector forcing it to run on 'kind-worker2', but its persistent volume (temp-pv) has node affinity restricted to 'kind-worker', resulting in a volume node affinity conflict that prevents the pod from being scheduled.

==================== FAULT: Corrupted database files (Hotel Reservation) ====================
What was injected: The data files of the `mongodb-geo` database, stored on its persistent volume, were damaged on disk. When MongoDB starts, its storage engine (WiredTiger) checks the files, finds they do not match their checksums, and stops. The pod restarts in a loop.
Place a correct diagnosis names: The `mongodb-geo` deployment (its data on the volume).
Cause a correct diagnosis gives: The data files are corrupted; WiredTiger checksum failures make MongoDB abort on start.
Must not blame: The `geo` service, the image, or the node's resources. It is also not a disk-full or I/O error.

Diagnoses:

[H17] The mongodb-geo pod is in a CrashLoopBackOff state because the MongoDB instance encounters a WiredTiger storage engine error (__wt_bm_corrupt_dump on _mdb_catalog.wt), indicating data corruption in the persistent volume (geo-pvc).

[H32] The root cause of the issue is data corruption in the MongoDB instance for the geo service (`mongodb-geo`). Specifically, the WiredTiger storage engine encounters a corruption error (`__wt_bm_corrupt_dump`) when trying to read the catalog file `_mdb_catalog.wt` from its persistent volume (`geo-pvc`), causing MongoDB to fail startup and enter a CrashLoopBackOff.

==================== FAULT: Ingress sends traffic to the wrong service (Hotel Reservation) ====================
What was injected: The Ingress `hotel-reservation-ingress` decides which service receives each web path. Its rule for `/api` was pointed at `recommendation-service` when it should point at `frontend-service`. Both services are healthy; requests simply arrive at the wrong one.
Place a correct diagnosis names: The Ingress `hotel-reservation-ingress`.
Cause a correct diagnosis gives: The `/api` rule routes to `recommendation-service` instead of `frontend-service`.
Must not blame: The recommendation or frontend pods.

Diagnoses:

[H29] The backend microservices experienced initial crash loops with 'no reachable servers' panics because they attempted to connect to their MongoDB instances before the persistent volume claims were bound and the MongoDB databases were fully started and ready to accept connections. Once the databases completed startup, the microservices successfully connected and stabilized.

==================== FAULT: A switched-on flag wakes a hidden bug (Hotel Reservation) ====================
What was injected: The frontend reads a setting called `SEARCH_BACKEND_VERSION` from the ConfigMap `frontend-runtime-config`. Someone turned it on. That activates a piece of frontend code that was never used before and is broken, so every hotel search returns an error (HTTP 500). All pods stay Running.
Place a correct diagnosis names: The `frontend` deployment and its configuration.
Cause a correct diagnosis gives: `SEARCH_BACKEND_VERSION` was set in `frontend-runtime-config`, which activates a dormant error path; every search fails.
Must not blame: The search service or other backends, or a crash/restart loop.

Diagnoses:

[H05] The root cause was an improper configuration update in revision 2 of the frontend deployment, which injected the 'SEARCH_BACKEND_VERSION' environment variable from the 'frontend-runtime-config' ConfigMap. This caused all hotel search requests from the frontend to fail with 'hotel search failed' errors. Rolling back the deployment to revision 1 removed the faulty environment variable and restored correct functionality.

[H36] The hotel reservation application's frontend is experiencing repeated errors during hotel search operations because the search service fails to successfully communicate with its required dependencies or process requests correctly.

[H38] The frontend service fails to execute hotel searches because the SEARCH_BACKEND_VERSION configuration in the frontend-runtime-config ConfigMap is set incorrectly (or points to an invalid backend implementation/version), causing requests from the frontend to the search backend to fail.

[H40] Probes ruled out by step 0: every pod is 1/1 Ready and there are no Unhealthy events newer than the pods.

==================== FAULT: Health check kills the pod before it starts (Hotel Reservation) ====================
What was injected: Kubernetes can be told to check that a container is alive (a liveness probe) and to restart it when the check fails. For `aux-service` the probe starts at second 0, repeats every second and gives up after a single failure, with zero seconds of grace on shutdown. The program needs about 15 seconds to start, so it is killed before it is ready, again and again.
Place a correct diagnosis names: The `aux-service` deployment.
Cause a correct diagnosis gives: The liveness probe is too aggressive (`initialDelaySeconds=0`, `periodSeconds=1`, `failureThreshold=1`) with zero termination grace, so pods are killed before they stabilize.
Must not blame: The node, the program's code or other services.

Diagnoses:

[H04] The aux-service container fails its liveness probe because the liveness probe has initialDelaySeconds: 0 and periodSeconds: 1 (with failureThreshold: 1), while the application script (aux-service-script) requires 15 seconds of initialization time (INIT_SECONDS = 15) before returning 200 OK on the /health endpoint (returning 503 during initialization).

[H12] The aux-service container crashes in a CrashLoopBackOff because its liveness probe is configured with a 0-second initial delay and checks the /health endpoint immediately. However, the Python application has a 15-second initialization period where /health returns HTTP 503 (Initializing). As a result, the kubelet kills the container immediately for failing the liveness probe, leading to rapid restart loops and occasional address-in-use port binding errors.

[H18] The aux-service Python script uses socketserver.TCPServer without setting allow_reuse_address = True. When the container or process restarts, port 8080 remains in a TIME_WAIT state or is briefly held, causing socketserver to fail with 'Address already in use' and leading to a CrashLoopBackOff.

[H30] The aux-service container experiences a crash loop due to two main issues: (1) The liveness probe has an initial delay of 0 seconds and a strict failure threshold, while the Python service script requires 15 seconds to initialize (INIT_SECONDS = 15), causing the liveness probe to fail immediately and trigger a container restart. (2) The deployment specifies terminationGracePeriodSeconds: 0, which kills the container instantly without allowing the OS to release port 8080, leading to an 'Address already in use' (Errno 98) OSError when the container immediately restarts.

==================== FAULT: Two things want the same port on the machine (Social Network) ====================
What was injected: The `media-service` pod asks for port 9100 on the machine itself (a `hostPort`). On every machine that port is already taken by a monitoring agent, `prometheus-node-exporter`. So no machine can accept the pod and it stays Pending.
Place a correct diagnosis names: The `media-service` deployment.
Cause a correct diagnosis gives: Its pod template binds `hostPort 9100`, which collides with `prometheus-node-exporter`, so scheduling fails with a host-port conflict.
Must not blame: Node capacity, the node-exporter (it is supposed to be there) or other services.

Diagnoses:

[H11] The media-service pod is failing to be scheduled because it requests a host port (Host Port: 9100/TCP) that is already in use or cannot be bound on the available nodes, resulting in a FailedScheduling error due to port conflicts.

[H19] The media-service deployment defines a hostPort of 9100 on containerPort 9090. During a rolling update, the new pod cannot be scheduled because all cluster nodes either have untolerated control-plane taints or already have the hostPort 9100 bound by the terminating old pod of the same service.

[H20] Diagnosis review:
1. Category 'startup' was followed to Step 2, where the scheduling event was quoted: '3 node(s) didn't have free ports for the requested pod ports' (newer than the pod, indicating a hostPort conflict). Capacity was correctly ruled out after inspecting the scheduler reason.
2. Triage showed one abnormal thing: media-service-57864b696c-wmjh9 in Pending status with a FailedScheduling event. The diagnosis explains this completely.

Root Cause:
The root cause of the issue is a scheduling failure for the media-service pod due to a port conflict. Specifically, the container requests a hostPort (9100), and during a rolling update, the old media-service pod was stuck in the Terminating state while still holding that host port across the nodes. This prevented the new media-service pod from being scheduled.

[H35] The media-service pod is stuck in Pending status because it requests a host port (Host Port: 9100/TCP) that is already bound or requested across the available worker nodes, causing a port conflict during scheduling.

[H37] The media-service deployment is configured with a hostPort (9100), which causes a port conflict when Kubernetes tries to perform a rolling update and schedule a new pod while the old terminating pod is still bound to that port on the worker nodes.

==================== FAULT: The database lost its user (Hotel Reservation) ====================
What was injected: The `rate` service logs in to its database `mongodb-rate` with a username and password, as it always did. Inside the database, that admin user was deleted. The database still runs and still demands a login, but the account no longer exists, so every login from `rate` fails.
Place a correct diagnosis names: `mongodb-rate` (the database). The structured ground truth names the database, not the `rate` service.
Cause a correct diagnosis gives: The expected admin user is missing from MongoDB, so the dependent service cannot authenticate.
Must not blame: The `rate` service's code or configuration, or other databases. The `rate` service is the symptom.

Diagnoses:

[H01] The `rate` service deployment in namespace `hotel-reservation` is missing MongoDB authentication credentials in its environment variables, causing the container to crash with a SASL authentication failure when attempting to connect to MongoDB (`mongodb-rate`).

[H08] The MongoDB instance for the rate service (mongodb-rate) has authentication enabled (--auth) and its initialization script creates a root user, but the rate service itself is not configured with MongoDB credentials (username/password), causing SASL authentication to fail on startup.

[H23] The rate service is crashing with a MongoDB SASL authentication failure because the rate deployment is missing the required MongoDB username and password environment variables.

[H25] The rate service fails to start because it encounters a MongoDB authentication failure (SASL authentication step failed). The MongoDB instance for the rate service requires authentication (username 'admin' and password 'password'), but the rate deployment lacks the necessary environment variables (MONGO_USERNAME and MONGO_PASSWORD) to authenticate successfully.

[H26] The rate deployment is missing MongoDB authentication environment variables (such as MONGO_USERNAME and MONGO_PASSWORD / MONGODB_USERNAME and MONGODB_PASSWORD), causing it to fail SASL authentication against the authenticated mongodb-rate instance.

[H28] The `rate` microservice fails to start because it attempts to connect to MongoDB (`mongodb-rate`) without proper authentication credentials, while the MongoDB instance has authentication enabled (`--auth`) and requires SASL authentication.

[H34] The rate service pod is crashing on startup due to a MongoDB authentication failure (SASL authentication failed when connecting to mongodb-rate). This occurs because the MongoDB database requires authentication credentials or configuration that is missing or incorrect in the rate service deployment/environment.

[H39] The rate service is crashing due to a MongoDB authentication failure. mongodb-rate has --auth enabled, but the rate service connects to mongodb-rate:27017 without credentials.

==================== FAULT: A new security rule on the namespace blocks new pods (Hotel Reservation) ====================
What was injected: A namespace is a folder that holds an application. The namespace `hotel-reservation` was given a security label (`pod-security.kubernetes.io/enforce=restricted`). From that moment Kubernetes refuses to create any new pod there unless it meets strict rules (not running as root, and so on). The application's pods were never written for those rules. Pods that were already running stay. One `recommendation` pod was then deleted, and its replacement is refused. Nothing in the `recommendation` deployment changed.
Place a correct diagnosis names: The namespace `hotel-reservation` (where the policy lives), with `recommendation` as the affected deployment.
Cause a correct diagnosis gives: The namespace label `enforce=restricted` rejects the recreation of pods that run as root and lack seccomp and dropped capabilities. No admission webhook is involved.
Must not blame: The image, the service, resources or a webhook. The deployment's spec and image are healthy.

Diagnoses:

[H06] The recommendation deployment failed to create pods due to PodSecurity violations against the 'restricted:latest' standard. Specifically, the container lacked allowPrivilegeEscalation=false, dropped capabilities, runAsNonRoot=true, and seccompProfile configuration.

[H09] There is no active root cause or failure in the hotel-reservation application. All pods are currently Running and Ready (1/1), and all PersistentVolumeClaims are Bound. The initial scheduling warnings ('persistentvolumeclaim ... not found' and 'pod does not exist any more') observed in events were transient race conditions during the initial scheduling and dynamic provisioning of pods utilizing WaitForFirstConsumer storage classes, which successfully self-resolved within seconds as the volumes were provisioned and pods scheduled.

[H10] The recommendation deployment has 0/1 ready replicas because its container (hotel-reserv-recommendation) lacks the required securityContext settings (allowPrivilegeEscalation: false, capabilities drop ALL, runAsNonRoot: true, and seccompProfile type RuntimeDefault), which violates the namespace's enforced restricted Pod Security Standard.

[H13] The recommendation deployment fails to create pods because its container lacks compliance with the namespace's restricted PodSecurity standards (missing securityContext settings like allowPrivilegeEscalation=false, runAsNonRoot=true, dropped capabilities, and seccomp profile).

[H14] The recommendation deployment fails to create pods because the container 'hotel-reserv-recommendation' violates the namespace's PodSecurity 'restricted' policy. Specifically, the container is missing securityContext settings such as allowPrivilegeEscalation=false, capabilities.drop=['ALL'], runAsNonRoot=true, and seccompProfile.type='RuntimeDefault'.

[H15] The recommendation deployment fails to create its pods due to a PodSecurity violation ("restricted:latest"), specifically because the container lacks required securityContext settings such as allowPrivilegeEscalation=false, capabilities drop ALL, runAsNonRoot=true, and a seccompProfile. Consequently, no recommendation pods are running and the recommendation service has no endpoints.

[H21] The recommendation deployment fails to create its pods due to a Pod Security Standards violation in the restricted profile. Specifically, the container lacks the required securityContext configuration: allowPrivilegeEscalation must be set to false, capabilities must drop ALL, runAsNonRoot must be true, and a seccompProfile of RuntimeDefault or Localhost must be configured.

[H22] The recommendation deployment cannot create pods because the namespace enforces the 'restricted' PodSecurity standard, but the recommendation deployment's pod template lacks the required securityContext settings (such as allowPrivilegeEscalation=false, capabilities.drop=['ALL'], runAsNonRoot=true, and seccompProfile.type='RuntimeDefault').

[H24] The recommendation deployment fails to create pods because its container specification violates the namespace's restricted PodSecurity standards. Specifically, it lacks the required securityContext settings (allowPrivilegeEscalation=false, dropping all capabilities, runAsNonRoot=true, and setting seccompProfile.type to RuntimeDefault).

[H31] The recommendation deployment fails to create pods (Step 3 of access procedure) because the ReplicaSet controller reports FailedCreate events with the message: 'violates PodSecurity restricted:latest: allowPrivilegeEscalation != false...'. The container lacks the required securityContext settings: allowPrivilegeEscalation=false, capabilities.drop=['ALL'], runAsNonRoot=true, and seccompProfile.type set to RuntimeDefault.