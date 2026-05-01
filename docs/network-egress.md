# Network-Layer Egress Control (SEC-021)

This document describes the **network-layer** egress control plan for `srgssr-mcp` deployments that use the `sse` or `streamable-http` transport (as opposed to the default `stdio` transport, where the process runs in the MCP client's user context and a network-layer firewall does not apply).

The **code-layer** allowlist (`ALLOWED_HOSTS = {"api.srgssr.ch"}` in `src/srgssr_mcp/_http.py`) is the primary control and is always active. This document covers the second defense-in-depth layer for production deployments.

## Goal

Restrict the server pod / container / VM to outbound TCP 443 traffic to `api.srgssr.ch` only. Block:

- Cloud metadata services (`169.254.169.254`, `fd00:ec2::254`, …) — already enforced at code layer, but defense-in-depth at network layer is recommended.
- Internal services (private RFC1918 ranges, `127.0.0.0/8`).
- Arbitrary public internet endpoints.
- Outbound DNS to non-trusted resolvers.

## Kubernetes NetworkPolicy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: srgssr-mcp-egress
  namespace: srgssr-mcp
spec:
  podSelector:
    matchLabels:
      app: srgssr-mcp
  policyTypes:
    - Egress
  egress:
    # Allow DNS to cluster DNS only
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Allow HTTPS to api.srgssr.ch (resolved IP range — refresh periodically
    # or use an egress gateway / service-mesh that supports DNS-based rules)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
              - 169.254.0.0/16
              - 127.0.0.0/8
      ports:
        - protocol: TCP
          port: 443
```

For DNS-name-based egress (recommended), pair this with an egress gateway like **Istio**, **Cilium**, or **Calico** that resolves `api.srgssr.ch` and dynamically programs the firewall:

```yaml
# Cilium CiliumNetworkPolicy with FQDN matching
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: srgssr-mcp-egress-fqdn
spec:
  endpointSelector:
    matchLabels:
      app: srgssr-mcp
  egress:
    - toFQDNs:
        - matchName: api.srgssr.ch
      toPorts:
        - ports:
            - port: "443"
              protocol: TCP
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
            k8s:k8s-app: kube-dns
      toPorts:
        - ports:
            - port: "53"
              protocol: UDP
          rules:
            dns:
              - matchPattern: "*"
```

## AWS Security Group

For ECS / EC2 deployments, attach a security group with restrictive egress rules:

```hcl
resource "aws_security_group" "srgssr_mcp" {
  name        = "srgssr-mcp"
  description = "srgssr-mcp egress: HTTPS to SRG SSR API only"
  vpc_id      = var.vpc_id

  # Egress: HTTPS only, to public CIDR ranges (refine via prefix list if
  # SRG SSR publishes one, or use VPC endpoints + AWS PrivateLink if available)
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS to api.srgssr.ch (refine to specific CIDR if known)"
  }

  # Egress: DNS to VPC resolver only
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = [var.vpc_cidr]
    description = "DNS to VPC resolver"
  }
}
```

## Cloudflare WARP / Zero Trust

For deployments behind Cloudflare WARP, configure a Zero Trust policy:

```
Action: Allow
Selector: Domain
Value:   api.srgssr.ch

Action: Block
Selector: All
```

## Verification After Deployment

```bash
# From inside the pod / container / VM:
$ curl -v https://api.srgssr.ch/oauth/v1/accesstoken
# Expected: TCP connect succeeds, TLS handshake succeeds.

$ curl -v https://example.com
# Expected: TCP connect blocked / times out — egress policy denies.

$ curl -v http://169.254.169.254/latest/meta-data/
# Expected: blocked — cloud metadata IP in blocklist (also enforced at code layer).
```

## Maintenance

- **DNS-name-based egress** is preferred over CIDR allowlists; SRG SSR's IP ranges may change without notice.
- Re-run verification after **any** infrastructure change (Terraform apply, Helm upgrade, security-group edit).
- Audit logs from the egress firewall should be ingested into the same SIEM as the application logs (`structlog` JSON on stderr — see [README → Logging](../README.md#logging)).

## References

- Code-layer allowlist: [`src/srgssr_mcp/_http.py`](../src/srgssr_mcp/_http.py) (`ALLOWED_HOSTS`, `_validate_url_safe`)
- Findings: [`audits/2026-04-30-srgssr-mcp/findings/SEC-004-ssrf-prevention.md`](../audits/2026-04-30-srgssr-mcp/findings/SEC-004-ssrf-prevention.md), [`audits/2026-04-30-srgssr-mcp/findings/SEC-021-egress-allowlist.md`](../audits/2026-04-30-srgssr-mcp/findings/SEC-021-egress-allowlist.md)
